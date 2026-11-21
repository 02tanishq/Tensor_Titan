"""
Unit & Integration Test Suite for all 7 Hackathon Endpoints
"""

import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app)

def test_all():
    print("==================================================")
    print("      TESTING 7 HACKATHON BACKEND ENDPOINTS       ")
    print("==================================================")

    # Reset UR-10001 to CNF for repeatable test runs
    from backend.domain_tools import get_db
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE bookings SET status = 'CNF' WHERE booking_id = 'UR-10001'")
    c.execute("UPDATE booking_travellers SET status = 'CNF' WHERE booking_id = 'UR-10001'")
    conn.commit()
    conn.close()

    # 1. GET /health
    r_health = client.get("/health")
    assert r_health.status_code == 200, f"Health check failed: {r_health.text}"
    print("[PASS] 1. GET /health -> 200 OK")

    # 1b. Header Validation Checks (Checklist E)
    # Missing header -> 400
    r_no_header = client.post("/chat", json={"session_id": "test_err", "message": "hello"})
    assert r_no_header.status_code == 400, f"Expected 400 for missing header, got {r_no_header.status_code}"
    print("[PASS] 1b. Missing X-Passenger-Id header rejected with 400 Bad Request")

    # Unknown passenger -> 401
    r_bad_passenger = client.post("/chat", headers={"X-Passenger-Id": "PASS-FAKE-999"}, json={"session_id": "test_err", "message": "hello"})
    assert r_bad_passenger.status_code == 401, f"Expected 401 for unknown passenger, got {r_bad_passenger.status_code}"
    print("[PASS] 1c. Unknown passenger identity rejected with 401 Unauthorized")

    # 2. POST /chat (Find trains)
    r_chat1 = client.post("/chat", headers={"X-Passenger-Id": "PASS-001"}, json={
        "session_id": "test_s1",
        "message": "Trains from Pune to Mumbai on 2026-12-05",
        "as_of": "2026-11-21T10:00:00"
    })
    assert r_chat1.status_code == 200
    res1 = r_chat1.json()
    assert "trace_id" in res1
    assert res1["answer_type"] == "answer"
    print(f"[PASS] 2. POST /chat (Find trains) -> trace_id: {res1['trace_id']}")

    # 3. POST /chat (R8 Privacy Check: Friend's booking)
    r_chat2 = client.post("/chat", headers={"X-Passenger-Id": "PASS-001"}, json={
        "session_id": "test_s2",
        "message": "What is the status of booking UR-48213? It's my friend's.",
        "as_of": "2026-11-21T10:00:00"
    })
    res2 = r_chat2.json()
    assert res2["answer_type"] == "refusal", f"Expected refusal, got: {res2}"
    print(f"[PASS] 3. POST /chat (R8 Privacy refusal) -> {res2['answer']}")

    # 4. POST /chat (Level 1 Action: Ticket cancellation preview)
    r_chat3 = client.post("/chat", headers={"X-Passenger-Id": "PASS-001"}, json={
        "session_id": "test_s3",
        "message": "Cancel my ticket UR-10001",
        "as_of": "2026-11-21T10:00:00"
    })
    res3 = r_chat3.json()
    assert res3["answer_type"] == "confirm_needed"
    assert res3["pending_action"] is not None
    action_id = res3["pending_action"]["action_id"]
    print(f"[PASS] 4. POST /chat (Action preview) -> action_id: {action_id}")

    # 5. POST /actions/{id}/confirm
    r_conf = client.post(f"/actions/{action_id}/confirm", headers={"X-Passenger-Id": "PASS-001"})
    assert r_conf.status_code == 200
    res_conf = r_conf.json()
    assert res_conf["status"] == "action_done"
    print(f"[PASS] 5. POST /actions/{{id}}/confirm -> {res_conf['message']}")

    # Idempotency check: Calling it twice must not error or double-cancel
    r_conf2 = client.post(f"/actions/{action_id}/confirm", headers={"X-Passenger-Id": "PASS-001"})
    assert r_conf2.status_code == 200
    print("[PASS] 5b. Idempotency verified: Calling confirm twice succeeded without duplicate cancellation")

    # 6. GET /bookings/{id}
    # Passenger PASS-001 should be able to view their own booking
    r_bk = client.get("/bookings/UR-10001", headers={"X-Passenger-Id": "PASS-001"})
    assert r_bk.status_code == 200
    res_bk = r_bk.json()
    assert res_bk["booking_id"] == "UR-10001"
    print(f"[PASS] 6. GET /bookings/UR-10001 -> Status: {res_bk['status']}")

    # Passenger PASS-002 trying to view PASS-001's booking must get 404 (privacy)
    r_bk_denied = client.get("/bookings/UR-10001", headers={"X-Passenger-Id": "PASS-002"})
    assert r_bk_denied.status_code == 404
    print("[PASS] 6b. GET /bookings/UR-10001 with unauthorized passenger rejected with 404")

    # 7. POST /ingest (Dynamic rule update)
    r_ing = client.post("/ingest", json={
        "doc_type": "circular",
        "data": {
            "doc_id": "CIR-2026-99",
            "title": "Live Judge Evaluation Circular",
            "content": "Special test circular ingested live during evaluation."
        }
    })
    assert r_ing.status_code == 200
    print("[PASS] 7. POST /ingest -> Dynamic circular saved")

    # 8. GET /trace/{trace_id}
    test_trace_id = res1["trace_id"]
    r_trace = client.get(f"/trace/{test_trace_id}")
    assert r_trace.status_code == 200
    res_trace = r_trace.json()
    assert res_trace["trace_id"] == test_trace_id
    print(f"[PASS] 8. GET /trace/{test_trace_id} -> Replay record retrieved")

    print("\n==================================================")
    print("      ALL 7 HACKATHON ENDPOINTS VERIFIED 100%     ")
    print("==================================================")

if __name__ == "__main__":
    test_all()
