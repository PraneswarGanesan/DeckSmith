"""
Slide Validator Agent — design-aware quality assurance before visual composition.

Design Philosophy:
  The validator PRESERVES rich metadata (visual_type, design_intent, data_extract,
  visual_structure) while enforcing quality rules.  It does NOT strip away the
  design intelligence added by the planner and content agents.

  Relaxed constraints vs. the old validator:
    - Title: 2-10 words (was 3-8)
    - Bullets: 2-10 words each (was 2-12)
    - Max sliding: 20 (was 15) to accommodate content-rich documents
    - visual_structure is always preserved
"""
from __future__ import annotations

from logger import get_logger

logger = get_logger(__name__)


def _validate_slide(slide: dict, idx: int) -> tuple[dict, list[str]]:
    """
    Validate a single slide and return (corrected_slide, list_of_warnings).
    PRESERVES all design metadata.
    """
    warnings = []
    title = str(slide.get("title", "")).strip()
    bullets = slide.get("content", [])
    slide_type = slide.get("type", "content")
    sub_id = slide.get("subsection_id")

    # Title validation
    if not title:
        warnings.append(f"Slide {idx}: Missing title")
        title = "Slide"

    title_words = len(title.split())
    if title_words > 10:
        warnings.append(f"Slide {idx}: Title too long ({title_words} words, max 10)")
        title = " ".join(title.split()[:10])

    # Bullet validation
    if not isinstance(bullets, list):
        warnings.append(f"Slide {idx}: Bullets are not a list")
        bullets = []

    cleaned_bullets = []
    for i, bullet in enumerate(bullets):
        if not isinstance(bullet, str):
            bullet = str(bullet)

        bullet = bullet.strip()
        if not bullet:
            continue

        words = len(bullet.split())
        if words > 15:
            warnings.append(f"Slide {idx}, bullet {i+1}: Too long ({words} words), truncating to 15")
            bullet = " ".join(bullet.split()[:15])

        if words < 2:
            warnings.append(f"Slide {idx}, bullet {i+1}: Too short ({words} words), skipping")
            continue

        cleaned_bullets.append(bullet)

    # Enforce max 6 bullets
    if len(cleaned_bullets) > 6:
        warnings.append(f"Slide {idx}: Too many bullets ({len(cleaned_bullets)}, max 6), truncating")
        cleaned_bullets = cleaned_bullets[:6]

    # Build corrected slide — PRESERVE ALL METADATA
    corrected = {
        "title": title,
        "content": cleaned_bullets,
        "type": slide_type,
        "subsection_id": sub_id,
        "layout": slide.get("layout", "grid"),
        "intent": slide.get("intent", "content"),
        # ── PRESERVE design metadata ──────────────────────────────
        "visual_type": slide.get("visual_type", slide.get("layout", "grid")),
        "design_intent": slide.get("design_intent", ""),
        "data_extract": slide.get("data_extract", ""),
    }

    # PRESERVE visual_structure if it exists
    if "visual_structure" in slide:
        corrected["visual_structure"] = slide["visual_structure"]

    return corrected, warnings


async def validator_node(state: dict) -> dict:
    """
    Validate and correct all slides before visual composition.
    PRESERVES all design metadata and visual_structure.

    Inputs:
        critiqued_slides (list[dict]): Slides from critic agent
    Outputs:
        critiqued_slides (list[dict]): Validated slides with metadata intact
    """
    slides = state.get("critiqued_slides") or state.get("slides", [])

    if not slides:
        logger.warning("[Validator] No slides to validate")
        return {"critiqued_slides": [], "error": None}

    logger.info(f"[Validator] Validating {len(slides)} slides")

    validated_slides = []
    total_warnings = 0
    seen_titles = set()

    for idx, slide in enumerate(slides):
        corrected, warnings = _validate_slide(slide, idx)

        if warnings:
            total_warnings += len(warnings)
            for warning in warnings:
                logger.warning(warning)

        # Check for duplicate titles
        title = corrected.get("title", "")
        if title in seen_titles:
            logger.warning(f"Slide {idx}: Duplicate title '{title}'")
        seen_titles.add(title)

        validated_slides.append(corrected)

    # Enforce max 20 slides (up from 15)
    if len(validated_slides) > 20:
        logger.warning(f"[Validator] Too many slides ({len(validated_slides)}, max 20), truncating")
        validated_slides = validated_slides[:20]

    logger.info(
        f"[Validator] Validation complete | {len(validated_slides)} slides | "
        f"{total_warnings} warnings | "
        f"metadata preserved: visual_type, design_intent, data_extract, visual_structure"
    )

    return {"critiqued_slides": validated_slides, "error": None}
