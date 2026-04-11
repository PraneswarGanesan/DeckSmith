"""
Chart utilities — produces chart data structures AND high-quality PNG images.

Two outputs:
  build_chart_data(table)  → structured JSON for python-pptx native charts
  build_chart_image(table) → PNG bytes (matplotlib) for embedding as a picture

Using matplotlib images is preferred: they look identical in all PowerPoint
viewers and are not subject to the rendering quirks of pptx native charts.
"""
from __future__ import annotations

import io
import re


# ── Number extraction ─────────────────────────────────────────────────────────

def _extract_number(value: str) -> float | None:
    match = re.search(r"[-+]?\d*\.\d+|\d+", str(value).replace(",", "").replace("%", ""))
    if match:
        return float(match.group())
    return None


# ── Structured chart data (for pptx native chart API) ────────────────────────

def build_chart_data(table: dict) -> dict | None:
    """
    Convert a parsed table dict into chart-ready structured data.

    Returns:
        {
            "title":      str,
            "categories": list[str],
            "series":     {series_name: list[float]},
            "chart_type": "column" | "bar" | "line"
        }
        or None if the table cannot be charted.
    """
    headers = table.get("headers", [])
    rows    = table.get("rows",    [])

    if len(headers) < 2 or not rows:
        return None

    label_col  = headers[0]
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
        # Only include series that have at least one non-zero value
        if any(v != 0.0 for v in values):
            series[col] = values

    if not series:
        return None

    chart_type = "bar" if len(categories) > 6 else "column"

    return {
        "title":      table.get("table_title", "Data"),
        "categories": categories,
        "series":     series,
        "chart_type": chart_type,
    }


# ── Matplotlib chart image (PNG bytes) ───────────────────────────────────────

# Accenture-style color palette matching the dark navy template
_PALETTE = [
    "#00BFFF",   # cyan accent
    "#FFD700",   # yellow
    "#FF6B6B",   # coral
    "#4ECDC4",   # teal
    "#45B7D1",   # sky blue
    "#96CEB4",   # sage
    "#FFEAA7",   # light yellow
]

_BG_DARK  = "#0D1B2A"   # dark navy background
_BG_LIGHT = "#F3F4F6"   # light grey (for light-theme slides)


def build_chart_image(
    table: dict,
    dark_theme: bool = True,
    width_in: float = 8.5,
    height_in: float = 4.5,
    dpi: int = 150,
) -> bytes | None:
    """
    Generate a publication-quality chart image from a table dict.

    Returns PNG bytes, or None if the table cannot be charted or
    matplotlib is unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")          # non-interactive backend — no display needed
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        return None

    chart_data = build_chart_data(table)
    if not chart_data:
        return None

    categories = chart_data["categories"]
    series     = chart_data["series"]
    title      = chart_data["title"]
    chart_type = chart_data["chart_type"]

    bg_color   = _BG_DARK if dark_theme else _BG_LIGHT
    text_color = "#FFFFFF" if dark_theme else "#1F2937"
    grid_color = "#2A3A4A" if dark_theme else "#E5E7EB"

    fig, ax = plt.subplots(figsize=(width_in, height_in))
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    n_series  = len(series)
    n_cats    = len(categories)
    bar_width = max(0.15, min(0.35, 0.8 / n_series))

    if chart_type in ("column", "bar"):
        import numpy as np
        x = np.arange(n_cats)
        offsets = [i - (n_series - 1) / 2 for i in range(n_series)]

        for idx, (sname, vals) in enumerate(series.items()):
            color = _PALETTE[idx % len(_PALETTE)]
            if chart_type == "column":
                bars = ax.bar(
                    x + offsets[idx] * bar_width,
                    vals,
                    width=bar_width,
                    color=color,
                    label=sname,
                    alpha=0.9,
                    zorder=3,
                )
                # Value labels on top of bars
                for bar, val in zip(bars, vals):
                    if val:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + max(vals) * 0.01,
                            f"{val:,.0f}" if val == int(val) else f"{val:.1f}",
                            ha="center", va="bottom",
                            fontsize=7, color=text_color, fontweight="bold",
                        )
            else:  # "bar" (horizontal)
                ax.barh(
                    x + offsets[idx] * bar_width,
                    vals,
                    height=bar_width,
                    color=color,
                    label=sname,
                    alpha=0.9,
                    zorder=3,
                )

        if chart_type == "column":
            ax.set_xticks(x)
            ax.set_xticklabels(
                [c if len(c) <= 14 else c[:12] + "…" for c in categories],
                color=text_color, fontsize=8, rotation=20 if n_cats > 5 else 0,
                ha="right" if n_cats > 5 else "center",
            )
        else:
            ax.set_yticks(x)
            ax.set_yticklabels(
                [c if len(c) <= 18 else c[:16] + "…" for c in categories],
                color=text_color, fontsize=8,
            )

    else:  # line chart
        import numpy as np
        x = list(range(n_cats))
        for idx, (sname, vals) in enumerate(series.items()):
            color = _PALETTE[idx % len(_PALETTE)]
            ax.plot(x, vals, marker="o", color=color, label=sname,
                    linewidth=2.5, markersize=6, zorder=3)
            ax.fill_between(x, vals, alpha=0.12, color=color, zorder=2)
        ax.set_xticks(x)
        ax.set_xticklabels(
            [c if len(c) <= 14 else c[:12] + "…" for c in categories],
            color=text_color, fontsize=8,
        )

    # ── Styling ───────────────────────────────────────────────────────────────
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{v:,.0f}" if v == int(v) else f"{v:.1f}")
    )
    ax.tick_params(colors=text_color, labelcolor=text_color)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(grid_color)
    ax.spines["bottom"].set_color(grid_color)
    ax.yaxis.label.set_color(text_color)
    ax.xaxis.label.set_color(text_color)
    ax.grid(axis="y" if chart_type != "bar" else "x",
            color=grid_color, linestyle="--", linewidth=0.6, zorder=0)

    if n_series > 1:
        legend = ax.legend(
            facecolor=bg_color, edgecolor=grid_color,
            labelcolor=text_color, fontsize=8,
        )

    if title:
        ax.set_title(title, color=text_color, fontsize=11, fontweight="bold", pad=10)

    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=dpi,
                facecolor=bg_color, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
