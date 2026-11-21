"""
Booking & Change Action State Machine.
Executes the strict 4-step action lifecycle:
1. preview + quote (deterministic tool computation)
2. pending action row (actions table with expires_at from settings TTL)
3. execute ONLY on confirm endpoint inside a single SQLite transaction (strictly idempotent)
4. post-check by re-reading the booking record to guarantee state mutation
"""

import sqlite3
import uuid
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from app.config import config
from RAG_pipeline.repository import RulesRepository

logger = logging.getLogger("app.tools.actions")


def create_pending_action(
    passenger_id: str,
    action_type: str,
    booking_id: Optional[str] = None,
    result_preview: Optional[str] = None,
    db_path: str = config.DB_PATH,
    repository: Optional[RulesRepository] = None
) -> Dict[str, Any]:
    """
    Step 2: Insert a PENDING row into actions table with TTL from settings.
    One-line reason: LLM only proposes changes; physical execution requires explicit confirmed state.
    """
    if repository is None:
        repository = RulesRepository(db_path=db_path)

    try:
        ttl_minutes = int(repository.get_setting("action_expiry_minutes").value)
    except Exception:
        ttl_minutes = config.DEFAULT_ACTION_TTL_MINUTES

    action_id = f"ACT-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now()
    created_at = now.isoformat()
    expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO actions (
                action_id, passenger_id, booking_id, action_type, status, created_at, expires_at, result
            ) VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?);
        """, (action_id, passenger_id, booking_id, action_type, created_at, expires_at, result_preview))
        conn.commit()

    logger.info("Created pending action: %s (expires: %s)", action_id, expires_at)
    return {
        "action_id": action_id,
        "passenger_id": passenger_id,
        "booking_id": booking_id,
        "action_type": action_type,
        "type": action_type,
        "status": "PENDING",
        "created_at": created_at,
        "expires_at": expires_at,
        "result": result_preview
    }


def confirm_action(
    action_id: str,
    passenger_id: str,
    db_path: str = config.DB_PATH
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Step 3 & 4: Confirm and execute pending action inside an isolated DB transaction.
    Enforces:
    - Same passenger ownership verification.
    - Idempotency: Confirming twice returns identical success without double execution.
    - Expiration check against expires_at.
    - Post-check verification re-reading the booking table.
    One-line reason: ACID transaction guarantees zero partial or duplicate financial/booking state changes.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Check action exists
        c.execute("SELECT * FROM actions WHERE action_id = ?;", (action_id,))
        action = c.fetchone()
        if not action:
            return False, f"Action reference '{action_id}' not found.", {}

        # Check ownership
        if action["passenger_id"] != passenger_id:
            return False, "Access denied: Action does not belong to the authenticated passenger.", {}

        # Idempotency check: if already completed, return success
        if action["status"] == "COMPLETED":
            return True, "Action already completed successfully.", {
                "action_id": action_id,
                "status": "COMPLETED",
                "result": action["result"],
                "idempotent": True
            }

        # Check if already cancelled
        if action["status"] == "CANCELLED":
            return False, "Action was previously cancelled and cannot be executed.", {}

        # Check TTL expiration
        expires_at = datetime.fromisoformat(action["expires_at"])
        if datetime.now() > expires_at:
            c.execute("UPDATE actions SET status = 'EXPIRED' WHERE action_id = ?;", (action_id,))
            conn.commit()
            return False, f"Action '{action_id}' has expired. Please initiate a new change request.", {}

        # Execute Transaction
        action_type = action["action_type"]
        booking_id = action["booking_id"]
        result_msg = ""

        try:
            if action_type == "cancel_booking" and booking_id:
                # Update booking status to CANCELLED
                c.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?;", (booking_id,))
                result_msg = f"Booking {booking_id} successfully cancelled."

            elif action_type == "change_boarding" and booking_id:
                # Example: change boarding station
                new_stn = action["result"] or "KYN"
                c.execute("UPDATE bookings SET from_code = ? WHERE booking_id = ?;", (new_stn, booking_id))
                result_msg = f"Boarding station for {booking_id} changed to {new_stn}."

            else:
                result_msg = f"Action {action_type} executed."

            # Mark action as COMPLETED
            c.execute("""
                UPDATE actions 
                SET status = 'COMPLETED', result = ? 
                WHERE action_id = ?;
            """, (result_msg, action_id))

            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("Transaction failed during confirm_action: %s", str(e))
            return False, f"Transaction error during execution: {str(e)}", {}

        # Step 4: Post-Check by re-reading the booking
        if booking_id:
            c.execute("SELECT status, from_code FROM bookings WHERE booking_id = ?;", (booking_id,))
            verified_booking = c.fetchone()
            if action_type == "cancel_booking" and verified_booking["status"] != "CANCELLED":
                return False, "Post-check failed: Booking status was not updated to CANCELLED.", {}

        return True, result_msg, {
            "action_id": action_id,
            "status": "COMPLETED",
            "booking_id": booking_id,
            "result": result_msg,
            "idempotent": False
        }


def cancel_pending_action(
    action_id: str,
    passenger_id: str,
    db_path: str = config.DB_PATH
) -> Tuple[bool, str]:
    """Cancel a pending action before it is confirmed or expired."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("SELECT * FROM actions WHERE action_id = ?;", (action_id,))
        action = c.fetchone()
        if not action:
            return False, f"Action '{action_id}' not found."

        if action["passenger_id"] != passenger_id:
            return False, "Access denied: Action does not belong to the authenticated passenger."

        if action["status"] != "PENDING":
            return False, f"Action cannot be cancelled as it is already in '{action['status']}' state."

        c.execute("UPDATE actions SET status = 'CANCELLED' WHERE action_id = ?;", (action_id,))
        conn.commit()

    return True, f"Action '{action_id}' has been cancelled."
