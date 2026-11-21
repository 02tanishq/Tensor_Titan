"""
Hybrid Knowledge Retriever for Ujjwal Rail.
Combines:
1. Exact-first structured lookup (for standard policy keys)
2. Keyword retrieval via BM25 (rank_bm25)
3. Multilingual Dense Semantic Vector search
4. Reciprocal Rank Fusion (RRF) for merging results
5. Query-time temporal precedence filtering by as_of date
"""

import math
import re
import numpy as np
from typing import List, Dict, Optional, Tuple, Set
try:
    from rank_bm25 import BM25Okapi
except ImportError:
    class BM25Okapi:
        """Pure-Python BM25Okapi implementation for environments without rank_bm25."""
        def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
            self.k1 = k1
            self.b = b
            self.corpus_size = len(corpus)
            self.doc_lens = np.array([len(doc) for doc in corpus], dtype=np.float32)
            self.avgdl = float(np.mean(self.doc_lens)) if self.corpus_size > 0 else 1.0
            self.doc_freqs: List[Dict[str, int]] = []
            self.nd: Dict[str, int] = {}
            for doc in corpus:
                df = {}
                for word in doc:
                    df[word] = df.get(word, 0) + 1
                self.doc_freqs.append(df)
                for word in df:
                    self.nd[word] = self.nd.get(word, 0) + 1
            self.idf = {}
            for word, freq in self.nd.items():
                self.idf[word] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1)

        def get_scores(self, query: List[str]) -> np.ndarray:
            scores = np.zeros(self.corpus_size, dtype=np.float32)
            for word in query:
                if word not in self.idf:
                    continue
                w_idf = self.idf[word]
                for i, df in enumerate(self.doc_freqs):
                    freq = df.get(word, 0)
                    if freq > 0:
                        numerator = freq * (self.k1 + 1)
                        denominator = freq + self.k1 * (1 - self.b + self.b * (self.doc_lens[i] / self.avgdl))
                        scores[i] += w_idf * (numerator / denominator)
            return scores

from RAG_pipeline.models import DocumentChunk, RetrievalResult, Citation, ClashRecord
from RAG_pipeline.chunker import chunk_all_documents
from RAG_pipeline.repository import RulesRepository
from RAG_pipeline.exact_lookup import try_exact_lookup
from RAG_pipeline.precedence import filter_by_date, resolve_precedence


def tokenize(text: str) -> List[str]:
    """
    Multilingual tokenizer preserving English words, numbers, and Devanagari Hindi words.
    One-line reason: Preserves Indian train terminology, Hindi characters, and station codes accurately.
    """
    if not text:
        return []
    # Match alphanumeric words or Devanagari script blocks
    tokens = re.findall(r"[\w\u0900-\u097F]+", text.lower())
    return tokens


