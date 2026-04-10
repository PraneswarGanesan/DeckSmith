"""
Integration test — end-to-end pipeline smoke test.

Usage:
    python -m tests.test_full_agentic

What it does:
  1. Parses the sample markdown and stores it in Supabase
  2. Uploads the sample .pptx template
  3. Runs the full agent pipeline (retrieve → plan → content → chart → image → critic → template)
  4. Saves the resulting .pptx to output/test_output.pptx
  5. Prints a pass/fail summary

Requires:
  - Ollama running locally (ollama serve)
  - Valid .env with SUPABASE_URL, SUPABASE_SERVICE_KEY, UNSPLASH_ACCESS_KEY
"""
from __future__ import annotations

import asyncio
import os
import sys
import pathlib

# Make sure the backend root is on sys.path
BACKEND_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from logger import get_logger

logger = get_logger("test_full_agentic")

SAMPLE_MD   = BACKEND_ROOT / "templates" / "sample.md"
SAMPLE_PPTX = BACKEND_ROOT / "templates" / "sample.pptx"
OUTPUT_DIR  = BACKEND_ROOT / "output"
OUTPUT_FILE = OUTPUT_DIR / "test_output.pptx"

QUERY = "Give me an executive overview of the document"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _banner(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def _check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        raise AssertionError(f"Check failed: {label}")


# ── Test steps ────────────────────────────────────────────────────────────────

async def test_parse_markdown() -> str:
    _banner("Step 1 — Parse & store markdown")
    from services.document_service import parse_and_store_markdown

    md_text = SAMPLE_MD.read_text(encoding="utf-8")
    result = await parse_and_store_markdown(md_text)

    _check("doc_id is non-empty",     bool(result.get("doc_id")))
    _check("at least 1 section",      result.get("sections", 0) >= 1)
    _check("at least 1 subsection",   result.get("subsections", 0) >= 1)

    doc_id = result["doc_id"]
    print(f"  doc_id = {doc_id}")
    return doc_id


def test_upload_template() -> str:
    _banner("Step 2 — Upload template")
    from services.template_service import store_template

    pptx_bytes = SAMPLE_PPTX.read_bytes()
    result = store_template("Test Template", pptx_bytes)

    _check("template_id is non-empty", bool(result.get("template_id")))

    template_id = result["template_id"]
    print(f"  template_id = {template_id}")
    return template_id


async def test_rag(doc_id: str) -> None:
    _banner("Step 3 — RAG search")
    from core.rag_engine import hybrid_search

    results = await hybrid_search(doc_id=doc_id, query=QUERY, top_k=4)
    _check("RAG returns at least 1 result", len(results) >= 1)
    print(f"  Retrieved {len(results)} subsections")
    for r in results:
        print(f"    · {r['subsection_title']}")


async def test_pipeline(doc_id: str, template_id: str) -> bytes:
    _banner("Step 4 — Full pipeline")
    from core.database import insert_output
    from services.presentation_service import run_pipeline
    from core.database import get_output

    output_id = insert_output("test_user", template_id, "queued")
    print(f"  output_id = {output_id}")

    await run_pipeline(
        output_id=output_id,
        doc_id=doc_id,
        template_id=template_id,
        query=QUERY,
        user_id="test_user",
    )

    record = get_output(output_id)
    _check("status == complete", record.get("status") == "complete")
    _check("output_path set",    bool(record.get("output_path")))
    print(f"  output_path = {record.get('output_path')}")

    # Download the generated PPTX
    from services.storage_service import download_file
    from config import settings
    pptx_bytes = download_file(settings.STORAGE_BUCKET_OUTPUT, record["output_path"])
    _check("PPTX is non-empty",  len(pptx_bytes) > 1000)
    return pptx_bytes


def save_output(pptx_bytes: bytes) -> None:
    _banner("Step 5 — Save local copy")
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_bytes(pptx_bytes)
    _check("File saved successfully", OUTPUT_FILE.exists())
    print(f"  Saved to: {OUTPUT_FILE}")


# ── Runner ────────────────────────────────────────────────────────────────────

async def main() -> None:
    _banner("DeckSmith — Full Integration Test")

    try:
        doc_id      = await test_parse_markdown()
        template_id = test_upload_template()
        await test_rag(doc_id)
        pptx_bytes  = await test_pipeline(doc_id, template_id)
        save_output(pptx_bytes)
        _banner("ALL TESTS PASSED")
    except AssertionError as exc:
        _banner(f"TEST FAILED: {exc}")
        sys.exit(1)
    except Exception as exc:
        _banner(f"UNEXPECTED ERROR: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
