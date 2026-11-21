import json
import sqlite3
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional, Union


def parse_datetime(val: Union[str, datetime]) -> datetime:
    if isinstance(val, datetime):
        return val
    cleaned = str(val).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(val), fmt)
            except ValueError:
                pass
        raise ValueError(f"Unable to parse datetime: {val}")


def _dict_row(cur: sqlite3.Cursor) -> Optional[dict[str, Any]]:
    row = cur.fetchone()
    if not row:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    col_names = [d[0] for d in cur.description]
    return dict(zip(col_names, row))


def _dict_rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], sqlite3.Row):
        return [dict(r) for r in rows]
    col_names = [d[0] for d in cur.description]
    return [dict(zip(col_names, r)) for r in rows]


def quote_cancellation(
    conn: sqlite3.Connection,
    passenger_id: str,
    booking_id: str,
    as_of: Union[str, datetime],
) -> dict[str, Any]:
    cur = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,))
    booking = _dict_row(cur)
    if not booking:
        raise ValueError(f"Booking '{booking_id}' not found.")

    if str(booking.get("passenger_id")).upper() != str(passenger_id).upper():
        raise PermissionError(f"Passenger '{passenger_id}' does not own booking '{booking_id}'.")

    current_status = str(booking.get("status", "")).lower()
    if current_status == "cancelled":
        raise ValueError(f"Booking '{booking_id}' is already cancelled.")

    train_id = booking.get("train_id") or booking.get("train_no")
    journey_date_val = booking.get("journey_date")
    amount_paid = float(booking.get("amount_paid", 0.0))
    boarding_station = booking.get("boarding_station") or booking.get("from_code")
    booking_class = booking.get("class") or booking.get("class_type") or "2AC"

    cur_stops_info = conn.execute("PRAGMA table_info(train_stops)")
    stop_cols = [c[1] for c in cur_stops_info.fetchall()]
    t_col = "train_no" if "train_no" in stop_cols else "train_id"
    seq_col = "stop_order" if "stop_order" in stop_cols else "stop_sequence"

    stop = None
    if boarding_station:
        cur_stops = conn.execute(
            f"SELECT departure, day_offset FROM train_stops WHERE {t_col} = ? AND station_code = ?",
            (train_id, boarding_station),
        )
        stop = _dict_row(cur_stops)

    if not stop:
        cur_stops = conn.execute(
            f"SELECT departure, day_offset FROM train_stops WHERE {t_col} = ? ORDER BY {seq_col} ASC LIMIT 1",
            (train_id,),
        )
        stop = _dict_row(cur_stops)

    if not stop:
        raise ValueError(f"No train stops found for train '{train_id}'.")

    departure_raw = stop.get("departure")
    day_offset = int(stop.get("day_offset") or 0)

    departure_str = str(departure_raw)
    if "-" in departure_str or "T" in departure_str:
        departure_dt = parse_datetime(departure_str)
    else:
        j_dt = parse_datetime(str(journey_date_val)).date()
        parts = departure_str.split(":")
        h = int(parts[0]) if parts[0].isdigit() else 0
        m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        s = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        departure_dt = datetime.combine(j_dt, time(h, m, s))

    if day_offset != 0:
        departure_dt += timedelta(days=day_offset)

    as_of_dt = parse_datetime(as_of)
    if as_of_dt.tzinfo is not None and departure_dt.tzinfo is None:
        departure_dt = departure_dt.replace(tzinfo=as_of_dt.tzinfo)
    elif as_of_dt.tzinfo is None and departure_dt.tzinfo is not None:
        as_of_dt = as_of_dt.replace(tzinfo=None)

    hours_before_departure = (departure_dt - as_of_dt).total_seconds() / 3600.0

    cur_settings_info = conn.execute("PRAGMA table_info(settings)")
    setting_cols = [c[1] for c in cur_settings_info.fetchall()]
    k_col = "name" if "name" in setting_cols else "key"

    cur_settings = conn.execute(f"SELECT {k_col} AS k, value, source_doc FROM settings")
    settings_rows = _dict_rows(cur_settings)
    settings_dict = {r["k"]: r for r in settings_rows}

    sources: list[dict[str, Any]] = []
    charge = 0.0

    if "cancellation_rules" in settings_dict:
        rule_entry = settings_dict["cancellation_rules"]
        rule_val = rule_entry.get("value")
        rule_source = rule_entry.get("source_doc") or "Ujjwal Rail Cancellation Rules"
        tiers = json.loads(rule_val) if isinstance(rule_val, str) else rule_val
        tiers = sorted(tiers, key=lambda x: float(x.get("min_hours", 0.0)), reverse=True)
        matched_tier = None
        for tier in tiers:
            if hours_before_departure >= float(tier.get("min_hours", 0.0)):
                matched_tier = tier
                break

        if matched_tier is not None:
            charge_type = matched_tier.get("charge_type", "percent")
            charge_val = float(matched_tier.get("charge_value", 0.0))
            tier_source = matched_tier.get("source_doc") or rule_source
            sources.append({"source_doc": tier_source, "min_hours": matched_tier.get("min_hours")})
            if charge_type in ("flat", "fixed"):
                charge = min(charge_val, amount_paid)
            elif charge_type in ("percent", "percentage"):
                charge = round(amount_paid * charge_val, 2)
            else:
                charge = min(charge_val, amount_paid)
        else:
            charge = amount_paid
            sources.append({"source_doc": rule_source, "min_hours": 0.0})

    elif any(k.startswith("cancel_charge_") for k in settings_dict):
        if hours_before_departure >= 48.0:
            key_name = f"cancel_charge_{booking_class}_over_48h"
            fee_row = settings_dict.get(key_name)
            flat_fee = float(fee_row["value"]) if fee_row else 200.0
            s_doc = (fee_row.get("source_doc") if fee_row else None) or "CIR-2026-01"
            sources.append({"source_doc": s_doc, "min_hours": 48.0})
            charge = min(flat_fee, amount_paid)
        elif 12.0 <= hours_before_departure < 48.0:
            pct_row = settings_dict.get("cancel_charge_pct_48h_to_12h")
            pct_val = float(pct_row["value"]) / 100.0 if pct_row and float(pct_row["value"]) > 1 else 0.25
            s_doc = (pct_row.get("source_doc") if pct_row else None) or "RUL-CAN-01"
            sources.append({"source_doc": s_doc, "min_hours": 12.0})
            charge = round(amount_paid * pct_val, 2)
        elif 4.0 <= hours_before_departure < 12.0:
            pct_row = settings_dict.get("cancel_charge_pct_12h_to_4h")
            pct_val = float(pct_row["value"]) / 100.0 if pct_row and float(pct_row["value"]) > 1 else 0.50
            s_doc = (pct_row.get("source_doc") if pct_row else None) or "RUL-CAN-01"
            sources.append({"source_doc": s_doc, "min_hours": 4.0})
            charge = round(amount_paid * pct_val, 2)
        else:
            charge = amount_paid
            sources.append({"source_doc": "RUL-CAN-01", "min_hours": 0.0})
    else:
        if hours_before_departure >= 4.0:
            charge = round(amount_paid * 0.50, 2)
            sources.append({"source_doc": "Ujjwal Rail Refund Policy", "cutoff_hours": 4.0})
        else:
            charge = amount_paid
            sources.append({"source_doc": "Ujjwal Rail Refund Policy", "cutoff_hours": 4.0})

    charge = round(min(charge, amount_paid), 2)
    refund = round(max(0.0, amount_paid - charge), 2)

    return {
        "booking_id": booking_id,
        "passenger_id": passenger_id,
        "amount_paid": amount_paid,
        "charge": charge,
        "refund": refund,
        "hours_before_departure": round(hours_before_departure, 4),
        "sources": sources,
    }


