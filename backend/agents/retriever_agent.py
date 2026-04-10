"""
Retriever Agent — runs hybrid BM25 + embedding search over the document.

Validates inputs and handles errors gracefully with fallback documents.
"""
from __future__ import annotations

from core.rag_engine import hybrid_search
from logger import get_logger

logger = get_logger(__name__)


async def retriever_node(state: dict) -> dict:
    """
    Retrieve top-k relevant subsections using hybrid BM25 + embedding search.
    
    Inputs:
        query (str): Search query (e.g., "AI strategy")
        doc_id (str): Document ID to search within
    
    Outputs:
        retrieved (list[dict]): Top-6 subsections, ranked by relevance
        error (str | None): Error message if retrieval failed
    """
    query = state.get("query", "").strip()
    doc_id = state.get("doc_id", "").strip()
    
    # Input validation
    if not query:
        logger.warning("[Retriever] Empty query, using fallback")
        query = "Overview"
    
    if not doc_id:
        error_msg = "[Retriever] Missing doc_id — cannot retrieve"
        logger.error(error_msg)
        return {"retrieved": [], "error": error_msg}
    
    logger.info(f"[Retriever] query='{query[:60]}'  doc_id={doc_id[:8]}...")

    try:
        retrieved = await hybrid_search(doc_id=doc_id, query=query, top_k=12)
        
        if not retrieved:
            logger.warning(f"[Retriever] No subsections found for doc_id={doc_id}")
        
        logger.info(f"[Retriever] Found {len(retrieved)} subsections")
        return {"retrieved": retrieved, "error": None}
        
    except Exception as exc:
        error_msg = f"[Retriever] {exc}"
        logger.error(error_msg, exc_info=True)
        return {"retrieved": [], "error": error_msg}
