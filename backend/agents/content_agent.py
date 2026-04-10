"""
Content Agent — converts each planned slide's subsection into concise bullet points.
"""
from __future__ import annotations

import json

from core.llm import generate
from core.database import get_subsection
from logger import get_logger

logger = get_logger(__name__)

_PROMPT = """\
You are a slide content writer. Convert the subsection below into slide bullets.

Slide Title: {title}
Subsection Content:
{content}

Rules:
- Maximum 5 bullet points
- Each bullet: max 12 words
- Start with a strong verb or key fact
- No filler ("etc.", "and more", "in summary")
- If there is data/numbers, include them
- Infographic-first: note where a visual would help

Return ONLY a JSON array of bullet strings. No markdown, no explanation.
"""


def _parse_bullets(raw: str) -> list[str]:
    start, end = raw.find("["), raw.rfind("]") + 1
    if start != -1 and end > 0:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    # Fallback: split lines
    return [
        line.lstrip("-•* ").strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("[")
    ][:5]


async def content_node(state: dict) -> dict:
    plan: list[dict] = state.get("plan", [])
    logger.info(f"[Content] Generating bullets for {len(plan)} slides")
    slides: list[dict] = []

    for item in plan:
        title = item.get("title", "Slide")
        sub_id = item.get("subsection_id")
        slide_type = item.get("type", "content")

        # Fetch content from DB
        content_text = ""
        if sub_id:
            sub = get_subsection(sub_id)
            if sub:
                content_text = sub.get("content", "")

        if not content_text.strip():
            slides.append({"title": title, "content": [], "subsection_id": sub_id, "type": slide_type})
            continue

        prompt = _PROMPT.format(title=title, content=content_text[:2000])
        try:
            raw = await generate(prompt, temperature=0.2, max_tokens=512)
            bullets = _parse_bullets(raw)[:5]
        except Exception as exc:
            logger.warning(f"[Content] LLM failed for '{title}': {exc}")
            bullets = [content_text[:120].strip()]

        slides.append({
            "title": title,
            "content": bullets,
            "subsection_id": sub_id,
            "type": slide_type,
        })
        logger.debug(f"[Content] '{title}' -> {len(bullets)} bullets")

    return {"slides": slides, "error": None}
