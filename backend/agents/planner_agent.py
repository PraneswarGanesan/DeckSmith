"""
Planner Agent — asks the LLM to create a structured slide plan from
retrieved subsections.
"""
from __future__ import annotations

import json

from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

_PROMPT = """\
You are a professional presentation planner.

Query: {query}

Available subsections (pick the most relevant):
{subsections}

Create a JSON slide plan — an array of objects with these keys:
  "title"         : short slide title (max 8 words, impactful)
  "subsection_id" : ID from the list above, or null for an intro slide
  "type"          : "content" | "chart"  (use "chart" only if subsection has table data)

Rules:
- First slide must be an intro/title slide (subsection_id: null, type: "content")
- Maximum 8 slides total
- Do not repeat subsection IDs
- Return ONLY valid JSON array, no markdown, no explanation.
"""


def _parse_json_array(raw: str) -> list:
    start, end = raw.find("["), raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON array found")
    return json.loads(raw[start:end])


async def planner_node(state: dict) -> dict:
    retrieved: list[dict] = state.get("retrieved", [])
    query: str = state.get("query", "Presentation")
    logger.info(f"[Planner] Planning slides from {len(retrieved)} subsections")

    sub_lines = "\n".join(
        f'- id: "{s["id"]}" | title: "{s["subsection_title"]}" '
        f'| has_table: {bool(s.get("keywords"))}'
        for s in retrieved
    )
    prompt = _PROMPT.format(query=query, subsections=sub_lines or "(none)")

    try:
        raw = await generate(prompt, temperature=0.3, max_tokens=1024)
        plan = _parse_json_array(raw)
        # Validate structure
        for item in plan:
            item.setdefault("type", "content")
            item.setdefault("subsection_id", None)
        logger.info(f"[Planner] Plan: {len(plan)} slides")
        return {"plan": plan, "error": None}
    except Exception as exc:
        logger.warning(f"[Planner] LLM failed ({exc}), using fallback plan")
        fallback = [{"title": query, "subsection_id": None, "type": "content"}]
        fallback += [
            {"title": s["subsection_title"], "subsection_id": s["id"], "type": "content"}
            for s in retrieved[:6]
        ]
        return {"plan": fallback, "error": None}
