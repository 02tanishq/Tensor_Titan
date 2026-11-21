"""
Document Section Chunker.
Splits rules, circulars, and FAQs into section-level chunks so every citation
strictly carries both doc_id and section name.
"""

import re
from typing import List, Dict, Any
from RAG_pipeline.models import DocumentChunk


def chunk_rule(rule_dict: Dict[str, Any]) -> List[DocumentChunk]:
    """
    Split a rule into sections matching 'Section <N>'.
    One-line reason: Fine-grained section chunking ensures accurate granular citations.
    """
    doc_id = rule_dict["doc_id"]
    title = rule_dict["title"]
    effective_from = rule_dict["effective_date"]
    content = rule_dict["content"]

    # Split by Section headers while retaining the header
    pattern = r"(Section\s+\d+[^:]*):"
    splits = re.split(pattern, content)

    chunks: List[DocumentChunk] = []

    if len(splits) > 1:
        # splits[0] is preface (often empty), then header1, text1, header2, text2...
        i = 1
        while i < len(splits):
            sec_header = splits[i].strip()
            sec_body = splits[i + 1].strip() if i + 1 < len(splits) else ""
            full_text = f"{sec_header}: {sec_body}"
            
            chunk = DocumentChunk(
                chunk_id=f"{doc_id}_{sec_header.replace(' ', '_')}",
                doc_id=doc_id,
                section=sec_header,
                doc_type="rule",
                effective_from=effective_from,
                supersedes=None,
                language="en",
                title=title,
                content=full_text,
                is_outdated=False
            )
            chunks.append(chunk)
            i += 2
    else:
        # Fallback if no sections detected
        chunks.append(DocumentChunk(
            chunk_id=f"{doc_id}_main",
            doc_id=doc_id,
            section="General",
            doc_type="rule",
            effective_from=effective_from,
            supersedes=None,
            language="en",
            title=title,
            content=content,
            is_outdated=False
        ))

    return chunks


def chunk_circular(circ_dict: Dict[str, Any]) -> List[DocumentChunk]:
    """
    Chunk circular documents. Circulars are typically focused policy updates.
    """
    doc_id = circ_dict["doc_id"]
    title = circ_dict["title"]
    effective_from = circ_dict["effective_date"]
    modifies_rule = circ_dict.get("modifies_rule")
    content = circ_dict["content"]
    language = circ_dict.get("language", "en")

    # Map meaningful section title from circular title or category
    section_name = "Revised Policy" if modifies_rule else "Notification"

    return [
        DocumentChunk(
            chunk_id=f"{doc_id}_main",
            doc_id=doc_id,
            section=section_name,
            doc_type="circular",
            effective_from=effective_from,
            supersedes=modifies_rule,
            language=language,
            title=title,
            content=content,
            is_outdated=False
        )
    ]


def chunk_faq(faq_dict: Dict[str, Any]) -> List[DocumentChunk]:
    """
    Convert FAQ to a DocumentChunk.
    """
    doc_id = faq_dict["faq_id"]
    question = faq_dict["question"]
    answer = faq_dict["answer"]
    category = faq_dict.get("category", "FAQ")
    language = faq_dict.get("language", "en")
    is_outdated = bool(faq_dict.get("is_outdated", 0))
    superseded_by = faq_dict.get("superseded_by")

    full_text = f"Q: {question}\nA: {answer}"

    return [
        DocumentChunk(
            chunk_id=f"{doc_id}_main",
            doc_id=doc_id,
            section=category,
            doc_type="faq",
            effective_from="2025-01-01",  # FAQs authored with base dataset
            supersedes=superseded_by,
            language=language,
            title=question,
            content=full_text,
            is_outdated=is_outdated
        )
    ]


def chunk_all_documents(docs_dict: Dict[str, List[Dict[str, Any]]]) -> List[DocumentChunk]:
    """
    Master chunker processing all rules, circulars, and faqs into unified DocumentChunk list.
    """
    chunks: List[DocumentChunk] = []

    for rule in docs_dict.get("rules", []):
        chunks.extend(chunk_rule(rule))

    for circ in docs_dict.get("circulars", []):
        chunks.extend(chunk_circular(circ))

    for faq in docs_dict.get("faqs", []):
        chunks.extend(chunk_faq(faq))

    return chunks
