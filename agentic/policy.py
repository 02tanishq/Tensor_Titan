from typing import Any, Optional
from agentic.models import AgenticRequest

# Level 1: Allowed actions
LEVEL_1_ALLOWED = {"book_ticket", "cancel_booking", "change_boarding"}

# Level 2: Human handoff
LEVEL_2_HANDOFF = {
    "refund_dispute", "missed_train_refund", "concession_claim",
    "complaint", "safety_issue",
}

# Level 3: Refusal
LEVEL_3_REFUSAL = {
    "excess_refund", "waitlist_override", "fare_change", "other_passenger_booking",
}


class PolicyDecision:
    def __init__(
        self,
        level: int,
        action_allowed: bool,
        answer_type: str,
        answer: str,
        handed_to_human: Optional[dict[str, Any]] = None,
        sources: Optional[list[dict[str, Any]]] = None,
    ):
        self.level = level
        self.action_allowed = action_allowed
        self.answer_type = answer_type
        self.answer = answer
        self.handed_to_human = handed_to_human
        self.sources = sources or []


def evaluate_policy(request: AgenticRequest) -> PolicyDecision:
    """
    Enforces policy classification and prompt-injection resistance.
    """
    intent = (request.intent or "").strip().lower()

    if intent in LEVEL_3_REFUSAL:
        refusal_messages = {
            "excess_refund": "Requests for refunds exceeding tariff rules are strictly prohibited by railway policy.",
            "waitlist_override": "Waitlist status cannot be manually overridden or expedited outside automated reservation rules.",
            "fare_change": "Railway ticket fares are statutory fixed tariffs and cannot be altered on request.",
            "other_passenger_booking": "Accessing or modifying bookings belonging to another passenger is strictly prohibited.",
        }
        return PolicyDecision(
            level=3,
            action_allowed=False,
            answer_type="refusal",
            answer=refusal_messages.get(intent, f"Action '{request.intent}' is strictly refused under Level 3 policy."),
            sources=[{"source_doc": "Ujjwal Rail Operating Policy Section 3 - Prohibited Actions"}],
        )

    if intent in LEVEL_2_HANDOFF:
        booking_id = request.entities.get("booking_id")
        summary = f"Passenger requested assistance regarding '{request.intent}'."
        if booking_id:
            summary += f" Related booking: {booking_id}."
        answer = (
            f"Your request regarding '{request.intent}' has been forwarded to a human representative "
            f"for manual review. Case summary: {summary} "
            f"Please note that submitting this request does not guarantee or promise any specific outcome."
        )
        return PolicyDecision(
            level=2,
            action_allowed=False,
            answer_type="handed_to_human",
            answer=answer,
            handed_to_human={"summary": summary, "booking_id": booking_id},
            sources=[{"source_doc": "Ujjwal Rail Operating Policy Section 2 - Manual Dispute & Review Guidelines"}],
        )

    if intent in LEVEL_1_ALLOWED:
        return PolicyDecision(
            level=1,
            action_allowed=True,
            answer_type="allowed",
            answer="Action permitted under Level 1 policy.",
            sources=[{"source_doc": "Ujjwal Rail Operating Policy Section 1 - Permitted Self-Service Actions"}],
        )

    return PolicyDecision(
        level=0,
        action_allowed=False,
        answer_type="clarification",
        answer=(
            f"Unrecognized intent '{request.intent}'. Permitted self-service actions are "
            "ticket booking, ticket cancellation, or changing boarding station."
        ),
        sources=[],
    )
