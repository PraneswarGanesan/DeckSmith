"""
Critic Agent — design-aware quality review of every slide.

Design Philosophy:
  The critic is an ART DIRECTOR reviewing slide copy before a client presentation.
  It enforces:
    - 10-word max per bullet (tighter than the old 12-word rule)
    - Impact-formatted numbers ($5.2B not $5,200,000,000)
    - Strong verb or key number at the start of every bullet
    - No redundancy — every bullet adds unique value
    - Preserves ALL metadata (visual_type, design_intent, data_extract, etc.)
"""
from __future__ import annotations

import json
import re

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

_CRITIC_PROMPT = """\
You are an ART DIRECTOR reviewing slide copy for a Fortune 500 client presentation.
Polish the bullet points below to perfection.

Slide Title: {title}
Visual Type: {visual_type}
Current Bullets:
{bullets}

MANDATORY QUALITY RULES:
1. Keep exactly the same number of bullets (max 6)
2. Each bullet: MAX 10 WORDS.  Ruthlessly cut filler.
3. Start each bullet with a STRONG VERB (Drive, Achieve, Deploy, Target, Scale) or KEY NUMBER ($5.2B, 76%, 3x)
4. Format numbers for IMPACT:
   - Large currency → "$252B" not "$252,300,000,000"
   - Percentages → "76% growth" not "76.4 percent growth rate"
   - Multiples → "3x increase" not "a three-fold increase"
5. Remove redundancy — every bullet adds UNIQUE value
6. NO passive voice.  NO filler (basically, very, currently, essentially).
7. Make language CRISP and SCAN-FRIENDLY — a CEO should grasp each bullet in 2 seconds.
8. Do NOT add new topics not present in the original.

Return ONLY a JSON array of improved bullet strings. No markdown, no explanation.
"""


async def critic_node(state: dict) -> dict:
    """
    Design-aware quality review of all slides.

    Reads:  state["slides"]
    Writes: state["critiqued_slides"] — refined slides with ALL metadata preserved.
    """
    slides: list[dict] = state.get("slides", [])
    logger.info(f"[Critic] Reviewing {len(slides)} slides")
    critiqued: list[dict] = []

    for slide in slides:
        bullets = slide.get("content", [])

        # Skip slides with no bullets (title/conclusion slides)
        if not bullets:
            critiqued.append(slide)
            continue

        visual_type = slide.get("visual_type", slide.get("layout", "grid"))
        bullet_text = "\n".join(f"- {b}" for b in bullets)
        prompt = _CRITIC_PROMPT.format(
            title=slide.get("title", ""),
            visual_type=visual_type,
            bullets=bullet_text,
        )

        try:
            raw = await generate(prompt, temperature=0.2, max_tokens=512)

            # Robustly extract JSON array
            raw_clean = re.sub(r"```(?:json)?\s*", "", raw.strip())
            raw_clean = re.sub(r"```\s*$", "", raw_clean)

            start = raw_clean.find("[")
            end = raw_clean.rfind("]")
            if start != -1 and end > start:
                improved: list[str] = json.loads(raw_clean[start:end + 1])
                # Quality filter: only accept clean string bullets with 2+ words
                clean = [b for b in improved if isinstance(b, str) and len(b.split()) >= 2]
                if clean:
                    # PRESERVE all metadata — only replace content
                    slide = {**slide, "content": clean[:6]}

        except Exception as exc:
            logger.warning(f"[Critic] Skipping '{slide.get('title', '?')}': {exc}")

        critiqued.append(slide)

    logger.info("[Critic] Review complete")
    return {"critiqued_slides": critiqued, "error": None}
