"""
Chart Agent — builds structured chart data (no matplotlib) for slides typed "chart".
The data is consumed by python-pptx's native chart API in the Template Agent.
"""
from __future__ import annotations

from core.database import get_tables_for_subsection
from utils.chart_utils import build_chart_data
from logger import get_logger

logger = get_logger(__name__)


async def chart_node(state: dict) -> dict:
    slides: list[dict] = state.get("slides", [])
    charts: list[dict] = []

    for i, slide in enumerate(slides):
        if slide.get("type") != "chart" or not slide.get("subsection_id"):
            charts.append({})
            continue

        try:
            tables = get_tables_for_subsection(slide["subsection_id"])
            if not tables:
                logger.debug(f"[Chart] Slide {i} has type=chart but no tables found")
                charts.append({})
                continue

            chart_data = build_chart_data(tables[0])
            charts.append(chart_data or {})
            logger.debug(f"[Chart] Slide {i}: chart_data={'ready' if chart_data else 'empty'}")
        except Exception as exc:
            logger.warning(f"[Chart] Slide {i}: Failed to fetch chart data ({type(exc).__name__}): {exc}")
            charts.append({})

    logger.info(f"[Chart] Processed {len(charts)} slides")
    return {"charts": charts, "error": None}
