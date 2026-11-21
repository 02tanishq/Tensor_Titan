"""
Intent, Language & Policy Router.
Detects language (en/hi/hinglish), classifies answer_type, maps to Change Level 0-3,
and routes to Branch A (Clarification), B (Refusal), C (Handoff), D (Rules Lookup), or E (Tools).
"""

import re
from typing import Tuple, Optional
from app.models import SubRequest, SessionState
from app.config import config


def detect_language(text: str) -> str:
    """Detect whether query is English, Hindi (Devanagari), or Hinglish."""
    # Check for Devanagari Unicode block
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"

    # Common Hinglish marker words
    hinglish_markers = [
        "kya", "hai", "mujhe", "mera", "meri", "karna", "karein", "milega",
        "kitna", "paisa", "wapas", "kal", "gadi", "kutte", "kutha", "badalna",
        "kaise", "batao", "chahiye", "aur", "bhi", "nahi", "nahin"
    ]
    words = re.findall(r"\b\w+\b", text.lower())
    match_count = sum(1 for w in words if w in hinglish_markers)
    if match_count >= 1:
        return "hi-en"

    return "en"


def classify_level(intent: str, text: str) -> int:
    """
    Map request to Change Level 0-3:
    - Level 0: Lookups (train timetable, seats, fares, policy rules)
    - Level 1: Own-booking changes permitted by policy (cancel, change boarding)
    - Level 2: Staff decisions (disputes, grievances, claims, safety escalations)
    - Level 3: Forbidden requests (jumping waitlist, overriding fares, out-of-scope)
    One-line reason: Explicit level policy ensures no unauthorized database mutations or unbacked promises.
    """
    t = text.lower()

    # Level 3: Forbidden requests
    if any(p in t for p in [
        "jump waitlist", "bypass rule", "waive cancellation fee", "free ticket",
        "ignore rules", "change someone else", "flight", "weather in tokyo", "pizza",
        "without paying", "waitlist ticket to confirmed", "to confirmed seat", "to confirmed status", "free upgrade",
        "change passenger name", "transfer ticket"
    ]):
        return 3

    # Level 2: Staff decisions / Escalations / Human hand-off
    if any(p in t for p in [
        "harass", "complaint", "grievance", "stolen", "dispute", "sue",
        "speak to human", "talk to agent", "escalate", "have not received", "haven't received", "havent received", "not received",
        "human", "executive", "agent", "officer", "manager", "supervisor", "representative", "delay", "delayed"
    ]) or intent in ("complaint", "dispute"):
        return 2

    # Level 1: Own-booking changes needing confirmation
    if intent in ("cancel", "change_boarding", "book"):
        return 1

    # Level 0: Pure deterministic lookups & conversational assistance
    if intent in ("greeting", "identity"):
        return 0

    return 0


def determine_branch(
    sub_request: SubRequest,
    session: SessionState
) -> Tuple[str, str, int]:
    """
    Determine execution Branch (A-E, G, I), answer_type, and change Level.
    Returns: (branch: A|B|C|D|E|G|I, answer_type, level)
    """
    level = classify_level(sub_request.intent, sub_request.text)

    # 1. Level 3 -> Branch B: Policy Refusal
    if level == 3:
        return "B", "refusal", 3

    # 2. Level 2 -> Branch C: Human Hand-off
    if level == 2:
        return "C", "handed_to_human", 2

    # 0. Conversational greetings and identity
    if sub_request.intent == "greeting":
        return "G", "answer", 0
    if sub_request.intent == "identity":
        return "I", "answer", 0

    # 3. Level 1 -> Check if required slots are present
    if level == 1:
        if sub_request.intent == "book":
            return "E", "confirm_needed", 1

        if sub_request.intent == "cancel":
            if not sub_request.slots.booking_id:
                # Missing booking reference -> Branch A: Clarification (Max 2 before Hand-off)
                if session.clarification_count >= config.MAX_CLARIFICATIONS:
                    # Fallback ladder: Asked twice -> Hand-off
                    return "C", "handed_to_human", 2
                return "A", "clarification", 1
            return "E", "confirm_needed", 1

        if sub_request.intent == "change_boarding":
            if not sub_request.slots.booking_id:
                if session.clarification_count >= config.MAX_CLARIFICATIONS:
                    return "C", "handed_to_human", 2
                return "A", "clarification", 1
            return "E", "confirm_needed", 1

    # 4. Level 0 Lookups
    if sub_request.intent == "seat_fare":
        # If train_no is known OR both stations are known, proceed to branch E
        if sub_request.slots.train_no or (sub_request.slots.from_stn and sub_request.slots.to_stn):
            return "E", "answer", 0
        if session.clarification_count >= config.MAX_CLARIFICATIONS:
            return "C", "handed_to_human", 2
        return "A", "clarification", 0

    if sub_request.intent == "train_search":
        # If route missing
        if not sub_request.slots.from_stn or not sub_request.slots.to_stn:
            if session.clarification_count >= config.MAX_CLARIFICATIONS:
                return "C", "handed_to_human", 2
            return "A", "clarification", 0
        return "E", "answer", 0

    if sub_request.intent in ("refund_quote", "booking_status"):
        if not sub_request.slots.booking_id:
            if session.clarification_count >= config.MAX_CLARIFICATIONS:
                return "C", "handed_to_human", 2
            return "A", "clarification", 0
        return "E", "answer", 0

    if sub_request.intent == "rules_qa":
        return "D", "answer", 0

    # Default out of scope / other
    t = sub_request.text.lower()
    rail_terms = [
        "train", "rail", "seat", "coach", "berth", "pnr", "ticket", "station",
        "tatkal", "ujjwal", "booking", "book", "reservation", "refund", "fare", "cancel"
    ]
    if not any(k in t for k in rail_terms):
        return "B", "refusal", 3

    return "D", "answer", 0
