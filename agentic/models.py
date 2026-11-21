from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


class PendingAction(BaseModel):
    action_id: str
    type: str
    booking_id: str
    expires_at: Union[datetime, str]

    @field_validator("expires_at", mode="before")
    @classmethod
    def format_expires_at(cls, v: Any) -> Union[str, datetime]:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class ToolRecord(BaseModel):
    tool: str
    output: dict[str, Any]

    @field_validator("output", mode="before")
    @classmethod
    def validate_output(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, dict):
            return v
        if hasattr(v, "model_dump"):
            return v.model_dump()
        return {"result": v}


class AgenticRequest(BaseModel):
    passenger_id: str
    session_id: str
    message: str
    intent: Optional[str] = None
    entities: dict[str, Any] = Field(default_factory=dict)
    as_of: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("as_of", mode="before")
    @classmethod
    def parse_as_of(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            cleaned = v.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        raise ValueError(f"Invalid datetime format: {v}")


class AgenticResponse(BaseModel):
    trace_id: str
    answer_type: Literal[
        "confirm_needed",
        "action_done",
        "handed_to_human",
        "refusal",
        "clarification",
    ]
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[ToolRecord] = Field(default_factory=list)
    pending_action: Optional[PendingAction] = None
    handed_to_human: Optional[dict[str, Any]] = None

    @field_validator("sources", mode="before")
    @classmethod
    def coerce_sources(cls, v: Any) -> list[dict[str, Any]]:
        if not isinstance(v, list):
            return []
        coerced = []
        for item in v:
            if isinstance(item, dict):
                coerced.append(item)
            elif isinstance(item, str):
                coerced.append({"source_doc": item})
            else:
                coerced.append({"source_doc": str(item)})
        return coerced
