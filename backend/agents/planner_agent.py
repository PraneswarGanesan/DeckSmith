"""
Semantic Planner Agent — converts grouped content sections into a structured slide plan.

Improvements over naive version:
  • Consumes "grouped" (post-grouper) instead of raw "retrieved" chunks
  • Passes semantic intent from grouper to the LLM for better layout decisions
  • Enforces a McKinsey-style story arc: intro → problem → analysis → solution → conclusion
  • Generates ACTION-ORIENTED titles (not raw section headings)
  • Carries combined_content into the plan so the transformer has rich context
  • Hard-limits the plan to 8 content slides + Q&A
"""
from __future__ import annotations

import json
import re
from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)

# ── LLM prompt ───────────────────────────────────────────────────────────────
_PROMPT = """\
You are a senior presentation designer. Generate a COMPLETE, professional slide plan.

Document topic: {query}

Content sections available:
{sections}

MANDATORY SLIDE ORDER (follow exactly):
  Slide 1 : AGENDA          → layout:"grid-2",   intent:"intro",      id:null
  Slide 2 : INTRODUCTION    → layout:"left-text-right-visual", intent:"intro", pick best intro section id
  Slides 3-5: CORE CONTENT  → pick 3 most important sections, use layout based on content type
  Slide 6 : DATA/ANALYSIS   → layout:"chart" or "comparison", intent:"analysis", pick data-rich section
  Slide 7 : SOLUTION/ACTION → layout:"process",  intent:"solution",   pick solution/recommendation section
  Slide 8 : KEY HIGHLIGHT   → layout:"centered", intent:"results",    id:null  (one powerful insight)
  Slide 9 : CONCLUSION      → layout:"centered", intent:"conclusion", id:null
  Slide 10: Q&A             → layout:"centered", intent:"qna",        id:null

TITLE RULES:
  • Action phrases only — verb + insight
  • Good: "Three Factors Drive 80% of Risk"   Bad: "Section 3 Overview"
  • Good: "Regulation Mandates Action by Q4"  Bad: "Policy Introduction"
  • Max 8 words. No section numbers.

LAYOUT SELECTION:
  "grid-2"                 : general content, overview, policy, two balanced columns
  "grid-3"                 : exactly 3 pillars/principles/categories
  "left-text-right-visual" : context, problem, risk — image placeholder on right
  "process"                : steps, workflow, implementation sequence
  "chart"                  : ANY slide with numbers, percentages, metrics, trends
  "comparison"             : before/after, pros/cons, old vs new
  "centered"               : highlight, conclusion, Q&A — single strong message

RULES:
  • If a section has numbers/percentages/dates → use layout "chart" and type "chart"
  • If a section compares things → use "comparison"
  • If a section lists steps → use "process"
  • Each section id used AT MOST ONCE
  • Agenda and Q&A always have id: null

OUTPUT: JSON array only. Each item MUST have ALL these fields:
  "title"          : string (action phrase, max 8 words)
  "subsection_id"  : string id from list above, or null
  "type"           : "content" or "chart"
  "layout"         : one of the 7 layout types above
  "intent"         : intro|problem|analysis|solution|results|policy|conclusion|qna

Return ONLY the JSON array. No markdown. No explanation. No extra text.
"""

# ── Layout validation ─────────────────────────────────────────────────────────
_VALID_LAYOUTS = {
    "grid-2", "grid-3", "left-text-right-visual",
    "process", "chart", "comparison", "centered",
}

# ── Keyword-based layout inference (fallback when LLM gives invalid value) ────
_LAYOUT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("process",                ["solution", "step", "workflow", "approach", "implement",
                                "method", "how to", "mitigation", "framework"]),
    ("left-text-right-visual", ["problem", "challenge", "context", "background",
                                "risk", "issue", "fraud", "threat", "breach"]),
    ("chart",                  ["data", "metric", "result", "statistic", "trend",
                                 "performance", "number", "rate", "percentage"]),
    ("comparison",             ["analysis", "comparison", "insight", "pros",
                                 "cons", "before", "after", "vs", "finding"]),
    ("centered",               ["conclusion", "summary", "takeaway", "q&a",
                                 "questions", "thank", "close"]),
    ("grid-3",                 ["three", "pillar", "principle", "framework",
                                 "three-layer", "triple"]),
]

