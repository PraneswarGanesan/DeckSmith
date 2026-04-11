"""
Visual Composer Agent — adds design intelligence to slides.

RESPONSIBILITY:
Transforms text-based bullets into visually-structured elements.

For each slide:
  1. Extract CORE MESSAGE (the ONE key takeaway)
  2. Decide VISUAL TYPE (process, cards, comparison, chart, etc.)
  3. Transform bullets into STRUCTURED ELEMENTS
  4. Enforce DESIGN RULES (grid, spacing, colors, hierarchy)

Sits BETWEEN: validator → template_node

Input:  critiqued_slides (from validator) + charts (for chart detection)
Output: Enhanced slides with visual_structure + design_rules fields

Backward compatible: If visual_structure not present, template agent
falls back to bullet rendering.
"""
from __future__ import annotations

import re
from core.llm import generate
from logger import get_logger

logger = get_logger(__name__)


# ── Prompt for message extraction ─────────────────────────────────────────────

_MESSAGE_EXTRACTION_PROMPT = """\
You are an executive communication specialist.

Slide title:  {title}
Slide intent: {intent}
Bullets:
{bullets_text}

Extract the ONE core message — the single most important takeaway
that summarizes this slide.

Guidelines:
  • Start with a KEY NUMBER or STRONG ACTION if present
  • Keep it under 12 words
  • Include specific metrics when available
  • Make it assertive and memorable
  • Example: "Real-time monitoring reduced fraud losses by 62 percent"
  • Bad: "There are many ways to improve security"

Return ONLY the message string. No explanation, no quotes.
"""


# ── Visual type detection logic ───────────────────────────────────────────────

_LAYOUT_TO_VISUAL_TYPE = {
    "chart":                  "chart",
    "process":                "process",
    "comparison":             "comparison",
    "grid-3":                 "cards",
    "grid-2":                 "grid",
    "left-text-right-visual": "left-text-right-visual",
    "centered":               "centered",
}

_INTENT_TO_VISUAL_TYPE = {
    "intro":       "grid",
    "problem":     "left-text-right-visual",
    "analysis":    "comparison",
    "solution":    "process",
    "results":     "chart",
    "conclusion":  "centered",
    "qna":         "centered",
}


def _detect_visual_type(
    slide_data: dict,
    has_chart_data: bool,
) -> str:
    """
    Detect the visual type for a slide based on:
      1. Explicit chart/layout in slide_data
      2. Content heuristics (contains numbers, etc.)
      3. Intent classification
      4. Fallback
    """
    # Priority 1: Explicit chart type
    if slide_data.get("type") == "chart" or has_chart_data:
        return "chart"

    # Priority 2: Layout-based detection
    layout = slide_data.get("layout", "").lower()
    if layout in _LAYOUT_TO_VISUAL_TYPE:
        return _LAYOUT_TO_VISUAL_TYPE[layout]

    # Priority 3: Intent-based detection
    intent = slide_data.get("intent", "").lower()
    if intent in _INTENT_TO_VISUAL_TYPE:
        return _INTENT_TO_VISUAL_TYPE[intent]

    # Priority 4: Content heuristics
    bullets = slide_data.get("content", [])
    bullets_text = " ".join(str(b) for b in bullets).lower()

    # Check for numeric data → chart
    if re.search(r"\d+%|\$\d+|[\d,]+\s*(thousand|million|billion|percent|%)", bullets_text):
        if len(bullets) <= 3:
            return "chart"

    # Check for sequential steps → process
    if any(word in bullets_text for word in ["first", "second", "third", "then", "finally",
                                              "step", "phase", "stage", "approach"]):
        return "process"

    # Check for comparison → comparison
    if any(word in bullets_text for word in ["vs", "versus", "compared", "before", "after",
                                              "traditional", "new", "current", "proposed"]):
        return "comparison"

    # Check for 3 items → cards
    if len(bullets) == 3:
        return "cards"

    # Default
    return "grid"


def _extract_numbers(text: str) -> list[str | int]:
    """Extract numeric values from text for chart purposes."""
    numbers = []
    for match in re.finditer(r"\d+(?:\.\d+)?(?:%)?", text):
        try:
            val = match.group()
            numbers.append(int(val.rstrip("%")) if "%" in val else float(val))
        except ValueError:
            pass
    return numbers


def _contains_metric(text: str) -> bool:
    """Check if text contains a business metric."""
    metric_keywords = [
        "reduced", "increased", "decreased", "improved",
        "loss", "gain", "percent", "%", "growth", "rate",
        "savings", "cost", "revenue", "profit", "efficiency"
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in metric_keywords)


# ── Message extraction ────────────────────────────────────────────────────────

