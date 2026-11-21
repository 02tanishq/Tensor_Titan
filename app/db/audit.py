"""
Audit Logging and Trace persistence for Ujjwal Rail.
Writes immutable trace records to audit_logs table for every chat response and action confirmation.
"""

import sqlite3
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

logger = logging.getLogger("app.db.audit")


def write_audit_trace(
    db_path: str,
    session_id: str,
    passenger_id: str,
    user_query: str,
    answer_type: str,
    answer_text: str,
    sources_cited: Optional[List[Dict[str, Any]]] = None,
    tools_used: Optional[List[Dict[str, Any]]] = None,
    pending_action: Optional[Dict[str, Any]] = None,
    handed_to_human: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> str:
    """
    Persist complete audit record to audit_logs table.
    One-line reason: Required for regulatory compliance, traceability, and competition evaluation.
    """
    if not trace_id:
        trace_id = uuid.uuid4().hex[:8]

    timestamp = datetime.now().isoformat()

    sources_json = json.dumps(sources_cited, ensure_ascii=False) if sources_cited else None
    tools_json = json.dumps(tools_used, ensure_ascii=False) if tools_used else None
    pending_json = json.dumps(pending_action, ensure_ascii=False) if pending_action else None
    human_json = json.dumps(handed_to_human, ensure_ascii=False) if handed_to_human else None

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO audit_logs (
                trace_id, session_id, passenger_id, timestamp, user_query,
                answer_type, answer_text, sources_cited, tools_used,
                pending_action, handed_to_human
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            trace_id, session_id, passenger_id, timestamp, user_query,
            answer_type, answer_text, sources_json, tools_json,
            pending_json, human_json
        ))
        conn.commit()

    logger.info("Audit trace written: trace_id=%s, passenger_id=%s", trace_id, passenger_id)
    return trace_id


def get_audit_trace(db_path: str, trace_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve an audit trace record by trace_id."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM audit_logs WHERE trace_id = ?;", (trace_id,))
        row = c.fetchone()
        if row:
            d = dict(row)
            if d.get("sources_cited"):
                try: d["sources_cited"] = json.loads(d["sources_cited"])
                except Exception: pass
            if d.get("tools_used"):
                try: d["tools_used"] = json.loads(d["tools_used"])
                except Exception: pass
            if d.get("pending_action"):
                try: d["pending_action"] = json.loads(d["pending_action"])
                except Exception: pass
            if d.get("handed_to_human"):
                try: d["handed_to_human"] = json.loads(d["handed_to_human"])
                except Exception: pass
            return d
    return None
