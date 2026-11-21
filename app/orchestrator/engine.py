"""
Core Orchestration Brain for Ujjwal Rail.
Implements the 6-step handle_chat pipeline:
1. identity_guard(header) -> passenger or refusal
2. isolate(message) -> delimited DATA block, injection scan (EN/HI/Hinglish)
3. split_requests(safe, session) -> max MAX_PARTS=3 SubRequests
4. Process each part: merge slots, route (Level 0-3, Branch A-E), execute branch
5. compose(results) -> deterministic template composition, priority answer_type
6. write audit trace, return response JSON
"""

import uuid
from typing import Optional
from datetime import datetime

from app.models import ChatResponse, PartResult
from app.config import config
from app.guardrails.identity import resolve_passenger, mask_pii
from app.guardrails.injection import isolate, post_check_output
from app.orchestrator.session import get_or_create_session
from app.orchestrator.splitter import split_requests
from app.orchestrator.router import detect_language, determine_branch
from app.orchestrator.branches import (
    execute_branch_a,
    execute_branch_b,
    execute_branch_c,
    execute_branch_d,
    execute_branch_e,
    execute_branch_greeting,
    execute_branch_identity,
)
from app.orchestrator.composer import compose
from app.db.audit import write_audit_trace

from RAG_pipeline.repository import RulesRepository
from RAG_pipeline.hybrid_retriever import HybridRetriever

# Module-level instances for retriever and repository
_repository = RulesRepository(db_path=config.DB_PATH)
_retriever = HybridRetriever(repository=_repository)


def get_retriever() -> HybridRetriever:
    return _retriever


def get_repository() -> RulesRepository:
    return _repository


def handle_chat(
    header: Optional[str],
    session_id: str,
    message: str,
    as_of: Optional[str] = None
) -> ChatResponse:
    """
    Main orchestration entrypoint for /chat.
    One-line reason: Coordinates end-to-end security, routing, retrieval, execution, and audit logging.
    """
    trace_id = uuid.uuid4().hex[:8]
    if not as_of:
        as_of = datetime.now().strftime("%Y-%m-%d")

    # Step 1: Identity Guard (Header only)
    passenger, auth_error = resolve_passenger(header, config.DB_PATH)
    if not passenger:
        refusal_resp = ChatResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer=auth_error or "Authentication failed.",
            sources=[],
            tools=[],
            pending_action=None,
            handed_to_human=None
        )
        write_audit_trace(
            db_path=config.DB_PATH,
            session_id=session_id,
            passenger_id=header or "ANONYMOUS",
            user_query=message,
            answer_type=refusal_resp.answer_type,
            answer_text=refusal_resp.answer,
            trace_id=trace_id
        )
        return refusal_resp

    passenger_id = passenger["passenger_id"]

    # Step 2: Prompt & Data Isolation + Injection Scan
    isolated_message, is_safe, injection_reason = isolate(message)
    if not is_safe:
        # Reject injection attempt with explicit refusal
        refusal_resp = ChatResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer="Security alert: Your message contains prohibited instruction-override patterns and cannot be processed.",
            sources=[],
            tools=[],
            pending_action=None,
            handed_to_human=None
        )
        write_audit_trace(
            db_path=config.DB_PATH,
            session_id=session_id,
            passenger_id=passenger_id,
            user_query=message,
            answer_type=refusal_resp.answer_type,
            answer_text=refusal_resp.answer,
            trace_id=trace_id
        )
        return refusal_resp

    # Detect user language
    lang = detect_language(message)

    # Retrieve or initialize session state
    session = get_or_create_session(session_id, passenger_id, lang)

    # Step 3: Request Splitter (max MAX_PARTS=3)
    sub_requests = split_requests(isolated_message, session)

    # Step 4: Process each sub-request part in order
    part_results = []
    has_pending_action = False

    for idx, sub_req in enumerate(sub_requests, start=1):
        branch, answer_type, level = determine_branch(sub_req, session)

        if branch == "A":
            res = execute_branch_a(sub_req, session, lang, idx)
        elif branch == "B":
            res = execute_branch_b(sub_req, lang, idx)
        elif branch == "C":
            res = execute_branch_c(sub_req, passenger_id, lang, idx)
        elif branch == "D":
            res = execute_branch_d(sub_req, _retriever, as_of, lang, idx)
        elif branch == "E":
            res = execute_branch_e(sub_req, passenger_id, session, as_of, lang, idx)
        elif branch == "G":
            res = execute_branch_greeting(sub_req, passenger_id, lang, idx)
        elif branch == "I":
            res = execute_branch_identity(sub_req, passenger_id, lang, idx)
        else:
            res = execute_branch_b(sub_req, lang, idx)

        if res.pending_action:
            has_pending_action = True

        part_results.append(res)

    # Step 5: Compose Response via Numbered Templates
    composed_response = compose(part_results, trace_id)

    # Apply PII Masking on the final response
    masked_answer = mask_pii(composed_response.answer)
    composed_response.answer = masked_answer

    # Safety Post-Check Output Validation
    is_output_safe, output_reason = post_check_output(composed_response.answer, allowed_action_done=False)
    if not is_output_safe:
        composed_response.answer = "An error occurred while validating the response. Please contact support."
        composed_response.answer_type = "refusal"

    # Step 6: Write Audit Trace
    write_audit_trace(
        db_path=config.DB_PATH,
        session_id=session_id,
        passenger_id=passenger_id,
        user_query=message,
        answer_type=composed_response.answer_type,
        answer_text=composed_response.answer,
        sources_cited=[s.model_dump() for s in composed_response.sources],
        tools_used=[t.model_dump() for t in composed_response.tools],
        pending_action=composed_response.pending_action.model_dump() if composed_response.pending_action else None,
        handed_to_human=composed_response.handed_to_human.model_dump() if composed_response.handed_to_human else None,
        trace_id=trace_id
    )

    return composed_response