def create_pending_action(
    conn: sqlite3.Connection,
    passenger_id: str,
    booking_id: str,
    action_type: str,
    payload: Union[dict[str, Any], str],
    as_of: Union[str, datetime],
) -> dict[str, Any]:
    cur_settings_info = conn.execute("PRAGMA table_info(settings)")
    setting_cols = [c[1] for c in cur_settings_info.fetchall()]
    k_col = "name" if "name" in setting_cols else "key"

    cur = conn.execute(
        f"SELECT value FROM settings WHERE {k_col} IN ('action_ttl_minutes', 'action_expiry_minutes')"
    )
    setting_row = _dict_row(cur)
    expiry_minutes = int(float(setting_row["value"])) if setting_row else 10

    as_of_dt = parse_datetime(as_of)
    expires_at_dt = as_of_dt + timedelta(minutes=expiry_minutes)
    action_id = f"act_{uuid.uuid4().hex[:12]}"
    created_at_iso = as_of_dt.isoformat()
    expires_at_iso = expires_at_dt.isoformat()
    payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)

    cur_act_info = conn.execute("PRAGMA table_info(actions)")
    act_cols = [c[1] for c in cur_act_info.fetchall()]

    if "payload" in act_cols:
        conn.execute(
            "INSERT INTO actions (action_id, passenger_id, booking_id, action_type, payload, status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (action_id, passenger_id, booking_id, action_type, payload_str, created_at_iso, expires_at_iso),
        )
    else:
        conn.execute(
            "INSERT INTO actions (action_id, passenger_id, booking_id, action_type, status, created_at, expires_at, result) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
            (action_id, passenger_id, booking_id, action_type, created_at_iso, expires_at_iso, payload_str),
        )
    conn.commit()

    return {
        "action_id": action_id,
        "passenger_id": passenger_id,
        "booking_id": booking_id,
        "type": action_type,
        "action_type": action_type,
        "payload": payload if isinstance(payload, dict) else json.loads(payload_str),
        "status": "pending",
        "created_at": created_at_iso,
        "expires_at": expires_at_iso,
    }


