"""
Planner Agent — the senior presentation designer drafting the story arc.

Design Philosophy:
  The planner does NOT just copy-paste sections. It establishes a compelling
  NARRATIVE ARC suitable for an audience. A professional deck must have:
    1. Title Slide (intro)
    2. Agenda/Table of Contents (agenda)
    3. Introduction/Executive Summary (summary)
    4. Body Content (metrics, process, comparisons, charts, timelines) (content)
    5. Conclusion/Takeaways (conclusion)
    6. Q&A / Thank You (qna)

  For each slide in the body, it must decide on the best visual_type
  to represent the data (cards, process, timeline, metrics, comparison, chart, grid).
"""
from __future__ import annotations

import json
import re

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

_PLANNER_PROMPT = """\
You are a SENIOR PRESENTATION DESIGNER. Your job is to transform a raw document
into a compelling, 10-15 slide presentation story arc.

YOU MUST NOT JUST COPY-PASTE. You are crafting a professional narrative.

The presentation MUST follow this strict structural arc:
1. "intro": The main Title Slide
2. "agenda": Table of Contents / Agenda
3. "summary": Executive Summary / Introduction
4. "content": The core body slides (metrics, challenges, processes, data)
5. "conclusion": Key Takeaways / Next Steps
6. "qna": Questions / Thank you slide

AVAILABLE VISUAL TYPES FOR CONTENT SLIDES:
  - metrics: Use when there are 3-4 key numbers/KPIs (e.g. "$5.2B", "76%")
  - process: Use for sequential steps (Step 1, Step 2...)
  - timeline: Use for historical or future roadmaps with dates
  - cards: Use for 3-6 distinct concepts that deserve equal weight
  - comparison: Use for "Before vs After", "Pros vs Cons", "Current vs Target"
  - chart: ONLY use if the subsection contains a [TABLE: ...] tag!
  - left-text-right-visual: Text on left, image on right
  - grid: Standard bullet points (use sparingly)
  - centered: A single big impactful statement

INPUT DOCUMENT KNOWLEDGE (Grouped Sections):
{doc_context}

OUTPUT FORMAT RULES:
Return a JSON array of slide objects. EACH array element MUST have exactly these fields:
- "title": (string) Short, punchy slide title (max 6 words). E.g. "The AI Investment Surge"
- "intent": (string) The story phase: "intro", "agenda", "summary", "content", "conclusion", or "qna".
- "visual_type": (string) Pick from the available visual types above.
- "design_intent": (string) Instruction for the stylist. E.g. "Show 3 big numbers highlighting market growth."
- "subsection_id": (string or null) The ID of the primary subsection to source data from. Use null for Intro/Agenda/QnA if you don't need direct text.
- "data_extract": (string) Specific highlights to pull out (e.g. "Highlight the £2.4M savings").

Ensure chronological narrative flow.
Return ONLY the JSON array. Do not include markdown formatting or explanations.
"""

def _extract_json_array(raw: str) -> list[dict] | None:
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?\s*", "", raw)
    raw = re.sub(r"```\s*$", "", raw)

    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None

async def planner_node(state: dict) -> dict:
    grouped: list[dict] = state.get("grouped", [])
    query: str = state.get("query", "Executive Presentation")

    if not grouped:
        logger.warning("[Planner] No grouped content provided")
        return {"plan": [], "error": "No content groups"}

    # Build context summary specifically for the LLM
    context_lines = []
    for g in grouped:
        sec_title = g.get("section_title", "Section")
        context_lines.append(f"== SECTION: {sec_title} ==")
        for sub in g.get("subsections", []):
            stitle = sub.get("subsection_title", "")
            sid = sub.get("id", "")
            sumry = sub.get("summary", "")[:200]
            tables = sub.get("tables", [])
            tag = " [CONTAINS TABLE]" if tables else ""
            context_lines.append(f"  - SUBSECTION '{stitle}' (ID: {sid}){tag}: {sumry}...")

    doc_context = "\n".join(context_lines)
    prompt = _PLANNER_PROMPT.format(doc_context=doc_context)

    logger.info("[Planner] Generating presentation story arc (LLM)")

    try:
        raw_response = await generate(prompt, temperature=0.3, max_tokens=3000)
        print("PLANNER RAW:", raw_response)
        plan = _extract_json_array(raw_response)

        if not plan:
            logger.error(f"[Planner] Failed to parse JSON array from response:\n{raw_response[:200]}...")
            raise RuntimeError("LLM returned malformed JSON for plan")

        # Validate layout of the plan
        for idx, slide in enumerate(plan):
            if "title" not in slide: slide["title"] = f"Slide {idx + 1}"
            if "intent" not in slide: slide["intent"] = "content"
            if "visual_type" not in slide: slide["visual_type"] = "grid"

        logger.info(f"[Planner] Created arc with {len(plan)} slides")
        return {"plan": plan, "error": None}

    except Exception as exc:
        logger.error(f"[Planner] Exception: {exc}")
        return {"plan": [], "error": str(exc)}
