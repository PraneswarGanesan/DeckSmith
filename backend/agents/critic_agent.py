"""
Critic Agent V2 — The Best Design Selector.

Design Philosophy:
  Replaces textual proofreading with visual architecture evaluation.
  Receives 3 blueprint variants for a slide and grades them on Balance,
  Hierarchy, and Contrast utilization to automatically select the optimal composition.
"""
from __future__ import annotations

import json
import re
import asyncio

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

_CRITIC_PROMPT = """\
You are an ELITE PRESENTATION DESIGN DIRECTOR. 
Your job is to evaluate 3 layout variations for a single slide's data and auto-select the best one.

EVALUATION CRITERIA:
1. Balance: Is the density appropriate for the slide intent? (e.g. Intro = low density)
2. Hierarchy: Does the primary data node get the highest priority?
3. Formatting: Is the composition aligned with Hackathon Awwwards-level design principles?

SLIDE INTENT: {intent}
VARIANTS TO EVALUATE:
{variants}

OUTPUT FORMAT:
Return exactly one JSON object:
{{
  "selected_variant_id": "A",
  "reasoning": "Variant A properly anchors the large $252B metric into a hero-grid..."
}}
Return ONLY JSON without markdown fences.
"""

def _extract_json_obj(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return {}

async def _evaluate_slide_variants(slide: dict) -> dict:
    variants = slide.get("variants", [])
    if not variants:
        logger.warning(f"No variants for slide '{slide.get('title')}'. Using default.")
        slide["composed_blueprint"] = {}
        return slide
    
    # If fallback hit
    if len(variants) == 1:
        slide["composed_blueprint"] = variants[0]
        return slide
        
    variants_str = json.dumps(variants, indent=2)
    prompt = _CRITIC_PROMPT.format(intent=slide.get("intent", "content"), variants=variants_str)
    
    try:
        raw = await generate(prompt, temperature=0.1, max_tokens=300)
        eval_data = _extract_json_obj(raw)
        sel_id = eval_data.get("selected_variant_id", "A")
        
        # Select matching variant
        chosen = next((v for v in variants if v.get("variant_id") == sel_id), variants[0])
        slide["composed_blueprint"] = chosen
        slide["design_reasoning"] = eval_data.get("reasoning", "")
    except Exception as e:
        logger.error(f"[Critic] Evaluation failed: {e}")
        slide["composed_blueprint"] = variants[0]
        
    return slide

async def critic_node(state: dict) -> dict:
    """Design-selector for every slide blueprint."""
    logger.info("[Critic V2] Grading layout compositions.")
    slides = state.get("slides", [])
    
    tasks = [_evaluate_slide_variants(s) for s in slides]
    critiqued_slides = await asyncio.gather(*tasks)
    
    return {"critiqued_slides": critiqued_slides, "error": None}
