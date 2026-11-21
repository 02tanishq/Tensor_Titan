"""
Ujjwal Rail Domain Engine & Deterministic Railway Tools
Strictly adheres to HCLTech Hackathon Requirements (Sections 4.2, 5.1, 6.1, 6.3, and Checklist A-G)
"""

import sqlite3
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "ujjwal_rail.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ----------------------------------------------------------------------
# 0. PII Masking Helper
# ----------------------------------------------------------------------

def mask_pii(val: Optional[str]) -> str:
    """Masks phone and ID numbers to protect privacy."""
    if not val:
        return ""
    val_str = str(val).strip()
    if len(val_str) > 4:
        return f"XXXXXX{val_str[-4:]}"
    return val_str

# ----------------------------------------------------------------------
# 1. Station Alias Resolution & Train Lookup
# ----------------------------------------------------------------------

def resolve_station(name_or_code: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, str]]:
    """Resolves station name, city or alias to official station_code."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True

    cleaned = name_or_code.strip()
    c = conn.cursor()
    # Direct code match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(station_code) = UPPER(?)", (cleaned,))
    row = c.fetchone()
    if row:
        res = dict(row)
        if should_close: conn.close()
        return res

    # Exact name match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(name) = UPPER(?)", (cleaned,))
    row = c.fetchone()
    if row:
        res = dict(row)
        if should_close: conn.close()
        return res

    # Other names / alias match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(other_names) LIKE ?", (f"%{cleaned.upper()}%",))
    row = c.fetchone()
    if row:
        res = dict(row)
        if should_close: conn.close()
        return res

    # City or partial match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(name) LIKE ? OR UPPER(city) LIKE ?", 
              (f"%{cleaned.upper()}%", f"%{cleaned.upper()}%"))
    row = c.fetchone()
    res = dict(row) if row else None
    if should_close: conn.close()
    return res

def search_trains(from_stn: str, to_stn: str, journey_date: str, 
                  class_pref: Optional[str] = None,
                  time_after: Optional[str] = None) -> List[Dict[str, Any]]:
    """Finds trains between two stations on a given date considering running days and intermediate stops."""
    conn = get_db()
    c = conn.cursor()

    from_meta = resolve_station(from_stn, conn)
    to_meta = resolve_station(to_stn, conn)

    if not from_meta or not to_meta:
        conn.close()
        return []

    # Get day of week
    dt = datetime.strptime(journey_date, "%Y-%m-%d")
    day_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    day_name = day_map[dt.weekday()]

    query = """
    SELECT 
        t.train_no, t.name, t.runs_on, t.classes,
        s1.departure AS departure_time, s1.day_offset AS dep_day_offset,
        s2.arrival AS arrival_time, s2.day_offset AS arr_day_offset
    FROM trains t
    JOIN train_stops s1 ON t.train_no = s1.train_no AND s1.station_code = ?
    JOIN train_stops s2 ON t.train_no = s2.train_no AND s2.station_code = ?
    WHERE s1.stop_order < s2.stop_order
      AND t.runs_on LIKE ?
    """
    c.execute(query, (from_meta["station_code"], to_meta["station_code"], f"%{day_name}%"))
    results = []
    for r in c.fetchall():
        row_dict = dict(r)
        if time_after and row_dict["departure_time"] < time_after:
            continue

        row_dict["from_station"] = from_meta
        row_dict["to_station"] = to_meta
        row_dict["journey_date"] = journey_date

        classes_available = [cls.strip() for cls in row_dict["classes"].split(",")]
        availability = {}
        for cls in classes_available:
            if class_pref and cls != class_pref:
                continue
            # Fare
            c.execute("SELECT fare FROM fares WHERE train_no = ? AND class = ? AND from_code = ? AND to_code = ?",
                      (row_dict["train_no"], cls, from_meta["station_code"], to_meta["station_code"]))
            fare_row = c.fetchone()
            fare = fare_row["fare"] if fare_row else None

            # Seats
            c.execute("SELECT available, rac, waitlist FROM seats WHERE train_no = ? AND journey_date = ? AND class = ?",
                      (row_dict["train_no"], journey_date, cls))
            seat_row = c.fetchone()
            seats = dict(seat_row) if seat_row else {"available": 0, "rac": 0, "waitlist": 0}

            availability[cls] = {"fare": fare, "seats": seats}

        row_dict["classes_info"] = availability
        results.append(row_dict)

    conn.close()
    return results

# ----------------------------------------------------------------------
# 2. Booking Privacy & Lookup (R8 Privacy Guarantee)
# ----------------------------------------------------------------------

def get_booking_secure(booking_id: str, requesting_passenger_id: str) -> Dict[str, Any]:
    """
    R8 Guarantee: Returns booking only if requesting_passenger_id owns it.
    If not owned, returns polite refusal without revealing whether booking exists.
    """
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    SELECT b.*, t.name AS train_name, s1.name AS from_name, s2.name AS to_name
    FROM bookings b
    JOIN trains t ON b.train_no = t.train_no
    JOIN stations s1 ON b.from_code = s1.station_code
    JOIN stations s2 ON b.to_code = s2.station_code
    WHERE b.booking_id = ?
    """, (booking_id,))
    booking = c.fetchone()

    # Identical refusal for "does not exist" or "not yours" to prevent existence enumeration
    if not booking or booking["passenger_id"] != requesting_passenger_id:
        conn.close()
        return {
            "authorized": False,
            "message": "Booking not found or not accessible under your account."
        }

    b_dict = dict(booking)

    # Fetch travellers
    c.execute("SELECT traveller_name, age, status, coach, berth FROM booking_travellers WHERE booking_id = ?", (booking_id,))
    travellers = [dict(t) for t in c.fetchall()]
    b_dict["travellers"] = travellers

    conn.close()
    return {"authorized": True, "booking": b_dict}

