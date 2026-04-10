"""
Hybrid RAG engine: BM25 keyword search + Ollama embedding cosine similarity,
combined via Reciprocal Rank Fusion (RRF).
"""
from __future__ import annotations

import json
import numpy as np
from rank_bm25 import BM25Okapi

from core.llm import embed as llm_embed
from logger import get_logger
from core.database import get_all_subsections_for_doc

logger = get_logger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return text.lower().split()


async def get_embedding(text: str) -> list[float] | None:
    """Delegate to the active LLM provider (Ollama or Gemini)."""
    return await llm_embed(text)


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over multiple ranked index lists."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── Public API ───────────────────────────────────────────────────────────────

async def hybrid_search(doc_id: str, query: str, top_k: int = 6) -> list[dict]:
    """
    Return top_k subsections most relevant to *query* from *doc_id*.
    Falls back to BM25-only if the Ollama embedding endpoint is unavailable.
    """
    subsections = get_all_subsections_for_doc(doc_id)
    if not subsections:
        logger.warning(f"No subsections for doc_id={doc_id}")
        return []

    corpus = [
        f"{s['subsection_title']} {s.get('content', '')} "
        f"{' '.join(s.get('keywords') or [])}"
        for s in subsections
    ]

    # ── BM25 ─────────────────────────────────────────────────────────────────
    tokenized = [_tokenize(doc) for doc in corpus]
    bm25 = BM25Okapi(tokenized)
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_ranking: list[int] = list(np.argsort(bm25_scores)[::-1])

    # ── Embedding similarity ──────────────────────────────────────────────────
    try:
        query_emb = await llm_embed(query)
        if query_emb is None:
            raise ValueError("No embedding returned")
        emb_scores: list[float] = []
        for s in subsections:
            stored = s.get("embedding")
            if stored:
                if isinstance(stored, str):
                    stored = json.loads(stored)
                emb_scores.append(_cosine(query_emb, stored))
            else:
                emb_scores.append(0.0)
        emb_ranking: list[int] = list(np.argsort(emb_scores)[::-1])
        fused = _rrf([bm25_ranking, emb_ranking])
    except Exception as exc:
        logger.warning(f"Embedding unavailable, BM25 only: {exc}")
        fused = [(i, float(bm25_scores[i])) for i in bm25_ranking]

    top_indices = [idx for idx, _ in fused[:top_k]]
    result = [subsections[i] for i in top_indices]
    logger.info(f"[RAG] Returned {len(result)} subsections for query='{query[:40]}'")
    return result