class DenseVectorIndex:
    """
    Fast, deterministic multilingual dense vector index using character & subword n-grams.
    Provides semantic similarity across English, Hindi, and Hinglish transliteration without external downloads.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.vectors: np.ndarray = np.empty((0, dim), dtype=np.float32)
        self.chunk_ids: List[str] = []

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = tokenize(text)
        if not tokens:
            return vec

        for token in tokens:
            # Word hash
            h_word = hash(token) % self.dim
            vec[h_word] += 2.0
            # Character 3-grams for morphology and Hinglish spelling robustness
            padded = f"^{token}$"
            for i in range(len(padded) - 2):
                ng = padded[i:i+3]
                h_ng = hash(ng) % self.dim
                vec[h_ng] += 1.0

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def index(self, chunks: List[DocumentChunk]) -> None:
        if not chunks:
            self.vectors = np.empty((0, self.dim), dtype=np.float32)
            self.chunk_ids = []
            return

        vec_list = [self._embed(f"{c.title} {c.section} {c.content}") for c in chunks]
        self.vectors = np.vstack(vec_list)
        self.chunk_ids = [c.chunk_id for c in chunks]

    def query(self, query_text: str, top_k: int = 10) -> List[Tuple[str, float]]:
        if len(self.chunk_ids) == 0:
            return []
        q_vec = self._embed(query_text)
        sims = np.dot(self.vectors, q_vec)
        top_indices = np.argsort(-sims)[:top_k]
        return [(self.chunk_ids[i], float(sims[i])) for i in top_indices]


class HybridRetriever:
    """
    Unified knowledge retriever maintaining in-memory BM25 and Dense Vector indices.
    Supports instant hot-reloading via upsert_document().
    """

    def __init__(self, repository: RulesRepository):
        self.repository = repository
        self.chunks: List[DocumentChunk] = []
        self.bm25: Optional[BM25Okapi] = None
        self.vector_index: DenseVectorIndex = DenseVectorIndex(dim=256)
        self.reload()

    def reload(self) -> None:
        """
        Loads all documents from repository and rebuilds both search indexes.
        One-line reason: Ensures hot reload and live ingest immediately populate the search space.
        """
        # Fetch all documents regardless of date for index building; temporal filtering happens at query time
        docs = self.repository.get_documents(as_of="2099-12-31")
        self.chunks = chunk_all_documents(docs)

        # Build BM25 index
        corpus = [tokenize(f"{c.title} {c.section} {c.content}") for c in self.chunks]
        if corpus:
            self.bm25 = BM25Okapi(corpus)
        else:
            self.bm25 = None

        # Build Dense Vector index
        self.vector_index.index(self.chunks)

    def retrieve(
        self,
        query: str,
        as_of: str = "2026-11-21",
        top_k: int = 5
    ) -> RetrievalResult:
        """
        Executes exact-first lookup, falling back to hybrid BM25 + dense search with RRF and precedence resolution.
        """
        # 1. Exact-first structured lookup
        exact_res = try_exact_lookup(query, self.chunks, as_of)
        if exact_res and exact_res.chunks:
            # Check for any clashes on exact match
            winning_chunks, winning_cit, clashes = resolve_precedence(
                exact_res.chunks, self.chunks, as_of
            )
            return RetrievalResult(
                chunks=winning_chunks,
                citations=winning_cit,
                clashes=clashes,
                retrieval_method="exact"
            )

        # 2. Filter available chunks by as_of date
        active_chunks = filter_by_date(self.chunks, as_of)
        if not active_chunks:
            return RetrievalResult(chunks=[], citations=[], clashes=[], retrieval_method="hybrid")

        # Map chunk_id to DocumentChunk
        chunk_map = {c.chunk_id: c for c in active_chunks}

        # 3. BM25 Search
        bm25_ranks: Dict[str, int] = {}
        if self.bm25:
            q_tokens = tokenize(query)
            bm25_scores = self.bm25.get_scores(q_tokens)
            # Rank candidates
            sorted_indices = np.argsort(-bm25_scores)
            rank = 1
            for idx in sorted_indices:
                c = self.chunks[idx]
                if c.chunk_id in chunk_map and bm25_scores[idx] > 0.05:
                    bm25_ranks[c.chunk_id] = rank
                    rank += 1
                if rank > 20:
                    break

        # 4. Dense Vector Search
        dense_results = self.vector_index.query(query, top_k=20)
        dense_ranks: Dict[str, int] = {}
        rank = 1
        for cid, sim in dense_results:
            if cid in chunk_map and sim > 0.05:
                dense_ranks[cid] = rank
                rank += 1

        # 5. Reciprocal Rank Fusion (RRF)
        all_candidate_ids: Set[str] = set(bm25_ranks.keys()).union(set(dense_ranks.keys()))
        rrf_scores: Dict[str, float] = {}
        k_constant = 60

        for cid in all_candidate_ids:
            score = 0.0
            if cid in bm25_ranks:
                score += 1.0 / (k_constant + bm25_ranks[cid])
            if cid in dense_ranks:
                score += 1.0 / (k_constant + dense_ranks[cid])
            rrf_scores[cid] = score

        # Sort by RRF score
        sorted_candidates = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
        top_candidates = [chunk_map[cid] for cid, _ in sorted_candidates[:top_k]]

        # 6. Apply Temporal Precedence & Clash Resolution
        winning_chunks, citations, clashes = resolve_precedence(
            top_candidates, self.chunks, as_of
        )

        return RetrievalResult(
            chunks=winning_chunks,
            citations=citations,
            clashes=clashes,
            retrieval_method="hybrid"
        )
