"""
Blueprint Agent & Slide Variations Engine.

Design Philosophy:
  Determines exact relational rules, composition grids, and generates 3 layout
  variants per slide to guarantee intelligent presentation choices.
"""
from __future__ import annotations

import json
import re
import asyncio

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

_BLUEPRINT_PROMPT = """\
You are an ELITE VISUAL COMPOSITION ENGINE. Your job is to analyze the isolated structural data 
for a slide and generate exactly 3 visual layout variations to pass to the Critic.

Determine relationship matrices (if trend -> line_chart).
Determine visual focus (if single big number -> hero_metric).
Set density scaling (low/medium/high).
Enforce hierarchy weights for the extracted data elements.

INPUT DATA ELEMENTS:
{extracted_data}
SLIDE INTENT: {intent}

Generate exactly 3 "variants" for this slide.
JSON OUTPUT FORMAT:
[
  {{
    "variant_id": "A",
    "visual_type": "bar_chart | line_chart | metric_cards | hero_metric | left-text-right-visual",
    "density": "low | medium | high",
    "rhythm": "centered | left-heavy | right-heavy | grid",
    "composition": {{
      "grid": "2-column | 1-column",
      "alignment": "center-left | center | top-heavy"
    }},
    "hierarchy": [
      {{"element_type": "chart", "priority": 1}},
      {{"element_type": "insight_label", "priority": 2}}
    ],
    "notes": "Speaker notes predicting narrative flow."
  }}, ...
]

Return ONLY the raw JSON array.
"""

def _extract_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return []

async def _generate_variants(slide: dict) -> dict:
    data_str = json.dumps(slide.get("extracted_data", []), indent=2)
    prompt = _BLUEPRINT_PROMPT.format(extracted_data=data_str, intent=slide.get("intent", "content"))
    
    try:
        raw = await generate(prompt, temperature=0.7, max_tokens=1000)
        variants = _extract_json_array(raw)
        if not variants:
            raise ValueError("No variants returned.")
        slide["variants"] = variants
    except Exception as e:
        logger.error(f"[Blueprint] Variation failure for '{slide.get('title')}': {e}")
        # Phase 3 Safe Fallback
        slide["variants"] = [{
            "variant_id": "A",
            "visual_type": "metric_cards",
            "density": "medium",
            "rhythm": "centered",
            "composition": {"grid": "1-column", "alignment": "center"},
            "hierarchy": [{"element_type": "insight_label", "priority": 1}],
            "notes": "System Error: Safe fallback triggered."
        }]
    return slide

async def blueprint_node(state: dict) -> dict:
    logger.info("[Blueprint] Generating competitive layout variations for all slides.")
    slides = state.get("slides", [])
    
    tasks = [_generate_variants(s) for s in slides]
    blueprint_slides = await asyncio.gather(*tasks)
    
    return {"slides": blueprint_slides, "error": None}
