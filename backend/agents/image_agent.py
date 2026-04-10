"""
Image Agent — fetches relevant images from Unsplash for each slide.
Only fetches for the first 4 slides to conserve API quota.
"""
from __future__ import annotations

import httpx
from config import settings
from logger import get_logger

logger = get_logger(__name__)


async def _unsplash_url(query: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.UNSPLASH_BASE_URL}/search/photos",
                params={
                    "query": query,
                    "per_page": 1,
                    "orientation": "landscape",
                    "content_filter": "high",
                },
                headers={"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return results[0]["urls"]["regular"]
    except Exception as exc:
        logger.warning(f"[Image] Unsplash failed for '{query}': {exc}")
    return None


async def image_node(state: dict) -> dict:
    slides: list[dict] = state.get("slides", [])
    images: dict[str, str] = {}

    # Limit to first 4 slides to stay within free-tier rate limits
    for i, slide in enumerate(slides[:4]):
        query = slide.get("title", "business presentation")
        url = await _unsplash_url(query)
        if url:
            images[str(i)] = url
            logger.debug(f"[Image] Slide {i}: fetched image")
        else:
            logger.debug(f"[Image] Slide {i}: no image")

    logger.info(f"[Image] {len(images)} images fetched")
    return {"images": images, "error": None}
