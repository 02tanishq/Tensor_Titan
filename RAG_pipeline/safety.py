"""
Safety and Injection Guard for Rules & Ingested Documents.
Scans document text as untrusted DATA for adversarial injection patterns
across English, Hindi, and Hinglish. Quarantines suspicious inputs before indexing.
"""

import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger("RAG_pipeline.safety")

# Patterns targeting jailbreaks, rule-overrides, prompt injections, and refund promises in EN, HI, Hinglish
INJECTION_PATTERNS = [
    # English injection & override patterns
    r"(?i)\bignore\s+(all\s+)?(previous\s+)?(rules|instructions|policies)\b",
    r"(?i)\bgive\s+(me\s+)?(a\s+)?full\s+refund\b",
    r"(?i)\boverride\s+(system|policy|security|safety)\b",
    r"(?i)\byou\s+are\s+now\s+(in\s+developer\s+mode|unrestricted)\b",
    r"(?i)\bdisregard\s+(the\s+)?(above|guidelines|restrictions)\b",
    r"(?i)\bpromise\s+(a\s+)?full\s+refund\b",
    r"(?i)\bpretend\s+to\s+be\b",
    r"(?i)\bsystem\s+prompt\b",
    r"(?i)\bhuman\s+approval\s+granted\b",
    # Hinglish & Hindi transliterated injection patterns
    r"(?i)\b(saare|sabhi)\s+(niyam|rules)\s+(bhool\s+jao|ignore\s+karo)\b",
    r"(?i)\bpura\s+paisa\s+(wapas|refund)\s+(karo|do)\b",
    r"(?i)\bfull\s+refund\s+de\s+do\b",
    r"(?i)\brules\s+mat\s+mano\b",
    r"(?i)\bmujhe\s+pura\s+refund\s+chahiye\b",
    # Devanagari Hindi injection patterns
    r"(?i)सारे\s+नियम\s+भूल\s+जाओ",
    r"(?i)पूरा\s+रिफंड\s+दो",
    r"(?i)सभी\s+निर्देशों\s+को\s+अनदेखा\s+करें",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in INJECTION_PATTERNS]


def scan_doc_safety(text: str) -> Tuple[bool, Optional[str]]:
    """
    Pure function to scan document text for instruction-like patterns.
    Returns (is_safe: bool, matched_reason: str | None).
    One-line reason: Treat all knowledge text as untrusted data to stop injection via ingested content.
    """
    if not text:
        return True, None

    for pattern in COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            reason = f"Quarantined due to prohibited instruction pattern: '{match.group(0)}'"
            logger.warning(reason)
            return False, reason

    return True, None
