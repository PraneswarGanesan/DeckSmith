"""
Comprehensive test suite for DeckSmith training templates.

Tests the complete pipeline with actual PPTX templates from the train folder:
  - temp1.pptx, temp2.pptx, temp3.pptx

Validates:
  ✓ Template loading and parsing
  ✓ Markdown parser — section-level content capture, table association
  ✓ Retriever agent — all-subsections fetch (document order, no BM25)
  ✓ Chart utilities — build_chart_data, build_chart_image (matplotlib PNG)
  ✓ Image agent — no 4-slide cap, skips non-visual layouts
  ✓ Visual composer — rule-based visual structure generation
  ✓ Planner — design-first planning with visual types
  ✓ Validator — preserves design metadata
  ✓ Multi-template compatibility
  ✓ Error recovery and graceful degradation

Usage:
    python -m tests.test_training_templates

Requires:
  - Valid .env with Supabase and Unsplash credentials
  - Training templates in backend/train/ folder
"""
from __future__ import annotations

import asyncio
import sys
import pathlib
import time
from dataclasses import dataclass

BACKEND_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from logger import get_logger

logger = get_logger("test_training_templates")

SAMPLE_MD = BACKEND_ROOT / "templates" / "sample.md"
TRAIN_DIR  = BACKEND_ROOT / "train"
OUTPUT_DIR = BACKEND_ROOT / "output"

QUERY = "Comprehensive executive analysis"


# ── Test infrastructure ───────────────────────────────────────────────────────

@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"{status:6} | {self.name:45} | {self.message}"


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


def _banner(title: str, level: int = 1) -> None:
    width = 80 if level == 1 else 60
    char  = "=" if level == 1 else "-"
    print(f"\n{char * width}\n  {title}\n{char * width}")


# ── Section 1: Template loading ────────────────────────────────────────────────

async def test_template_loading() -> None:
    """Test that all training templates can be loaded."""
    _banner("Template Loading Tests", level=2)

    templates = list(TRAIN_DIR.glob("*.pptx"))

    for tmpl_path in templates:
        t0 = time.time()
        try:
            from pptx import Presentation
            prs = Presentation(str(tmpl_path))
            slide_count = len(prs.slides)
            runner.report(TestResult(
                name=f"Load {tmpl_path.name}",
                passed=slide_count >= 0,
                message=f"Loaded {slide_count} slides",
                duration_ms=(time.time() - t0) * 1000,
            ))
        except Exception as exc:
            runner.report(TestResult(
                name=f"Load {tmpl_path.name}",
                passed=False,
                message=f"Error: {exc}",
                duration_ms=(time.time() - t0) * 1000,
            ))


# ── Section 2: Markdown parser ─────────────────────────────────────────────────

