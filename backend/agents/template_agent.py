"""
Template Agent — assembles the final PPTX from template + slides + charts + images.

Design system (CLAUDE.md):
  • Grid-based layout with fixed 0.6 in margins
  • Title 32 pt bold primary-color
  • Body 16 pt regular dark-color
  • Max 5 bullets per slide, each max 12 words
  • Native python-pptx charts (no matplotlib)
  • Unsplash images as right-side panels
  • Clean containers, minimal borders, consistent corner radius
"""
from __future__ import annotations

import io
import httpx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.oxml.ns import qn

from config import settings
from core.database import get_template, update_output
from logger import get_logger

logger = get_logger(__name__)

# ── Design constants ──────────────────────────────────────────────────────────
PRIMARY   = RGBColor(0x1A, 0x56, 0xDB)   # deep blue
ACCENT    = RGBColor(0xE3, 0x77, 0x02)   # warm orange
DARK      = RGBColor(0x1F, 0x29, 0x37)   # near-black text
LIGHT_BG  = RGBColor(0xF3, 0xF4, 0xF6)  # slide background tint

SLIDE_W   = Inches(13.33)
SLIDE_H   = Inches(7.5)
MARGIN_L  = Inches(0.6)
MARGIN_T  = Inches(0.5)
MARGIN_R  = Inches(0.6)
CONTENT_W = SLIDE_W - MARGIN_L - MARGIN_R


# ── Internal helpers ──────────────────────────────────────────────────────────

def _style_tf(tf, size: Pt, bold: bool = False,
              color: RGBColor = DARK, align: PP_ALIGN = PP_ALIGN.LEFT) -> None:
    """Apply consistent typography to every run in a text frame."""
    for para in tf.paragraphs:
        para.alignment = align
        for run in para.runs:
            run.font.size = size
            run.font.bold = bold
            run.font.color.rgb = color


def _clear_slides(prs: Presentation) -> None:
    """Remove every existing slide from the presentation (keeps layouts/theme)."""
    sld_id_lst = prs.slides._sldIdLst
    for sld_id_elem in list(sld_id_lst):
        r_id = sld_id_elem.get(qn("r:id"))
        if r_id:
            try:
                prs.part.drop_rel(r_id)
            except Exception:
                pass
        sld_id_lst.remove(sld_id_elem)


def _get_layout(prs: Presentation, index: int):
    try:
        return prs.slide_layouts[index]
    except IndexError:
        return prs.slide_layouts[0]


def _download_image(url: str) -> bytes | None:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.warning(f"[Template] Image download failed: {exc}")
        return None


# ── Slide builders ────────────────────────────────────────────────────────────

def _add_title_slide(prs: Presentation, title: str, subtitle: str = "") -> None:
    """Slide layout 0 — Title Slide."""
    slide = prs.slides.add_slide(_get_layout(prs, 0))

    if slide.shapes.title:
        slide.shapes.title.text = title
        _style_tf(slide.shapes.title.text_frame, Pt(36), bold=True,
                  color=PRIMARY, align=PP_ALIGN.CENTER)

    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 1:
            ph.text = subtitle
            _style_tf(ph.text_frame, Pt(20), color=DARK, align=PP_ALIGN.CENTER)
            break


