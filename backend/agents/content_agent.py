"""
Content Agent — drafts professional copy for the slides.

Design Philosophy:
  Do NOT just copy-paste from the original markdown. Professional slides
  require crisp, synthesized, and highly readable bullets.
  The Content Agent adopts a "McKinsey presentation copywriter" persona:
    - Synthesizes the core meaning of the subsection.
    - Writes entirely new, punchy bullets.
    - Incorporates the planner's `design_intent` and `data_extract`.
  If the intent is 'intro', 'agenda', or 'qna', it writes structural text,
  not heavy content.
"""
from __future__ import annotations

import asyncio
from core.llm import generate
from core.database import get_subsection
from logger import get_logger

logger = get_logger(__name__)


_COPYWRITER_PROMPT = """\
You are an ELITE PRESENTATION COPYWRITER (ex-McKinsey).
Your job is to read the raw source text and WRITE COMPELLING SLIDE BULLETS.
DO NOT COPY-PASTE. Synthesize and write for a C-level audience.

SLIDE CONTEXT:
  Title: {title}
  Story Phase: {intent}
  Visual Structure: {visual_type}
  Design Instructions: {design_intent}
  Key Data to Extract: {data_extract}

RAW SOURCE TEXT:
{source_text}

COPYWRITING RULES:
1. Max {max_bullets} bullet points.
2. Max 10 words per bullet.
3. Start every bullet with a strong action verb or a powerful noun.
4. Integrate numbers actively (e.g. "$5.2B market growth" not "the market grew by 5.2 billion").
5. If the Story Phase is 'agenda', write 3-5 high-level topics.
6. If the Story Phase is 'intro' or 'conclusion', write 1-3 powerful summary statements.
7. If the Story Phase is 'qna', just write "Questions?" or "Open for Discussion".
8. DO NOT use markdown like `**` or `*`. Just the raw text.
9. DO NOT output bullet characters like `-` or `•`. Just one line per point.

Produce ONLY the text lines. Nothing else.
"""

async def _process_slide(slide: dict, query: str) -> dict:
    """Draft presentation-native copy for a single slide."""
    intent = slide.get("intent", "content")
    visual_type = slide.get("visual_type", "grid")
    
    # Structural slides often need less text and no subsection lookup
    max_bullets = 6
    if intent in ("intro", "qna"):
        max_bullets = 2
    elif visual_type == "cards":
        max_bullets = 4
    elif visual_type == "metrics":
        max_bullets = 4
        
    source_text = "General presentation overview."
    
    sub_id = slide.get("subsection_id")
    if sub_id:
        import uuid
        try:
            val = uuid.UUID(str(sub_id))
            sub_data = get_subsection(sub_id)
            if sub_data:
                source_text = sub_data.get("content", "")
        except ValueError:
            logger.warning(f"[Content] Invalid UUID '{sub_id}' for subsection. Skipping DB lookup.")
        except Exception as e:
            logger.warning(f"[Content] DB Error fetching '{sub_id}': {e}")
    
    # If it's an Agenda slide without a sub_id, use the overall query as context
    if intent == "agenda" and not sub_id:
        source_text = f"Agenda for presentation on: {query}"
        
    prompt = _COPYWRITER_PROMPT.format(
        title=slide.get("title", ""),
        intent=intent,
        visual_type=visual_type,
        design_intent=slide.get("design_intent", ""),
        data_extract=slide.get("data_extract", ""),
        source_text=source_text,
        max_bullets=max_bullets
    )
    
    try:
        raw_text = await generate(prompt, temperature=0.7, max_tokens=600)
        lines = [line.strip("-•* \t") for line in raw_text.strip().split("\n")]
        bullets = [line for line in lines if line and len(line) > 2]
        
        # Enforce hard limits safely
        bullets = bullets[:max_bullets]
        
        slide["content"] = bullets
        logger.debug(f"[Content] Wrote {len(bullets)} bullets for '{slide.get('title')}'")
        
    except Exception as exc:
        logger.warning(f"[Content] Failed to draft copy for '{slide.get('title')}': {exc}")
        slide["content"] = ["Content generation failed."]
        
    return slide


async def content_node(state: dict) -> dict:
    """
    Synthesize presentation content for all planned slides.
    """
    if state.get("error"):
        return {"error": state["error"]}

    plan: list[dict] = state.get("plan", [])
    query: str = state.get("query", "")

    if not plan:
        return {"slides": [], "error": "No plan provided to content builder"}

    logger.info(f"[Content] Drafting copy for {len(plan)} slides via LLM...")

    # Process all slides explicitly mapped by the planner
    tasks = [_process_slide(slide.copy(), query) for slide in plan]
    slides = await asyncio.gather(*tasks)

    return {"slides": slides, "error": None}