async def _extract_message(
    title: str,
    intent: str,
    bullets: list[str],
) -> str:
    """
    Use LLM to extract the core message from bullets.
    Falls back to first bullet if LLM fails.
    """
    bullets_text = "\n".join(f"  • {b}" for b in bullets)
    prompt = _MESSAGE_EXTRACTION_PROMPT.format(
        title=title,
        intent=intent,
        bullets_text=bullets_text,
    )

    try:
        message = await generate(prompt, temperature=0.2, max_tokens=128)
        message = message.strip().strip('"\'')
        if message and len(message) > 5:
            return message
    except Exception as exc:
        logger.debug(f"[VC] Message extraction LLM failed: {exc}, using fallback")

    # Fallback: Use first bullet or title
    if bullets and len(str(bullets[0])) > 3:
        return str(bullets[0])
    return title


# ── Visual structure builders ─────────────────────────────────────────────────

def _build_cards_structure(bullets: list[str]) -> dict:
    """Transform bullets into numbered cards (grid-3)."""
    colors = ["primary", "secondary", "accent"]
    elements = []

    for i, bullet in enumerate(bullets[:6]):
        if not bullet:
            continue
        elements.append({
            "type": "card",
            "number": f"{i+1:02d}",
            "color": colors[i % len(colors)],
            "text": str(bullet).strip(),
        })

    return {
        "type": "cards",
        "elements": elements,
    }


def _build_process_structure(bullets: list[str]) -> dict:
    """Transform bullets into sequential steps."""
    elements = []

    for i, bullet in enumerate(bullets[:6]):
        if not bullet:
            continue
        elements.append({
            "type": "step",
            "number": i + 1,
            "text": str(bullet).strip(),
        })

    return {
        "type": "process",
        "elements": elements,
    }


def _build_comparison_structure(bullets: list[str]) -> dict:
    """Transform bullets into before/after or pros/cons."""
    mid = (len(bullets) + 1) // 2

    # Try to detect left/right titles from first bullets
    left_title = "Current State"
    right_title = "Proposed State"

    left_items = []
    right_items = []

    for i, bullet in enumerate(bullets[:mid]):
        if bullet:
            left_items.append({"type": "item", "text": str(bullet).strip()})

    for i, bullet in enumerate(bullets[mid:]):
        if bullet:
            right_items.append({"type": "item", "text": str(bullet).strip()})

    return {
        "type": "comparison",
        "left_column": {
            "title": left_title,
            "items": left_items,
        },
        "right_column": {
            "title": right_title,
            "items": right_items,
        },
    }


def _build_chart_structure(chart_entry: dict) -> dict:
    """
    Build chart visual structure from chart_agent's chart_entry.

    chart_entry format (from chart_agent):
        {
            "chart_data":  {"title": ..., "categories": [...], "series": {...}, "chart_type": ...},
            "chart_image": <bytes>,   # matplotlib PNG
        }
    """
    if not chart_entry:
        return {"type": "chart", "elements": []}

    # Unwrap the nested "chart_data" dict produced by chart_agent
    inner: dict = chart_entry.get("chart_data") or {}
    categories = inner.get("categories", [])
    series     = inner.get("series", {})
    chart_type = inner.get("chart_type", "column")

    if not categories and not chart_entry.get("chart_image"):
        return {"type": "chart", "elements": []}

    return {
        "type":       "chart",
        "chart_type": chart_type,
        "has_image":  bool(chart_entry.get("chart_image")),
        "data": {
            "categories": categories,
            "series":     series,
        },
    }


def _build_grid_structure(bullets: list[str]) -> dict:
    """Fallback: generic grid layout (2-column or single column)."""
    if len(bullets) <= 3:
        return {
            "type": "grid",
            "layout": "single-column",
            "elements": [
                {"type": "item", "text": str(b).strip()} for b in bullets if b
            ],
        }
    else:
        mid = (len(bullets) + 1) // 2
        return {
            "type": "grid",
            "layout": "two-column",
            "left_column": [
                {"type": "item", "text": str(b).strip()} for b in bullets[:mid] if b
            ],
            "right_column": [
                {"type": "item", "text": str(b).strip()} for b in bullets[mid:] if b
            ],
        }


def _build_centered_structure(bullets: list[str]) -> dict:
    """Conclusion/Q&A: centered takeaway."""
    return {
        "type": "centered",
        "elements": [
            {"type": "item", "text": str(b).strip()} for b in bullets[:4] if b
        ],
    }


def _build_left_text_right_visual_structure(bullets: list[str]) -> dict:
    """Problem/context: text on left, space on right for image."""
    return {
        "type": "left-text-right-visual",
        "text_items": [
            {"type": "item", "text": str(b).strip()} for b in bullets if b
        ],
    }


# ── Design rules ──────────────────────────────────────────────────────────────

