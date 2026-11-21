"""
Pydantic data models for Ujjwal Rail Orchestrator & Guardrails.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class Slots(BaseModel):
    """Extracted conversation slots."""
    from_stn: Optional[str] = None
    to_stn: Optional[str] = None
    date: Optional[str] = None
    time_pref: Optional[str] = None
    cls: Optional[str] = None
    booking_id: Optional[str] = None
    train_no: Optional[str] = None


class SubRequest(BaseModel):
    """Segment of a user query produced by the request splitter."""
    text: str
    intent: Literal[
        "train_search",
        "seat_fare",
        "booking_status",
        "refund_quote",
        "rules_qa",
        "cancel",
        "change_boarding",
        "book",
        "complaint",
        "dispute",
        "greeting",
        "identity",
        "other"
    ]
    slots: Slots = Field(default_factory=Slots)


class SourceCited(BaseModel):
    doc_id: str
    section: str


class ToolExecutionTrace(BaseModel):
    tool: str
    output: Dict[str, Any]


class PendingAction(BaseModel):
    action_id: str
    type: str
    booking_id: Optional[str] = None
    expires_at: str


class HandedToHuman(BaseModel):
    desk: str
    ticket_id: str
    passenger_id: str
    booking_id: Optional[str] = None
    summary: str


class PartResult(BaseModel):
    """Outcome of processing an individual sub-request."""
    sub_request_idx: int
    answer_type: Literal[
        "answer",
        "clarification",
        "confirm_needed",
        "action_done",
        "handed_to_human",
        "not_found",
        "refusal"
    ]
    level: int = 0  # Level 0 (lookup), 1 (own booking change), 2 (staff decision), 3 (forbidden)
    text: str
    sources: List[SourceCited] = Field(default_factory=list)
    tools: List[ToolExecutionTrace] = Field(default_factory=list)
    pending_action: Optional[PendingAction] = None
    handed_to_human: Optional[HandedToHuman] = None


class ChatRequest(BaseModel):
    session_id: str
    message: str
    as_of: Optional[str] = None


class ChatResponse(BaseModel):
    trace_id: str
    answer_type: str
    answer: str
    sources: List[SourceCited] = Field(default_factory=list)
    tools: List[ToolExecutionTrace] = Field(default_factory=list)
    pending_action: Optional[PendingAction] = None
    handed_to_human: Optional[HandedToHuman] = None


class SessionState(BaseModel):
    session_id: str
    passenger_id: str
    preferred_language: str = "en"
    slots: Slots = Field(default_factory=Slots)
    clarification_count: int = 0
    last_clarification_slot: Optional[str] = None
    queued_changes: List[SubRequest] = Field(default_factory=list)
