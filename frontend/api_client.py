"""
Ujjwal Rail API Client
Wrapper for the 7 official hackathon endpoints exposed by FastAPI backend.
"""

import requests
from typing import Dict, Any, Optional

DEFAULT_BACKEND_URL = "http://localhost:8000"

class UjjwalRailClient:
    def __init__(self, base_url: str = DEFAULT_BACKEND_URL):
        self.base_url = base_url.rstrip("/")

    def check_health(self) -> Dict[str, Any]:
        """GET /health"""
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            return {"online": r.status_code == 200, "data": r.json() if r.status_code == 200 else {}}
        except Exception as e:
            return {"online": False, "error": str(e)}

    def send_chat(self, passenger_id: str, session_id: str, message: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        """POST /chat"""
        headers = {"X-Passenger-Id": passenger_id}
        payload = {"session_id": session_id, "message": message}
        if as_of:
            payload["as_of"] = as_of
        try:
            r = requests.post(f"{self.base_url}/chat", headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": f"Failed to connect to backend: {str(e)}"}

    def confirm_action(self, action_id: str, passenger_id: str) -> Dict[str, Any]:
        """POST /actions/{id}/confirm"""
        headers = {"X-Passenger-Id": passenger_id}
        try:
            r = requests.post(f"{self.base_url}/actions/{action_id}/confirm", headers=headers, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_action(self, action_id: str, passenger_id: str) -> Dict[str, Any]:
        """POST /actions/{id}/cancel"""
        headers = {"X-Passenger-Id": passenger_id}
        try:
            r = requests.post(f"{self.base_url}/actions/{action_id}/cancel", headers=headers, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_booking(self, booking_id: str, passenger_id: str) -> Dict[str, Any]:
        """GET /bookings/{id}"""
        headers = {"X-Passenger-Id": passenger_id}
        try:
            r = requests.get(f"{self.base_url}/bookings/{booking_id}", headers=headers, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def ingest_document(self, doc_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /ingest"""
        try:
            r = requests.post(f"{self.base_url}/ingest", json={"doc_type": doc_type, "data": data}, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """GET /trace/{trace_id}"""
        try:
            r = requests.get(f"{self.base_url}/trace/{trace_id}", timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_rules(self, as_of: Optional[str] = None) -> Dict[str, Any]:
        """GET /rules"""
        try:
            params = {"as_of": as_of} if as_of else {}
            r = requests.get(f"{self.base_url}/rules", params=params, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_rule_detail(self, doc_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        """GET /rules/{doc_id}"""
        try:
            params = {"as_of": as_of} if as_of else {}
            r = requests.get(f"{self.base_url}/rules/{doc_id}", params=params, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def adjust_rule(self, circular_id: str, base_rule_id: str, title: str, amendment_content: str, effective_date: str, numeric_settings: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """POST /rules/adjust"""
        try:
            payload = {
                "circular_id": circular_id,
                "base_rule_id": base_rule_id,
                "title": title,
                "amendment_content": amendment_content,
                "effective_date": effective_date,
                "numeric_settings": numeric_settings
            }
            r = requests.post(f"{self.base_url}/rules/adjust", json=payload, timeout=5)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}
