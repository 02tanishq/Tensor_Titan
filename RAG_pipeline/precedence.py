"""
Rule Precedence & Temporal Filtering Engine.
Applies date-based validity and document hierarchy:
1. Filters out documents where effective_from > as_of (e.g. future-dated circulars).
2. Circular beats the Rule it modifies.
3. Official Rule & Circular beats any FAQ.
4. If a superseded document was retrieved, excludes it and logs a clash record for audit.
"""

from typing import List, Tuple, Dict, Set
from RAG_pipeline.models import DocumentChunk, ClashRecord, Citation


def filter_by_date(chunks: List[DocumentChunk], as_of: str) -> List[DocumentChunk]:
    """
    Drop chunks whose effective_from is in the future relative to as_of.
    One-line reason: Future circulars like CIR-2026-05 must stay completely hidden until effective date.
    """
    as_of_date = as_of[:10]
    return [c for c in chunks if c.effective_from <= as_of_date]


def resolve_precedence(
    retrieved_chunks: List[DocumentChunk],
    all_chunks: List[DocumentChunk],
    as_of: str
) -> Tuple[List[DocumentChunk], List[Citation], List[ClashRecord]]:
    """
    Applies precedence ordering on retrieved chunks:
    - Circular > Rule (for modified rule)
    - Rule/Circular > FAQ
    Returns (winning_chunks, winning_citations, detected_clashes).
    One-line reason: Legal hierarchy dictates revised circulars always override base rules and stale FAQs.
    """
    as_of_date = as_of[:10]

    # Map all active circulars that modify rules
    active_circular_mods: Dict[str, str] = {}  # rule_doc_id -> circular_doc_id
    for c in all_chunks:
        if c.doc_type == "circular" and c.effective_from <= as_of_date and c.supersedes:
            active_circular_mods[c.supersedes] = c.doc_id

    # Map outdated FAQs
    outdated_faqs: Dict[str, str] = {}  # faq_id -> superseded_by
    for c in all_chunks:
        if c.doc_type == "faq" and c.is_outdated and c.supersedes:
            outdated_faqs[c.doc_id] = c.supersedes

    winning_chunks: List[DocumentChunk] = []
    clashes: List[ClashRecord] = []
    seen_chunk_keys: Set[str] = set()

    for chunk in retrieved_chunks:
        # Check if future-dated
        if chunk.effective_from > as_of_date:
            continue

        # Check if FAQ is outdated by an active circular or rule
        if chunk.doc_type == "faq" and chunk.doc_id in outdated_faqs:
            winning_doc = outdated_faqs[chunk.doc_id]
            clash = ClashRecord(
                superseded_doc_id=chunk.doc_id,
                winning_doc_id=winning_doc,
                reason=f"FAQ {chunk.doc_id} is outdated and superseded by {winning_doc}",
                as_of=as_of_date
            )
            clashes.append(clash)
            continue  # Exclude outdated FAQ from final answer

        # Check if Rule is modified by an active circular
        if chunk.doc_type == "rule" and chunk.doc_id in active_circular_mods:
            circular_id = active_circular_mods[chunk.doc_id]
            # If the query relates to the modified portion, circular takes precedence
            # We check if any chunk from circular_id is present or should replace it
            circ_chunks = [c for c in all_chunks if c.doc_id == circular_id and c.effective_from <= as_of_date]
            if circ_chunks:
                clash = ClashRecord(
                    superseded_doc_id=chunk.doc_id,
                    winning_doc_id=circular_id,
                    reason=f"Rule {chunk.doc_id} amended by Circular {circular_id} effective {circ_chunks[0].effective_from}",
                    as_of=as_of_date
                )
                clashes.append(clash)
                # Include the winning circular chunk instead of the superseded rule chunk
                for cc in circ_chunks:
                    key = f"{cc.doc_id}:{cc.section}"
                    if key not in seen_chunk_keys:
                        seen_chunk_keys.add(key)
                        winning_chunks.append(cc)
                continue

        key = f"{chunk.doc_id}:{chunk.section}"
        if key not in seen_chunk_keys:
            seen_chunk_keys.add(key)
            winning_chunks.append(chunk)

    # Build deduplicated citations
    citations: List[Citation] = []
    seen_citations: Set[Tuple[str, str]] = set()
    for c in winning_chunks:
        cit_tuple = (c.doc_id, c.section)
        if cit_tuple not in seen_citations:
            seen_citations.add(cit_tuple)
            citations.append(Citation(doc_id=c.doc_id, section=c.section))

    return winning_chunks, citations, clashes
