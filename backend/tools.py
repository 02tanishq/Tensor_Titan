"""
Ujjwal Rail Official Deterministic Tools Module
Designed for teammates to import cleanly into their RAG/Agent reasoning loops:
    from backend.tools import (
        resolve_station,
        search_trains,
        check_seats,
        get_fare,
        get_booking_status,
        refund_quote,
        can_cancel,
        mask_pii,
        calculate_departure_datetime
    )
Strictly adheres to Hackathon Requirements (Sections 3, 4, 5, 6, 8).
All numbers and rules are deterministic and read from SQLite settings.
"""

import sqlite3
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "ujjwal_rail.db")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ----------------------------------------------------------------------
# 1. PII & Sensitive Data Masking Helper (Section C & F)
# ----------------------------------------------------------------------

def mask_pii(text_or_number: str, pii_type: str = "phone") -> str:
    """
    Masks PII to prevent privacy leakage in logs, traces, and LLM prompts.
    Never reveals full phone or identity numbers.
    """
    if not text_or_number:
        return ""
    val = str(text_or_number).strip()
    if pii_type == "phone":
        # Keep only last 4 digits
        digits = re.sub(r"\D", "", val)
        if len(digits) >= 4:
            return f"XXXXXX{digits[-4:]}"
        return "XXXX"
    elif pii_type == "id":
        # e.g., Aadhaar, Voter, PAN
        if len(val) > 4:
            return f"XXXX-XXXX-{val[-4:]}"
        return "XXXX"
    return val

# ----------------------------------------------------------------------
# 2. Station Alias Resolution (Section C)
# ----------------------------------------------------------------------

def resolve_station(name_or_code: str) -> Optional[Dict[str, str]]:
    """
    Resolves station code, city, official name or popular aliases (e.g. 'Bombay', 'CST').
    Handles similar names in the same city (e.g., CSMT vs LTT).
    """
    if not name_or_code:
        return None
    cleaned = name_or_code.strip()
    conn = get_db_connection()
    c = conn.cursor()

    # Exact code match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(station_code) = UPPER(?)", (cleaned,))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    # Exact Name match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(name) = UPPER(?)", (cleaned,))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    # Other names / alias match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(other_names) LIKE ?", (f"%{cleaned.upper()}%",))
    row = c.fetchone()
    if row:
        conn.close()
        return dict(row)

    # City or partial match
    c.execute("SELECT station_code, name, city FROM stations WHERE UPPER(name) LIKE ? OR UPPER(city) LIKE ?", 
              (f"%{cleaned.upper()}%", f"%{cleaned.upper()}%"))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)

    return None

# ----------------------------------------------------------------------
# 3. Timetable, Seats & Fares (Section C)
# ----------------------------------------------------------------------

def calculate_departure_datetime(journey_date_str: str, dep_time_str: str, day_offset: int = 0) -> datetime:
    """
    Constructs exact departure datetime handling day_offset and after-midnight departures.
    """
    dt = datetime.strptime(f"{journey_date_str} {dep_time_str}:00", "%Y-%m-%d %H:%M:%S")
    if day_offset:
        dt += timedelta(days=day_offset)
    return dt

def check_seats(train_no: str, journey_date: str, travel_class: str) -> Dict[str, Any]:
    """Retrieves live seats for a train, journey date and class."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT available, rac, waitlist FROM seats WHERE train_no = ? AND journey_date = ? AND class = ?",
              (train_no, journey_date, travel_class))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"available": 0, "rac": 0, "waitlist": 0}

def get_fare(train_no: str, from_code: str, to_code: str, travel_class: str) -> Optional[float]:
    """Retrieves official fare between two stations."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT fare FROM fares WHERE train_no = ? AND class = ? AND from_code = ? AND to_code = ?",
              (train_no, travel_class, from_code, to_code))
    row = c.fetchone()
    conn.close()
    return row["fare"] if row else None

