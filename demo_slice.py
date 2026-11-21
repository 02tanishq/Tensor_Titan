"""
Demonstration script for Guardrails & Orchestrator vertical slice.
Runs one real end-to-end request through handle_chat() and fetches the persisted audit record from the database.
"""

import json
from app.orchestrator.engine import handle_chat
from app.db.audit import get_audit_trace
from app.config import config

def main():
    print("=" * 70)
    print("     UJJWAL RAIL ORCHESTRATOR & GUARDRAILS VERTICAL SLICE DEMO     ")
    print("=" * 70)

    header = "PASS-001"
    session_id = "sess-demo-vertical-slice"
    user_query = "Can I carry my pet dog in 2AC coach? And what is the online booking window?"
    as_of = "2026-11-21"

    print(f"\n[REQUEST]")
    print(f"Header: X-Passenger-Id: {header}")
    print(f"Session ID: {session_id}")
    print(f"As Of Date: {as_of}")
    print(f"User Query: '{user_query}'")

    response = handle_chat(
        header=header,
        session_id=session_id,
        message=user_query,
        as_of=as_of
    )

    print(f"\n[RESPONSE]")
    print(f"Trace ID: {response.trace_id}")
    print(f"Answer Type: {response.answer_type}")
    print(f"Answer Content:\n{response.answer}")
    print(f"Sources Cited: {[s.model_dump() for s in response.sources]}")
    print(f"Tools Used: {[t.model_dump() for t in response.tools]}")
    print(f"Pending Action: {response.pending_action}")
    print(f"Handed to Human: {response.handed_to_human}")

    print(f"\n[SAVED AUDIT TRACE FROM SQLITE audit_logs TABLE]")
    trace_record = get_audit_trace(config.DB_PATH, response.trace_id)
    if trace_record:
        print(json.dumps(trace_record, indent=2, ensure_ascii=False))
    else:
        print(f"ERROR: Trace {response.trace_id} not found in database!")

    print("\n" + "=" * 70)
    print("                     DEMO EXECUTION SUCCESSFUL                     ")
    print("=" * 70)

if __name__ == "__main__":
    main()
