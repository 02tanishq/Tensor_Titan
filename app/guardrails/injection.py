"""
Prompt Isolation & Output Guardrail.
1. Wraps user text and retrieved context into isolated DATA blocks.
2. Scans for adversarial injections in EN/HI/Hinglish (flag and log, never obey).
3. Post-checks LLM outputs to reject unauthorized claims of execution, unbacked refund promises, or guaranteed approvals.
"""

import re
import logging
from typing import Tuple, Optional, List
from RAG_pipeline.safety import scan_doc_safety

logger = logging.getLogger("app.guardrails.injection")

UNAUTHORIZED_CHANGE_PATTERNS = [
    r"(?i)\b(your\s+booking|ticket)\s+has\s+been\s+(cancelled|changed|booked)\b",
    r"(?i)\bi\s+have\s+(cancelled|changed|booked)\s+your\b",
    r"(?i)\byour\s+refund\s+of\s+rs\.?\s*\d+\s+is\s+processed\b",
    r"(?i)\byour\s+request\s+is\s+approved\b",
    r"(?i)\bi\s+promise\s+you\s+(will\s+get|a\s+full)\b",
]

COMPILED_OUTPUT_PATTERNS = [re.compile(p) for p in UNAUTHORIZED_CHANGE_PATTERNS]


def isolate(message: str) -> Tuple[str, bool, Optional[str]]:
    """
    Wraps user message in explicit DATA boundaries and runs heuristic injection scan.
    One-line reason: Explicit delimiter blocks ensure the LLM treats user input as passive data, not system instructions.
    """
    is_safe, reason = scan_doc_safety(message)
    if not is_safe:
        logger.warning("Injection attempt flagged in user message: %s", reason)

    # Delimit message securely
    isolated_text = f"<<<UNTRUSTED_DATA>>>\n{message.strip()}\n<<<END_UNTRUSTED_DATA>>>"
    return isolated_text, is_safe, reason


def post_check_output(output_text: str, allowed_action_done: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validates generated output against unauthorized claims.
    One-line reason: Safeguards against hallucinated execution or unauthorized financial promises.
    """
    if allowed_action_done:
        # Action was legitimately confirmed via DB transaction, so completion claims are permitted
        return True, None

    for pattern in COMPILED_OUTPUT_PATTERNS:
        match = pattern.search(output_text)
        if match:
            reason = f"Post-check blocked output: claimed unauthorized execution or promise ('{match.group(0)}')"
            logger.error(reason)
            return False, reason

    return True, None
