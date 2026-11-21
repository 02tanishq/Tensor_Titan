"""
Pydantic data models for Ujjwal Rail RAG Pipeline and Rules Repository.
All schemas are strictly typed and immutable where appropriate.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


class SettingValue(BaseModel):
    """Authoritative setting value directly from settings table."""
    name: str
    value: float
    source_doc: str


class DocumentChunk(BaseModel):
    """Section-level document chunk preserved for hybrid indexing and exact citations."""
    chunk_id: str
    doc_id: str
    section: str
    doc_type: Literal["rule", "circular", "faq"]
    effective_from: str  # YYYY-MM-DD
    supersedes: Optional[str] = None  # doc_id of rule or FAQ superseded/amended
    language: str = "en"  # en, hi, hi-en
    title: str
    content: str
    is_outdated: bool = False


class Citation(BaseModel):
    """Citation schema returned in all responses."""
    doc_id: str
    section: str


class ClashRecord(BaseModel):
    """Audit record when a newer or higher precedence document overrides an older one."""
    superseded_doc_id: str
    winning_doc_id: str
    reason: str
    as_of: str


class IngestPayload(BaseModel):
    """Payload for live document ingestion via POST /ingest."""
    doc_id: str
    doc_type: Literal["rule", "circular", "faq"]
    title: str
    content: str
    effective_from: str  # YYYY-MM-DD
    modifies_rule: Optional[str] = None
    language: str = "en"
    settings_update: Optional[dict[str, float]] = None  # Optional numeric parameters to update in settings table


class IngestResult(BaseModel):
    """Result of document ingestion."""
    doc_id: str
    status: Literal["SUCCESS", "QUARANTINED", "FAILED"]
    chunks_indexed: int = 0
    settings_updated: int = 0
    message: str
    quarantine_reason: Optional[str] = None


class RetrievalResult(BaseModel):
    """Result of hybrid retrieval with winning sources and detected clashes."""
    chunks: list[DocumentChunk]
    citations: list[Citation]
    clashes: list[ClashRecord]
    retrieval_method: Literal["exact", "hybrid"] = "hybrid"
