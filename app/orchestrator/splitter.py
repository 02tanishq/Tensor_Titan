"""
Request Splitter for Multi-Intent Messages.
Splits compound queries into at most MAX_PARTS=3 SubRequest objects.
Under MOCK_LLM=true, executes deterministic rule-based splitting on sentence boundaries,
conjunctions ('and', 'aur'), and question marks.
"""

import re
from typing import List, Tuple
from app.models import SubRequest, Slots, SessionState
from app.config import config


# Station alias normalization map
STATION_ALIASES = {
    "bombay": "CSMT",
    "mumbai": "CSMT",
    "cst": "CSMT",
    "bombay vt": "CSMT",
    "csmt": "CSMT",
    "bombay central": "BCT",
    "mumbai central": "BCT",
    "bct": "BCT",
    "poona": "PUNE",
    "pune": "PUNE",
    "nagpur": "NGP",
    "ngp": "NGP",
    "delhi": "NDLS",
    "new delhi": "NDLS",
    "ndls": "NDLS",
    "kalyan": "KYN",
    "bhusawal": "BSL",
    "solapur": "SUR",
    "bhopal": "BPL",
    "howrah": "HWH",
    "kolkata": "HWH",
    "goa": "MAO",
    "madgaon": "MAO",
    "jammu": "JAT"
}


def extract_slots(text: str) -> Slots:
    """Extract station codes, travel date, class, and booking ID from text."""
    slots = Slots()
    text_lower = text.lower()

    # 1. Booking ID (UR-XXXXX)
    b_match = re.search(r"\b(UR-\d{5})\b", text, re.IGNORECASE)
    if b_match:
        slots.booking_id = b_match.group(1).upper()

    # 1.5 Train Number (12XXX, 02XXX, 22XXX)
    t_match = re.search(r"\b(12\d{3}|02\d{3}|22\d{3})\b", text)
    if t_match:
        slots.train_no = t_match.group(1)

    # 2. Travel Class (1AC, 2AC, 3AC, CC, SL, 2S, Sleeper, First AC)
    cls_match = re.search(r"\b(1AC|2AC|3AC|CC|SL|2S|sleeper|first\s*ac|chair\s*car)\b", text, re.IGNORECASE)
    if cls_match:
        raw_cls = cls_match.group(1).upper()
        if "SLEEPER" in raw_cls: slots.cls = "SL"
        elif "CHAIR" in raw_cls: slots.cls = "CC"
        elif "FIRST" in raw_cls: slots.cls = "1AC"
        else: slots.cls = raw_cls

    # 3. Date pattern: YYYY-MM-DD or DD Month or tomorrow / kal / Friday
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if date_match:
        slots.date = date_match.group(1)
    elif "friday" in text_lower:
        slots.date = "2026-12-05"
    elif "tomorrow" in text_lower or "kal" in text_lower:
        slots.date = "2026-11-22"

    # 4. Route from / to
    route_match = re.search(r"\bfrom\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)(?:\s+on|\s+in|\s+for|[.?,]|$)", text, re.IGNORECASE)
    if route_match:
        orig = route_match.group(1).strip().lower()
        dest = route_match.group(2).strip().lower()
        slots.from_stn = STATION_ALIASES.get(orig, orig.upper()[:4])
        slots.to_stn = STATION_ALIASES.get(dest, dest.upper()[:4])
    else:
        # Check Hindi/Hinglish "Pune se Nagpur" or "Pune se Mumbai"
        hi_match = re.search(r"\b([a-zA-Z]+)\s+se\s+([a-zA-Z]+)\b", text, re.IGNORECASE)
        if hi_match:
            orig = hi_match.group(1).strip().lower()
            dest = hi_match.group(2).strip().lower()
            if orig in STATION_ALIASES: slots.from_stn = STATION_ALIASES[orig]
            if dest in STATION_ALIASES: slots.to_stn = STATION_ALIASES[dest]
        else:
            # Check 'Pune to Nagpur' or 'PUNE-NGP' pattern
            to_match = re.search(r"\b([a-zA-Z]+)\s+to\s+([a-zA-Z]+)\b", text, re.IGNORECASE)
            if to_match and to_match.group(1).lower() not in ("want", "how", "need"):
                orig = to_match.group(1).strip().lower()
                dest = to_match.group(2).strip().lower()
                if orig in STATION_ALIASES: slots.from_stn = STATION_ALIASES[orig]
                if dest in STATION_ALIASES: slots.to_stn = STATION_ALIASES[dest]

    return slots


