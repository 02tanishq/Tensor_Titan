"""
Session Memory Manager.
Maintains in-memory conversation state keyed by session_id:
- Known route/date/class/booking slots
- Clarification counter (max 2 in a row before hand-off)
- Queued change requests when a pending action is already active
"""

from typing import Dict, Optional
from app.models import SessionState, Slots, SubRequest

_SESSIONS: Dict[str, SessionState] = {}


def get_or_create_session(session_id: str, passenger_id: str, language: str = "en") -> SessionState:
    """Retrieve existing session state or initialize a fresh one."""
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = SessionState(
            session_id=session_id,
            passenger_id=passenger_id,
            preferred_language=language
        )
    return _SESSIONS[session_id]


def update_session_slots(session: SessionState, new_slots: Slots) -> None:
    """Merge new extracted slots into session memory without overwriting existing valid ones with None."""
    for field in ["from_stn", "to_stn", "date", "time_pref", "cls", "booking_id"]:
        new_val = getattr(new_slots, field)
        if new_val:
            setattr(session.slots, field, new_val)


def reset_clarification_count(session: SessionState) -> None:
    session.clarification_count = 0
    session.last_clarification_slot = None


def increment_clarification_count(session: SessionState, slot_name: str) -> int:
    session.clarification_count += 1
    session.last_clarification_slot = slot_name
    return session.clarification_count


def clear_session(session_id: str) -> None:
    """Remove session from memory (useful for testing)."""
    if session_id in _SESSIONS:
        del _SESSIONS[session_id]
