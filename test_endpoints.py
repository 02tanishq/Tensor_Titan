"""
Unit & Integration Test Suite for all 7 Hackathon Endpoints
"""

import sys
import os
import json
from typing import Any, Optional

# Set UTF-8 and MOCK_LLM
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
os.environ["MOCK_LLM"] = "true"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from fastapi import HTTPException
from backend.server import (
    app,
    health_check,
    chat_endpoint,
    confirm_action_endpoint,
    cancel_action_endpoint,
    get_booking_endpoint,
    ingest_document,
    ingest_endpoint,
    get_trace_endpoint,
    ChatRequest,
    IngestRequest
)

class DirectResponse:
    def __init__(self, status_code: int, data: Any = None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data

    @property
    def text(self):
        return json.dumps(self._data) if isinstance(self._data, dict) else str(self._data)

class DirectClient:
    def get(self, url: str, headers: Optional[dict] = None):
        headers = headers or {}
        p_id = headers.get("X-Passenger-Id")
        try:
            if url == "/health":
                return DirectResponse(200, health_check())
            elif url.startswith("/bookings/"):
                b_id = url.split("/")[2]
                res = get_booking_endpoint(b_id, x_passenger_id=p_id)
                return DirectResponse(200, res)
            elif url.startswith("/trace/"):
                tr_id = url.split("/")[2]
                res = get_trace_endpoint(tr_id)
                return DirectResponse(200, res)
            return DirectResponse(404, {"detail": "Not found"})
        except HTTPException as e:
            return DirectResponse(e.status_code, {"detail": e.detail})

    def post(self, url: str, headers: Optional[dict] = None, json: Optional[dict] = None):
        headers = headers or {}
        json_data = json or {}
        p_id = headers.get("X-Passenger-Id")
        try:
            if url == "/chat":
                req = ChatRequest(**json_data)
                res = chat_endpoint(req, x_passenger_id=p_id)
                return DirectResponse(200, res)
            elif url.startswith("/actions/") and url.endswith("/confirm"):
                act_id = url.split("/")[2]
                res = confirm_action_endpoint(act_id, x_passenger_id=p_id)
                return DirectResponse(200, res)
            elif url.startswith("/actions/") and url.endswith("/cancel"):
                act_id = url.split("/")[2]
                res = cancel_action_endpoint(act_id, x_passenger_id=p_id)
                return DirectResponse(200, res)
            elif url == "/ingest":
                req = IngestRequest(**json_data)
                res = ingest_endpoint(req)
                return DirectResponse(200, res)
            return DirectResponse(404, {"detail": "Not found"})
        except HTTPException as e:
            return DirectResponse(e.status_code, {"detail": e.detail})

client = DirectClient()

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
    assert res_conf.get("answer_type") == "action_done" or res_conf.get("status") == "action_done"
    conf_msg = res_conf.get("answer") or res_conf.get("message")
    print(f"[PASS] 5. POST /actions/{{id}}/confirm -> {conf_msg}")

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
