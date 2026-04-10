"""
Critic Agent — reviews every slide's bullets and asks the LLM to improve
clarity, remove redundancy, and enforce the 12-word-per-bullet rule.
"""
from __future__ import annotations

import json

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

_PROMPT = """\
You are a presentation quality critic. Improve the bullet points below.

Slide Title: {title}
Current Bullets:
{bullets}

Rules:
- Keep exactly the same number of bullets (max 5)
- Each bullet: max 12 words, starts with a strong verb or key number
- Remove redundancy — every bullet must add unique value
- Make language crisp and scan-friendly
- Do NOT add new topics not present in the original

Return ONLY a JSON array of improved bullet strings. No markdown, no explanation.
"""


async def critic_node(state: dict) -> dict:
    slides: list[dict] = state.get("slides", [])
    logger.info(f"[Critic] Reviewing {len(slides)} slides")
    critiqued: list[dict] = []

    for slide in slides:
        bullets = slide.get("content", [])
        if not bullets:
            critiqued.append(slide)
            continue

        bullet_text = "\n".join(f"- {b}" for b in bullets)
        prompt = _PROMPT.format(title=slide["title"], bullets=bullet_text)

        try:
            raw = await generate(prompt, temperature=0.2, max_tokens=512)
            start, end = raw.find("["), raw.rfind("]") + 1
            if start != -1 and end > 0:
                improved: list[str] = json.loads(raw[start:end])
                # Only accept clean string bullets — reject if LLM returned garbage
                clean = [b for b in improved if isinstance(b, str) and len(b.split()) >= 2]
                if clean:
                    slide = {**slide, "content": clean[:5]}
        except Exception as exc:
            logger.warning(f"[Critic] Skipping '{slide['title']}': {exc}")

        critiqued.append(slide)

    logger.info("[Critic] Review complete")
    return {"critiqued_slides": critiqued, "error": None}
