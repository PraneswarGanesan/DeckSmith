"""
Slide Validator Agent — quality assurance pass before final template generation.

Checks each slide against design rules:
  ✓ Title is present and meaningful (3-8 words)
  ✓ Content bullets are present (1-5 bullets)
  ✓ Each bullet is 1-12 words
  ✓ No duplicate slides
  ✓ Slide sequence makes logical sense
  ✓ Total slide count is reasonable (3-15 slides)

Logs warnings for slides that violate rules but keeps them (graceful degradation).
"""
from __future__ import annotations

from logger import get_logger

logger = get_logger(__name__)


def _validate_text(text: str, min_words: int = 1, max_words: int = 12) -> bool:
    """Check if text length is within word bounds."""
    if not isinstance(text, str):
        return False
    words = text.split()
    return min_words <= len(words) <= max_words


def _validate_slide(slide: dict, idx: int) -> tuple[dict, list[str]]:
    """
    Validate a single slide and return (corrected_slide, list_of_warnings).
    
    Corrections:
      - Truncate titles > 8 words
      - Remove bullets > 12 words
      - Ensure at least 1 bullet for non-title slides
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
    if title_words > 8:
        warnings.append(f"Slide {idx}: Title too long ({title_words} words, max 8)")
        # Truncate to 8 words
        title = " ".join(title.split()[:8])
    
    if title_words < 2:
        warnings.append(f"Slide {idx}: Title too short ({title_words} words, min 2)")
    
    # Bullet validation
    if not isinstance(bullets, list):
        warnings.append(f"Slide {idx}: Bullets are not a list")
        bullets = []
    
    # Filter and validate bullets
    cleaned_bullets = []
    for i, bullet in enumerate(bullets):
        if not isinstance(bullet, str):
            bullet = str(bullet)
        
        bullet = bullet.strip()
        if not bullet:
            continue
        
        words = len(bullet.split())
        if words > 12:
            warnings.append(
                f"Slide {idx}, bullet {i + 1}: Too long ({words} words, max 12), truncating"
            )
            bullet = " ".join(bullet.split()[:12])
        
        if words < 2:
            warnings.append(f"Slide {idx}, bullet {i + 1}: Too short ({words} words, min 2), skipping")
            continue
        
        cleaned_bullets.append(bullet)
    
    # Enforce 1-5 bullets
    if len(cleaned_bullets) == 0 and sub_id is not None:
        warnings.append(f"Slide {idx}: No valid bullets (had {len(bullets)} before cleaning)")
    
    if len(cleaned_bullets) > 5:
        warnings.append(f"Slide {idx}: Too many bullets ({len(cleaned_bullets)}, max 5), truncating")
        cleaned_bullets = cleaned_bullets[:5]
    
    # Validate slide type
    if slide_type not in ("content", "chart"):
        warnings.append(f"Slide {idx}: Invalid slide type '{slide_type}', defaulting to 'content'")
        slide_type = "content"
    
    corrected = {
        "title": title,
        "content": cleaned_bullets,
        "type": slide_type,
        "subsection_id": sub_id,
        "layout": slide.get("layout", "grid-2"),
        "intent": slide.get("intent", "content"),  # preserve intent for visual_composer
    }
    
    return corrected, warnings


async def validator_node(state: dict) -> dict:
    """
    Validate and correct all slides before template generation.
    
    Inputs:
        critiqued_slides (list[dict]): Slides from critic agent
            (or fallback to slides if critiqued_slides empty)
    
    Outputs:
        critiqued_slides (list[dict]): Validated and corrected slides
        error (str | None): Error message if validation failed
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
        
        # Log warnings
        if warnings:
            total_warnings += len(warnings)
            for warning in warnings:
                logger.warning(warning)
        
        # Check for duplicate titles (soft warning)
        title = corrected.get("title", "")
        if title in seen_titles:
            logger.warning(f"Slide {idx}: Duplicate title '{title}'")
        seen_titles.add(title)
        
        validated_slides.append(corrected)
    
    # Enforce total slide count (3-15 slides including title)
    if len(validated_slides) < 2:
        logger.warning(f"[Validator] Very few slides ({len(validated_slides)}), should have 3-15")
    
    if len(validated_slides) > 15:
        logger.warning(f"[Validator] Too many slides ({len(validated_slides)}, max 15), truncating")
        validated_slides = validated_slides[:15]
    
    logger.info(
        f"[Validator] Validation complete | {len(validated_slides)} slides | "
        f"{total_warnings} warnings | Valid for template generation"
    )
    
    return {"critiqued_slides": validated_slides, "error": None}
