"""
Visual Composer Agent — the master layout stylist.

Design Philosophy:
  Unlike the old approach of arbitrarily drawing rectangles on a Blank slide,
  the modern Stylist operates semantically. It analyzes the specific placeholder
  inventory of the User's uploaded template and intelligently maps the written
  content directly into the BEST natively-matching slide layout.
  
  This ensures "Awwwards-level", perfect aesthetic adherence to the template.
"""
from __future__ import annotations

import asyncio
import json
import re

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)


_STYLIST_PROMPT = """\
You are an ELITE PRESENTATION STYLIST.
You must map the slide content into the best available native PPTX layout from the user's template.

SLIDE TO STYLE:
Title: {title}
Intent: {intent}
Bullets:
{bullets}

TEMPLATE LAYOUT SCHEMA AVAILABLE:
{schema_text}

YOUR TASK:
1. Choose the single best 'layout_index' from the schema above.
   - For 'intro', find a layout with a big 'title' and 'subtitle' (often index 0).
   - For 'content' with lots of bullets, find a layout with a large 'body' placeholder.
   - For 'cards' or 'comparison', look for layouts with multiple 'body' placeholders side-by-side.
2. Provide an exact mapping of slide text to placeholder 'idx' values.
   - You MUST match the placeholder 'idx' strings exactly as they appear in the schema.
   - Mapping values should be the actual string content intended for that placeholder.

OUTPUT JSON FORMAT:
{{
   "layout_index": <int>,
   "mappings": {{
       "<idx_from_schema>": "Content string to insert here",
       "<idx_from_schema>": "Other content..."
   }}
}}

Return ONLY the JSON object. No explanation.
"""

def _extract_json_object(raw: str) -> dict | None:
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


async def _style_slide(slide: dict, schema: list[dict]) -> dict:
    """Map slide content into the perfect native layout."""
    
    # If no schema available, fallback to basic visual_structure
    if not schema:
        # We will handle fallback drawing in template_agent if native_mapping is None
        return slide
        
    schema_text = json.dumps(schema, indent=2)
    bullets_text = "\n".join(f"- {b}" for b in slide.get("content", []))
    
    prompt = _STYLIST_PROMPT.format(
        title=slide.get("title", ""),
        intent=slide.get("intent", "content"),
        bullets=bullets_text,
        schema_text=schema_text
    )
    
    try:
        raw = await generate(prompt, temperature=0.2, max_tokens=1500)
        mapping_data = _extract_json_object(raw)
        
        if mapping_data and "layout_index" in mapping_data and "mappings" in mapping_data:
             slide["native_mapping"] = mapping_data
             return slide
             
    except Exception as exc:
        logger.warning(f"[Stylist] Failed to map layout for '{slide.get('title')}': {exc}")
        
    return slide


async def visual_composer_node(state: dict) -> dict:
    """
    Transforms critique slides by mapping them perfectly into the template schema.
    """
    if state.get("error"):
        return {"error": state["error"]}

    slides: list[dict] = state.get("critiqued_slides") or state.get("slides", [])
    schema: list[dict] = state.get("template_schema", [])
    
    if not slides:
        return {"slides": [], "error": None}

    logger.info(f"[Stylist] Mapping {len(slides)} slides into template layouts...")

    tasks = [_style_slide(slide, schema) for slide in slides]
    composed = await asyncio.gather(*tasks)

    mapped_count = sum(1 for s in composed if "native_mapping" in s)
    logger.info(f"[Stylist] Successfully mapped {mapped_count}/{len(composed)} slides to native layouts.")
    
    return {"slides": composed, "error": None}
