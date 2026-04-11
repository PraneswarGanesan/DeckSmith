"""
Retriever Agent — fetches ALL subsections for the document.

Design Philosophy:
  A full-document → presentation conversion requires the LLM to see the ENTIRE
  document structure, not a BM25 fragment.  We fetch every subsection and sort by
  document order so the downstream Grouper → Planner pipeline has the complete picture.

  BM25 ranking is applied as a secondary sort only when the query is highly specific,
  but the default is DOCUMENT ORDER to preserve the author's narrative arc.
"""
from __future__ import annotations

from core.database import get_all_subsections_for_doc
from logger import get_logger

logger = get_logger(__name__)


async def retriever_node(state: dict) -> dict:
    """
    Fetch ALL subsections for the document in document order.

    No content is discarded.  No statistical ranking.  The LLM planner decides
    what to include and how to prioritise it.

    Inputs:
        query  (str): Presentation topic / user query
        doc_id (str): Document ID to fetch from

    Outputs:
        retrieved (list[dict]): ALL subsections in document order
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

        # Sort by document order (section_index → subsection_index) to preserve
        # the author's intended narrative arc.  The planner will decide what to
        # include and in what order.
        all_subs.sort(key=lambda x: (
            int(x.get("subsection_index", 0)),
        ))

        logger.info(
            f"[Retriever] Retrieved {len(all_subs)} subsections "
            f"(document order) | query='{query[:50]}'"
        )
        return {"retrieved": all_subs, "error": None}

    except Exception as exc:
        msg = f"[Retriever] {exc}"
        logger.error(msg, exc_info=True)
        return {"retrieved": [], "error": msg}
