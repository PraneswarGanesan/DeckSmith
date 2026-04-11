"""
Retriever Agent — fetches ALL subsections for the document.

Design decision (vs. original BM25 approach):
  RAG / BM25 retrieval makes sense for open-ended Q&A ("find the 6 most relevant
  chunks for this question").  For a full-document → presentation conversion, that
  paradigm is wrong: it discards 80-90 % of the document before the planner even
  sees it.

  We now fetch EVERY subsection for the doc and let the Grouper + Planner decide
  what to include and how to prioritise it.  The Planner has the full picture and
  can build a coherent narrative from all sections instead of a BM25 fragment.

  BM25 ranking is still applied as a soft-sort so the most query-relevant content
  floats to the top — but nothing is discarded.
"""
from __future__ import annotations

import numpy as np
from rank_bm25 import BM25Okapi

from core.database import get_all_subsections_for_doc
from logger import get_logger

logger = get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _bm25_sort(subsections: list[dict], query: str) -> list[dict]:
    """
    Return subsections sorted by BM25 score (descending).
    All subsections are preserved — BM25 is used for ordering only.
    """
    if not subsections or not query.strip():
        return subsections

    corpus = [
        f"{s.get('subsection_title', '')} {s.get('content', '')} "
        f"{' '.join(s.get('keywords') or [])}"
        for s in subsections
    ]
    tokenized = [_tokenize(doc) for doc in corpus]
    try:
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(_tokenize(query))
        order = list(np.argsort(scores)[::-1])
        return [subsections[i] for i in order]
    except Exception as exc:
        logger.warning(f"[Retriever] BM25 sort failed ({exc}), using document order")
        return subsections


async def retriever_node(state: dict) -> dict:
    """
    Fetch ALL subsections for the document, BM25-sorted so the planner gets
    the most relevant content first.

    Inputs:
        query  (str): Presentation topic / user query (used for soft-ranking)
        doc_id (str): Document ID to fetch from

    Outputs:
        retrieved (list[dict]): ALL subsections, sorted by BM25 relevance
        error     (str | None): Error message if fetch failed
    """
    query  = state.get("query", "").strip() or "Overview"
    doc_id = state.get("doc_id", "").strip()

    if not doc_id:
        msg = "[Retriever] Missing doc_id — cannot retrieve"
        logger.error(msg)
        return {"retrieved": [], "error": msg}

    logger.info(f"[Retriever] Fetching ALL subsections for doc_id={doc_id[:8]}…")

    try:
        all_subs = get_all_subsections_for_doc(doc_id)

        if not all_subs:
            logger.warning(f"[Retriever] No subsections found for doc_id={doc_id}")
            return {"retrieved": [], "error": None}

        # Soft-sort by BM25 so the planner sees the most relevant content first,
        # but EVERY subsection is included.
        sorted_subs = _bm25_sort(all_subs, query)

        logger.info(
            f"[Retriever] Retrieved {len(sorted_subs)} subsections "
            f"(BM25-sorted) | query='{query[:50]}'"
        )
        return {"retrieved": sorted_subs, "error": None}

    except Exception as exc:
        msg = f"[Retriever] {exc}"
        logger.error(msg, exc_info=True)
        return {"retrieved": [], "error": msg}
