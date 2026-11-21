"""
Branch Handlers for Ujjwal Rail Orchestrator.
Executes:
- Branch A: Clarification (asks missing slot, max 2 follow-ups)
- Branch B: Policy Refusal (Level 3 or out-of-scope)
- Branch C: Human Hand-off (complaint, dispute, safety escalation)
- Branch D: Rules Retrieval (wires HybridRetriever with exact citations)
- Branch E: Deterministic Tools (search, seats, refund quote, propose action)
"""

import re
import uuid
from typing import Dict, Any, Optional
from app.models import (
    SubRequest,
    PartResult,
    SessionState,
    SourceCited,
    ToolExecutionTrace,
    PendingAction,
    HandedToHuman,
)
from app.config import config
from app.guardrails.identity import ownership_check
from app.orchestrator.session import increment_clarification_count
from app.tools.interface import (
    search_trains,
    seat_fare,
    refund_quote,
    propose_action,
)
from RAG_pipeline.hybrid_retriever import HybridRetriever
from app.llm_client import (
    is_grok_available,
    generate_rules_answer,
    synthesize_tool_answer,
    generate_conversational_response,
    generate_clarification_response,
)


def execute_branch_greeting(
    sub_req: SubRequest,
    passenger_id: str,
    lang: str,
    idx: int
) -> PartResult:
    """Greeting branch with personalized passenger name lookup."""
    import sqlite3
    p_name = ""
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM passengers WHERE passenger_id = ?", (passenger_id,))
            row = c.fetchone()
            if row and row[0]:
                p_name = f" {row[0]}"
    except Exception:
        pass

    if lang in ("hi", "hi-en"):
        msg = f"Namaste{p_name}! Main aapka Ujjwal Rail Travel Assistant hoon. Aap mujhse train timetable, seat availability, refund calculations ya railway policies ke baare mein pooch sakte hain. Main aapki kya madad kar sakta hoon?"
    else:
        msg = f"Hello{p_name}! I am your Ujjwal Rail Travel Assistant. You can ask me about train schedules, seat availability, cancellation refunds, or railway policies. How can I help you today?"

    if is_grok_available():
        grok_msg = generate_conversational_response(sub_req.text, p_name.strip() or "Passenger", passenger_id, lang=lang)
        if grok_msg:
            msg = grok_msg

    return PartResult(
        sub_request_idx=idx,
        answer_type="answer",
        level=0,
        text=msg
    )


