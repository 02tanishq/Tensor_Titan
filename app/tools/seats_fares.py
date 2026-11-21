"""
Seat Availability & Fare Lookup Module.
Performs read-only lookups strictly against the seats and fares SQLite tables.
Zero arithmetic or invention permitted.
"""

import sqlite3
from typing import Dict, Any, List, Optional
from app.config import config


def get_seat_availability(
    train_no: str,
    journey_date: str,
    class_type: Optional[str] = None,
    db_path: str = config.DB_PATH
) -> List[Dict[str, Any]]:
    """
    Look up 14-day availability from seats table for a train and journey date.
    One-line reason: Reads deterministic availability records directly from database.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if class_type:
            c.execute("""
                SELECT train_no, journey_date, class, available, rac, waitlist
                FROM seats
                WHERE train_no = ? AND journey_date = ? AND class = ?;
            """, (train_no, journey_date, class_type.upper()))
        else:
            c.execute("""
                SELECT train_no, journey_date, class, available, rac, waitlist
                FROM seats
                WHERE train_no = ? AND journey_date = ?
                ORDER BY class;
            """, (train_no, journey_date))

        rows = c.fetchall()
        return [dict(r) for r in rows]


def get_fare(
    train_no: str,
    from_code: str,
    to_code: str,
    class_type: str,
    db_path: str = config.DB_PATH
) -> Optional[float]:
    """
    Fetch authoritative fare from fares table for a station pair and class.
    One-line reason: Prohibits dynamic price invention by reading static fares table.
    """
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT fare 
            FROM fares 
            WHERE train_no = ? AND from_code = ? AND to_code = ? AND class = ?;
        """, (train_no, from_code.upper(), to_code.upper(), class_type.upper()))
        row = c.fetchone()
        if row:
            return float(row[0])
    return None
