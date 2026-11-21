"""
Identity & Privacy Guard for Ujjwal Rail.
Enforces:
1. Passenger identity originates ONLY from X-Passenger-Id header.
2. Identical refusal for non-existent and other-passenger bookings (zero existence leakage).
3. PII masking on all phone and identity numbers (last4 only).
"""

import re
import sqlite3
from typing import Optional, Tuple, Dict, Any, Union


def resolve_passenger(header: Optional[str], db_path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Resolve passenger identity strictly via the X-Passenger-Id header.
    One-line reason: Prevents identity spoofing by never extracting passenger credentials from user prose.
    """
    if not header or not header.strip():
        return None, "Authentication required: Missing X-Passenger-Id header."

    passenger_id = header.strip()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT passenger_id, name, phone_last4, preferred_language FROM passengers WHERE passenger_id = ?;", (passenger_id,))
        row = c.fetchone()
        if row:
            return dict(row), None

    return None, f"Unauthorized: Passenger '{passenger_id}' not found in registry."


def ownership_check(passenger_id: str, booking_id: str, db_path: str) -> Tuple[bool, str]:
    """
    Verifies that a booking exists and belongs to the authenticated passenger.
    Returns IDENTICAL refusal message for non-existent or other-passenger booking.
    One-line reason: Information-theoretic privacy guarantees booking existence is never leaked to third parties.
    """
    if not booking_id:
        return False, "Booking ID must be provided."

    b_id = booking_id.strip()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT passenger_id FROM bookings WHERE booking_id = ?;", (b_id,))
        row = c.fetchone()

        # If booking does not exist OR belongs to another passenger, yield identical message
        if not row or row["passenger_id"] != passenger_id:
            return False, "I could not locate an active booking under that reference associated with your account. Please verify the booking ID."

    return True, ""


def mask_pii(data: Union[str, Dict[str, Any], list]) -> Union[str, Dict[str, Any], list]:
    """
    Recursively masks phone numbers, Aadhaar, and national IDs to retain last 4 digits only.
    One-line reason: Compliance with privacy guardrail to never output full PII.
    """
    if isinstance(data, str):
        # Mask 10-digit Indian phone numbers: e.g. 9876543210 -> ******3210
        text = re.sub(r"\b(?:\+?91[\s-]?)?([6-9]\d{5})(\d{4})\b", r"******\2", data)
        # Mask 12-digit Aadhaar: e.g. 1234 5678 9012 or 123456789012 -> ********9012
        text = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?(\d{4})\b", r"********\1", text)
        # Mask PAN Card: e.g. ABCDE1234F -> ******1234F or ******1234
        text = re.sub(r"\b([A-Z]{5})(\d{4})([A-Z])\b", r"*****\2\3", text)
        return text

    elif isinstance(data, dict):
        masked_dict = {}
        for k, v in data.items():
            if k in ("phone", "mobile", "aadhaar", "id_number") and isinstance(v, str) and len(v) >= 4:
                masked_dict[k] = f"***{v[-4:]}"
            else:
                masked_dict[k] = mask_pii(v)
        return masked_dict

    elif isinstance(data, list):
        return [mask_pii(item) for item in data]

    return data
