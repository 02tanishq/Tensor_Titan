import json
import os
import re
import urllib.request
from typing import Any

BIONIC_BASE_URL = os.getenv("BIONIC_BASE_URL", "http://localhost:11434/v1")
BIONIC_MODEL = os.getenv("BIONIC_MODEL", "qwen2.5:0.5b")
BIONIC_API_KEY = os.getenv("BIONIC_API_KEY", "ollama")

INTENT_KEYWORDS = {
    # Check Level 3 Refusals and Security first
    "other_passenger_booking": ["other passenger", "someone else booking", "cancel friend ticket", "friend", "someone else", "another passenger"],
    "excess_refund": ["excess refund", "extra refund", "100% refund anyway", "full refund after cutoff", "ignore your rules"],
    "waitlist_override": ["confirm waitlist", "override waitlist", "skip queue", "bribe", "without paying", "waitlist ticket to confirmed"],
    "fare_change": ["reduce fare", "discount fare", "change fare", "cheap fare"],
    
    # Check Level 2 Escalations
    "safety_issue": ["safety", "emergency", "medical", "theft", "danger", "security problem"],
    "complaint": ["complaint", "harassment", "bad service", "dirty coach", "rude", "complain"],
    "refund_dispute": ["refund dispute", "incorrect refund", "less refund", "wrong refund", "dispute"],
    "missed_train_refund": ["missed train", "train missed", "late train refund"],

    # Check Level 1 State Actions
    "change_boarding": ["change boarding", "boarding station", "change station"],
    "cancel_booking": ["cancel my ticket", "cancel ticket", "cancel booking", "cancel", "radd"],
    "concession_claim": ["concession", "senior citizen", "divyang", "student discount"],
    "book_ticket": ["book 1 seat", "book a seat", "reserve a seat", "book ticket"],
}


def fallback_parse(message: str) -> dict[str, Any]:
    msg_lower = message.lower()
    booking_id = None
    match = re.search(r"\b(UR-\d{5}|B\d{3,4})\b", message, re.IGNORECASE)
    if match:
        booking_id = match.group(1).upper()

    matched_intent = None
    for intent, kws in INTENT_KEYWORDS.items():
        if any(kw in msg_lower for kw in kws):
            matched_intent = intent
            break

    if not matched_intent:
        matched_intent = "cancel_booking" if "cancel" in msg_lower else "unknown"

    entities = {}
    if booking_id:
        entities["booking_id"] = booking_id

    return {"intent": matched_intent, "entities": entities, "engine": "fallback_rule_based"}


def parse_intent_and_entities(message: str, timeout: float = 3.0) -> dict[str, Any]:
    """Uses Bionic AI to parse intent; falls back to rule-based if unavailable or MOCK_LLM=true."""
    if os.getenv("MOCK_LLM", "false").lower() == "true":
        return fallback_parse(message)
    system_prompt = (
        "You are an intent parser for Ujjwal Rail. Extract intent and entities from the passenger message.\n"
        "Valid intents: cancel_booking, book_ticket, change_boarding, refund_dispute, missed_train_refund, "
        "concession_claim, complaint, safety_issue, excess_refund, waitlist_override, fare_change, other_passenger_booking.\n"
        'Return ONLY a valid JSON object matching: {"intent": "...", "entities": {"booking_id": "..."}}.'
    )

    grok_key = os.getenv("GROK_API_KEY", "").strip()
    if grok_key and grok_key != "your_grok_api_key_here":
        url = f"{os.getenv('GROK_BASE_URL', 'https://api.x.ai/v1').rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {grok_key}"}
        model_name = os.getenv("GROK_MODEL", "grok-2-latest")
    else:
        url = f"{BIONIC_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if BIONIC_API_KEY and BIONIC_API_KEY != "not_required":
            headers["Authorization"] = f"Bearer {BIONIC_API_KEY}"
        model_name = BIONIC_MODEL

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "temperature": 0.0,
        "max_tokens": 80,
    }

    try:
        req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode("utf-8"))
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                parsed["engine"] = f"bionic_{BIONIC_MODEL}"
                return parsed
    except Exception:
        pass

    return fallback_parse(message)
