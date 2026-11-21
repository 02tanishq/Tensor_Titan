"""
RAG Pipeline package for Ujjwal Rail.
Includes repository, chunker, hybrid retriever, exact-first lookup, precedence engine, and live ingestion.
"""

from RAG_pipeline.models import (
    SettingValue,
    DocumentChunk,
    Citation,
    ClashRecord,
    IngestPayload,
    IngestResult,
    RetrievalResult,
)
from RAG_pipeline.repository import RulesRepository, MissingSettingError
from RAG_pipeline.chunker import chunk_all_documents
from RAG_pipeline.safety import scan_doc_safety
from RAG_pipeline.exact_lookup import try_exact_lookup
from RAG_pipeline.precedence import filter_by_date, resolve_precedence
from RAG_pipeline.hybrid_retriever import HybridRetriever
from RAG_pipeline.ingest import upsert_document

__all__ = [
    "SettingValue",
    "DocumentChunk",
    "Citation",
    "ClashRecord",
    "IngestPayload",
    "IngestResult",
    "RetrievalResult",
    "RulesRepository",
    "MissingSettingError",
    "chunk_all_documents",
    "scan_doc_safety",
    "try_exact_lookup",
    "filter_by_date",
    "resolve_precedence",
    "HybridRetriever",
    "upsert_document",
]
