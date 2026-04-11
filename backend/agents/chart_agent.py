"""
Chart Agent — generates chart data AND high-quality PNG images for slides.

Strategy:
  1. For slides explicitly typed "chart" with a subsection_id → fetch table from DB,
     build both chart_data (pptx native fallback) and chart_image (matplotlib PNG).
  2. For ANY slide whose content contains numeric patterns → attempt chart generation
     from in-line data detected in the content text (no DB needed).
  3. Produces one entry per slide in state["charts"]:
       {}                         → no chart
       {"chart_data": ...,
        "chart_image": bytes}     → full chart (image preferred by template agent)
"""
from __future__ import annotations

import re

from core.database import get_tables_for_subsection
from utils.chart_utils import build_chart_data, build_chart_image
from logger import get_logger

logger = get_logger(__name__)

# Regex to detect numeric-rich content worth charting
_HAS_NUMBERS = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[%$BMK]|\s+(?:billion|million|percent|%))")


def _content_has_chartable_numbers(text: str) -> bool:
    """Return True if the text contains multiple numeric data points."""
    return len(_HAS_NUMBERS.findall(text)) >= 3


async def chart_node(state: dict) -> dict:
    """
    Build chart data + matplotlib PNG for every slide that can benefit.

    Reads:  state["slides"]
    Writes: state["charts"]  — one dict per slide, empty dict if no chart
    """
    slides: list[dict] = state.get("slides", [])
    charts: list[dict] = []

    for i, slide in enumerate(slides):
        slide_type    = slide.get("type", "content")
        subsection_id = slide.get("subsection_id")
        layout        = slide.get("layout", "")
        content_text  = " ".join(slide.get("content", []))

        chart_entry: dict = {}

        # ── Path 1: DB table lookup (explicit chart slides) ───────────────
        if slide_type == "chart" and subsection_id:
            try:
                tables = get_tables_for_subsection(subsection_id)
                if tables:
                    tbl       = tables[0]
                    cdata     = build_chart_data(tbl)
                    cimage    = build_chart_image(tbl)

                    if cdata:
                        chart_entry["chart_data"] = cdata
                    if cimage:
                        chart_entry["chart_image"] = cimage

                    logger.debug(
                        f"[Chart] Slide {i} (type=chart): "
                        f"data={'ok' if cdata else 'none'} "
                        f"image={'ok' if cimage else 'none'}"
                    )
            except Exception as exc:
                logger.warning(f"[Chart] Slide {i} DB lookup failed: {exc}")

        # ── Path 2: In-line numeric detection for non-chart slides ────────
        # Even for content slides, if the content is number-heavy we try to
        # create a supplemental chart so the template can optionally show it.
        elif layout in ("chart", "comparison") or _content_has_chartable_numbers(content_text):
            if subsection_id:
                try:
                    tables = get_tables_for_subsection(subsection_id)
                    if tables:
                        tbl    = tables[0]
                        cdata  = build_chart_data(tbl)
                        cimage = build_chart_image(tbl)
                        if cdata:
                            chart_entry["chart_data"] = cdata
                        if cimage:
                            chart_entry["chart_image"] = cimage
                        logger.debug(
                            f"[Chart] Slide {i} (layout={layout}): inferred chart from table"
                        )
                except Exception as exc:
                    logger.debug(f"[Chart] Slide {i} inline chart failed: {exc}")

        charts.append(chart_entry)

    n_charts = sum(1 for c in charts if c)
    logger.info(f"[Chart] Processed {len(charts)} slides, {n_charts} have chart data")
    return {"charts": charts, "error": None}