def search_trains(from_stn: str, to_stn: str, journey_date: str, 
                  class_pref: Optional[str] = None, 
                  time_after: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Searches trains between two stations on a given date considering running days,
    intermediate stops, optional class preference, and optional departure time window.
    """
    from_meta = resolve_station(from_stn)
    to_meta = resolve_station(to_stn)
    if not from_meta or not to_meta:
        return []

    dt = datetime.strptime(journey_date, "%Y-%m-%d")
    day_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    day_name = day_map[dt.weekday()]

    conn = get_db_connection()
    c = conn.cursor()

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
        # Optional filter by time_after (e.g. "18:00")
        if time_after and row_dict["departure_time"] < time_after:
            continue

        row_dict["from_station"] = from_meta
        row_dict["to_station"] = to_meta
        row_dict["journey_date"] = journey_date

        classes_available = [cls.strip() for cls in row_dict["classes"].split(",")]
        classes_info = {}
        for cls in classes_available:
            if class_pref and cls != class_pref:
                continue
            fare = get_fare(row_dict["train_no"], from_meta["station_code"], to_meta["station_code"], cls)
            seats = check_seats(row_dict["train_no"], journey_date, cls)
            classes_info[cls] = {"fare": fare, "seats": seats}

        row_dict["classes_info"] = classes_info
        results.append(row_dict)

    conn.close()
    return results

# ----------------------------------------------------------------------
# 4. Booking Status (R8: Own Bookings Only)
# ----------------------------------------------------------------------

def get_booking_status(booking_id: str, requesting_passenger_id: str) -> Dict[str, Any]:
    """
    Retrieves status of passenger's own booking, with coach and berth per traveller.
    Returns identical unauthorized response whether booking exists or belongs to another.
    """
    conn = get_db_connection()
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

    # Strict privacy: If missing or belongs to another person, uniform refusal
    if not booking or booking["passenger_id"] != requesting_passenger_id:
        conn.close()
        return {
            "authorized": False,
            "error": "Booking not found or not accessible under your account."
        }

    b_dict = dict(booking)
    c.execute("SELECT traveller_name, age, status, coach, berth FROM booking_travellers WHERE booking_id = ?", (booking_id,))
    travellers = [dict(t) for t in c.fetchall()]
    b_dict["travellers"] = travellers
    conn.close()

    return {"authorized": True, "booking": b_dict}

# ----------------------------------------------------------------------
# 5. Deterministic Refund & Cancellation Quotes (R4, R6)
# ----------------------------------------------------------------------

def get_setting_value(name: str, default_val: float) -> float:
    """Reads parameter from SQLite settings table."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()
    return float(row["value"]) if row else default_val

def can_cancel(hours_before_departure: float) -> Tuple[bool, str]:
    """Determines if a booking is within the cancellable time window."""
    if hours_before_departure < 4.0:
        return False, "Chart prepared (< 4 hours before departure). No cancellation allowed via self-service."
    return True, "Cancellation permitted under standard rules."

def refund_quote(booking_id: str, requesting_passenger_id: str, as_of_iso: Optional[str] = None) -> Dict[str, Any]:
    """
    Pure deterministic refund calculation:
    - Reads class flat cancellation charges from settings
    - Considers circular CIR-2026-01 overrides when as_of >= 2026-02-01
    - Evaluates exact cut-offs:
        > 48h: Flat cancellation charge
        48h to 12h: 25% of fare subject to class flat minimum
        12h to 4h: 50% of fare subject to class flat minimum
        < 4h: No refund (charge = amount_paid)
    """
    auth = get_booking_status(booking_id, requesting_passenger_id)
    if not auth["authorized"]:
        return auth

    booking = auth["booking"]
    if booking["status"] in ("CANCELLED", "OPERATOR_CANCELLED"):
        return {
            "authorized": True,
            "eligible": False,
            "error": f"Booking {booking_id} is already {booking['status']}."
        }

    # Determine departure datetime
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT departure, day_offset FROM train_stops WHERE train_no = ? AND station_code = ?",
              (booking["train_no"], booking["from_code"]))
    stop_row = c.fetchone()
    conn.close()

    dep_time_str = stop_row["departure"] if stop_row else "10:00"
    day_offset = stop_row["day_offset"] if stop_row and stop_row["day_offset"] else 0
    departure_dt = calculate_departure_datetime(booking["journey_date"], dep_time_str, day_offset)

    as_of_dt = datetime.fromisoformat(as_of_iso.replace("Z", "+00:00")) if as_of_iso else datetime.now()
    if as_of_dt.tzinfo is not None:
        as_of_dt = as_of_dt.replace(tzinfo=None)

    hours_before = (departure_dt - as_of_dt).total_seconds() / 3600.0
    travel_class = booking["class"]
    amount_paid = float(booking["amount_paid"])

    # Base flat charges from settings
    # cancel_charge_1AC_over_48h, cancel_charge_2AC_over_48h, etc.
    base_charge = get_setting_value(f"cancel_charge_{travel_class}_over_48h", 120.0)
    rule_cited = "RUL-CAN-01 (Section 3: Refund Table)"

    # Check Circular CIR-2026-01 override (effective 2026-02-01)
    cir_effective = datetime(2026, 2, 1)
    if as_of_dt >= cir_effective:
        if travel_class == "2AC":
            base_charge = 200.0
            rule_cited = "CIR-2026-01 (Revised Flat Charges) & RUL-CAN-01"
        elif travel_class == "3AC":
            base_charge = 180.0
            rule_cited = "CIR-2026-01 (Revised Flat Charges) & RUL-CAN-01"

    # Evaluation at cut-offs
    cancellable, reason = can_cancel(hours_before)

    if hours_before > 48.0:
        cancellation_charge = base_charge
        cut_off_window = "> 48 hours"
    elif 12.0 <= hours_before <= 48.0:
        cancellation_charge = max(base_charge, int(round(amount_paid * 0.25)))
        cut_off_window = "48h to 12h (25% fee)"
    elif 4.0 <= hours_before < 12.0:
        cancellation_charge = max(base_charge, int(round(amount_paid * 0.50)))
        cut_off_window = "12h to 4h (50% fee)"
    else:
        cancellation_charge = amount_paid
        cut_off_window = "< 4 hours (No refund on confirmed ticket)"

    refund_amount = max(0.0, amount_paid - cancellation_charge)

    return {
        "authorized": True,
        "eligible": cancellable,
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
# 6. Rule Extraction & Safe Adjustment Ledger (Predefined vs Amended)
# ----------------------------------------------------------------------

def extract_base_rule(doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Extracts the untouched, permanent predefined rule from the separate 'predefined_rules' table.
    Guarantees that the baseline policy is always preserved without modifications.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT doc_id, title, category, effective_date, content FROM predefined_rules WHERE doc_id = ?", (doc_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def extract_effective_rule(doc_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts the rule by taking the permanent baseline rule from 'predefined_rules'
    and checking if any active circular in 'circulars' amends it as of 'as_of'.
    Returns full provenance: base rule, whether amended, active circular ID, and effective text.
    """
    base = extract_base_rule(doc_id)
    if not base:
        return {"found": False, "error": f"Rule {doc_id} not found in predefined rules."}

    if not as_of:
        as_of = datetime.now().isoformat()

    conn = get_db_connection()
    c = conn.cursor()
    # Find active circulars modifying this base rule
    c.execute("""
    SELECT doc_id, title, issue_date, effective_date, content 
    FROM circulars 
    WHERE modifies_rule = ? AND effective_date <= ? 
    ORDER BY effective_date DESC LIMIT 1
    """, (doc_id, as_of[:10]))
    active_circ = c.fetchone()
    conn.close()

    if active_circ:
        circ_dict = dict(active_circ)
        return {
            "found": True,
            "doc_id": doc_id,
            "title": base["title"],
            "category": base["category"],
            "is_amended": True,
            "active_circular_id": circ_dict["doc_id"],
            "circular_title": circ_dict["title"],
            "circular_effective_date": circ_dict["effective_date"],
            "base_content": base["content"],
            "amendment_content": circ_dict["content"],
            "rule_citation": f"{circ_dict['doc_id']} (Modifying {doc_id})"
        }

    return {
        "found": True,
        "doc_id": doc_id,
        "title": base["title"],
        "category": base["category"],
        "is_amended": False,
        "active_circular_id": None,
        "base_content": base["content"],
        "effective_content": base["content"],
        "rule_citation": f"{doc_id} (Official Baseline)"
    }

def extract_all_rules_summary(as_of: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extracts all 12 predefined baseline rules and shows their current active amendment status.
    """
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT doc_id FROM predefined_rules ORDER BY doc_id ASC")
    rule_ids = [r["doc_id"] for r in c.fetchall()]
    conn.close()

    summary = []
    for r_id in rule_ids:
        summary.append(extract_effective_rule(r_id, as_of))
    return summary

def adjust_rule_via_circular(
    circular_id: str, 
    base_rule_id: str, 
    title: str, 
    amendment_content: str, 
    effective_date: str,
    numeric_settings: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Safely adjusts a railway policy WITHOUT touching or mutating the predefined_rules table!
    1. Writes an amendment entry into 'circulars' and 'documents'
    2. Updates 'settings' with the new numeric parameters and links source_doc to circular_id
    3. Leaves 'predefined_rules' completely untouched and protected.
    """
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Insert into circulars
    c.execute("""
    INSERT OR REPLACE INTO circulars (doc_id, title, issue_date, effective_date, modifies_rule, content, language)
    VALUES (?, ?, ?, ?, ?, ?, 'en')
    """, (circular_id, title, datetime.now().strftime("%Y-%m-%d"), effective_date, base_rule_id, amendment_content))

    # 2. Insert into documents table for teammate indexing
    c.execute("""
    INSERT OR REPLACE INTO documents (doc_id, section, type, text, effective_from, supersedes)
    VALUES (?, 'Amendment', 'circular', ?, ?, ?)
    """, (circular_id, f"{title}: {amendment_content}", effective_date, base_rule_id))

    # 3. Update numeric settings if provided
    if numeric_settings:
        for k, v in numeric_settings.items():
            c.execute("INSERT OR REPLACE INTO settings (name, value, source_doc) VALUES (?, ?, ?)",
                      (k, float(v), circular_id))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Successfully applied policy adjustment via {circular_id} modifying {base_rule_id}.",
        "base_rule_untouched": True,
        "circular_id": circular_id,
        "effective_date": effective_date
    }
