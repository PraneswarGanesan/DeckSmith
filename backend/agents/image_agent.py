"""
Image Agent — fetches relevant images from Unsplash for slides that can show them.

Strategy:
  - Skip slides whose layout/intent never shows images (title, chart, centered, qna)
  - Fetch in parallel (capped to 5 concurrent calls to respect Unsplash rate limits)
  - Build a rich search query from slide title + overall query for relevance
  - Store as images[str(slide_index)] = URL (consumed by template_agent)
"""
from __future__ import annotations

import asyncio
import httpx
from config import settings
from logger import get_logger

logger = get_logger(__name__)

# Layouts/intents that cannot render an image — skip them to save quota
_NO_IMAGE_LAYOUTS = {"title", "chart", "centered", "qna", "agenda"}
_NO_IMAGE_INTENTS = {"intro", "qna", "conclusion"}

# Max concurrent Unsplash calls (free tier: 50 req/hour)
_SEMAPHORE = asyncio.Semaphore(5)


async def _unsplash_url(query: str) -> str | None:
    """
    Fetch a single high-quality landscape image from Unsplash.

    Returns: image URL string, or None if request fails / no results.
    """
    if not query:
        query = "business presentation professional"

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
                        logger.debug(f"[Image] Got URL for '{query[:60]}': {url[:60]}…")
                        return url
                    logger.warning(f"[Image] No 'regular' URL in result for '{query[:50]}'")
                else:
                    logger.debug(f"[Image] No Unsplash results for '{query[:60]}'")

        except httpx.TimeoutException:
            logger.warning(f"[Image] Unsplash timeout for '{query[:50]}'")
        except httpx.HTTPStatusError as exc:
            logger.warning(f"[Image] Unsplash HTTP {exc.response.status_code} for '{query[:50]}'")
        except httpx.HTTPError as exc:
            logger.warning(f"[Image] Unsplash HTTP error for '{query[:50]}': {exc}")
        except Exception as exc:
            logger.warning(f"[Image] Unsplash error for '{query[:50]}': {type(exc).__name__}: {exc}")

    return None


def _should_fetch_image(slide: dict) -> bool:
    """Return True if this slide's layout can render an image."""
    layout = (slide.get("layout") or "").lower()
    intent = (slide.get("intent") or "").lower()
    stype  = (slide.get("type")   or "").lower()

    if layout in _NO_IMAGE_LAYOUTS:
        return False
    if intent in _NO_IMAGE_INTENTS and layout not in ("left-text-right-visual", "grid-2"):
        return False
    if stype == "chart":
        return False
    return True


def _build_query(slide: dict, overall_query: str) -> str:
    """Build an Unsplash search query from slide context."""
    title = (slide.get("title") or "business").strip()

    # Combine topic + slide title for specificity
    if overall_query and overall_query.lower() not in title.lower():
        query = f"{overall_query} {title} professional"
    else:
        query = f"{title} professional corporate"

    return query[:120]  # Unsplash ignores very long queries


async def image_node(state: dict) -> dict:
    """
    Fetch images from Unsplash for every slide that can display one.

    Reads:  state["slides"], state["query"]
    Writes: state["images"]  — dict[str(slide_index), url]
            state["error"]   — None on success
    """
    slides: list[dict] = state.get("slides", [])
    images: dict[str, str] = {}

    if not slides:
        logger.warning("[Image] No slides available for image fetching")
        return {"images": images, "error": None}

    overall_query: str = state.get("query", "").strip()

    # Determine eligible slides and build fetch tasks
    eligible: list[tuple[int, str]] = []  # (slide_index, search_query)
    for i, slide in enumerate(slides):
        if _should_fetch_image(slide):
            q = _build_query(slide, overall_query)
            eligible.append((i, q))
            logger.debug(f"[Image] Slide {i} eligible: '{q[:70]}'")
        else:
            logger.debug(
                f"[Image] Slide {i} skipped "
                f"(layout={slide.get('layout')!r}, intent={slide.get('intent')!r})"
            )

    logger.info(
        f"[Image] Fetching images for {len(eligible)}/{len(slides)} eligible slides"
    )

    if not eligible:
        return {"images": images, "error": None}

    # Fetch in parallel (semaphore inside _unsplash_url limits concurrency)
    async def _fetch(idx: int, query: str) -> tuple[int, str | None]:
        url = await _unsplash_url(query)
        return idx, url

    results = await asyncio.gather(*[_fetch(i, q) for i, q in eligible])

    for idx, url in results:
        if url:
            images[str(idx)] = url
            logger.info(f"[Image] Slide {idx}: image fetched")
        else:
            logger.debug(f"[Image] Slide {idx}: no image found")

    logger.info(
        f"[Image] Done — {len(images)}/{len(eligible)} images fetched "
        f"(keys: {sorted(images.keys(), key=int)})"
    )
    return {"images": images, "error": None}