def detect_intent(text: str) -> str:
    """Classify the sub-request into an intent category."""
    t = text.lower()

    # 0. Conversational greetings
    if t.strip() in ["hi", "hello", "hey", "namaste", "good morning", "good evening", "good afternoon", "hi!", "hello!", "hey!"] or (
        t.startswith(("hi ", "hello ", "hey ", "namaste ")) 
        and not any(k in t for k in ["train", "ticket", "cancel", "refund", "tatkal", "seat", "fare", "ur-", "status"])
    ):
        return "greeting"

    # 0.1 Identity / Profile inquiry
    if any(phrase in t for phrase in [
        "what is my name", "who am i", "my name", "my profile", "mera naam", 
        "who i am", "my passenger id", "which user am i", "logged in as"
    ]):
        return "identity"

    # 1. Privacy / Passenger manifest snooping
    if any(p in t for p in ["passenger list", "phone numbers", "other passenger", "manifest", "show me passenger"]):
        return "other"

    # 2. Disallowed name changes / transfer / unauthorized fee waivers
    if any(p in t for p in [
        "change passenger name", "transfer ticket", "brother", "without paying",
        "jump waitlist", "free ticket", "free upgrade"
    ]):
        return "other"

    # 3. Informational cancellation & refund questions (Rules QA)
    if any(p in t for p in [
        "can i cancel", "deadline", "hours before", "chart", "how much refund",
        "kitna paisa", "paisa milega", "cancellation charge", "refund for ur-"
    ]):
        return "rules_qa"

    # 4. Rules, policy, luggage, pet, id, tatkal
    if any(w in t for w in [
        "pet", "dog", "kutta", "kutte", "animal", "identity", "aadhaar",
        "digilocker", "tatkal", "break of journey", "concession", "senior citizen",
        "luggage", "rule", "rules", "policy", "guideline"
    ]) or re.search(r"\b(id|ids)\b", t):
        return "rules_qa"

    # 5. Booking action request
    if any(p in t for p in ["book 1 seat", "book a seat", "reserve a seat"]):
        return "book"

    # 6. Vague ticket ask
    if t in ["i need a ticket", "i need a ticket to delhi", "book ticket", "train ticket", "ticket"]:
        return "train_search"

    # 7. Specific Cancellation Action
    if any(w in t for w in ["cancel my ticket", "cancel ticket", "cancel booking", "cancel my booking", "cancel it", "cancel"]):
        return "cancel"

    # 8. Specific Refund Quote Action
    if any(w in t for w in ["refund quote", "quote my refund"]):
        return "refund_quote"

    # 9. Boarding change
    if any(w in t for w in ["change boarding", "boarding station badal"]):
        return "change_boarding"

    # 10. Complaints and human escalation
    if any(w in t for w in ["complain", "complaint", "grievance", "harassment", "lost bag", "human", "agent"]):
        return "complaint"

    # 11. Fares and seats
    if re.search(r"\b(12\d{3}|02\d{3}|22\d{3})\b", t) and any(w in t for w in ["seat", "seats", "available", "availability", "fare", "kiraya", "berth", "1ac", "2ac", "3ac", "cc", "sl"]):
        return "seat_fare"
    if any(w in t for w in ["fare", "ticket price", "kiraya", "seat", "available", "berth"]):
        return "seat_fare"

    # 12. Timetable and train search
    if any(w in t for w in ["train", "schedule", "timetable", "gadi", "departure", "kaunsi train"]):
        return "train_search"

    # 13. Booking status / PNR
    if any(w in t for w in ["status", "pnr", "booking status"]):
        return "booking_status"

    # Default fallback
    return "other"


def split_requests(raw_message: str, session: SessionState) -> List[SubRequest]:
    """
    Splits compound user query into up to MAX_PARTS=3 SubRequests.
    Merges slots across parts and session memory.
    One-line reason: Ensures multi-question messages are handled independently without cross-blocking.
    """
    # Clean text
    clean_text = raw_message.replace("<<<UNTRUSTED_DATA>>>", "").replace("<<<END_UNTRUSTED_DATA>>>", "").strip()

    # Split on sentence boundaries, question marks, and distinct conjunctions
    split_pattern = r"(?<=[.?!])\s+|\s+(?:and\s+also|aur\s+bhi|and|aur)\s+(?=[a-zA-Z0-9\?])"
    raw_parts = [p.strip() for p in re.split(split_pattern, clean_text, flags=re.IGNORECASE) if p.strip()]

    if not raw_parts:
        raw_parts = [clean_text]

    # Enforce maximum parts limit
    parts_to_process = raw_parts[:config.MAX_PARTS]

    sub_requests: List[SubRequest] = []
    shared_slots = Slots()

    for part_text in parts_to_process:
        intent = detect_intent(part_text)
        part_slots = extract_slots(part_text)

        # Merge slots: prioritize part slots, then shared slots from earlier parts, then session memory
        merged_slots = Slots()
        for field in ["from_stn", "to_stn", "date", "time_pref", "cls", "booking_id", "train_no"]:
            val = (
                getattr(part_slots, field)
                or getattr(shared_slots, field)
                or getattr(session.slots, field)
            )
            setattr(merged_slots, field, val)
            if getattr(part_slots, field):
                setattr(shared_slots, field, getattr(part_slots, field))

        sub_requests.append(SubRequest(
            text=part_text,
            intent=intent,
            slots=merged_slots
        ))

    return sub_requests
