"""
Presentation Service — wires up a pre-created output record
and drives the LangGraph pipeline.
"""
from __future__ import annotations

from core.database import update_output
from core.graph import get_pipeline
from logger import get_logger

logger = get_logger(__name__)


async def run_pipeline(
    *,
    output_id: str,
    doc_id: str,
    template_id: str,
    query: str,
    user_id: str,
) -> None:
    """
    Execute the full multi-agent pipeline for a pre-created output record.
    Updates output status to "complete" or "failed" when done.
    """
    logger.info(f"[PresentationService] Pipeline start  output_id={output_id}")
    update_output(output_id, "processing")

    initial_state = {
        "query": query,
        "doc_id": doc_id,
        "template_id": template_id,
        "output_id": output_id,
        "user_id": user_id,
        # Intermediate fields — empty at start
        "retrieved": [],
        "plan": [],
        "slides": [],
        "charts": [],
        "images": {},
        "critiqued_slides": [],
        "pptx_bytes": b"",
        "error": None,
    }

    try:
        pipeline = get_pipeline()
        result = await pipeline.ainvoke(initial_state)
        if result.get("error"):
            raise RuntimeError(result["error"])
        logger.info(f"[PresentationService] Pipeline complete  output_id={output_id}")
    except Exception as exc:
        logger.error(f"[PresentationService] Pipeline FAILED: {exc}")
        update_output(output_id, "failed")
