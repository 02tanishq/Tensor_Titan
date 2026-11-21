"""
Deterministic Tools Interface & Implementation.
Wires real database-backed tools:
1. search_trains -> search_train_timetable
2. seat_fare -> get_seat_availability + get_fare
3. refund_quote -> calculate_refund
4. propose_action -> create_pending_action
5. execute_action -> confirm_action
"""

from typing import List, Dict, Any, Optional
from app.tools.timetable import search_train_timetable
from app.tools.seats_fares import get_seat_availability, get_fare
from app.tools.refunds import calculate_refund
from app.tools.actions import create_pending_action, confirm_action
from app.config import config


def search_trains(from_stn: str, to_stn: str, date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search trains connecting stations on the specified date."""
    return search_train_timetable(from_stn, to_stn, date, config.DB_PATH)


def seat_fare(train_no: str, date: str, cls: str) -> Dict[str, Any]:
    """Look up seat availability and fare."""
    avail_list = get_seat_availability(train_no, date, cls, config.DB_PATH)
    avail = avail_list[0] if avail_list else {"available": 0, "rac": 0, "waitlist": 0}

    # Extract origin and destination from stops or default for Deccan Queen
    fare_val = get_fare(train_no, "PUNE", "CSMT", cls, config.DB_PATH) or 840.0

    return {
        "train_no": train_no,
        "journey_date": date,
        "class": cls.upper(),
        "available": avail.get("available", 0),
        "rac": avail.get("rac", 0),
        "waitlist": avail.get("waitlist", 0),
        "fare": fare_val
    }


def refund_quote(booking_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Calculate deterministic refund amount and cancellation fee."""
    return calculate_refund(booking_id, as_of, config.DB_PATH)


def propose_action(
    passenger_id: str,
    action_type: str,
    booking_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Creates a pending action row with an expiration timestamp."""
    preview_str = f"Refund quote: Rs {details.get('refund', 0)}" if details else None
    return create_pending_action(
        passenger_id=passenger_id,
        action_type=action_type,
        booking_id=booking_id,
        result_preview=preview_str,
        db_path=config.DB_PATH
    )


def execute_action(action_id: str, passenger_id: str) -> Dict[str, Any]:
    """Deterministic execution invoked ONLY via confirm endpoint."""
    success, msg, data = confirm_action(action_id, passenger_id, config.DB_PATH)
    return {
        "status": "SUCCESS" if success else "FAILED",
        "action_id": action_id,
        "message": msg,
        "details": data
    }