def _add_content_slide(
    prs: Presentation,
    title: str,
    bullets: list[str],
    image_url: str | None = None,
) -> None:
    """
    Content slide with title + bullet list.
    If an image URL is given, the image occupies a 3-inch right panel
    and the text content is narrowed accordingly.
    """
    slide = prs.slides.add_slide(_get_layout(prs, 1))

    # ── Title ─────────────────────────────────────────────────────────────────
    if slide.shapes.title:
        slide.shapes.title.text = title
        _style_tf(slide.shapes.title.text_frame, Pt(28), bold=True, color=PRIMARY)

    # ── Bullets via placeholder ────────────────────────────────────────────────
    body_set = False
    for ph in slide.placeholders:
        if ph.placeholder_format.idx in (1, 2):
            tf = ph.text_frame
            tf.word_wrap = True
            tf.clear()
            for i, bullet in enumerate(bullets[:5]):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.text = f"\u2022  {bullet}"
                p.space_before = Pt(5)
                for run in p.runs:
                    run.font.size = Pt(16)
                    run.font.color.rgb = DARK
            body_set = True
            break

    # ── Fallback: manual textbox ───────────────────────────────────────────────
    if not body_set and bullets:
        content_right = SLIDE_W - MARGIN_R - (Inches(3.2) if image_url else Inches(0))
        tb = slide.shapes.add_textbox(MARGIN_L, Inches(1.6),
                                      content_right - MARGIN_L, Inches(4.8))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, bullet in enumerate(bullets[:5]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"\u2022  {bullet}"
            p.space_before = Pt(5)
            for run in p.runs:
                run.font.size = Pt(16)
                run.font.color.rgb = DARK

    # ── Right-side image panel ─────────────────────────────────────────────────
    if image_url:
        img_bytes = _download_image(image_url)
        if img_bytes:
            stream = io.BytesIO(img_bytes)
            slide.shapes.add_picture(
                stream,
                SLIDE_W - Inches(3.1),   # left edge of image
                Inches(1.4),             # top edge
                width=Inches(2.9),
                height=Inches(4.4),
            )


def _add_chart_slide(
    prs: Presentation,
    title: str,
    bullets: list[str],
    chart_data: dict,
) -> None:
    """
    Chart slide: native python-pptx column chart (left 7.5 in)
    with key-point bullets on the right (3.5 in panel).
    """
    slide = prs.slides.add_slide(_get_layout(prs, 5))  # blank layout

    # ── Title textbox ─────────────────────────────────────────────────────────
    tb = slide.shapes.add_textbox(MARGIN_L, Inches(0.25), CONTENT_W, Inches(0.8))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    for run in p.runs:
        run.font.size = Pt(26)
        run.font.bold = True
        run.font.color.rgb = PRIMARY

    # ── Native chart ──────────────────────────────────────────────────────────
    cd = ChartData()
    categories = chart_data.get("categories", [])
    series_dict: dict[str, list[float]] = chart_data.get("series", {})
    cd.categories = categories
    for series_name, values in series_dict.items():
        cd.add_series(series_name, values)

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        MARGIN_L, Inches(1.2),
        Inches(7.5), Inches(5.5),
        cd,
    )
    chart_obj = chart_frame.chart
    chart_obj.has_legend = len(series_dict) > 1
    chart_obj.chart_title.has_text_frame = False   # title already in textbox

    # ── Bullet panel (right side) ─────────────────────────────────────────────
    if bullets:
        rb = slide.shapes.add_textbox(Inches(8.3), Inches(1.2), Inches(4.4), Inches(5.5))
        tf = rb.text_frame
        tf.word_wrap = True
        for i, b in enumerate(bullets[:4]):
            p2 = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p2.text = f"\u2022  {b}"
            p2.space_before = Pt(8)
            for run in p2.runs:
                run.font.size = Pt(14)
                run.font.color.rgb = DARK


# ── Main agent node ───────────────────────────────────────────────────────────

async def template_node(state: dict) -> dict:
    logger.info("[Template] Building PPTX")

    slides_data: list[dict] = state.get("critiqued_slides") or state.get("slides", [])
    charts: list[dict]       = state.get("charts", [])
    images: dict[str, str]   = state.get("images", {})
    template_id: str         = state.get("template_id", "")
    output_id: str           = state.get("output_id", "")
    query: str               = state.get("query", "AI Presentation")

    # ── Load template from Supabase Storage ───────────────────────────────────
    prs: Presentation | None = None
    try:
        from services.storage_service import download_file
        tmpl_meta = get_template(template_id)
        tmpl_bytes = download_file(settings.STORAGE_BUCKET_RAW, tmpl_meta["storage_path"])
        prs = Presentation(io.BytesIO(tmpl_bytes))
        _clear_slides(prs)
        logger.info("[Template] Template loaded and cleared")
    except Exception as exc:
        logger.warning(f"[Template] Could not load template ({exc}), using blank 16:9")
        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H

    # ── Build slides ──────────────────────────────────────────────────────────
    _add_title_slide(prs, query, "AI-Generated Presentation · DeckSmith")

    for i, slide in enumerate(slides_data):
        title      = slide.get("title", f"Slide {i + 1}")
        bullets    = slide.get("content", [])
        slide_type = slide.get("type", "content")
        chart_data = charts[i] if i < len(charts) else {}
        image_url  = images.get(str(i))

        if slide_type == "chart" and chart_data:
            try:
                _add_chart_slide(prs, title, bullets, chart_data)
                continue
            except Exception as exc:
                logger.warning(f"[Template] Chart slide failed ({exc}), falling back to content")

        _add_content_slide(prs, title, bullets, image_url)

    # ── Serialise ─────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    prs.save(buf)
    pptx_bytes = buf.getvalue()

    # ── Upload to Supabase Storage ────────────────────────────────────────────
    try:
        from services.storage_service import upload_pptx, get_public_url
        filename = f"{output_id}.pptx"
        upload_pptx(settings.STORAGE_BUCKET_OUTPUT, filename, pptx_bytes)
        public_url = get_public_url(settings.STORAGE_BUCKET_OUTPUT, filename)
        update_output(output_id, "complete", filename)
        logger.info(f"[Template] Uploaded → {public_url[:80]}")
    except Exception as exc:
        logger.error(f"[Template] Upload failed: {exc}")
        update_output(output_id, "failed")

    return {"pptx_bytes": pptx_bytes, "error": None}
