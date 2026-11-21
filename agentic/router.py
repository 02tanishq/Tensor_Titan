import json
import sqlite3
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from agentic.models import (
    AgenticRequest,
    AgenticResponse,
    PendingAction,
    ToolRecord,
)
from agentic.policy import evaluate_policy
from agentic.tools import (
    cancel_action,
    confirm_action,
    create_pending_action,
    quote_cancellation,
)
from agentic.bionic_client import parse_intent_and_entities

_global_db_conn: Optional[sqlite3.Connection] = None


def get_db():
    global _global_db_conn
    if _global_db_conn is not None:
        yield _global_db_conn
        return
    from agentic.database import get_connection
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def set_db_connection(conn: sqlite3.Connection) -> None:
    global _global_db_conn
    _global_db_conn = conn


def _record_audit(
    conn: sqlite3.Connection,
    trace_id: str,
    session_id: str,
    passenger_id: str,
    user_query: str,
    res: AgenticResponse,
    as_of: Optional[str] = None,
) -> None:
    """Inserts interaction into audit_logs table if it exists."""
    try:
        cur = conn.execute("PRAGMA table_info(audit_logs)")
        if not cur.fetchall():
            return
        timestamp = as_of or res.trace_id
        conn.execute(
            """
            INSERT INTO audit_logs (
                trace_id, session_id, passenger_id, timestamp, user_query,
                answer_type, answer_text, sources_cited, tools_used, pending_action, handed_to_human
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                session_id,
                passenger_id,
                timestamp,
                user_query,
                res.answer_type,
                res.answer,
                json.dumps(res.sources),
                json.dumps([t.model_dump() for t in res.tools]),
                json.dumps(res.pending_action.model_dump()) if res.pending_action else None,
                json.dumps(res.handed_to_human) if res.handed_to_human else None,
            ),
        )
        conn.commit()
    except Exception:
        pass


router = APIRouter()


@router.post("/agentic/handle", response_model=AgenticResponse)
def handle_agentic_request(
    request: AgenticRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> AgenticResponse:
    """
    Handles an agentic request:
    1. Interprets natural language via Bionic AI (with fallback).
    2. Evaluates policy (Level 1 allowed, Level 2 hand-off, Level 3 refusal).
    3. For Level 1 cancel_booking, quotes cancellation deterministically and creates pending action.
    """
    trace_id = f"trc_{uuid.uuid4().hex[:12]}"

    # Use Bionic AI if intent or booking_id is missing
    if not request.intent or not request.entities.get("booking_id"):
        ai_parsed = parse_intent_and_entities(request.message)
        if not request.intent and ai_parsed.get("intent"):
            request.intent = ai_parsed["intent"]
        for k, v in ai_parsed.get("entities", {}).items():
            if k not in request.entities:
                request.entities[k] = v

    # Evaluate policy
    policy_decision = evaluate_policy(request)

    # Level 3: Refusal
    if policy_decision.level == 3:
        res = AgenticResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer=policy_decision.answer,
            sources=policy_decision.sources,
            tools=[],
            pending_action=None,
            handed_to_human=None,
        )
        _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
        return res

    # Level 2: Human Hand-off
    if policy_decision.level == 2:
        res = AgenticResponse(
            trace_id=trace_id,
            answer_type="handed_to_human",
            answer=policy_decision.answer,
            sources=policy_decision.sources,
            tools=[],
            pending_action=None,
            handed_to_human=policy_decision.handed_to_human,
        )
        _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
        return res

    # Clarification for unrecognized intent
    if policy_decision.level == 0:
        res = AgenticResponse(
            trace_id=trace_id,
            answer_type="clarification",
            answer=policy_decision.answer,
            sources=[],
            tools=[],
            pending_action=None,
            handed_to_human=None,
        )
        _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
        return res

    # Level 1: Autonomous action
    booking_id = request.entities.get("booking_id")
    passenger_id = request.passenger_id
    as_of = request.entities.get("as_of") or getattr(request, "as_of", None)

    if request.intent == "cancel_booking" and booking_id:
        # Quote cancellation — catch ownership / not-found errors
        try:
            quote = quote_cancellation(
                conn=conn,
                passenger_id=passenger_id,
                booking_id=booking_id,
                as_of=as_of,
            )
        except PermissionError as e:
            res = AgenticResponse(
                trace_id=trace_id,
                answer_type="refusal",
                answer=f"Refusal: {str(e)}",
                sources=[{"source_doc": "Ujjwal Rail Security & Access Policy"}],
                tools=[],
                pending_action=None,
                handed_to_human=None,
            )
            _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
            return res
        except ValueError as e:
            res = AgenticResponse(
                trace_id=trace_id,
                answer_type="refusal",
                answer=f"Cannot preview cancellation: {str(e)}",
                sources=[],
                tools=[],
                pending_action=None,
                handed_to_human=None,
            )
            _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
            return res

        tool_records = [ToolRecord(tool="quote_cancellation", output=quote)]

        # Create pending action
        pending_act = create_pending_action(
            conn=conn,
            passenger_id=passenger_id,
            booking_id=booking_id,
            action_type="cancel_booking",
            payload=quote,
            as_of=as_of,
        )
        tool_records.append(ToolRecord(tool="create_pending_action", output=pending_act))

        pending_model = PendingAction(
            action_id=pending_act["action_id"],
            type="cancel_booking",
            booking_id=booking_id,
            expires_at=pending_act["expires_at"],
        )

        charge = quote.get("charge", 0.0)
        refund = quote.get("refund", 0.0)
        amount_paid = quote.get("amount_paid", 0.0)
        hours = quote.get("hours_before_departure", 0.0)

        # refund==0 and charge==amount_paid means past cut-off (100% fee)
        if refund == 0.0 and amount_paid > 0:
            answer = (
                f"Cancellation preview for booking {booking_id}: "
                f"Past cancellation cut-off — "
                f"Fare paid ₹{amount_paid:.2f}, cancellation charge ₹{charge:.2f}, "
                f"refund amount ₹0.00 ({hours:.2f} hours before departure). "
                f"Action '{pending_act['action_id']}' is pending. "
                f"Please confirm before {pending_act['expires_at']}."
            )
        else:
            answer = (
                f"Cancellation preview for booking {booking_id}: "
                f"Fare paid ₹{amount_paid:.2f}, cancellation charge ₹{charge:.2f}, "
                f"refund amount ₹{refund:.2f} ({hours:.2f} hours before departure). "
                f"Action '{pending_act['action_id']}' is pending. "
                f"Please confirm before {pending_act['expires_at']}."
            )

        res = AgenticResponse(
            trace_id=trace_id,
            answer_type="confirm_needed",
            answer=answer,
            sources=quote.get("sources", []),
            tools=tool_records,
            pending_action=pending_model,
            handed_to_human=None,
        )
        _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
        return res

    # Fallback for other Level 1 actions
    res = AgenticResponse(
        trace_id=trace_id,
        answer_type="confirm_needed",
        answer=f"Preview generated for action '{request.intent}'. Please confirm to proceed.",
        sources=policy_decision.sources,
        tools=[],
        pending_action=None,
        handed_to_human=None,
    )
    _record_audit(conn, trace_id, request.session_id, request.passenger_id, request.message, res)
    return res


@router.post("/actions/{action_id}/confirm", response_model=AgenticResponse)
def confirm_action_endpoint(
    action_id: str,
    x_passenger_id: str = Header(..., alias="X-Passenger-Id"),
    as_of: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
) -> AgenticResponse:
    """
    Confirms a pending action:
    - Reads X-Passenger-Id header.
    - Verifies ownership and expiry.
    - Runs idempotently without double-mutating.
    - Updates bookings / seats / actions and re-reads booking state.
    """
    trace_id = f"trc_{uuid.uuid4().hex[:12]}"
    try:
        result = confirm_action(
            conn=conn,
            passenger_id=x_passenger_id,
            action_id=action_id,
            as_of=as_of,
        )
    except PermissionError as e:
        return AgenticResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer=f"Refusal: {str(e)}",
            sources=[{"source_doc": "Ujjwal Rail Security & Access Policy"}],
            tools=[],
            pending_action=None,
            handed_to_human=None,
        )
    except ValueError as e:
        return AgenticResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer=f"Cannot confirm action: {str(e)}",
            sources=[],
            tools=[],
            pending_action=None,
            handed_to_human=None,
        )

    tool_records = [ToolRecord(tool="confirm_action", output=result)]
    refund = result.get("refund", 0.0)
    booking_id = result.get("booking_id")

    if result.get("idempotent"):
        answer = (
            f"Action '{action_id}' was already confirmed previously. "
            f"Booking '{booking_id}' is cancelled with refund ₹{refund:.2f}."
        )
    else:
        answer = (
            f"Action '{action_id}' successfully confirmed. "
            f"Booking '{booking_id}' has been cancelled with a refund of ₹{refund:.2f}."
        )

    return AgenticResponse(
        trace_id=trace_id,
        answer_type="action_done",
        answer=answer,
        sources=[],
        tools=tool_records,
        pending_action=None,
        handed_to_human=None,
    )


@router.post("/actions/{action_id}/cancel", response_model=AgenticResponse)
def cancel_action_endpoint(
    action_id: str,
    x_passenger_id: str = Header(..., alias="X-Passenger-Id"),
    conn: sqlite3.Connection = Depends(get_db),
) -> AgenticResponse:
    """
    Cancels a pending action:
    - Reads X-Passenger-Id header.
    - Marks pending action as cancelled without changing booking.
    """
    trace_id = f"trc_{uuid.uuid4().hex[:12]}"
    try:
        result = cancel_action(
            conn=conn,
            passenger_id=x_passenger_id,
            action_id=action_id,
        )
    except PermissionError as e:
        return AgenticResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer=f"Refusal: {str(e)}",
            sources=[{"source_doc": "Ujjwal Rail Security & Access Policy"}],
            tools=[],
            pending_action=None,
            handed_to_human=None,
        )
    except ValueError as e:
        return AgenticResponse(
            trace_id=trace_id,
            answer_type="refusal",
            answer=f"Cannot cancel action: {str(e)}",
            sources=[],
            tools=[],
            pending_action=None,
            handed_to_human=None,
        )

    tool_records = [ToolRecord(tool="cancel_action", output=result)]
    return AgenticResponse(
        trace_id=trace_id,
        answer_type="action_done",
        answer=result.get("message", f"Action '{action_id}' has been cancelled."),
        sources=[],
        tools=tool_records,
        pending_action=None,
        handed_to_human=None,
    )