def execute_branch_identity(
    sub_req: SubRequest,
    passenger_id: str,
    lang: str,
    idx: int
) -> PartResult:
    """Passenger profile and identity inquiry."""
    import sqlite3
    p_name = "Passenger"
    p_phone = "XXXX"
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT name, phone_last4 FROM passengers WHERE passenger_id = ?", (passenger_id,))
            row = c.fetchone()
            if row:
                p_name = row[0]
                p_phone = row[1]
    except Exception:
        pass

    if lang in ("hi", "hi-en"):
        msg = f"Aap {p_name} ke roop mein authenticated hain (Passenger ID: {passenger_id}, Registered Mobile: ••••{p_phone}). Main aapki yatra mein kya sahayata kar sakta hoon?"
    else:
        msg = f"You are logged in as {p_name} (Passenger ID: {passenger_id}, Registered Mobile: ••••{p_phone}). How can I assist you with your travels today?"

    if is_grok_available():
        grok_msg = generate_conversational_response(sub_req.text, p_name, passenger_id, lang=lang)
        if grok_msg:
            msg = grok_msg

    t_lower = sub_req.text.lower()
    is_booking_inquiry = any(w in t_lower for w in ["booking", "bookings", "ticket", "tickets", "gadi", "gaadi", "booked"])
    if is_booking_inquiry:
        with sqlite3.connect(config.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT b.booking_id, b.train_no, t.name as train_name, b.from_code, b.to_code, 
                       b.journey_date, b.class, b.status, b.amount_paid
                FROM bookings b
                LEFT JOIN trains t ON b.train_no = t.train_no
                WHERE b.passenger_id = ?
                ORDER BY b.journey_date DESC
            """, (passenger_id,))
            rows = c.fetchall()
        if rows:
            booking_lines = []
            for r in rows:
                t_name = f" ({r['train_name']})" if r['train_name'] else ""
                booking_lines.append(
                    f"• {r['booking_id']}: Train {r['train_no']}{t_name} from {r['from_code']} to {r['to_code']} on {r['journey_date']} "
                    f"| Class: {r['class']} | Status: {r['status']} | Fare: Rs {r['amount_paid']}"
                )
            if lang in ("hi", "hi-en"):
                msg = f"Aapke account ({passenger_id}) ke registered bookings:\n" + "\n".join(booking_lines)
            else:
                msg = f"Here are the bookings registered under your account ({passenger_id}):\n" + "\n".join(booking_lines)
            b_list = [{"booking_id": r["booking_id"], "train_no": r["train_no"], "status": r["status"]} for r in rows]
        else:
            if lang in ("hi", "hi-en"):
                msg = f"Aapke account ({passenger_id}) par koi booking darj nahi hai."
            else:
                msg = f"You do not have any registered bookings under Passenger ID {passenger_id}."
            b_list = []

        tool_traces = [
            ToolExecutionTrace(tool="get_passenger_bookings", output={"count": len(rows), "bookings": b_list})
        ]
        return PartResult(
            sub_request_idx=idx,
            answer_type="answer",
            level=0,
            text=msg,
            tools=tool_traces,
            sources=[SourceCited(doc_id="RUL-BKG-01", section="2. Passenger Bookings")]
        )

    tool_traces = [
        ToolExecutionTrace(tool="get_passenger_profile", output={"passenger_id": passenger_id, "name": p_name, "phone_last4": p_phone})
    ]

    return PartResult(
        sub_request_idx=idx,
        answer_type="answer",
        level=0,
        text=msg,
        tools=tool_traces
    )


def execute_branch_a(
    sub_req: SubRequest,
    session: SessionState,
    lang: str,
    idx: int
) -> PartResult:
    """Branch A: Clarification."""
    needed_slot = "booking_id" if sub_req.intent in ("cancel", "change_boarding", "refund_quote", "booking_status") else "route"
    increment_clarification_count(session, needed_slot)

    if lang == "hi-en":
        if needed_slot == "booking_id":
            msg = "Kripya apna booking ID (jaise UR-30418) batayein taaki main aage check kar sakun."
        else:
            msg = "Kripya kahan se kahan travel karna hai (from station aur to station) batayein."
    elif lang == "hi":
        if needed_slot == "booking_id":
            msg = "कृपया अपनी बुकिंग आईडी (जैसे UR-30418) बताएं ताकि मैं विवरण देख सकूं।"
        else:
            msg = "कृपया यात्रा का प्रस्थान और गंतव्य स्टेशन बताएं।"
    else:
        if needed_slot == "booking_id":
            msg = "Please provide your booking reference ID (e.g., UR-30418) to proceed."
        else:
            msg = "Please specify your origin and destination stations (e.g., Pune to CSMT)."

    if is_grok_available():
        grok_msg = generate_clarification_response(sub_req.text, needed_slot, lang=lang)
        if grok_msg:
            msg = grok_msg

    return PartResult(
        sub_request_idx=idx,
        answer_type="clarification",
        level=0,
        text=msg
    )


def execute_branch_b(
    sub_req: SubRequest,
    lang: str,
    idx: int
) -> PartResult:
    """Branch B: Policy Refusal (Level 3 / Out-of-scope)."""
    t = sub_req.text.lower()
    if any(k in t for k in ["jump waitlist", "waive", "bypass", "free ticket", "discount", "without paying", "waitlist", "brother", "name"]):
        if lang == "hi-en":
            msg = "Ujjwal Rail ke niyam anusaar fare override karna, bina shulk waitlist confirm karna ya naam badalna mana hai."
        else:
            msg = "Ujjwal Rail policy strictly prohibits manual fare overrides, waitlist jumps, unauthorized fee waivers, or passenger name transfers."
    else:
        if lang == "hi-en":
            msg = "Main keval Ujjwal Rail train yatra, timetable, booking aur policy niyam me sahayata kar sakta hoon."
        else:
            msg = "I can only assist with Ujjwal Rail train travel, reservations, timetables, and official railway policies."

    return PartResult(
        sub_request_idx=idx,
        answer_type="refusal",
        level=3,
        text=msg
    )


def execute_branch_c(
    sub_req: SubRequest,
    passenger_id: str,
    lang: str,
    idx: int
) -> PartResult:
    """Branch C: Human Hand-off."""
    ticket_id = f"ESC-{uuid.uuid4().hex[:4].upper()}"
    desk = "Grievance Redressal Desk" if sub_req.intent in ("complaint", "dispute") else "Passenger Support Desk"

    if lang == "hi-en":
        msg = f"Aapka request hamare human {desk} ko bhej diya gaya hai (Ticket #{ticket_id}). Hamari team aapse sampark karegi."
    else:
        msg = f"I have escalated your request regarding '{sub_req.text}' to our {desk}. Ticket ID #{ticket_id} has been logged. An official representative will review this."

    hand_off = HandedToHuman(
        desk=desk,
        ticket_id=ticket_id,
        passenger_id=passenger_id,
        booking_id=sub_req.slots.booking_id,
        summary=sub_req.text[:120]
    )

    return PartResult(
        sub_request_idx=idx,
        answer_type="handed_to_human",
        level=2,
        text=msg,
        handed_to_human=hand_off
    )


def execute_branch_d(
    sub_req: SubRequest,
    retriever: HybridRetriever,
    as_of: str,
    lang: str,
    idx: int
) -> PartResult:
    """Branch D: Rules Knowledge Retrieval."""
    ret_result = retriever.retrieve(sub_req.text, as_of=as_of, top_k=3)

    if not ret_result.chunks:
        if lang == "hi-en":
            msg = "Maaf kijiye, Ujjwal Rail ke rules me is vishay par koi niyam nahi mila."
        else:
            msg = "I could not find an applicable Ujjwal Rail policy document for your query."
        return PartResult(
            sub_request_idx=idx,
            answer_type="not_found",
            level=0,
            text=msg
        )

    # Compile citations
    sources = [SourceCited(doc_id=c.doc_id, section=c.section) for c in ret_result.citations]

    # Deterministic canned synthesis of answer using top winning chunks
    top_chunk = ret_result.chunks[0]
    if lang == "hi-en":
        answer_text = f"Niyam {top_chunk.doc_id} ({top_chunk.section}) ke anusaar: {top_chunk.content}"
    else:
        answer_text = f"According to {top_chunk.doc_id} ({top_chunk.section}): {top_chunk.content}"

    # If Grok LLM is active, generate natural language response grounded in retrieved chunks
    if is_grok_available():
        grok_ans = generate_rules_answer(sub_req.text, ret_result.chunks, ret_result.citations, lang=lang)
        if grok_ans:
            answer_text = grok_ans

    tool_traces = [
        ToolExecutionTrace(
            tool="rag_hybrid_retriever",
            output={
                "retrieval_method": ret_result.retrieval_method,
                "chunks_count": len(ret_result.chunks),
                "top_doc": top_chunk.doc_id,
                "top_section": top_chunk.section,
                "clashes": [c.winning_doc_id for c in ret_result.clashes],
                "snippet": top_chunk.content[:200]
            }
        )
    ]

    return PartResult(
        sub_request_idx=idx,
        answer_type="answer",
        level=0,
        text=answer_text,
        sources=sources,
        tools=tool_traces
    )


def execute_branch_e(
    sub_req: SubRequest,
    passenger_id: str,
    session: SessionState,
    as_of: str,
    lang: str,
    idx: int
) -> PartResult:
    """Branch E: Deterministic Tools & Booking Actions."""
    slots = sub_req.slots

    # Level 1 Booking Changes: cancel / change_boarding
    if sub_req.intent in ("cancel", "change_boarding"):
        # 1. Ownership check (identical refusal for non-existent vs other passenger)
        is_owned, refusal_msg = ownership_check(passenger_id, slots.booking_id, config.DB_PATH)
        if not is_owned:
            return PartResult(
                sub_request_idx=idx,
                answer_type="refusal",
                level=3,
                text=refusal_msg
            )

        # 2. Check if an action is already pending in this session
        # If so, queue subsequent changes
        has_pending = any(sub.intent in ("cancel", "change_boarding") for sub in session.queued_changes)
        if has_pending:
            session.queued_changes.append(sub_req)
            msg = f"You already have a pending action awaiting confirmation. Your request for booking {slots.booking_id} has been queued and will be presented after your current action is confirmed or cancelled."
            return PartResult(
                sub_request_idx=idx,
                answer_type="answer",
                level=1,
                text=msg
            )

        # 3. Calculate refund quote and create pending action
        quote = refund_quote(slots.booking_id, as_of)
        proposed = propose_action(
            passenger_id=passenger_id,
            action_type="cancel_booking" if sub_req.intent == "cancel" else "change_boarding",
            booking_id=slots.booking_id,
            details=quote
        )

        p_act = PendingAction(
            action_id=proposed["action_id"],
            type=proposed.get("type", proposed.get("action_type", "cancel_booking")),
            booking_id=slots.booking_id,
            expires_at=proposed["expires_at"]
        )

        tool_traces = [
            ToolExecutionTrace(tool="refund_quote", output=quote),
            ToolExecutionTrace(tool="propose_action", output=proposed)
        ]

        if lang == "hi-en":
            msg = f"Booking {slots.booking_id} cancel karne par Rs {quote['refund']} wapas milenge (Deduction Rs {quote['charge']}). Kya aap ise confirm karna chahte hain? (Action ID: {p_act.action_id})"
        else:
            msg = f"Cancelling booking {slots.booking_id} now will give you a refund of Rs {quote['refund']} (deduction of Rs {quote['charge']}). Shall I go ahead? Confirm via Action ID {p_act.action_id} within 10 minutes."

        return PartResult(
            sub_request_idx=idx,
            answer_type="confirm_needed",
            level=1,
            text=msg,
            tools=tool_traces,
            pending_action=p_act
        )

    # Level 1: Ticket Booking Creation
    if sub_req.intent == "book":
        has_pending = any(sub.intent in ("cancel", "change_boarding", "book") for sub in session.queued_changes)
        if has_pending:
            session.queued_changes.append(sub_req)
            msg = "You already have a pending action awaiting confirmation. Your booking request has been queued."
            return PartResult(
                sub_request_idx=idx,
                answer_type="answer",
                level=1,
                text=msg
            )

        train_match = re.search(r"\b(\d{5})\b", sub_req.text)
        train_no = train_match.group(1) if train_match else "12123"
        cls = slots.cls or "3AC"
        date = slots.date or "2026-12-05"

        quote = seat_fare(train_no, date, cls)
        fare_amt = quote.get("fare", 1250)

        proposed = propose_action(
            passenger_id=passenger_id,
            action_type="book_ticket",
            booking_id=None,
            details={"train_no": train_no, "date": date, "class": cls, "fare": fare_amt}
        )

        p_act = PendingAction(
            action_id=proposed["action_id"],
            type=proposed.get("type", proposed.get("action_type", "book_ticket")),
            booking_id=None,
            expires_at=proposed["expires_at"]
        )

        tool_traces = [
            ToolExecutionTrace(tool="seat_fare", output=quote),
            ToolExecutionTrace(tool="propose_action", output=proposed)
        ]

        if lang == "hi-en":
            msg = f"Train {train_no} ({cls}) me {date} ke liye ticket book karne ka fare Rs {fare_amt} hai. Kya aap confirm karna chahte hain? (Action ID: {p_act.action_id})"
        else:
            msg = f"Booking 1 seat on Train {train_no} ({cls}) for {date} will cost Rs {fare_amt}. Shall I proceed? Confirm via Action ID {p_act.action_id} within 10 minutes."

        return PartResult(
            sub_request_idx=idx,
            answer_type="confirm_needed",
            level=1,
            text=msg,
            tools=tool_traces,
            pending_action=p_act
        )

    # Level 0 Lookups: train_search
    if sub_req.intent == "train_search":
        trains = search_trains(slots.from_stn, slots.to_stn, slots.date)
        tool_traces = [ToolExecutionTrace(tool="search_trains", output={"results": trains})]
        if trains:
            train_names = ", ".join([f"{t['train_no']} ({t['name']} departs {t['departure']})" for t in trains])
            if lang in ("hi", "hi-en"):
                msg = f"{slots.from_stn} se {slots.to_stn} ke liye uplabdh trains: {train_names}."
            else:
                msg = f"Trains available from {slots.from_stn} to {slots.to_stn}: {train_names}."
        else:
            if lang in ("hi", "hi-en"):
                msg = f"Maaf kijiye, {slots.from_stn} se {slots.to_stn} ke beech koi direct train nahi mili."
            else:
                msg = f"No direct trains found from {slots.from_stn} to {slots.to_stn} on {slots.date or 'this date'}."

        if is_grok_available() and trains:
            grok_msg = synthesize_tool_answer(sub_req.text, "search_trains", {"from": slots.from_stn, "to": slots.to_stn, "trains": trains}, lang=lang)
            if grok_msg:
                msg = grok_msg

        return PartResult(
            sub_request_idx=idx,
            answer_type="answer",
            level=0,
            text=msg,
            tools=tool_traces
        )

    # Level 0 Lookups: seat_fare
    if sub_req.intent == "seat_fare":
        train_no = slots.train_no or "12123"
        sf = seat_fare(
            train_no,
            slots.date or "2026-12-05",
            slots.cls or "3AC",
            from_stn=slots.from_stn,
            to_stn=slots.to_stn
        )
        tool_traces = [ToolExecutionTrace(tool="seat_fare", output=sf)]
        if lang in ("hi", "hi-en"):
            msg = f"Train {sf['train_no']} me {sf['class']} ({sf['journey_date']}) ka fare Rs {sf['fare']} hai. Available seats: {sf['available']}, RAC: {sf['rac']}, WL: {sf['waitlist']}."
        else:
            msg = f"Train {sf['train_no']} ({sf['class']} on {sf['journey_date']}) fare is Rs {sf['fare']}. Availability: {sf['available']} seats, RAC: {sf['rac']}, WL: {sf['waitlist']}."

        if is_grok_available():
            grok_msg = synthesize_tool_answer(sub_req.text, "seat_fare", sf, lang=lang)
            if grok_msg:
                msg = grok_msg

        return PartResult(
            sub_request_idx=idx,
            answer_type="answer",
            level=0,
            text=msg,
            tools=tool_traces
        )

    # Level 0 Lookups: refund_quote
    if sub_req.intent == "refund_quote":
        is_owned, refusal_msg = ownership_check(passenger_id, slots.booking_id, config.DB_PATH)
        if not is_owned:
            return PartResult(sub_request_idx=idx, answer_type="refusal", level=3, text=refusal_msg)

        quote = refund_quote(slots.booking_id, as_of)
        tool_traces = [ToolExecutionTrace(tool="refund_quote", output=quote)]
        if lang == "hi-en":
            msg = f"Booking {slots.booking_id} ke liye refund quote: Paid Rs {quote['amount_paid']}, Cancellation charge Rs {quote['charge']}, Net Refund Rs {quote['refund']}."
        else:
            msg = f"Refund quote for booking {slots.booking_id}: Total paid Rs {quote['amount_paid']}, deduction Rs {quote['charge']}, estimated refund Rs {quote['refund']}."

        if is_grok_available():
            grok_msg = synthesize_tool_answer(sub_req.text, "refund_quote", quote, lang=lang)
            if grok_msg:
                msg = grok_msg

        return PartResult(
            sub_request_idx=idx,
            answer_type="answer",
            level=0,
            text=msg,
            tools=tool_traces
        )

    # Fallback
    return PartResult(
        sub_request_idx=idx,
        answer_type="answer",
        level=0,
        text="Lookup processed successfully."
    )
