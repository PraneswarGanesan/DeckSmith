"""
Data Extractor Agent — the pure structural data extractor.

Design Philosophy:
  This agent completely refuses to write paragraphs or generic lists.
  Its ONLY job is to extract numbers, labels, tables, and functional text 
  from the source materials into strict JSON structures.
"""
from __future__ import annotations

import json
import re
import asyncio

from core.llm import generate
from core.database import get_subsection
from logger import get_logger

logger = get_logger(__name__)

_DATA_EXTRACTOR_PROMPT = """\
You are an ELITE DATA EXTRACTOR & STRUCTURAL ANALYST.
Your sole job is to ingest text and strictly isolate quantitative data, logical structures, and table architectures. 

CRITICAL RULE: YOU MUST NEVER WRITE "CONTENT". NO GENERIC BUSINESS PHRASES. DO NOT USE WORDS LIKE "LEVERAGE", "DRIVE", "ENHANCE", "OPTIMIZE", "TRANSFORMATIVE".
NO PARAGRAPHS. NO GENERIC BULLETS.

Your output must be pure, functional structural metadata formatted EXACTLY as a JSON array of UI elements.

Categories of output allowed per array object:
- "metric": For standalone numbers. e.g. {{"type": "metric", "label": "Investment Growth", "value": "76%"}}
- "insight_label": Minimal annotation tags, tightly bounded (MAX 6 WORDS). e.g. {{"type": "insight_label", "value": "Capital flows saturated standard markets."}}
- "axis_label": Mapping source data elements. e.g. {{"type": "axis_label", "source": "Q1-Q4"}}
- "table_data": Explicit table structure. e.g. {{"type": "table_data", "headers": ["A"], "rows": [{{"A":"1"}}]}}

Extract all data from the following source text.
Slide Phase: {intent}
Slide Title: {title}

Source Text Context:
{source_text}

OUTPUT FORMAT:
Return ONLY a raw JSON array of objects. Do not wrap in markdown ```json blocks.
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
        except json.JSONDecodeError:
            pass
    return []

async def _extract_data_for_slide(slide: dict, overall_query: str) -> dict:
    sub_id = slide.get("subsection_id")
    intent = slide.get("intent", "content")
    title = slide.get("title", "")
    
    source_text = ""
    # Pull explicit context if mapped to a subsection
    if sub_id:
        import uuid
        try:
            val = uuid.UUID(str(sub_id))
            sub_data = get_subsection(sub_id)
            if sub_data:
                source_text = sub_data.get("content", "")
                if sub_data.get("tables"):
                    source_text += "\n[TABLES IDENTIFIED IN SOURCE]\n" + json.dumps(sub_data["tables"])
        except ValueError:
            logger.warning(f"[DataExtractor] Invalid UUID '{sub_id}'.")
        except Exception as e:
            logger.warning(f"[DataExtractor] DB Error: {e}")

    # Fallback to query context
    if not source_text:
        source_text = f"Context: This is a high-level '{intent}' slide about '{overall_query}'. Extract minimal structural data."

    prompt = _DATA_EXTRACTOR_PROMPT.format(
        intent=intent,
        title=title,
        source_text=source_text
    )

    try:
        raw_response = await generate(prompt, temperature=0.1, max_tokens=1500)
        elements = _extract_json_array(raw_response)
        
        # Fallback safety if the LLM completely fails
        if not elements:
            logger.warning(f"Data extractor returned empty for '{title}'. Imposing safety fallback.")
            elements = [{"type": "insight_label", "value": "Data processing error or insufficient context."}]
            
        slide["extracted_data"] = elements

        # Populate content list so old validators and templates have text to render
        content_lines = []
        for el in elements:
            if el.get("type") == "metric":
                lbl = el.get("label", "").strip()
                val = el.get("value", "").strip()
                content_lines.append(f"{lbl}: {val}" if lbl else val)
            elif el.get("type") == "insight_label":
                content_lines.append(el.get("value", "").strip())
            elif el.get("type") == "axis_label":
                content_lines.append(f"Axis: {el.get('source', '')}")
            elif type(el.get("value")) is str:
                content_lines.append(el.get("value").strip())

        slide["content"] = [c for c in content_lines if c]

    except Exception as e:
        logger.error(f"[DataExtractor] Failed to extract data for '{title}': {e}")
        slide["extracted_data"] = [{"type": "insight_label", "value": f"Extraction error: {e}"}]
        slide["content"] = [f"Extraction error: {e}"]
        
    return slide

async def data_extractor_node(state: dict) -> dict:
    """
    Replaces content_agent. Loops through planned slides and extracts rigorous structural JSON 
    data representations, eliminating all "story text".
    """
    logger.info("[DataExtractor] Starting strict data extraction for all slides.")
    
    plan: list[dict] = state.get("plan", [])
    if not plan:
        return {"slides": [], "error": "No plan to extract data for."}
        
    query = state.get("query", "")
    
    tasks = []
    for slide_def in plan:
        tasks.append(_extract_data_for_slide(dict(slide_def), query))
        
    extracted_slides = await asyncio.gather(*tasks)
    
    logger.info(f"[DataExtractor] Data isolated for {len(extracted_slides)} slides.")
    return {"slides": extracted_slides, "error": None}
