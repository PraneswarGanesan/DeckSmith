"""
Document Service — parses a Markdown string and stores the full structure to Supabase.

Key improvements over original:
  1. Uses the updated markdown_parser that captures section-level content (## level)
     instead of dropping it silently.
  2. Tables are attached to the subsection they physically appear within
     (position-based), not cursor-sequentially.
  3. Embedding + summary generation are opt-in (ENABLE_PARSE_EMBEDDINGS=true).
"""
from __future__ import annotations

import os

from core.llm import generate as llm_generate, embed as llm_embed
from core.database import (
    insert_document,
    insert_section,
    insert_subsection,
    insert_table,
)
from utils.markdown_parser import parse_markdown
from logger import get_logger

logger = get_logger(__name__)

_EMBEDDINGS_ON = os.getenv("ENABLE_PARSE_EMBEDDINGS", "false").lower() == "true"


# ── Ollama / Gemini helpers ───────────────────────────────────────────────────

async def _get_embedding(text: str) -> list[float] | None:
    if not _EMBEDDINGS_ON:
        return None
    try:
        return await llm_embed(text)
    except Exception as exc:
        logger.warning(f"[DocService] Embedding skipped: {exc}")
        return None


async def _summarise(title: str, content: str) -> str:
    """First-sentence summary — skipped (local) when ENABLE_PARSE_EMBEDDINGS=false."""
    if not _EMBEDDINGS_ON:
        for sentence in content.replace("\n", " ").split("."):
            sentence = sentence.strip()
            if len(sentence) > 20:
                return sentence[:200]
        return content[:200]

    try:
        raw = await llm_generate(
            f"One sentence summary:\nTitle: {title}\n{content[:400]}",
            temperature=0.1,
            max_tokens=80,
        )
        return raw.strip()[:300]
    except Exception as exc:
        logger.warning(f"[DocService] Summary skipped: {exc}")
        return content[:200]


def _extract_keywords(title: str, content: str) -> list[str]:
    """Pure-Python keyword extraction — no LLM needed."""
    text = f"{title} {content}".lower()
    seen: set[str] = set()
    keywords: list[str] = []
    for word in text.split():
        w = word.strip(".,;:!?\"'()-[]")
        if len(w) > 4 and w.isalpha() and w not in seen:
            seen.add(w)
            keywords.append(w)
        if len(keywords) >= 20:
            break
    return keywords


# ── Public API ────────────────────────────────────────────────────────────────

async def parse_and_store_markdown(markdown_text: str) -> dict:
    """
    Parse *markdown_text* and persist every section, subsection, and table to Supabase.

    Tables are stored under the subsection they belong to (position-based),
    not cursor-sequentially.

    Returns: {doc_id, doc_title, sections (int), subsections (int)}
    """
    if _EMBEDDINGS_ON:
        logger.info("[DocService] Embedding mode ON — Ollama/Gemini will be called per subsection")
    else:
        logger.info("[DocService] Fast mode — skipping embeddings at parse time (BM25 only)")

    parsed = parse_markdown(markdown_text)

    doc_title: str = parsed.get("title") or "Untitled"
    doc_id = insert_document(doc_title, executive_summary="")
    logger.info(f"[DocService] Created doc_id={doc_id} title='{doc_title}'")

    section_count    = 0
    subsection_count = 0

    for section in parsed.get("sections", []):
        sec_id = insert_section(
            doc_id,
            section["section_index"],
            section["section_title"],
        )
        section_count += 1

        for sub in section.get("subsections", []):
            content  = sub["content"].strip()
            title    = sub["subsection_title"]
            # Remove table placeholder lines from content text
            clean_content = "\n".join(
                l for l in content.splitlines()
                if not l.strip().startswith("[TABLE:")
            ).strip()

            summary   = await _summarise(title, clean_content)
            keywords  = _extract_keywords(title, clean_content)
            embedding = await _get_embedding(f"{title} {clean_content[:500]}")

            sub_id = insert_subsection(
                section_id        = sec_id,
                subsection_index  = sub["subsection_index"],
                subsection_title  = title,
                content           = clean_content,
                summary           = summary,
                keywords          = keywords,
                embedding         = embedding,
            )
            subsection_count += 1
            logger.debug(f"[DocService] Stored subsection '{title}'")

            # ── Store tables that belong to THIS subsection (position-based) ──
            for tbl in sub.get("tables", []):
                try:
                    insert_table(
                        sub_id,
                        tbl.get("table_title") or title,
                        tbl["headers"],
                        tbl["rows"],
                    )
                    logger.debug(
                        f"[DocService] Stored table '{tbl.get('table_title', '')}' "
                        f"for subsection '{title}'"
                    )
                except Exception as exc:
                    logger.warning(f"[DocService] Table insert failed for '{title}': {exc}")

    logger.info(
        f"[DocService] Done — {section_count} sections, "
        f"{subsection_count} subsections stored for doc_id={doc_id}"
    )
    return {
        "doc_id":       doc_id,
        "doc_title":    doc_title,
        "sections":     section_count,
        "subsections":  subsection_count,
    }
