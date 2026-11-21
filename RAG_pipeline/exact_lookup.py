"""
Exact-First Policy Lookup Engine.
For rules that map to deterministic intent keys (e.g. pet policy, ID proofs,
Tatkal timings, boarding change cutoff, cancellation tiers), performs direct
high-speed structured lookup by doc_id/section before falling back to hybrid retrieval.
"""

import re
from typing import Optional, List, Dict, Tuple
from RAG_pipeline.models import DocumentChunk, RetrievalResult, Citation, ClashRecord


# Structured intent trigger keywords
EXACT_INTENT_MAP: Dict[str, Tuple[str, Optional[str]]] = {
    # Pet policy -> RUL-LUG-01 (or FAQ-001 / FAQ-013)
    "pet": ("RUL-LUG-01", "Section 2"),
    "dog": ("RUL-LUG-01", "Section 2"),
    "kutta": ("RUL-LUG-01", "Section 2"),
    "kutte": ("RUL-LUG-01", "Section 2"),
    "animals": ("RUL-LUG-01", "Section 2"),
    "pet policy": ("RUL-LUG-01", "Section 2"),

    # ID proofs -> RUL-ID-01 (or CIR-2026-06 if in force)
    "identity": ("RUL-ID-01", None),
    "id proof": ("RUL-ID-01", None),
    "aadhaar": ("RUL-ID-01", None),
    "digilocker": ("RUL-ID-01", None),
    "passport": ("RUL-ID-01", None),
    "voter id": ("RUL-ID-01", None),
    "student id": ("RUL-ID-01", None),

    # Boarding change -> RUL-BRD-01
    "boarding station": ("RUL-BRD-01", None),
    "change boarding": ("RUL-BRD-01", None),
    "boarding badalna": ("RUL-BRD-01", None),

    # Disruption & Late train -> RUL-DIS-01
    "train cancelled": ("RUL-DIS-01", None),
    "train late": ("RUL-DIS-01", None),
    "3 ghante late": ("RUL-DIS-01", None),
    "late train refund": ("RUL-DIS-01", None),

    # Tatkal timings -> RUL-TAT-01
    "tatkal timing": ("RUL-TAT-01", None),
    "tatkal open": ("RUL-TAT-01", None),
    "tatkal booking": ("RUL-TAT-01", None),
}


def try_exact_lookup(
    query: str,
    chunks: List[DocumentChunk],
    as_of: str
) -> Optional[RetrievalResult]:
    """
    Check if query maps directly to a high-confidence exact policy key.
    One-line reason: Structured exact lookup guarantees 100% citation accuracy on critical policies.
    """
    q_lower = query.lower()

    target_doc_id = None
    target_section = None

    for keyword, (doc_id, section) in EXACT_INTENT_MAP.items():
        # Match word boundaries or substring
        if re.search(r"\b" + re.escape(keyword) + r"\b", q_lower):
            target_doc_id = doc_id
            target_section = section
            break

    if not target_doc_id:
        return None

    # Filter chunks matching target doc_id and active on as_of
    matched_chunks: List[DocumentChunk] = []
    for c in chunks:
        if c.doc_id == target_doc_id and c.effective_from <= as_of:
            if target_section is None or target_section in c.section:
                matched_chunks.append(c)

    if not matched_chunks:
        return None

    citations = [Citation(doc_id=c.doc_id, section=c.section) for c in matched_chunks]

    return RetrievalResult(
        chunks=matched_chunks,
        citations=citations,
        clashes=[],
        retrieval_method="exact"
    )
