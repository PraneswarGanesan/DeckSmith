"""
Chart utilities — pure Python, no matplotlib.
Produces structured JSON data consumed by python-pptx native chart API.
"""
import re


def _extract_number(value: str) -> float | None:
    match = re.search(r"[-+]?\d*\.\d+|\d+", str(value).replace(",", ""))
    if match:
        return float(match.group())
    return None


def build_chart_data(table: dict) -> dict | None:
    """
    Convert a parsed table dict into chart-ready structured data.

    Returns:
        {
            "title": str,
            "categories": list[str],
            "series": {series_name: list[float]},
            "chart_type": "column" | "bar" | "line"
        }
        or None if the table cannot be charted.
    """
    headers = table.get("headers", [])
    rows = table.get("rows", [])

    if len(headers) < 2 or not rows:
        return None

    label_col = headers[0]
    value_cols = headers[1:]

    categories = [str(r.get(label_col, "")) for r in rows if r.get(label_col)]
    if not categories:
        return None

    series: dict[str, list[float]] = {}
    for col in value_cols:
        values = []
        for r in rows:
            val = _extract_number(r.get(col, "0") or "0")
            values.append(val if val is not None else 0.0)
        series[col] = values

    # Auto-detect chart type
    chart_type = "column"
    if len(categories) > 6:
        chart_type = "bar"
    elif len(value_cols) == 1:
        chart_type = "column"

    return {
        "title": table.get("table_title", "Data"),
        "categories": categories,
        "series": series,
        "chart_type": chart_type,
    }
