import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app)
print("Sending GET /health...")
r = client.get("/health")
print("Response:", r.status_code, r.json())

print("Sending POST /chat...")
r2 = client.post("/chat", headers={"X-Passenger-Id": "PASS-001"}, json={"session_id": "test", "message": "Trains from Pune to Mumbai on 2026-12-05"})
print("Response:", r2.status_code, r2.json())