def confirm_action(
    conn: sqlite3.Connection,
    passenger_id: str,
    action_id: str,
    as_of: Optional[Union[str, datetime]] = None,
) -> dict[str, Any]:
    cur = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,))
    action = _dict_row(cur)
    if not action:
        raise ValueError(f"Action '{action_id}' not found.")

    if str(action.get("passenger_id")).upper() != str(passenger_id).upper():
        raise PermissionError(f"Action '{action_id}' does not belong to passenger '{passenger_id}'.")

    status = str(action.get("status", "")).lower()
    booking_id = action.get("booking_id")
    action_type = action.get("action_type")
    payload = action.get("payload") or action.get("result")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    if status == "confirmed":
        cur_booking = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,))
        verified_booking = _dict_row(cur_booking)
        return {
            "action_id": action_id,
            "status": "confirmed",
            "booking_id": booking_id,
            "idempotent": True,
            "booking": verified_booking,
            "refund": payload.get("refund", 0.0),
            "message": "Action was already confirmed.",
        }

    if status == "cancelled":
        raise ValueError(f"Action '{action_id}' has already been cancelled.")
    if status == "expired":
        raise ValueError(f"Action '{action_id}' has expired.")

    if as_of is not None:
        as_of_dt = parse_datetime(as_of)
        expires_at_dt = parse_datetime(action.get("expires_at"))
        if as_of_dt.tzinfo is not None and expires_at_dt.tzinfo is None:
            expires_at_dt = expires_at_dt.replace(tzinfo=as_of_dt.tzinfo)
        elif as_of_dt.tzinfo is None and expires_at_dt.tzinfo is not None:
            as_of_dt = as_of_dt.replace(tzinfo=None)
        if as_of_dt > expires_at_dt:
            conn.execute("UPDATE actions SET status = 'expired' WHERE action_id = ?", (action_id,))
            conn.commit()
            raise ValueError(f"Action '{action_id}' has expired.")

    now_iso = (parse_datetime(as_of) if as_of else datetime.now(timezone.utc)).isoformat()

    cur_act_info = conn.execute("PRAGMA table_info(actions)")
    act_cols = [c[1] for c in cur_act_info.fetchall()]
    if "updated_at" in act_cols:
        conn.execute("UPDATE actions SET status = 'confirmed', updated_at = ? WHERE action_id = ?", (now_iso, action_id))
    else:
        conn.execute("UPDATE actions SET status = 'confirmed' WHERE action_id = ?", (action_id,))

    if action_type in ("cancel_booking", "cancellation"):
        refund = float(payload.get("refund", 0.0))
        cur_bk_info = conn.execute("PRAGMA table_info(bookings)")
        bk_cols = [c[1] for c in cur_bk_info.fetchall()]

        if "refund_amount" in bk_cols:
            conn.execute(
                "UPDATE bookings SET status = 'cancelled', refund_amount = ? WHERE booking_id = ?",
                (refund, booking_id),
            )
        else:
            conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))

        cur_s_info = conn.execute("PRAGMA table_info(seats)")
        seat_cols = [c[1] for c in cur_s_info.fetchall()]

        if "available_seats" in seat_cols:
            cur_b = conn.execute("SELECT train_id FROM bookings WHERE booking_id = ?", (booking_id,))
            b_row = cur_b.fetchone()
            if b_row:
                train_id = b_row[0]
                cur_t = conn.execute("SELECT count(*) FROM booking_travellers WHERE booking_id = ?", (booking_id,))
                t_row = cur_t.fetchone()
                seat_increment = t_row[0] if (t_row and t_row[0]) else 1
                conn.execute("UPDATE seats SET available_seats = available_seats + ? WHERE train_id = ?", (seat_increment, train_id))
        elif "available" in seat_cols:
            cur_b = conn.execute("SELECT train_no, journey_date, class FROM bookings WHERE booking_id = ?", (booking_id,))
            b_row = cur_b.fetchone()
            if b_row:
                conn.execute(
                    "UPDATE seats SET available = available + 1 WHERE train_no = ? AND journey_date = ? AND class = ?",
                    (b_row[0], b_row[1], b_row[2]),
                )

        if "status" in seat_cols and "booking_id" in seat_cols:
            conn.execute("UPDATE seats SET status = 'available', booking_id = NULL WHERE booking_id = ?", (booking_id,))

    conn.commit()

    cur_verify = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,))
    verified_booking = _dict_row(cur_verify)
    if not verified_booking or str(verified_booking.get("status")).lower() not in ("cancelled",):
        raise RuntimeError(f"Failed to verify cancelled status for booking '{booking_id}'.")

    return {
        "action_id": action_id,
        "status": "confirmed",
        "booking_id": booking_id,
        "idempotent": False,
        "booking": verified_booking,
        "refund": payload.get("refund", 0.0),
        "message": "Action successfully confirmed and state verified.",
    }


def cancel_action(
    conn: sqlite3.Connection,
    passenger_id: str,
    action_id: str,
) -> dict[str, Any]:
    cur = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,))
    action = _dict_row(cur)
    if not action:
        raise ValueError(f"Action '{action_id}' not found.")

    if str(action.get("passenger_id")).upper() != str(passenger_id).upper():
        raise PermissionError(f"Action '{action_id}' does not belong to passenger '{passenger_id}'.")

    if str(action.get("status")).lower() == "confirmed":
        raise ValueError(f"Cannot cancel action '{action_id}' as it has already been confirmed.")

    conn.execute("UPDATE actions SET status = 'cancelled' WHERE action_id = ?", (action_id,))
    conn.commit()

    return {
        "action_id": action_id,
        "status": "cancelled",
        "booking_id": action.get("booking_id"),
        "message": f"Pending action '{action_id}' marked as cancelled without modifying booking.",
    }