# Intent → layout (override when LLM gives wrong layout for an intent)
_INTENT_LAYOUT_MAP: dict[str, str] = {
    "intro":      "grid-2",
    "problem":    "left-text-right-visual",
    "analysis":   "comparison",
    "solution":   "process",
    "policy":     "grid-2",
    "results":    "comparison",
    "conclusion": "centered",
    "qna":        "centered",
}


def _parse_json_array(raw: str) -> list:
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    start, end = raw.find("["), raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON array found")
    parsed = json.loads(raw[start:end])
    if not isinstance(parsed, list):
        raise ValueError("JSON root must be array")
    return parsed


def _infer_layout(title: str, intent: str, position: int, total: int) -> str:
    # Intent takes priority
    if intent in _INTENT_LAYOUT_MAP:
        return _INTENT_LAYOUT_MAP[intent]
    # Keyword scan
    tl = title.lower()
    for layout, keywords in _LAYOUT_KEYWORDS:
        if any(kw in tl for kw in keywords):
            return layout
    # Position defaults
    if position == 0:
        return "grid-2"
    if position >= total - 1:
        return "centered"
    if position == 1:
        return "left-text-right-visual"
    return "grid-2"


def _build_fallback_plan(grouped: list[dict], query: str) -> list[dict]:
    """Create a sensible plan from grouped sections without LLM."""
    agenda_bullets = " | ".join(g["title"] for g in grouped[:6])
    plan = [
        {
            "title":            "Agenda",
            "subsection_id":    None,
            "type":             "content",
            "layout":           "grid-2",
            "intent":           "intro",
            "combined_content": agenda_bullets,
        },
    ]
    total = min(len(grouped), 7) + 3
    for i, group in enumerate(grouped[:7]):
        intent = group.get("intent", "content")
        layout = _infer_layout(group["title"], intent, i + 1, total)
        slide_type = "chart" if (group.get("has_table") and layout == "chart") else "content"
        plan.append({
            "title":            group["title"],
            "subsection_id":    group["id"],
            "type":             slide_type,
            "layout":           layout,
            "intent":           intent,
            "combined_content": group.get("combined_content", ""),
        })
    plan.extend([
        {
            "title":            f"Key Insight: {query[:40]}",
            "subsection_id":    None,
            "type":             "content",
            "layout":           "centered",
            "intent":           "results",
            "combined_content": "",
        },
        {
            "title":            "Questions?",
            "subsection_id":    None,
            "type":             "content",
            "layout":           "centered",
            "intent":           "qna",
            "combined_content": "",
        },
    ])
    return plan


