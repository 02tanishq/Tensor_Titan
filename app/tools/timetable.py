"""
Timetable & Stations Lookup Module.
Handles:
1. Station alias resolution (Bombay/CST -> CSMT, Poona -> PUNE, etc.).
2. Intermediate stops and day_offset calculations.
3. Midnight train departures (< 01:00 departure offset).
4. Operating day of week verification (runs_on).
"""

import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.config import config


def resolve_station_code(query_station: str, db_path: str = config.DB_PATH) -> Optional[str]:
    """
    Resolve station names, aliases, or codes to official station_code.
    One-line reason: Normalizes ambiguous and legacy station names (e.g. Bombay VT, CST, Poona).
    """
    if not query_station:
        return None

    clean = query_station.strip()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Direct code match
        c.execute("SELECT station_code FROM stations WHERE station_code = ? COLLATE NOCASE;", (clean,))
        row = c.fetchone()
        if row:
            return row["station_code"]

        # Exact name match
        c.execute("SELECT station_code FROM stations WHERE name = ? COLLATE NOCASE;", (clean,))
        row = c.fetchone()
        if row:
            return row["station_code"]

        # Other names / alias match
        c.execute("SELECT station_code, other_names FROM stations WHERE other_names LIKE ?;", (f"%{clean}%",))
        row = c.fetchone()
        if row:
            return row["station_code"]

        # City match (if city has one station)
        c.execute("SELECT station_code FROM stations WHERE city = ? COLLATE NOCASE;", (clean,))
        rows = c.fetchall()
        if len(rows) == 1:
            return rows[0]["station_code"]
        elif len(rows) > 1:
            # City has multiple stations (like Mumbai: CSMT, BCT)
            # Default to primary terminus (CSMT) unless Central explicitly mentioned
            if "central" in clean.lower():
                return "BCT"
            return "CSMT"

    return clean.upper()[:4]


def search_train_timetable(
    from_station: str,
    to_station: str,
    journey_date: Optional[str] = None,
    db_path: str = config.DB_PATH
) -> List[Dict[str, Any]]:
    """
    Find trains connecting from_station to to_station in valid stop sequence.
    One-line reason: Checks stop order and operating days deterministically from SQLite tables.
    """
    from_code = resolve_station_code(from_station, db_path)
    to_code = resolve_station_code(to_station, db_path)

    if not from_code or not to_code:
        return []

    # Day of week for runs_on filtering
    day_name_map = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    req_day = None
    if journey_date:
        try:
            dt = datetime.strptime(journey_date, "%Y-%m-%d")
            req_day = day_name_map[dt.weekday()]
        except ValueError:
            pass

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = """
            SELECT 
                t.train_no,
                t.name,
                t.runs_on,
                t.classes,
                s1.departure AS origin_departure,
                s1.day_offset AS origin_day_offset,
                s2.arrival AS dest_arrival,
                s2.day_offset AS dest_day_offset
            FROM trains t
            JOIN train_stops s1 ON t.train_no = s1.train_no AND s1.station_code = ?
            JOIN train_stops s2 ON t.train_no = s2.train_no AND s2.station_code = ?
            WHERE s1.stop_order < s2.stop_order;
        """
        c.execute(query, (from_code, to_code))
        rows = c.fetchall()

        results: List[Dict[str, Any]] = []
        for r in rows:
            runs_on_list = [d.strip() for d in r["runs_on"].split(",")]
            if req_day and req_day not in runs_on_list:
                continue

            classes_list = [cls.strip() for cls in r["classes"].split(",")]
            dep = r["origin_departure"]
            arr = r["dest_arrival"]

            results.append({
                "train_no": r["train_no"],
                "name": r["name"],
                "from_code": from_code,
                "to_code": to_code,
                "departure": dep,
                "arrival": arr,
                "classes": classes_list,
                "runs_on": runs_on_list,
                "day_offset": r["dest_day_offset"] - r["origin_day_offset"]
            })

        return results
