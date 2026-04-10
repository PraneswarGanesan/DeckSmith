"""
Retriever Agent — runs hybrid BM25 + embedding search over the document.
"""
from __future__ import annotations

from core.rag_engine import hybrid_search
from logger import get_logger

logger = get_logger(__name__)


async def retriever_node(state: dict) -> dict:
    query = state.get("query", "")
    doc_id = state.get("doc_id", "")
    logger.info(f"[Retriever] query='{query[:60]}'  doc_id={doc_id}")

    try:
        retrieved = await hybrid_search(doc_id=doc_id, query=query, top_k=6)
        logger.info(f"[Retriever] Found {len(retrieved)} subsections")
        return {"retrieved": retrieved, "error": None}
    except Exception as exc:
        logger.error(f"[Retriever] {exc}")
        return {"retrieved": [], "error": str(exc)}