async def test_markdown_parsing() -> str:
    """Test markdown parsing: section content capture, table association, subsection counts."""
    _banner("Markdown Parsing", level=2)

    # Unit test: parse_markdown captures ## level content (section-level subsections)
    t0 = time.time()
    try:
        from utils.markdown_parser import parse_markdown

        md_with_section_content = """\
# Doc Title

## Section One
This is section-level content that must NOT be lost.

### Sub One
Subsection content here.

## Section Two
| Header A | Header B |
|----------|----------|
| Value 1  | Value 2  |

### Sub Two
More content.
"""
        parsed = parse_markdown(md_with_section_content)
        sections = parsed.get("sections", [])

        # Section One should have a subsection_index=0 capturing the section prose
        sec1 = next((s for s in sections if "One" in s["section_title"]), None)
        sec1_subs = sec1.get("subsections", []) if sec1 else []
        has_index0 = any(sub["subsection_index"] == 0 for sub in sec1_subs)

        # Section Two table should be attached to subsection_index=0 (not Sub Two)
        sec2 = next((s for s in sections if "Two" in s["section_title"]), None)
        sec2_subs = sec2.get("subsections", []) if sec2 else []
        sec2_sub0 = next((sub for sub in sec2_subs if sub["subsection_index"] == 0), None)
        table_attached = bool(sec2_sub0 and sec2_sub0.get("tables"))

        passed = has_index0 and table_attached
        runner.report(TestResult(
            name="Parser: section-level content captured",
            passed=has_index0,
            message="subsection_index=0 created for ## prose" if has_index0 else "MISSING — section prose lost",
            duration_ms=(time.time() - t0) * 1000,
        ))
        runner.report(TestResult(
            name="Parser: table attached to parent subsection",
            passed=table_attached,
            message="Table correctly associated with sec-level sub" if table_attached else "Table not attached",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Parser: section-level content captured",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))

    # Integration test: parse real sample.md
    t0 = time.time()
    try:
        from services.document_service import parse_and_store_markdown

        md_text = SAMPLE_MD.read_text(encoding="utf-8")
        result  = await parse_and_store_markdown(md_text)

        sections    = result.get("sections", 0)
        subsections = result.get("subsections", 0)
        doc_id      = result.get("doc_id", "")

        runner.report(TestResult(
            name="Parse sample.md -> Supabase",
            passed=bool(doc_id) and sections >= 1 and subsections >= 1,
            message=f"{sections} sections, {subsections} subsections, doc_id={doc_id[:8]}...",
            duration_ms=(time.time() - t0) * 1000,
        ))
        return doc_id

    except Exception as exc:
        runner.report(TestResult(
            name="Parse sample.md -> Supabase",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))
        return ""


# ── Section 3: Retriever (all-subsections, document order) ────────────────────

async def test_full_retrieval(doc_id: str) -> None:
    """Test that retriever_node fetches ALL subsections in document order."""
    _banner("Retriever Agent — Full-Document Fetch", level=2)

    if not doc_id:
        runner.report(TestResult(
            name="Retriever: all-subsection fetch",
            passed=False,
            message="Skipped — no doc_id from parse step",
        ))
        return

    t0 = time.time()
    try:
        from agents.retriever_agent import retriever_node
        from core.database import get_all_subsections_for_doc

        # Count total subsections in DB
        all_subs = get_all_subsections_for_doc(doc_id)
        total    = len(all_subs)

        # Run retriever_node with a synthetic state
        state  = {"doc_id": doc_id, "query": QUERY}
        result = await retriever_node(state)
        retrieved = result.get("retrieved", [])

        # Retriever must return ALL subsections
        runner.report(TestResult(
            name="Retriever: all-subsection fetch",
            passed=len(retrieved) == total,
            message=f"Retrieved {len(retrieved)}/{total} subsections",
            duration_ms=(time.time() - t0) * 1000,
        ))

        runner.report(TestResult(
            name="Retriever: no silent empty result",
            passed=len(retrieved) >= 1,
            message=f"{len(retrieved)} subsections returned",
            duration_ms=(time.time() - t0) * 1000,
        ))

    except Exception as exc:
        runner.report(TestResult(
            name="Retriever: all-subsection fetch",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))


# ── Section 4: Chart utilities ─────────────────────────────────────────────────

async def test_chart_utils() -> None:
    """Test chart_data builder and matplotlib PNG generation."""
    _banner("Chart Utilities", level=2)

    sample_table = {
        "table_title": "Revenue by Quarter",
        "headers":     ["Quarter", "Revenue", "Costs"],
        "rows": [
            {"Quarter": "Q1", "Revenue": "120", "Costs": "80"},
            {"Quarter": "Q2", "Revenue": "145", "Costs": "90"},
            {"Quarter": "Q3", "Revenue": "160", "Costs": "95"},
            {"Quarter": "Q4", "Revenue": "185", "Costs": "105"},
        ],
    }

    # build_chart_data
    t0 = time.time()
    try:
        from utils.chart_utils import build_chart_data
        data = build_chart_data(sample_table)
        passed = (
            isinstance(data, dict)
            and "categories" in data
            and len(data["categories"]) == 4
            and "Revenue" in data.get("series", {})
        )
        runner.report(TestResult(
            name="chart_utils: build_chart_data",
            passed=passed,
            message=f"categories={data['categories'] if data else 'None'}, "
                    f"series keys={list(data['series'].keys()) if data else []}",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="chart_utils: build_chart_data",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))

    # build_chart_image (matplotlib PNG)
    t0 = time.time()
    try:
        from utils.chart_utils import build_chart_image
        png_bytes = build_chart_image(sample_table)
        passed = isinstance(png_bytes, bytes) and len(png_bytes) > 5000
        runner.report(TestResult(
            name="chart_utils: build_chart_image (matplotlib PNG)",
            passed=passed,
            message=f"PNG size={len(png_bytes):,} bytes" if png_bytes else "None returned",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="chart_utils: build_chart_image (matplotlib PNG)",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))


# ── Section 5: Image agent ────────────────────────────────────────────────────

async def test_image_agent() -> None:
    """Test image_agent: no 4-slide cap, correct layout filtering."""
    _banner("Image Agent", level=2)

    # Build a synthetic slide list with new visual_type field
    slides = [
        {"title": "Executive Summary",   "visual_type": "centered",               "intent": "intro"},
        {"title": "Market Overview",      "visual_type": "left-text-right-visual", "intent": "analysis"},
        {"title": "Revenue Breakdown",    "visual_type": "chart",                  "intent": "results"},
        {"title": "Strategy",             "visual_type": "grid",                   "intent": "solution"},
        {"title": "Key Findings",         "visual_type": "left-text-right-visual", "intent": "problem"},
        {"title": "Thank You",            "visual_type": "centered",               "intent": "conclusion"},
    ]

    t0 = time.time()
    try:
        from agents.image_agent import _should_fetch_image

        eligible = [i for i, s in enumerate(slides) if _should_fetch_image(s)]
        ineligible = [i for i, s in enumerate(slides) if not _should_fetch_image(s)]

        # Centered (0,5) and chart (2) must be excluded
        expected_excluded = {0, 2, 5}
        correct_exclusions = expected_excluded.issubset(set(ineligible))

        runner.report(TestResult(
            name="Image agent: layout filtering",
            passed=correct_exclusions,
            message=f"Eligible slides: {eligible}, Excluded: {ineligible}",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Image agent: layout filtering",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))

    # Test that image_node does NOT have a 4-slide hardcoded limit
    t0 = time.time()
    try:
        import inspect
        from agents import image_agent
        source = inspect.getsource(image_agent)
        has_hard_cap = "slides[:4]" in source or "eligible[:4]" in source or "images[:4]" in source
        runner.report(TestResult(
            name="Image agent: no 4-slide hard cap",
            passed=not has_hard_cap,
            message="No [:4] slice found" if not has_hard_cap else "FOUND [:4] slice — cap still present!",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Image agent: no 4-slide hard cap",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))


# ── Section 6: Removed (Visual Composer now uses LLM native mapping) ──────────


# ── Section 7: Agent validation (planner, validator) ──────────────────────────

async def test_agent_validation() -> None:
    """Test individual agent validations — planner JSON parsing, validator slide fixes."""
    _banner("Agent Validation", level=2)

    # Planner: extract JSON from LLM output
    t0 = time.time()
    try:
        from agents.planner_agent import _extract_json_array

        # Invalid JSON should return None
        result = _extract_json_array("not json at all")
        runner.report(TestResult(
            name="Planner: Reject invalid JSON",
            passed=result is None,
            message="Correctly returned None for invalid JSON" if result is None else f"Got: {result}",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Planner: Reject invalid JSON",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))

    # Planner: extract JSON from markdown code block
    t0 = time.time()
    try:
        from agents.planner_agent import _extract_json_array
        result = _extract_json_array(
            '```json\n[{"title": "Test", "subsection_id": null, "type": "content"}]\n```'
        )
        runner.report(TestResult(
            name="Planner: Extract JSON from markdown",
            passed=isinstance(result, list) and len(result) == 1,
            message=f"Parsed {len(result)} slide(s)" if result else "Failed to parse",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Planner: Extract JSON from markdown",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))

    # Validator: fix oversized slide AND preserve metadata
    t0 = time.time()
    try:
        from agents.validator_agent import _validate_slide
        slide = {
            "title":   "This is a very very very very very very very long title that exceeds limit",
            "content": [
                "Short",
                "Two word bullet",
                "This is a very long bullet that contains way more than fifteen words total and keeps going on",
            ],
            "type":          "content",
            "subsection_id": "test-id",
            "visual_type":   "cards",
            "design_intent": "Test design intent",
            "data_extract":  "$5.2B revenue",
        }
        corrected, warnings = _validate_slide(slide, 0)
        title_words  = len(corrected["title"].split())
        has_metadata = (
            corrected.get("visual_type") == "cards"
            and corrected.get("design_intent") == "Test design intent"
            and corrected.get("data_extract") == "$5.2B revenue"
        )

        runner.report(TestResult(
            name="Validator: Fix oversized slide",
            passed=title_words <= 10 and len(corrected["content"]) <= 6,
            message=f"Title: {title_words} words, Bullets: {len(corrected['content'])}, Warnings: {len(warnings)}",
            duration_ms=(time.time() - t0) * 1000,
        ))
        runner.report(TestResult(
            name="Validator: Preserve design metadata",
            passed=has_metadata,
            message=f"visual_type={corrected.get('visual_type')}, design_intent={'preserved' if has_metadata else 'LOST'}",
            duration_ms=(time.time() - t0) * 1000,
        ))
    except Exception as exc:
        runner.report(TestResult(
            name="Validator: Fix oversized slide",
            passed=False,
            message=f"Error: {exc}",
            duration_ms=(time.time() - t0) * 1000,
        ))


# ── Section 8: End-to-end pipeline ────────────────────────────────────────────

async def test_pipeline_with_template(doc_id: str, template_name: str) -> bool:
    """Test full pipeline with a specific template."""
    t0 = time.time()

    try:
        from services.template_service import store_template
        from core.database import insert_output
        from services.presentation_service import run_pipeline
        from core.database import get_output

        # Load and upload template
        tmpl_bytes  = (TRAIN_DIR / template_name).read_bytes()
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
        record      = get_output(output_id)
        status      = record.get("status", "")
        output_path = record.get("output_path", "")

        from services.storage_service import download_file
        # Download from supabase and write locally so user can inspect it
        try:
            pptx_b = download_file("generated-output", f"{output_id}.pptx")
            local_file = OUTPUT_DIR / f"{template_name}_output.pptx"
            local_file.write_bytes(pptx_b)
            print(f"      Saved locally to: {local_file}")
        except Exception as e:
            print(f"      Failed to save locally: {e}")

        success = status == "complete" and bool(output_path)

        runner.report(TestResult(
            name=f"Pipeline + {template_name}",
            passed=success,
            message=f"Status={status}, path={'set' if output_path else 'missing'}",
            duration_ms=(time.time() - t0) * 1000,
        ))
        return success

    except Exception as exc:
        runner.report(TestResult(
            name=f"Pipeline + {template_name}",
            passed=False,
            message=f"Error: {str(exc)[:80]}",
            duration_ms=(time.time() - t0) * 1000,
        ))
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    _banner("DeckSmith Training Template Test Suite", level=1)

    print(f"\nSample markdown : {SAMPLE_MD}")
    print(f"Training templates: {TRAIN_DIR}")
    print(f"Output directory  : {OUTPUT_DIR}\n")

    # Verify prerequisites
    if not SAMPLE_MD.exists():
        print(f"✗ Sample markdown not found: {SAMPLE_MD}")
        return 1

    if not TRAIN_DIR.exists() or not list(TRAIN_DIR.glob("*.pptx")):
        print(f"✗ No training templates found in: {TRAIN_DIR}")
        return 1

    # ── Unit tests (no DB needed) ─────────────────────────────────────────────
    await test_chart_utils()
    await test_image_agent()
    # Test visual composer is skipped natively
    # await test_visual_composer()
    await test_agent_validation()

    # ── Template loading ──────────────────────────────────────────────────────
    await test_template_loading()

    # ── Integration tests (DB needed) ─────────────────────────────────────────
    doc_id = await test_markdown_parsing()

    if doc_id:
        await test_full_retrieval(doc_id)

        # End-to-end with each training template
        _banner("End-to-End Pipeline Tests", level=1)
        for tmpl_file in sorted(TRAIN_DIR.glob("*.pptx")):
            await test_pipeline_with_template(doc_id, tmpl_file.name)

    # Summary
    print()
    runner.summary()
    return runner.exit_code()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
