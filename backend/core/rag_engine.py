"""
Hybrid RAG engine: BM25 keyword search + Ollama embedding cosine similarity,
combined via Reciprocal Rank Fusion (RRF).

Features:
  - Dual retrieval: BM25 (keyword) + embedding (semantic)
  - Fusion: Reciprocal Rank Fusion for balanced results
  - Fallback: Graceful degradation to BM25-only if embeddings unavailable
  - Caching: (Future) In-memory embedding cache to reduce Ollama calls
"""
from __future__ import annotations

import json
import numpy as np
from rank_bm25 import BM25Okapi

from core.llm import embed as llm_embed
from logger import get_logger
from core.database import get_all_subsections_for_doc

logger = get_logger(__name__)

# Simple embedding cache to reduce Ollama calls within a session
_embedding_cache: dict[str, list[float] | None] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 — lowercase split by whitespace."""
    return text.lower().split()


async def get_embedding(text: str) -> list[float] | None:
    """
    Get embedding with caching. Delegate to the active LLM provider.
    Returns None if the embedding endpoint fails (graceful fallback).
    """
    if text in _embedding_cache:
        return _embedding_cache[text]
    
    try:
        result = await llm_embed(text)
        _embedding_cache[text] = result
        return result
    except Exception as exc:
        logger.warning(f"[RAG] Embedding failed for query: {exc}")
        _embedding_cache[text] = None
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion over multiple ranked index lists.
    Combines BM25 and embedding rankings into a single merged ranking.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── Public API ───────────────────────────────────────────────────────────────

async def hybrid_search(doc_id: str, query: str, top_k: int = 6) -> list[dict]:
    """
    Return top_k subsections most relevant to *query* from *doc_id*.
    
    Algorithm:
      1. BM25 scoring (keyword-based relevance)
      2. Embedding similarity (semantic relevance) — skipped if unavailable
      3. Reciprocal Rank Fusion to combine both rankings
      4. Return top_k results
    
    Gracefully falls back to BM25 only if embeddings are unavailable.
    """
    subsections = get_all_subsections_for_doc(doc_id)
    if not subsections:
        logger.warning(f"[RAG] No subsections for doc_id={doc_id}")
        return []

    # Build corpus from subsection text + keywords
    corpus = [
        f"{s['subsection_title']} {s.get('content', '')} "
        f"{' '.join(s.get('keywords') or [])}"
        for s in subsections
    ]

    # ── BM25 scoring ──────────────────────────────────────────────────────────
    tokenized = [_tokenize(doc) for doc in corpus]
    bm25 = BM25Okapi(tokenized)
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_ranking: list[int] = list(np.argsort(bm25_scores)[::-1])
    logger.debug(f"[RAG] BM25 top-3: {bm25_ranking[:3]} (scores: {bm25_scores[bm25_ranking[0]]:.3f})")

    # ── Embedding similarity ──────────────────────────────────────────────────
    rankings_to_fuse = [bm25_ranking]
    
    query_emb = await get_embedding(query)
    if query_emb is not None:
        emb_scores: list[float] = []
        for s in subsections:
            stored = s.get("embedding")
            if stored:
                try:
                    if isinstance(stored, str):
                        stored = json.loads(stored)
                    emb_scores.append(_cosine(query_emb, stored))
                except (json.JSONDecodeError, TypeError):
                    emb_scores.append(0.0)
            else:
                emb_scores.append(0.0)
        
        emb_ranking: list[int] = list(np.argsort(emb_scores)[::-1])
        rankings_to_fuse.append(emb_ranking)
        logger.debug(f"[RAG] Embedding top-3: {emb_ranking[:3]} (score: {emb_scores[emb_ranking[0]]:.3f})")
    else:
        logger.info("[RAG] Embeddings unavailable, using BM25 only")

    # ── Reciprocal Rank Fusion ────────────────────────────────────────────────
    fused = _rrf(rankings_to_fuse)
    top_indices = [idx for idx, _ in fused[:top_k]]
    result = [subsections[i] for i in top_indices if i < len(subsections)]
    
    logger.info(
        f"[RAG] Retrieved {len(result)}/{len(subsections)} subsections | "
        f"query='{query[:40]}' | methods={len(rankings_to_fuse)}"
    )
    return result
