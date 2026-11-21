import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx
from backend.server import app

async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        print("Health:", r.status_code, r.json())
        r2 = await client.post("/chat", headers={"X-Passenger-Id": "PASS-001"}, json={"session_id": "test", "message": "Trains from Pune to Mumbai on 2026-12-05"})
        print("Chat:", r2.status_code, r2.json()["answer_type"])

asyncio.run(main())
