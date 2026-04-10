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
    """
    Fetch a single high-quality landscape image from Unsplash.
    
    Returns: Full URL to the image, or None if request fails
    """
    if not query:
        query = "business presentation"
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
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
            data = resp.json()
            results = data.get("results", [])
            
            if results:
                url = results[0].get("urls", {}).get("regular")
                if url:
                    logger.debug(f"[Image] Got Unsplash URL for '{query}': {url[:60]}...")
                    return url
                else:
                    logger.warning(f"[Image] No 'regular' URL in Unsplash result for '{query}'")
            else:
                logger.debug(f"[Image] No Unsplash results for '{query}'")
        return None
        
    except httpx.TimeoutException:
        logger.warning(f"[Image] Unsplash timeout for '{query}'")
        return None
    except httpx.HTTPError as exc:
        logger.warning(f"[Image] Unsplash HTTP error for '{query}': {exc}")
        return None
    except Exception as exc:
        logger.warning(f"[Image] Unsplash error for '{query}': {type(exc).__name__}: {exc}")
        return None


async def image_node(state: dict) -> dict:
    """
    Fetch images from Unsplash for first 4 slides (free-tier limit).
    
    Outputs:
        images (dict[str, str]): Map of slide index -> image URL
        error (str | None): Error message if fetching failed
    """
    slides: list[dict] = state.get("slides", [])
    images: dict[str, str] = {}

    if not slides:
        logger.warning("[Image] No slides available for image fetching")
        return {"images": images, "error": None}

    logger.info(f"[Image] Fetching images for {min(len(slides), 4)} slides (free-tier limit)")

    overall_query: str = state.get("query", "").strip()

    # Limit to first 4 slides to stay within free-tier rate limits
    for i, slide in enumerate(slides[:4]):
        title = slide.get("title", "business presentation")

        # Build a richer query: combine the deck topic with the slide title
        # so generic titles like "Further Reading" still return relevant images.
        if overall_query and overall_query.lower() not in title.lower():
            search_query = f"{overall_query} {title} professional"
        else:
            search_query = f"{title} professional corporate"

        logger.debug(f"[Image] Slide {i}: Fetching for '{search_query[:70]}'")

        url = await _unsplash_url(search_query)
        if url:
            images[str(i)] = url
            logger.info(f"[Image] Slide {i}: ✓ Image fetched (URL stored)")
        else:
            logger.debug(f"[Image] Slide {i}: ✗ No image found for '{title[:50]}'")

    logger.info(
        f"[Image] Image fetch complete: {len(images)}/4 images fetched | "
        f"Keys: {list(images.keys())}"
    )
    return {"images": images, "error": None}