async def planner_node(state: dict) -> dict:
    """
    Build a structured slide plan.

    Prefers state["grouped"] (grouper output); falls back to state["retrieved"].
    Outputs:
        plan (list[dict]) — each item has: title, subsection_id, type, layout,
                            intent, combined_content
    """
    # Use grouped if available; degrade to retrieved
    grouped: list[dict] = state.get("grouped") or []
    retrieved: list[dict] = state.get("retrieved", [])
    query: str = state.get("query", "Presentation").strip() or "AI-Generated Presentation"

    # Build a grouped-like list from retrieved when grouper didn't run
    if not grouped and retrieved:
        logger.info("[Planner] No grouped data — synthesising from retrieved")
        grouped = [
            {
                "id":               s["id"],
                "all_ids":          [s["id"]],
                "title":            re.sub(r"^\d+(\.\d+)*\.?\s+", "", s.get("subsection_title", ""))[:60],
                "combined_content": s.get("content", ""),
                "intent":           "content",
                "layout":           "grid-2",
                "has_table":        bool(s.get("keywords")),
                "keywords":         s.get("keywords", []),
            }
            for s in retrieved
        ]

    if not grouped:
        logger.warning("[Planner] No content to plan — returning minimal fallback")
        return {
            "plan": [{"title": query, "subsection_id": None,
                      "type": "content", "layout": "grid-2",
                      "intent": "intro", "combined_content": ""}],
            "error": None,
        }

    logger.info(f"[Planner] Planning {len(grouped)} groups | query='{query[:60]}'")

    # Format sections for LLM
    section_lines = []
    for g in grouped:
        intent_tag = f"[{g.get('intent', 'content').upper()}]"
        snippet = g.get("combined_content", "")[:200].replace("\n", " ")
        section_lines.append(
            f'- id: "{g["id"]}" | {intent_tag} title: "{g["title"]}" '
            f'| has_table: {g.get("has_table", False)} | snippet: "{snippet}..."'
        )
    sections_text = "\n".join(section_lines)
    prompt = _PROMPT.format(query=query, sections=sections_text)

    # Build a lookup map: id → group (so we can inject combined_content)
    group_map: dict[str, dict] = {g["id"]: g for g in grouped}

    try:
        raw = await generate(prompt, temperature=0.3, max_tokens=1024)
        plan_raw = _parse_json_array(raw)

        validated: list[dict] = []
        used_ids: set[str] = set()
        total = len([x for x in plan_raw if isinstance(x, dict)])

        for pos, item in enumerate(plan_raw):
            if not isinstance(item, dict):
                continue

            title = str(item.get("title", "Slide")).strip()[:100] or "Content Slide"
            sub_id = item.get("subsection_id")
            intent = str(item.get("intent", "content")).lower()
            slide_type = str(item.get("type", "content")).lower()
            if slide_type not in ("content", "chart"):
                slide_type = "content"

            # Validate / infer layout
            layout = str(item.get("layout", "")).strip().lower()
            if layout not in _VALID_LAYOUTS:
                layout = _infer_layout(title, intent, pos, total)

            # Cross-check layout vs intent to catch LLM mistakes
            if intent in _INTENT_LAYOUT_MAP and layout not in _VALID_LAYOUTS:
                layout = _INTENT_LAYOUT_MAP[intent]

            # Deduplication
            if sub_id and sub_id in used_ids:
                continue
            if sub_id:
                used_ids.add(sub_id)

            # Pull combined_content from our group_map
            combined_content = ""
            if sub_id and sub_id in group_map:
                combined_content = group_map[sub_id].get("combined_content", "")

            validated.append({
                "title":            title,
                "subsection_id":    sub_id,
                "type":             slide_type,
                "layout":           layout,
                "intent":           intent,
                "combined_content": combined_content,
            })

        # Cap at 10 content slides
        validated = validated[:10]

        # Ensure slide 1 is AGENDA (no subsection_id, intent=intro)
        if not validated or validated[0].get("intent") != "intro" or validated[0].get("subsection_id") is not None:
            # Build agenda bullets from section titles
            agenda_bullets = " | ".join(g["title"] for g in grouped[:6])
            validated.insert(0, {
                "title":            "Agenda",
                "subsection_id":    None,
                "type":             "content",
                "layout":           "grid-2",
                "intent":           "intro",
                "combined_content": agenda_bullets,
            })

        # Ensure a highlight/centered slide exists before conclusion
        has_highlight = any(s.get("intent") in ("results", "conclusion") and s.get("subsection_id") is None
                            for s in validated)
        if not has_highlight:
            # Insert highlight before last slide
            validated.insert(-1, {
                "title":            f"Key Insight: {query[:40]}",
                "subsection_id":    None,
                "type":             "content",
                "layout":           "centered",
                "intent":           "results",
                "combined_content": "",
            })

        # Ensure last slide is Q&A
        last = validated[-1] if validated else {}
        if last.get("intent") != "qna":
            validated.append({
                "title":            "Questions?",
                "subsection_id":    None,
                "type":             "content",
                "layout":           "centered",
                "intent":           "qna",
                "combined_content": "",
            })

        logger.info(
            f"[Planner] Plan: {len(validated)} slides | "
            f"layouts: {[s['layout'] for s in validated]}"
        )
        return {"plan": validated, "error": None}

    except Exception as exc:
        logger.warning(f"[Planner] LLM planning failed ({type(exc).__name__}: {exc}) — using fallback")
        fallback = _build_fallback_plan(grouped, query)
        logger.info(f"[Planner] Fallback plan: {len(fallback)} slides")
        return {"plan": fallback, "error": None}
