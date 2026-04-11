"""
Image Agent — fetches contextually relevant images from Unsplash.

Design Philosophy:
  Images must feel INTENTIONAL, not generic.  Strategy:
    1. Build rich search queries from slide content keywords (not just title)
    2. Use a fallback strategy: specific → topic-level → abstract
    3. Skip slides that don't benefit from images
    4. Cache queries to avoid duplicate API calls
"""
from __future__ import annotations

import asyncio
import httpx
from config import settings
from logger import get_logger

logger = get_logger(__name__)

# Layouts/intents that should NOT have images
_NO_IMAGE_TYPES = {"chart", "metrics", "centered", "timeline"}
_NO_IMAGE_INTENTS = {"intro", "conclusion"}

# Max concurrent Unsplash calls (free tier: 50 req/hour)
_SEMAPHORE = asyncio.Semaphore(5)

# Query cache to avoid duplicate API calls
_query_cache: dict[str, str | None] = {}


async def _unsplash_url(query: str) -> str | None:
    """Fetch a single high-quality landscape image from Unsplash."""
    if not query:
        query = "business presentation professional"

    # Check cache
    if query in _query_cache:
        return _query_cache[query]

    async with _SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{settings.UNSPLASH_BASE_URL}/search/photos",
                    params={
                        "query":          query,
                        "per_page":       1,
                        "orientation":    "landscape",
                        "content_filter": "high",
                    },
                    headers={"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"},
                )
                resp.raise_for_status()
                data    = resp.json()
                results = data.get("results", [])

                if results:
                    url = results[0].get("urls", {}).get("regular")
                    if url:
                        _query_cache[query] = url
                        logger.debug(f"[Image] Got URL for '{query[:60]}': {url[:60]}…")
                        return url

        except httpx.TimeoutException:
            logger.warning(f"[Image] Unsplash timeout for '{query[:50]}'")
        except httpx.HTTPStatusError as exc:
            logger.warning(f"[Image] Unsplash HTTP {exc.response.status_code} for '{query[:50]}'")
        except Exception as exc:
            logger.warning(f"[Image] Unsplash error for '{query[:50]}': {type(exc).__name__}: {exc}")

    _query_cache[query] = None
    return None


def _should_fetch_image(slide: dict) -> bool:
    """Return True if this slide's layout can benefit from an image."""
    visual_type = (slide.get("visual_type") or slide.get("layout") or "").lower()
    intent = (slide.get("intent") or "").lower()
    stype = (slide.get("type") or "").lower()

    if visual_type in _NO_IMAGE_TYPES:
        return False
    if stype == "chart":
        return False
    if intent in _NO_IMAGE_INTENTS and visual_type != "left-text-right-visual":
        return False

    # Images work best with: grid, left-text-right-visual, cards
    return visual_type in ("grid", "left-text-right-visual", "cards", "comparison")


def _build_queries(slide: dict, overall_query: str) -> list[str]:
    """
    Build a LIST of Unsplash search queries from slide context.
    Returns most-specific first, with fallbacks.
    """
    title = (slide.get("title") or "").strip()
    design_intent = (slide.get("design_intent") or "").strip()
    data_extract = (slide.get("data_extract") or "").strip()
    intent = (slide.get("intent") or "").strip()

    queries = []

    # Most specific: title + design intent keywords
    if design_intent:
        # Extract key concepts from design_intent
        concepts = " ".join(w for w in design_intent.split() if len(w) > 3)[:60]
        queries.append(f"{concepts} professional corporate")

    # Specific: title + topic
    if title and overall_query:
        queries.append(f"{title} {overall_query} professional")

    # Medium: just the title
    if title:
        queries.append(f"{title} business corporate")

    # Broad: overall topic
    if overall_query:
        queries.append(f"{overall_query} professional presentation")

    # Ultra-broad fallback by intent
    intent_queries = {
        "problem": "business challenge risk analytics",
        "analysis": "data analytics business chart",
        "solution": "innovation technology solution",
        "policy": "governance compliance regulation",
        "results": "business growth success achievement",
    }
    if intent in intent_queries:
        queries.append(intent_queries[intent])

    # Last resort
    queries.append("professional business presentation")

    return queries[:4]  # max 4 attempts


async def image_node(state: dict) -> dict:
    """
    Fetch contextually relevant images for slides.

    Reads:  state["slides"], state["query"]
    Writes: state["images"] — dict[str(slide_index), url]
    """
    slides: list[dict] = state.get("slides", [])
    images: dict[str, str] = {}

    if not slides:
        return {"images": images, "error": None}

    overall_query: str = state.get("query", "").strip()

    # Determine eligible slides
    eligible: list[tuple[int, list[str]]] = []
    for i, slide in enumerate(slides):
        if _should_fetch_image(slide):
            queries = _build_queries(slide, overall_query)
            eligible.append((i, queries))

    logger.info(f"[Image] Fetching images for {len(eligible)}/{len(slides)} eligible slides")

    if not eligible:
        return {"images": images, "error": None}

    # Fetch with fallback strategy
    async def _fetch_with_fallback(idx: int, queries: list[str]) -> tuple[int, str | None]:
        for query in queries:
            url = await _unsplash_url(query)
            if url:
                return idx, url
        return idx, None

    results = await asyncio.gather(*[_fetch_with_fallback(i, q) for i, q in eligible])

    for idx, url in results:
        if url:
            images[str(idx)] = url
            logger.info(f"[Image] Slide {idx}: image fetched")
        else:
            logger.debug(f"[Image] Slide {idx}: no image found (all queries exhausted)")

    logger.info(
        f"[Image] Done — {len(images)}/{len(eligible)} images fetched"
    )
    return {"images": images, "error": None}
