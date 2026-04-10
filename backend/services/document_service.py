"""
Document Service — parses a Markdown string and stores the full structure to Supabase.

Embedding + summary generation are DISABLED during parse by default to keep
upload fast on low-RAM machines. BM25 keyword search works without embeddings.
Set ENABLE_PARSE_EMBEDDINGS=true in .env to turn them on.
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
from utils.table_parser import extract_tables
from logger import get_logger

logger = get_logger(__name__)

# Opt-in: set ENABLE_PARSE_EMBEDDINGS=true in .env to generate embeddings at
# upload time. On slow machines leave this false — embeddings are generated
# lazily during the first pipeline run instead.
_EMBEDDINGS_ON = os.getenv("ENABLE_PARSE_EMBEDDINGS", "false").lower() == "true"
_TIMEOUT_EMBED = 15   # seconds — give up fast if Ollama is overloaded
_TIMEOUT_LLM   = 20


# ── Ollama helpers ────────────────────────────────────────────────────────────

async def _get_embedding(text: str) -> list[float] | None:
    if not _EMBEDDINGS_ON:
        return None
    try:
        return await llm_embed(text)
    except Exception as exc:
        logger.warning(f"[DocService] Embedding skipped: {exc}")
        return None


async def _summarise(title: str, content: str) -> str:
    """1-sentence summary — skipped (local) when ENABLE_PARSE_EMBEDDINGS=false."""
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
    Parse *markdown_text* and persist to Supabase.

    Fast path (default, ENABLE_PARSE_EMBEDDINGS=false):
      • Keywords extracted locally (instant)
      • Summary = first sentence of content (instant)
      • No Ollama calls — upload completes in seconds
      • BM25 search still works perfectly

    Rich path (ENABLE_PARSE_EMBEDDINGS=true):
      • Calls Ollama for per-subsection summaries + embeddings
      • Enables semantic (cosine) search in addition to BM25

    Returns: {doc_id, doc_title, sections (int), subsections (int)}
    """
    if _EMBEDDINGS_ON:
        logger.info("[DocService] Embedding mode ON — Ollama will be called per subsection")
    else:
        logger.info("[DocService] Fast mode — skipping Ollama at parse time (BM25 only)")

    parsed = parse_markdown(markdown_text)
    all_tables = extract_tables(markdown_text)

    doc_title: str = parsed.get("title") or "Untitled"
    doc_id = insert_document(doc_title, executive_summary="")
    logger.info(f"[DocService] Created doc_id={doc_id} title='{doc_title}'")

    section_count = 0
    subsection_count = 0
    table_cursor = 0

    for section in parsed.get("sections", []):
        sec_id = insert_section(
            doc_id,
            section["section_index"],
            section["section_title"],
        )
        section_count += 1

        for sub in section.get("subsections", []):
            content = sub["content"].strip()
            title   = sub["subsection_title"]

            summary   = await _summarise(title, content)   # fast or LLM
            keywords  = _extract_keywords(title, content)  # always fast
            embedding = await _get_embedding(f"{title} {content[:500]}")  # None if disabled

            sub_id = insert_subsection(
                section_id=sec_id,
                subsection_index=sub["subsection_index"],
                subsection_title=title,
                content=content,
                summary=summary,
                keywords=keywords,
                embedding=embedding,
            )
            subsection_count += 1
            logger.debug(f"[DocService] Stored subsection '{title}'")

            # Attach the next available markdown table to this subsection
            if table_cursor < len(all_tables):
                tbl = all_tables[table_cursor]
                insert_table(sub_id, title, tbl["headers"], tbl["rows"])
                table_cursor += 1

    logger.info(
        f"[DocService] Done — {section_count} sections, "
        f"{subsection_count} subsections stored for doc_id={doc_id}"
    )
    return {
        "doc_id": doc_id,
        "doc_title": doc_title,
        "sections": section_count,
        "subsections": subsection_count,
    }