# ----------------------------------------------------------------------
# 3. Exact Deterministic Refund Calculator (R4, R6)
# ----------------------------------------------------------------------

def calculate_refund_quote(booking_id: str, requesting_passenger_id: str, as_of_iso: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculates exact refund based on class, departure time, settings table and as_of timestamp.
    Applies Circular CIR-2026-01 (overriding RUL-CAN-01) if effective.
    """
    auth_check = get_booking_secure(booking_id, requesting_passenger_id)
    if not auth_check["authorized"]:
        return auth_check

    booking = auth_check["booking"]
    if booking["status"] in ("CANCELLED", "OPERATOR_CANCELLED"):
        return {
            "authorized": True,
            "eligible": False,
            "message": f"Booking {booking_id} is already in {booking['status']} state. No further refund applies."
        }

    conn = get_db()
    c = conn.cursor()

    # Determine departure datetime including day offset
    c.execute("SELECT departure, day_offset FROM train_stops WHERE train_no = ? AND station_code = ?", 
              (booking["train_no"], booking["from_code"]))
    stop_row = c.fetchone()
    dep_time_str = stop_row["departure"] if stop_row else "10:00"
    day_offset = stop_row["day_offset"] if stop_row and stop_row["day_offset"] else 0

    dep_dt_str = f"{booking['journey_date']} {dep_time_str}:00"
    departure_dt = datetime.strptime(dep_dt_str, "%Y-%m-%d %H:%M:%S") + timedelta(days=day_offset)

    as_of_dt = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00")) if as_of_iso else datetime.now()
    if as_of_dt.tzinfo is not None:
        as_of_dt = as_of_dt.replace(tzinfo=None)

    hours_before = (departure_dt - as_of_dt).total_seconds() / 3600.0

    travel_class = booking["class"]
    amount_paid = float(booking["amount_paid"])

    # Base flat charges from settings table
    c.execute("SELECT value FROM settings WHERE name = ?", (f"cancel_charge_{travel_class}_over_48h",))
    set_row = c.fetchone()
    base_charge = float(set_row["value"]) if set_row else 120.0
    rule_cited = "RUL-CAN-01 (Sec 3: Refund Table)"

    # Check Circular CIR-2026-01 (Effective 2026-02-01)
    cir_effective = datetime(2026, 2, 1)
    if as_of_dt >= cir_effective:
        if travel_class == "2AC":
            base_charge = 200.0
            rule_cited = "CIR-2026-01 (Revised Flat Charges) & RUL-CAN-01"
        elif travel_class == "3AC":
            base_charge = 180.0
            rule_cited = "CIR-2026-01 (Revised Flat Charges) & RUL-CAN-01"

    # Cut-off windows:
    # > 48 hours: Flat cancellation fee per passenger
    # 48h to 12h: 25% of fare subject to class minimum flat charge
    # 12h to 4h: 50% of fare subject to class minimum flat charge
    # < 4h: No refund
    if hours_before > 48.0:
        cancellation_charge = base_charge
        refund_amount = max(0.0, amount_paid - cancellation_charge)
        cut_off_window = "> 48 hours"
        eligible = True
    elif 12.0 <= hours_before <= 48.0:
        cancellation_charge = max(base_charge, int(round(amount_paid * 0.25)))
        refund_amount = max(0.0, amount_paid - cancellation_charge)
        cut_off_window = "48h to 12h (25% fee)"
        eligible = True
    elif 4.0 <= hours_before < 12.0:
        cancellation_charge = max(base_charge, int(round(amount_paid * 0.50)))
        refund_amount = max(0.0, amount_paid - cancellation_charge)
        cut_off_window = "12h to 4h (50% fee)"
        eligible = True
    else:
        cancellation_charge = amount_paid
        refund_amount = 0.0
        cut_off_window = "< 4 hours (No refund on confirmed ticket)"
        eligible = False

    conn.close()

    return {
        "authorized": True,
        "eligible": eligible,
        "booking_id": booking_id,
        "train_no": booking["train_no"],
        "class": travel_class,
        "amount_paid": amount_paid,
        "charge": cancellation_charge,
        "refund": refund_amount,
        "hours_before_departure": round(hours_before, 2),
        "cut_off_window": cut_off_window,
        "rule_cited": rule_cited,
        "as_of_evaluated": as_of_dt.isoformat()
    }

# ----------------------------------------------------------------------
# 4. Level 1 Action Lifecycle: State Machine (Section D & A)
# State Machine: proposed -> confirmed | cancelled | expired | failed
# ----------------------------------------------------------------------

def propose_action(passenger_id: str, booking_id: str, action_type: str, details: Dict[str, Any], ttl_minutes: Optional[int] = None) -> Dict[str, Any]:
    """Creates a Level 1 proposed action with TTL expiration read from settings."""
    conn = get_db()
    c = conn.cursor()

    if ttl_minutes is None:
        c.execute("SELECT value FROM settings WHERE name = 'action_expiry_minutes'")
        set_row = c.fetchone()
        ttl_minutes = int(set_row["value"]) if set_row else 10

    action_id = f"ACT-{uuid.uuid4().hex[:6].upper()}"
    now_dt = datetime.now()
    exp_dt = now_dt + timedelta(minutes=ttl_minutes)

    created_at = now_dt.isoformat()
    expires_at = exp_dt.isoformat()
    result_json = json.dumps(details)

    c.execute("""
    INSERT INTO actions (action_id, passenger_id, booking_id, action_type, status, created_at, expires_at, result)
    VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?)
    """, (action_id, passenger_id, booking_id, action_type, created_at, expires_at, result_json))

    conn.commit()
    conn.close()

    return {
        "action_id": action_id,
        "type": action_type,
        "booking_id": booking_id,
        "status": "proposed",
        "created_at": created_at,
        "expires_at": expires_at,
        "details": details
    }

def confirm_action_execution(action_id: str, requesting_passenger_id: str) -> Dict[str, Any]:
    """
    R5 & Idempotency: Confirms proposed change in one transaction, re-reads and verifies.
    Only the passenger who asked may confirm. Calling twice returns stored result without duplicate changes.
    """
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,))
    act = c.fetchone()

    if not act:
        conn.close()
        return {"success": False, "error": f"Action {action_id} not found."}

    # Strict passenger verification
    if act["passenger_id"] != requesting_passenger_id:
        conn.close()
        return {"success": False, "error": "Unauthorized: Only the passenger who requested this action can confirm it."}

    try:
        stored_res = json.loads(act["result"]) if act["result"] else {}
    except Exception:
        stored_res = {"preview": act["result"]}
    if act["status"] in ("confirmed", "CONFIRMED"):
        conn.close()
        return {
            "success": True,
            "action_id": action_id,
            "status": "action_done",
            "message": "Action was already confirmed and processed.",
            "result": stored_res
        }

    # Check expiration from settings
    exp_dt = datetime.fromisoformat(act["expires_at"])
    if datetime.now() > exp_dt:
        c.execute("UPDATE actions SET status = 'expired' WHERE action_id = ?", (action_id,))
        conn.commit()
        conn.close()
        return {"success": False, "error": "Action has expired (exceeded TTL). Please request again."}

    action_type = act["action_type"]
    booking_id = act["booking_id"]
    try:
        details = json.loads(act["result"]) if act["result"] else {}
    except Exception:
        details = {"preview": act["result"]}

    try:
        # Atomic Transaction
        if action_type == "cancel_booking":
            c.execute("SELECT train_no, journey_date, class FROM bookings WHERE booking_id = ?", (booking_id,))
            bk_row = c.fetchone()

            # Update booking status
            c.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
            c.execute("UPDATE booking_travellers SET status = 'CAN' WHERE booking_id = ?", (booking_id,))
            
            # Seat restoration
            if bk_row:
                c.execute("""
                UPDATE seats 
                SET available = available + 1 
                WHERE train_no = ? AND journey_date = ? AND class = ?
                """, (bk_row["train_no"], bk_row["journey_date"], bk_row["class"]))

            # Update action state to confirmed
            c.execute("UPDATE actions SET status = 'confirmed' WHERE action_id = ?", (action_id,))

            # Re-read and verify check
            c.execute("SELECT status FROM bookings WHERE booking_id = ?", (booking_id,))
            verify_row = c.fetchone()
            if not verify_row or verify_row["status"] != "CANCELLED":
                conn.rollback()
                c.execute("UPDATE actions SET status = 'failed' WHERE action_id = ?", (action_id,))
                conn.commit()
                conn.close()
                return {"success": False, "error": "Verification check failed: booking status was not updated."}

            # Record in audit logs & traces
            trace_id = f"trc-{uuid.uuid4().hex[:6]}"
            audit_record = (
                trace_id,
                "CONFIRM_SESSION",
                requesting_passenger_id,
                datetime.now().isoformat(),
                f"Confirm action {action_id}",
                "action_done",
                f"Booking {booking_id} successfully cancelled. Refund of Rs {details.get('refund', 0)} initiated.",
                json.dumps([{"doc_id": "RUL-CAN-01"}, {"doc_id": "CIR-2026-01"}]),
                json.dumps([{"tool": "confirm_action", "output": {"action_id": action_id, "booking_id": booking_id}}]),
                None,
                None
            )
            c.execute("""
            INSERT INTO audit_logs (trace_id, session_id, passenger_id, timestamp, user_query, answer_type, answer_text, sources_cited, tools_used, pending_action, handed_to_human)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, audit_record)
            c.execute("""
            INSERT OR REPLACE INTO traces (trace_id, session_id, passenger_id, timestamp, user_query, answer_type, answer_text, sources_cited, tools_used, pending_action, handed_to_human)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, audit_record)

            conn.commit()
            conn.close()

            return {
                "success": True,
                "action_id": action_id,
                "status": "action_done",
                "message": f"Booking {booking_id} has been successfully cancelled. Refund of Rs {details.get('refund', 0)} will be credited.",
                "details": details
            }
        else:
            conn.close()
            return {"success": False, "error": f"Unsupported action type: {action_type}"}

    except Exception as e:
        conn.rollback()
        c.execute("UPDATE actions SET status = 'failed' WHERE action_id = ?", (action_id,))
        conn.commit()
        conn.close()
        return {"success": False, "error": f"Execution error: {str(e)}"}

def cancel_action_execution(action_id: str, requesting_passenger_id: str) -> Dict[str, Any]:
    """Drops a proposed action cleanly (status -> cancelled, nothing happens to bookings)."""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,))
    act = c.fetchone()
    if not act:
        conn.close()
        return {"success": False, "error": f"Action {action_id} not found."}

    if act["passenger_id"] != requesting_passenger_id:
        conn.close()
        return {"success": False, "error": "Unauthorized."}

    c.execute("UPDATE actions SET status = 'cancelled' WHERE action_id = ?", (action_id,))
    conn.commit()
    conn.close()

    return {"success": True, "action_id": action_id, "status": "action_dropped", "message": "Proposed change cancelled. No changes were made to the booking."}

# ----------------------------------------------------------------------
# 5. Level 2 Safe Handover Records
# ----------------------------------------------------------------------

def create_handover_record(passenger_id: str, category: str, summary: str, booking_id: Optional[str] = None) -> Dict[str, Any]:
    """Creates a grievance / dispute handover record without false promises."""
    conn = get_db()
    c = conn.cursor()
    handover_id = f"HND-{uuid.uuid4().hex[:6].upper()}"
    now_str = datetime.now().isoformat()

    c.execute("""
    INSERT INTO handovers (handover_id, passenger_id, booking_id, category, summary, status, created_at)
    VALUES (?, ?, ?, ?, ?, 'OPEN', ?)
    """, (handover_id, passenger_id, booking_id, category, summary, now_str))

    conn.commit()
    conn.close()

    return {
        "handover_id": handover_id,
        "passenger_id": passenger_id,
        "booking_id": booking_id,
        "category": category,
        "summary": summary,
        "status": "OPEN",
        "created_at": now_str
    }

# ----------------------------------------------------------------------
# 6. Ingestion Engine & Audit Tracing (R10, R11, Documents Table)
# ----------------------------------------------------------------------

def ingest_document(doc_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    R11: Ingests rules, circulars, or FAQs into SQLite specialized tables
    AND the plain documents table so teammate agents can index directly.
    """
    conn = get_db()
    c = conn.cursor()

    doc_type = doc_type.lower()
    doc_id = data.get("doc_id") or data.get("faq_id", "DOC-UNKNOWN")
    effective_from = data.get("effective_date", "2026-11-21")
    supersedes = data.get("modifies_rule") or data.get("superseded_by")
    text_content = data.get("content") or f"Q: {data.get('question', '')} A: {data.get('answer', '')}"
    section = data.get("section", "General")

    if doc_type == "rule":
        c.execute("""
        INSERT OR REPLACE INTO rules (doc_id, title, category, effective_date, content)
        VALUES (?, ?, ?, ?, ?)
        """, (doc_id, data.get("title", doc_id), data.get("category", "General"), effective_from, text_content))
    elif doc_type == "circular":
        c.execute("""
        INSERT OR REPLACE INTO circulars (doc_id, title, issue_date, effective_date, modifies_rule, content, language)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, data.get("title", doc_id), data.get("issue_date", "2026-11-21"), 
            effective_from, supersedes, text_content, data.get("language", "en")
        ))
    elif doc_type == "faq":
        c.execute("""
        INSERT OR REPLACE INTO faqs (faq_id, question, answer, category, language, is_outdated, superseded_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, data.get("question", ""), data.get("answer", ""), data.get("category", "General"), 
            data.get("language", "en"), data.get("is_outdated", 0), supersedes
        ))
    else:
        conn.close()
        return {"success": False, "error": f"Invalid doc_type {doc_type}. Must be rule, circular, or faq."}

    # Write to plain documents table
    c.execute("""
    INSERT OR REPLACE INTO documents (doc_id, section, type, text, effective_from, supersedes)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (doc_id, section, doc_type, text_content, effective_from, supersedes))

    conn.commit()
    conn.close()

    # Trigger teammate indexing hook if present
    try:
        from backend import teammate_agent
        if hasattr(teammate_agent, "on_document_ingested"):
            teammate_agent.on_document_ingested(doc_id, doc_type, text_content)
    except Exception:
        pass

    return {"success": True, "message": f"Successfully ingested {doc_type} {doc_id} into documents table."}

def save_audit_trace(trace_dict: Dict[str, Any]):
    """R10: Records full trace record for judge review."""
    conn = get_db()
    c = conn.cursor()
    record = (
        trace_dict.get("trace_id"),
        trace_dict.get("session_id"),
        trace_dict.get("passenger_id"),
        trace_dict.get("timestamp", datetime.now().isoformat()),
        trace_dict.get("user_query"),
        trace_dict.get("answer_type"),
        trace_dict.get("answer"),
        json.dumps(trace_dict.get("sources", [])),
        json.dumps(trace_dict.get("tools", [])),
        json.dumps(trace_dict.get("pending_action")) if trace_dict.get("pending_action") else None,
        json.dumps(trace_dict.get("handed_to_human")) if trace_dict.get("handed_to_human") else None
    )
    c.execute("""
    INSERT OR REPLACE INTO audit_logs (trace_id, session_id, passenger_id, timestamp, user_query, answer_type, answer_text, sources_cited, tools_used, pending_action, handed_to_human)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, record)
    c.execute("""
    INSERT OR REPLACE INTO traces (trace_id, session_id, passenger_id, timestamp, user_query, answer_type, answer_text, sources_cited, tools_used, pending_action, handed_to_human)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, record)

    conn.commit()
    conn.close()

def get_audit_trace(trace_id: str, requesting_passenger_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns saved trace record for a reply with owner verification and PII masking."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    r_dict = dict(row)

    if requesting_passenger_id and r_dict["passenger_id"] != requesting_passenger_id:
        return None

    if r_dict["sources_cited"]:
        r_dict["sources"] = json.loads(r_dict["sources_cited"])
    if r_dict["tools_used"]:
        r_dict["tools"] = json.loads(r_dict["tools_used"])
    if r_dict["pending_action"]:
        r_dict["pending_action"] = json.loads(r_dict["pending_action"])
    if r_dict["handed_to_human"]:
        r_dict["handed_to_human"] = json.loads(r_dict["handed_to_human"])
    return r_dict
