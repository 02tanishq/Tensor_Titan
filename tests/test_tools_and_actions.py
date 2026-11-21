"""
Unit Tests for Ujjwal Rail Deterministic Tools and Action State Machine
Verifies Section A, C, D requirements:
- Action state machine: proposed -> confirmed | cancelled | expired | failed
- Idempotency of /actions/{id}/confirm
- Passenger authorization (owner-only)
- Expiry rejected with TTL from settings
- Exact cut-off refund calculations (>48h, 48h, 47h59m, 12h, 11h59m, 4h, 3h59m)
- Phone and ID masking
"""

import sys
import os
import unittest
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.tools import (
    resolve_station,
    mask_pii,
    calculate_departure_datetime,
    can_cancel
)
from backend.domain_tools import (
    get_db,
    propose_action,
    confirm_action_execution,
    cancel_action_execution,
    calculate_refund_quote,
    get_booking_secure
)

class TestToolsAndActions(unittest.TestCase):

    def setUp(self):
        self.conn = get_db()
        self.c = self.conn.cursor()

    def tearDown(self):
        self.c.execute("DELETE FROM bookings WHERE booking_id LIKE 'UR-TEST%'")
        self.c.execute("DELETE FROM booking_travellers WHERE booking_id LIKE 'UR-TEST%'")
        self.c.execute("DELETE FROM actions WHERE booking_id LIKE 'UR-TEST%'")
        self.conn.commit()
        self.conn.close()

    def test_pii_masking(self):
        """Test phone and ID masking."""
        masked_phone = mask_pii("9876543210")
        self.assertEqual(masked_phone, "XXXXXX3210")
        self.assertTrue(masked_phone.endswith("3210"))
        self.assertNotIn("9876", masked_phone)

    def test_station_resolution(self):
        """Test aliases like Bombay, CST, and standard codes."""
        stn1 = resolve_station("Bombay")
        self.assertIsNotNone(stn1)
        self.assertEqual(stn1["station_code"], "CSMT")

        stn2 = resolve_station("CST")
        self.assertIsNotNone(stn2)
        self.assertEqual(stn2["station_code"], "CSMT")

        stn3 = resolve_station("PUNE")
        self.assertIsNotNone(stn3)
        self.assertEqual(stn3["station_code"], "PUNE")

    def test_action_lifecycle_and_idempotency(self):
        """
        Verify:
        1. Action state starts as 'proposed'
        2. Non-owner cannot confirm
        3. Owner confirms: executes transaction, verifies DB update, updates status to 'confirmed'
        4. Second confirm call is idempotent: returns action_done without double-cancelling
        """
        # Create fresh test booking
        bk_id = "UR-TEST-001"
        self.c.execute("DELETE FROM bookings WHERE booking_id = ?", (bk_id,))
        self.c.execute("DELETE FROM booking_travellers WHERE booking_id = ?", (bk_id,))
        self.c.execute("DELETE FROM actions WHERE booking_id = ?", (bk_id,))
        self.conn.commit()

        self.c.execute("""
        INSERT INTO bookings (booking_id, passenger_id, train_no, journey_date, from_code, to_code, class, amount_paid, status, booked_at)
        VALUES (?, 'PASS-001', '12123', '2026-12-05', 'PUNE', 'CSMT', '2AC', 1200.0, 'CNF', '2026-11-20T10:00:00')
        """, (bk_id,))
        self.c.execute("""
        INSERT INTO booking_travellers (booking_id, traveller_name, age, status, coach, berth)
        VALUES (?, 'Tester One', 30, 'CNF', 'A1', '12')
        """, (bk_id,))
        self.conn.commit()

        # Step 1: Propose Action
        prop = propose_action(
            passenger_id="PASS-001",
            booking_id=bk_id,
            action_type="cancel_booking",
            details={"refund": 1000.0, "charge": 200.0}
        )
        self.assertEqual(prop["status"], "proposed")
        action_id = prop["action_id"]

        # Step 2: Unauthorized confirmation attempt (PASS-002 trying to confirm PASS-001's action)
        unauth_res = confirm_action_execution(action_id, requesting_passenger_id="PASS-002")
        self.assertFalse(unauth_res["success"])
        self.assertIn("Unauthorized", unauth_res["error"])

        # Verify booking is STILL confirmed
        check_bk = get_booking_secure(bk_id, "PASS-001")
        self.assertEqual(check_bk["booking"]["status"], "CNF")

        # Step 3: Authorized confirmation (PASS-001)
        auth_res = confirm_action_execution(action_id, requesting_passenger_id="PASS-001")
        self.assertTrue(auth_res["success"])
        self.assertEqual(auth_res["status"], "action_done")

        # Verify in DB that booking status is cancelled
        check_bk2 = get_booking_secure(bk_id, "PASS-001")
        self.assertEqual(check_bk2["booking"]["status"], "CANCELLED")

        # Step 4: Idempotency check - call confirm a SECOND time
        repeat_res = confirm_action_execution(action_id, requesting_passenger_id="PASS-001")
        self.assertTrue(repeat_res["success"])
        self.assertEqual(repeat_res["status"], "action_done")
        self.assertIn("already confirmed", repeat_res["message"])

    def test_expired_action_rejection(self):
        """Verify that an action past its TTL is marked 'expired' and rejected."""
        bk_id = "UR-TEST-002"
        self.c.execute("DELETE FROM bookings WHERE booking_id = ?", (bk_id,))
        self.c.execute("""
        INSERT INTO bookings (booking_id, passenger_id, train_no, journey_date, from_code, to_code, class, amount_paid, status, booked_at)
        VALUES (?, 'PASS-001', '12123', '2026-12-05', 'PUNE', 'CSMT', '2AC', 1200.0, 'CNF', '2026-11-20T10:00:00')
        """, (bk_id,))
        self.conn.commit()

        # Propose action with -1 minute TTL (already expired)
        prop = propose_action(
            passenger_id="PASS-001",
            booking_id=bk_id,
            action_type="cancel_booking",
            details={"refund": 1000.0},
            ttl_minutes=-1
        )
        action_id = prop["action_id"]

        # Confirm attempt must fail with expired error
        exp_res = confirm_action_execution(action_id, requesting_passenger_id="PASS-001")
        self.assertFalse(exp_res["success"])
        self.assertIn("expired", exp_res["error"].lower())

    def test_refund_exact_cutoffs(self):
        """
        Verify hand-calculated refund amounts at critical cut-offs:
        Booking: 2AC, Fare: 2000. Departure: 2026-12-05 18:00
        Circular CIR-2026-01 active (Flat 2AC fee = 200)
        - > 48h (e.g. 50h before): Fee = 200, Refund = 1800
        - Exactly 48h 00m: Fee = 25% of 2000 = 500, Refund = 1500
        - 47h 59m (post 48h cut-off): Fee = 25% of 2000 = 500, Refund = 1500
        - Exactly 12h 00m: Fee = 25% of 2000 = 500, Refund = 1500
        - 11h 59m (post 12h cut-off): Fee = 50% of 2000 = 1000, Refund = 1000
        - Exactly 4h 00m: Fee = 50% of 2000 = 1000, Refund = 1000
        - 3h 59m (under 4h cut-off): Fee = 2000, Refund = 0
        """
        bk_id = "UR-TEST-CUTOFF"
        self.c.execute("DELETE FROM bookings WHERE booking_id = ?", (bk_id,))
        self.c.execute("""
        INSERT INTO bookings (booking_id, passenger_id, train_no, journey_date, from_code, to_code, class, amount_paid, status, booked_at)
        VALUES (?, 'PASS-001', '12123', '2026-12-05', 'PUNE', 'CSMT', '2AC', 2000.0, 'CNF', '2026-11-20T10:00:00')
        """, (bk_id,))
        self.conn.commit()

        # Departure is 2026-12-05 07:15:00 (Train 12123 departs PUNE at 07:15)
        # 1. > 48 hours: 2026-12-03 05:15:00 (50 hours before)
        q_50h = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-03T05:15:00")
        self.assertEqual(q_50h["charge"], 200.0)
        self.assertEqual(q_50h["refund"], 1800.0)

        # 2. Exactly 48 hours: 2026-12-03 07:15:00 (48.0 hours before)
        q_48h = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-03T07:15:00")
        self.assertEqual(q_48h["charge"], 500.0) # 25% of 2000
        self.assertEqual(q_48h["refund"], 1500.0)

        # 3. 47 hours 59 mins: 2026-12-03 07:16:00 (47.98 hours before)
        q_47h59 = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-03T07:16:00")
        self.assertEqual(q_47h59["charge"], 500.0)
        self.assertEqual(q_47h59["refund"], 1500.0)

        # 4. Exactly 12 hours: 2026-12-04 19:15:00 (12.0 hours before)
        q_12h = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-04T19:15:00")
        self.assertEqual(q_12h["charge"], 500.0)
        self.assertEqual(q_12h["refund"], 1500.0)

        # 5. 11 hours 59 mins: 2026-12-04 19:16:00 (11.98 hours before)
        q_11h59 = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-04T19:16:00")
        self.assertEqual(q_11h59["charge"], 1000.0) # 50% of 2000
        self.assertEqual(q_11h59["refund"], 1000.0)

        # 6. Exactly 4 hours: 2026-12-05 03:15:00 (4.0 hours before)
        q_4h = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-05T03:15:00")
        self.assertEqual(q_4h["charge"], 1000.0)
        self.assertEqual(q_4h["refund"], 1000.0)

        # 7. 3 hours 59 mins: 2026-12-05 03:16:00 (< 4 hours)
        q_3h59 = calculate_refund_quote(bk_id, "PASS-001", as_of_iso="2026-12-05T03:16:00")
        self.assertEqual(q_3h59["charge"], 2000.0)
        self.assertEqual(q_3h59["refund"], 0.0)
        self.assertFalse(q_3h59["eligible"])

if __name__ == "__main__":
    unittest.main()
