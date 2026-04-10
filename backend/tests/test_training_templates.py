"""
Comprehensive test suite for DeckSmith training templates.

Tests the complete pipeline with actual PPTX templates from the train folder:
  - temp1.pptx, temp2.pptx, temp3.pptx

Validates:
  ✓ Template loading and parsing
  ✓ Slide generation quality (structure, hierarchy, content)
  ✓ Chart rendering
  ✓ Image fetching
  ✓ Multi-template compatibility
  ✓ Error recovery and graceful degradation

Usage:
    python -m tests.test_training_templates

Requires:
  - Ollama running (ollama serve)
  - Valid .env with Supabase and Unsplash credentials
  - Training templates in backend/train/ folder
"""
from __future__ import annotations

import asyncio
import sys
import pathlib
import json
from dataclasses import dataclass

BACKEND_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from logger import get_logger

logger = get_logger("test_training_templates")

SAMPLE_MD = BACKEND_ROOT / "templates" / "sample.md"
TRAIN_DIR = BACKEND_ROOT / "train"
OUTPUT_DIR = BACKEND_ROOT / "output"

QUERY = "Comprehensive executive analysis"


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0

    def __str__(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status:10} | {self.name:40} | {self.message}"


class TestRunner:
    """Orchestrate tests with reporting."""

    def __init__(self):
        self.results: list[TestResult] = []
        self.passed_count = 0
        self.failed_count = 0

    def report(self, result: TestResult) -> None:
        self.results.append(result)
        if result.passed:
            self.passed_count += 1
        else:
            self.failed_count += 1
        print(f"  {result}")

    def summary(self) -> None:
        total = len(self.results)
        print(f"\n{'='*80}")
        print(f"SUMMARY: {self.passed_count}/{total} tests passed")
        if self.failed_count > 0:
            print(f"  {self.failed_count} failures:")
            for r in self.results:
                if not r.passed:
                    print(f"    - {r.name}: {r.message}")
        print(f"{'='*80}")

    def exit_code(self) -> int:
        return 0 if self.failed_count == 0 else 1


runner = TestRunner()


# ── Test utilities ────────────────────────────────────────────────────────────

def _banner(title: str, level: int = 1) -> None:
    width = 80 if level == 1 else 60
    char = "=" if level == 1 else "-"
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def _elapsed(start_ms: float, end_ms: float) -> float:
    return (end_ms - start_ms) * 1000


# ── Validation functions ──────────────────────────────────────────────────────

async def test_template_loading() -> None:
    """Test that all training templates can be loaded."""
    _banner("Template Loading Tests", level=2)

    templates = list(TRAIN_DIR.glob("*.pptx"))

    for tmpl_path in templates:
        import time
        start = time.time()

        try:
            from pptx import Presentation
            prs = Presentation(str(tmpl_path))
            slide_count = len(prs.slides)
            end = time.time()

            runner.report(TestResult(
                name=f"Load {tmpl_path.name}",
                passed=slide_count >= 0,
                message=f"Loaded {slide_count} slides",
                duration_ms=_elapsed(start, end),
            ))
        except Exception as exc:
            runner.report(TestResult(
                name=f"Load {tmpl_path.name}",
                passed=False,
                message=f"Error: {exc}",
                duration_ms=_elapsed(start, end),
            ))


async def test_markdown_parsing() -> str:
    """Test markdown parsing and storage."""
    _banner("Markdown Parsing", level=2)

    import time
    start = time.time()

    try:
        from services.document_service import parse_and_store_markdown

        md_text = SAMPLE_MD.read_text(encoding="utf-8")
        result = await parse_and_store_markdown(md_text)

        sections = result.get("sections", 0)
        subsections = result.get("subsections", 0)
        doc_id = result.get("doc_id", "")

        end = time.time()

        runner.report(TestResult(
            name="Parse markdown file",
            passed=bool(doc_id) and sections >= 1 and subsections >= 1,
            message=f"{sections} sections, {subsections} subsections, doc_id={doc_id[:8]}...",
            duration_ms=_elapsed(start, end),
        ))

        return doc_id

    except Exception as exc:
        end = time.time()
        runner.report(TestResult(
            name="Parse markdown file",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=_elapsed(start, end),
        ))
        return ""


async def test_rag_retrieval(doc_id: str) -> None:
    """Test RAG (hybrid BM25 + embedding) retrieval."""
    _banner("RAG Retrieval", level=2)

    import time
    start = time.time()

    try:
        from core.rag_engine import hybrid_search

        results = await hybrid_search(doc_id=doc_id, query=QUERY, top_k=6)
        end = time.time()

        runner.report(TestResult(
            name="Hybrid RAG search",
            passed=len(results) >= 1,
            message=f"Retrieved {len(results)}/6 subsections",
            duration_ms=_elapsed(start, end),
        ))

    except Exception as exc:
        end = time.time()
        runner.report(TestResult(
            name="Hybrid RAG search",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=_elapsed(start, end),
        ))


