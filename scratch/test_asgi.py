import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from backend.server import app

print("Creating ASGITransport...")
transport = httpx.ASGITransport(app=app)
print("Creating client...")
with httpx.Client(transport=transport, base_url="http://test") as client:
    print("Calling /health...")
    r = client.get("/health")
    print("Health response:", r.status_code, r.json())
    print("Calling /chat...")
    r2 = client.post("/chat", headers={"X-Passenger-Id": "PASS-001"}, json={"session_id": "test", "message": "Trains from Pune to Mumbai on 2026-12-05"})
    print("Chat response:", r2.status_code, r2.json()["answer_type"])
