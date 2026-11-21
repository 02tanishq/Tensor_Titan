"""
Teammate Agent Integration Module.
Implements process_with_rag_agent, bridging backend/server.py and backend/agent_hook.py
to our RAG & Orchestration brain.
"""

from typing import Dict, Any, Optional
from app.orchestrator.engine import handle_chat


def process_with_rag_agent(
    passenger_id: str,
    session_id: str,
    message: str,
    as_of: Optional[str] = None,
    trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delegates /chat requests to our full Orchestrator and Guardrails engine.
    Returns the exact Section 6.1 contract dictionary.
    """
    resp = handle_chat(
        header=passenger_id,
        session_id=session_id,
        message=message,
        as_of=as_of
    )

    return {
        "trace_id": resp.trace_id,
        "session_id": session_id,
        "passenger_id": passenger_id,
        "timestamp": as_of or "",
        "user_query": message,
        "answer_type": resp.answer_type,
        "answer": resp.answer,
        "sources": [s.model_dump() for s in resp.sources],
        "tools": [t.model_dump() for t in resp.tools],
        "pending_action": resp.pending_action.model_dump() if resp.pending_action else None,
        "handed_to_human": resp.handed_to_human.model_dump() if resp.handed_to_human else None
    }


def on_document_ingested(doc_id: str, doc_type: str, content: str):
    """Called automatically when POST /ingest receives a new document."""
    try:
        from app.orchestrator.engine import get_retriever
        get_retriever().reload()
    except Exception:
        pass