def _build_design_rules(visual_type: str) -> dict:
    """
    Define design constraints for each visual type.
    Used by template agent to render consistently.
    """
    common_rules = {
        "grid_columns": 12,
        "margin_left": 0.5,
        "margin_right": 0.5,
        "margin_top": 0.5,
        "margin_bottom": 0.4,
        "title_color": "primary",
        "title_size": 28,
        "title_bold": True,
        "message_color": "dark",
        "message_size": 14,
    }

    type_specific = {
        "cards": {
            **common_rules,
            "card_height": 1.1,
            "card_gap": 0.1,
            "max_items": 6,
            "use_numbers": True,
            "accent_position": "left",
            "colors": ["primary", "secondary", "accent"],
        },
        "process": {
            **common_rules,
            "step_height": 0.55,
            "step_gap": 0.18,
            "max_items": 5,
            "use_numbers": True,
            "accent_position": "top",
            "show_arrows": True,
        },
        "comparison": {
            **common_rules,
            "column_gap": 0.3,
            "header_color_left": "primary",
            "header_color_right": "secondary",
            "header_height": 0.42,
            "max_items_per_column": 3,
        },
        "chart": {
            **common_rules,
            "chart_width": 8.5,
            "chart_height": 5.9,
            "side_panel_width": 3.0,
        },
        "centered": {
            **common_rules,
            "alignment": "center",
            "max_items": 4,
            "item_size": 18,
            "background_color": "light_bg",
        },
        "grid": {
            **common_rules,
            "layout": "two-column",
            "column_gap": 0.3,
        },
        "left-text-right-visual": {
            **common_rules,
            "text_width": 7.2,
            "visual_width": 4.8,
            "max_text_items": 5,
        },
    }

    return type_specific.get(visual_type, common_rules)


# ── Main Visual Composer logic ───────────────────────────────────────────────

async def _compose_slide(
    slide_data: dict,
    chart_data: dict | None,
) -> dict:
    """
    Transform a single slide with visual intelligence.
    
    Adds:
      - message: core takeaway
      - visual_type: detected visual category
      - visual_structure: structured elements for rendering
      - design_rules: styling constraints
    """
    title = slide_data.get("title", "Slide")
    intent = slide_data.get("intent", "content")
    bullets = slide_data.get("content", [])

    # Step 1: Extract message
    message = await _extract_message(title, intent, bullets)

    # Step 2: Detect visual type
    # chart_data is {"chart_data": {...}, "chart_image": bytes} from chart_agent
    _inner = (chart_data or {}).get("chart_data") or {}
    has_chart = bool(
        chart_data and (
            chart_data.get("chart_image")
            or _inner.get("categories")
        )
    )
    visual_type = _detect_visual_type(slide_data, has_chart)

    # Step 3: Build visual structure
    if visual_type == "cards":
        visual_structure = _build_cards_structure(bullets)
    elif visual_type == "process":
        visual_structure = _build_process_structure(bullets)
    elif visual_type == "comparison":
        visual_structure = _build_comparison_structure(bullets)
    elif visual_type == "chart":
        visual_structure = _build_chart_structure(chart_data or {})  # chart_entry passed through
    elif visual_type == "centered":
        visual_structure = _build_centered_structure(bullets)
    elif visual_type == "left-text-right-visual":
        visual_structure = _build_left_text_right_visual_structure(bullets)
    else:  # "grid"
        visual_structure = _build_grid_structure(bullets)

    # Step 4: Enforce design rules
    design_rules = _build_design_rules(visual_type)

    # Step 5: Return enhanced slide
    enhanced_slide = {
        **slide_data,  # Preserve all original fields
        "message": message,
        "visual_type": visual_type,
        "visual_structure": visual_structure,
        "design_rules": design_rules,
    }

    logger.debug(
        f"[VC] Slide '{title[:40]}' → visual_type='{visual_type}' "
        f"elements={len(visual_structure.get('elements', []))}"
    )

    return enhanced_slide


# ── Main agent node ───────────────────────────────────────────────────────────

async def visual_composer_node(state: dict) -> dict:
    """
    Visual Composer Agent Node.
    
    Transforms all slides with visual intelligence.
    
    Reads:
        state["critiqued_slides"] or state["slides"]
        state["charts"]
    
    Writes:
        state["slides"] — enhanced with visual structure + design rules
    """
    slides: list[dict] = state.get("critiqued_slides") or state.get("slides", [])
    charts: list[dict] = state.get("charts", [])

    if not slides:
        logger.warning("[VC] No slides to compose — returning empty")
        return {"slides": [], "error": None}

    logger.info(f"[VC] Composing {len(slides)} slides with visual intelligence")

    enhanced_slides: list[dict] = []

    for i, slide in enumerate(slides):
        if not isinstance(slide, dict):
            logger.warning(f"[VC] Slide {i} is not a dict, skipping")
            enhanced_slides.append(slide)
            continue

        chart_data = charts[i] if i < len(charts) else {}

        try:
            enhanced_slide = await _compose_slide(slide, chart_data)
            enhanced_slides.append(enhanced_slide)
        except Exception as exc:
            logger.warning(
                f"[VC] Slide {i} composition failed ({type(exc).__name__}: {exc}), "
                f"proceeding with original"
            )
            enhanced_slides.append(slide)

    logger.info(f"[VC] Composed all {len(enhanced_slides)} slides successfully")
    return {"slides": enhanced_slides, "error": None}