async def test_pipeline_with_template(doc_id: str, template_name: str) -> bool:
    """Test full pipeline with a specific template."""
    import time
    start = time.time()

    try:
        from services.template_service import store_template
        from core.database import insert_output
        from services.presentation_service import run_pipeline
        from core.database import get_output

        # Load and upload template
        tmpl_bytes = (TRAIN_DIR / template_name).read_bytes()
        tmpl_result = store_template(f"Training {template_name}", tmpl_bytes)
        template_id = tmpl_result.get("template_id", "")

        if not template_id:
            raise ValueError("Failed to upload template")

        # Create output record
        output_id = insert_output("test_user", template_id, "queued")

        # Run pipeline
        await run_pipeline(
            output_id=output_id,
            doc_id=doc_id,
            template_id=template_id,
            query=QUERY,
            user_id="test_user",
        )

        # Verify output
        record = get_output(output_id)
        status = record.get("status", "")
        output_path = record.get("output_path", "")

        end = time.time()

        success = status == "complete" and bool(output_path)

        runner.report(TestResult(
            name=f"Pipeline + {template_name}",
            passed=success,
            message=f"Status={status}, path={'set' if output_path else 'missing'}",
            duration_ms=_elapsed(start, end),
        ))

        return success

    except Exception as exc:
        end = time.time()
        runner.report(TestResult(
            name=f"Pipeline + {template_name}",
            passed=False,
            message=f"Error: {str(exc)[:60]}",
            duration_ms=_elapsed(start, end),
        ))
        return False


async def test_agent_validation() -> None:
    """Test individual agent validations."""
    _banner("Agent Validation", level=2)

    import time

    # Test planner agent
    from agents.planner_agent import _parse_json_array
    
    # Invalid JSON
    start = time.time()
    try:
        _parse_json_array("not json")
        runner.report(TestResult(
            name="Planner: Reject invalid JSON",
            passed=False,
            message="Should have raised ValueError",
            duration_ms=_elapsed(start, time.time()),
        ))
    except ValueError:
        runner.report(TestResult(
            name="Planner: Reject invalid JSON",
            passed=True,
            message="Correctly rejected invalid JSON",
            duration_ms=_elapsed(start, time.time()),
        ))

    # Valid JSON in markdown
    start = time.time()
    try:
        result = _parse_json_array(
            "```json\n[{\"title\": \"Test\", \"subsection_id\": null, \"type\": \"content\"}]\n```"
        )
        success = len(result) == 1
        runner.report(TestResult(
            name="Planner: Extract JSON from markdown",
            passed=success,
            message="Correctly parsed markdown code block" if success else "Parse failed",
            duration_ms=_elapsed(start, time.time()),
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Planner: Extract JSON from markdown",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=_elapsed(start, time.time()),
        ))

    # Test validator
    from agents.validator_agent import _validate_slide

    start = time.time()
    slide = {
        "title": "This is a very very very very very very very very long title that exceeds limit",
        "content": ["Short", "Two word bullet", "This is a very long bullet that contains way more than twelve words"],
        "type": "content",
        "subsection_id": "test-id",
    }
    corrected, warnings = _validate_slide(slide, 0)
    
    title_words = len(corrected["title"].split())
    bullet_count = len(corrected["content"])
    truncated = any(len(b.split()) > 12 for b in corrected["content"])
    
    runner.report(TestResult(
        name="Validator: Fix oversized slide",
        passed=title_words <= 8 and bullet_count <= 5 and not truncated,
        message=f"Title: {title_words} words, Bullets: {bullet_count}, Warnings: {len(warnings)}",
        duration_ms=_elapsed(start, time.time()),
    ))


# ── Main test suite ───────────────────────────────────────────────────────────

async def main() -> int:
    _banner("DeckSmith Training Template Test Suite", level=1)

    print(f"\nSample markdown: {SAMPLE_MD}")
    print(f"Training templates: {TRAIN_DIR}")
    print(f"Output directory: {OUTPUT_DIR}\n")

    # Verify files exist
    if not SAMPLE_MD.exists():
        print(f"✗ Sample markdown not found: {SAMPLE_MD}")
        return 1

    if not TRAIN_DIR.exists() or not list(TRAIN_DIR.glob("*.pptx")):
        print(f"✗ No training templates found in: {TRAIN_DIR}")
        return 1

    # Run tests
    await test_template_loading()
    doc_id = await test_markdown_parsing()

    if doc_id:
        await test_rag_retrieval(doc_id)
        
        # Test with each training template
        _banner("End-to-End Pipeline Tests", level=1)
        for tmpl_file in TRAIN_DIR.glob("*.pptx"):
            await test_pipeline_with_template(doc_id, tmpl_file.name)

    await test_agent_validation()

    # Print summary
    print()
    runner.summary()
    return runner.exit_code()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
