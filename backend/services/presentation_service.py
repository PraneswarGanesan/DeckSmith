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
    
    Pipeline flow:
      1. Retriever: Fetch relevant subsections via hybrid RAG
      2. Planner: Create structured slide plan
      3. Content: Generate bullet points for each slide
      4. Chart: Build chart data from tables
      5. Image: Fetch images from Unsplash
      6. Critic: Review and improve bullets
      7. Template: Assemble final PPTX and upload
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
        
        # Validate pipeline completion
        if result.get("error"):
            raise RuntimeError(result["error"])
        
        # Verify PPTX was generated
        pptx_bytes = result.get("pptx_bytes")
        if not pptx_bytes or len(pptx_bytes) == 0:
            raise RuntimeError("Pipeline completed but no PPTX was generated")
        
        logger.info(
            f"[PresentationService] Pipeline complete  output_id={output_id} "
            f"size={len(pptx_bytes)} bytes  slides={len(result.get('critiqued_slides', []))}"
        )
    except Exception as exc:
        logger.error(f"[PresentationService] Pipeline FAILED: {exc}", exc_info=True)
        update_output(output_id, "failed")
