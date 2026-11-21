"""
Ujjwal Rail Official FastAPI Service
Implements the 7 exact hackathon endpoints from Section 6 of the Participant Guide.
"""

import os
import sys
from typing import Optional, Dict, Any
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime

# Ensure project root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.domain_tools import (
    get_booking_secure,
    confirm_action_execution,
    cancel_action_execution,
    ingest_document,
    get_audit_trace
)
from backend.agent_hook import handle_chat_query

app = FastAPI(
    title="Ujjwal Rail Travel Assistant API",
    description="Official API for HCLTech Future Ready AI Engineer Hackathon",
    version="1.0.0"
)

# Enable CORS for Streamlit and external callers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Request Models
# ----------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Unique conversation session identifier")
    message: str = Field(..., description="Passenger message")
    as_of: Optional[str] = Field(default=None, description="ISO timestamp for temporal evaluation (defaults to now)")

class IngestRequest(BaseModel):
    doc_type: str = Field(..., description="Type of document: rule, circular, or faq")
    data: Dict[str, Any] = Field(..., description="Document fields and content")

# ----------------------------------------------------------------------
# Endpoints (Section 6 Contract)
# ----------------------------------------------------------------------

@app.get("/health", status_code=status.HTTP_200_OK, tags=["System"])
def health_check():
    """Endpoint: GET /health - Check system is up. Returns 200 when ready."""
    return {
        "status": "healthy",
        "service": "Ujjwal Rail Travel Assistant",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/chat", tags=["Assistant"])
def chat_endpoint(
    req: ChatRequest,
    x_passenger_id: Optional[str] = Header(default="PASS-001", alias="X-Passenger-Id")
):
    """
    Endpoint: POST /chat - Send a passenger's message.
    Header X-Passenger-Id says who is asking.
    Body has session_id, message and an optional as_of time.
    """
    if not x_passenger_id:
        raise HTTPException(status_code=400, detail="Missing required X-Passenger-Id header.")

    response = handle_chat_query(
        passenger_id=x_passenger_id,
        session_id=req.session_id,
        message=req.message,
        as_of=req.as_of
    )
    return response

@app.post("/actions/{action_id}/confirm", tags=["Actions"])
def confirm_action_endpoint(
    action_id: str,
    x_passenger_id: Optional[str] = Header(default="PASS-001", alias="X-Passenger-Id")
):
    """
    Endpoint: POST /actions/{id}/confirm - Confirm a proposed change.
    Only the passenger who asked may confirm. Idempotent: calling twice will not book or cancel twice.
    """
    if not x_passenger_id:
        raise HTTPException(status_code=400, detail="Missing X-Passenger-Id header.")

    res = confirm_action_execution(action_id=action_id, requesting_passenger_id=x_passenger_id)
    if not res.get("success", False):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to confirm action."))
    return res

@app.post("/actions/{action_id}/cancel", tags=["Actions"])
def cancel_action_endpoint(
    action_id: str,
    x_passenger_id: Optional[str] = Header(default="PASS-001", alias="X-Passenger-Id")
):
    """
    Endpoint: POST /actions/{id}/cancel - Drop a proposed change.
    Nothing happens to the database bookings.
    """
    if not x_passenger_id:
        raise HTTPException(status_code=400, detail="Missing X-Passenger-Id header.")

    res = cancel_action_execution(action_id=action_id, requesting_passenger_id=x_passenger_id)
    if not res.get("success", False):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to drop action."))
    return res

@app.get("/bookings/{booking_id}", tags=["Bookings"])
def get_booking_endpoint(
    booking_id: str,
    x_passenger_id: Optional[str] = Header(default="PASS-001", alias="X-Passenger-Id")
):
    """
    Endpoint: GET /bookings/{id} - Fetch one booking.
    Judges use it to check what you claim. Same privacy rule as the chat (R8).
    """
    if not x_passenger_id:
        raise HTTPException(status_code=400, detail="Missing X-Passenger-Id header.")

    res = get_booking_secure(booking_id=booking_id, requesting_passenger_id=x_passenger_id)
    if not res.get("authorized", False):
        # Polite refusal without leaking existence
        raise HTTPException(status_code=404, detail="Booking not found or not accessible under your account.")
    return res["booking"]

@app.post("/ingest", tags=["Knowledge"])
def ingest_endpoint(req: IngestRequest):
    """
    Endpoint: POST /ingest - Add or update a rule, circular or FAQ.
    New content must show up in answers straight away without restarting.
    """
    res = ingest_document(doc_type=req.doc_type, data=req.data)
    if not res.get("success", False):
        raise HTTPException(status_code=400, detail=res.get("error", "Ingestion failed."))
    return res

@app.get("/trace/{trace_id}", tags=["Observability"])
def get_trace_endpoint(trace_id: str):
    """
    Endpoint: GET /trace/{trace_id} - Return the saved record of a reply.
    Documents found, tools used, changes proposed and final answer.
    """
    trace_record = get_audit_trace(trace_id=trace_id)
    if not trace_record:
        raise HTTPException(status_code=404, detail=f"Trace ID {trace_id} not found.")
    return trace_record

# ----------------------------------------------------------------------
# Rule Extraction & Safe Adjustment Endpoints
# ----------------------------------------------------------------------

from backend.tools import (
    extract_base_rule,
    extract_effective_rule,
    extract_all_rules_summary,
    adjust_rule_via_circular
)

class RuleAdjustmentRequest(BaseModel):
    circular_id: str = Field(..., description="Unique circular identifier e.g. CIR-2026-10")
    base_rule_id: str = Field(..., description="Target base rule e.g. RUL-CAN-01")
    title: str = Field(..., description="Amendment circular title")
    amendment_content: str = Field(..., description="Specific text of amendment")
    effective_date: str = Field(..., description="Date amendment becomes active (YYYY-MM-DD)")
    numeric_settings: Optional[Dict[str, float]] = Field(default=None, description="Optional updated fee parameters")

@app.get("/rules", tags=["Rules Ledger"])
def list_rules_endpoint(as_of: Optional[str] = None):
    """
    Extracts all 12 predefined baseline rules and shows their current active amendments.
    Guarantees baseline rules remain permanent in 'predefined_rules'.
    """
    return extract_all_rules_summary(as_of=as_of)

@app.get("/rules/{doc_id}", tags=["Rules Ledger"])
def get_rule_detail_endpoint(doc_id: str, as_of: Optional[str] = None):
    """
    Extracts a specific rule showing the untouched baseline rule and any active circular amendment.
    """
    res = extract_effective_rule(doc_id=doc_id, as_of=as_of)
    if not res.get("found", False):
        raise HTTPException(status_code=404, detail=res.get("error", "Rule not found."))
    return res

@app.post("/rules/adjust", tags=["Rules Ledger"])
def adjust_rule_endpoint(req: RuleAdjustmentRequest):
    """
    Safely adjusts a railway policy via a circular without touching predefined_rules.
    """
    res = adjust_rule_via_circular(
        circular_id=req.circular_id,
        base_rule_id=req.base_rule_id,
        title=req.title,
        amendment_content=req.amendment_content,
        effective_date=req.effective_date,
        numeric_settings=req.numeric_settings
    )
    return res


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000, reload=True)
