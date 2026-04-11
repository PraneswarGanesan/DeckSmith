"""
Template Agent — assembles the final PPTX from template + slides + charts + images.

Architecture (template-first):
  1. Load the uploaded template as the base Presentation (inherits theme, fonts, colours)
  2. Clear its existing slides but keep slide_master + slide_layouts intact
  3. Analyse layouts → map each slide type to the best matching template layout index
  4. For simple slides (title, content, two-column): fill template placeholders directly
  5. For complex visual slides (chart, process, grid-3, comparison): add blank template
     layout slide then draw shapes on top so the template background/theme still shows
  6. Fall back to the custom drawing system when placeholder filling fails

Layout mapping strategy:
  title   → layout with CENTER_TITLE (type 3) or TITLE + SUBTITLE
  content → layout with TITLE (type 1) + single BODY (type 2/7)
  two_col → layout with TITLE + 2+ BODY placeholders
  picture → layout with TITLE + BODY + PICTURE (type 18)
  blank   → layout with fewest content placeholders (for custom drawing)
"""
from __future__ import annotations

import io
import re
import httpx
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.oxml.ns import qn
from lxml import etree

from config import settings
from core.database import get_template, update_output
from logger import get_logger

logger = get_logger(__name__)

# ── Fallback design constants (used when template theme is absent) ─────────────
PRIMARY    = RGBColor(0x1A, 0x56, 0xDB)
SECONDARY  = RGBColor(0xC0, 0x39, 0x2B)
ACCENT     = RGBColor(0xE3, 0x77, 0x02)
DARK       = RGBColor(0x1F, 0x29, 0x37)
MID_GRAY   = RGBColor(0x6B, 0x72, 0x80)
LIGHT_BG   = RGBColor(0xF3, 0xF4, 0xF6)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
CARD_BG    = RGBColor(0xEE, 0xF2, 0xFF)

SLIDE_W  = Inches(13.33)
SLIDE_H  = Inches(7.5)
M_L      = Inches(0.5)
M_T      = Inches(0.5)
M_R      = Inches(0.5)
M_B      = Inches(0.4)


# ── Text / shape helpers ──────────────────────────────────────────────────────

def _set_cell_bg(cell, rgb: RGBColor) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    solidFill = etree.SubElement(tcPr, qn("a:solidFill"))
    srgbClr = etree.SubElement(solidFill, qn("a:srgbClr"))
    srgbClr.set("val", f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")


def _add_textbox(
    slide,
    left: Emu, top: Emu, width: Emu, height: Emu,
    text: str,
    size: Pt = Pt(16),
    bold: bool = False,
    color: RGBColor = DARK,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    word_wrap: bool = True,
) -> None:
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = word_wrap
    para = tf.paragraphs[0]
    para.alignment = align
    run = para.add_run()
    run.text = text
    run.font.size = size
    run.font.bold = bold
    run.font.color.rgb = color


def _add_rect(slide, left, top, width, height, fill: RGBColor) -> None:
    shape = slide.shapes.add_shape(1, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()


def _truncate(text: str, max_words: int = 12) -> str:
    words = text.split()
    return " ".join(words[:max_words]) if len(words) > max_words else text


def _sanitize(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"^[-•*]\s*", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return _truncate(text)


# ── Template analysis ─────────────────────────────────────────────────────────

# Placeholder type constants (OpenXML spec)
_PH_TITLE        = 1
_PH_BODY         = 2
_PH_CENTER_TITLE = 3
_PH_SUBTITLE     = 4
_PH_DATE         = 10
_PH_FOOTER       = 11
_PH_SLIDE_NUM    = 12
_PH_OBJECT       = 14   # generic object (older PPT format)
_PH_PICTURE      = 18
_PH_BODY_ALT     = 7    # seen in some templates

_BODY_TYPES = (_PH_BODY, _PH_BODY_ALT, _PH_OBJECT)
_NON_CONTENT_TYPES = (_PH_DATE, _PH_FOOTER, _PH_SLIDE_NUM)


def _analyze_template_layouts(prs: Presentation) -> dict:
    """
    Analyse all slide layouts in *prs* and return a dict mapping our layout
    role names → the best matching layout index.

    Roles:
      "title"   — hero / title slide  (CENTER_TITLE or TITLE+SUBTITLE)
      "content" — standard content    (TITLE + 1 BODY)
      "two_col" — two-column content  (TITLE + 2+ BODY)
      "picture" — image + content     (TITLE + BODY + PICTURE)
      "blank"   — fewest placeholders (for custom-drawn slides)
    """
    n = len(prs.slide_layouts)
    result = {
        "title":   0,
        "content": min(1, n - 1),
        "two_col": min(1, n - 1),
        "picture": min(1, n - 1),
        "blank":   n - 1,
    }

    min_content_ph = float("inf")

    for i, layout in enumerate(prs.slide_layouts):
        has_title        = False
        has_center_title = False
        has_subtitle     = False
        body_count       = 0
        has_picture      = False
        content_ph_count = 0   # placeholders that carry actual content

        for shape in layout.shapes:
            if not shape.is_placeholder:
                continue
            t = shape.placeholder_format.type
            if t in _NON_CONTENT_TYPES:
                continue
            content_ph_count += 1

            if t == _PH_TITLE:
                has_title = True
            elif t == _PH_CENTER_TITLE:
                has_center_title = True
            elif t == _PH_SUBTITLE:
                has_subtitle = True
            elif t in _BODY_TYPES:
                body_count += 1
            elif t == _PH_PICTURE:
                has_picture = True

        # Title slide: prefer CENTER_TITLE
        if has_center_title:
            result["title"] = i

        # Title + subtitle is a good fallback for title slide
        elif has_title and has_subtitle and result["title"] == 0:
            result["title"] = i

        # Two-column: TITLE + ≥2 BODY
        if has_title and body_count >= 2 and result["two_col"] == min(1, n - 1):
            result["two_col"] = i

        # Picture: TITLE + BODY + PICTURE
        if has_title and has_picture and result["picture"] == min(1, n - 1):
            result["picture"] = i

        # Standard content: TITLE + exactly 1 BODY (prefer first found)
        if has_title and body_count == 1 and result["content"] == min(1, n - 1):
            result["content"] = i

        # Blank: fewest content placeholders
        if content_ph_count < min_content_ph:
            min_content_ph = content_ph_count
            result["blank"] = i

    logger.info(
        f"[Template] Layout analysis ({n} layouts): "
        f"title={result['title']}, content={result['content']}, "
        f"two_col={result['two_col']}, picture={result['picture']}, blank={result['blank']}"
    )
    return result


# ── Slide management helpers ──────────────────────────────────────────────────

def _clear_slides(prs: Presentation) -> None:
    """Remove every existing slide from the presentation (keep master + layouts)."""
    sld_id_lst = prs.slides._sldIdLst
    for elem in list(sld_id_lst):
        r_id = elem.get(qn("r:id"))
        if r_id:
            try:
                prs.part.drop_rel(r_id)
            except Exception:
                pass
        sld_id_lst.remove(elem)


def _blank_layout(prs: Presentation):
    """
    Return the most blank layout available — either one named 'Blank' or the
    layout with the fewest content placeholders.  Used by custom-draw functions.
    """
    layouts = prs.slide_layouts

    # Prefer a layout explicitly named "Blank"
    for layout in layouts:
        try:
            if layout.name.lower() == "blank":
                return layout
        except Exception:
            pass

    # Fall back to layout with fewest content placeholders
    min_ph = float("inf")
    best_idx = max(0, len(layouts) - 1)
    for i, layout in enumerate(layouts):
        count = sum(
            1 for sh in layout.shapes
            if sh.is_placeholder
            and sh.placeholder_format.type not in _NON_CONTENT_TYPES
        )
        if count < min_ph:
            min_ph = count
            best_idx = i

    return layouts[best_idx]


# ── Placeholder filling helpers ───────────────────────────────────────────────

def _fill_title_placeholder(slide, title: str) -> bool:
    """Fill the TITLE or CENTER_TITLE placeholder on a slide. Returns True on success."""
    for shape in slide.placeholders:
        t = shape.placeholder_format.type
        if t in (_PH_TITLE, _PH_CENTER_TITLE):
            tf = shape.text_frame
            tf.clear()
            p = tf.paragraphs[0]
            p.text = str(title)
            return True
    return False


def _fill_body_placeholder(slide, bullets: list[str], body_idx: int = 0) -> bool:
    """
    Fill the *body_idx*-th BODY placeholder with bullet paragraphs.
    Returns True on success.
    """
    found = 0
    for shape in slide.placeholders:
        t = shape.placeholder_format.type
        if t in (*_BODY_TYPES, _PH_SUBTITLE):
            if found == body_idx:
                tf = shape.text_frame
                tf.clear()
                for i, bullet in enumerate(bullets):
                    if i == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = str(bullet)
                    p.level = 0
                return True
            found += 1
    return False


def _fill_picture_placeholder(slide, img_bytes: bytes) -> bool:
    """Fill the PICTURE placeholder on a slide with image bytes."""
    for shape in slide.placeholders:
        if shape.placeholder_format.type == _PH_PICTURE:
            try:
                shape.insert_picture(io.BytesIO(img_bytes))
                return True
            except Exception as exc:
                logger.warning(f"[Template] Picture placeholder fill failed: {exc}")
                return False
    return False


# ── Template-aware slide builders ─────────────────────────────────────────────

def _add_template_title_slide(
    prs: Presentation, layout_idx: int, title: str, subtitle: str = ""
) -> None:
    """Add title slide using the template's title layout and its placeholders."""
    layout = prs.slide_layouts[layout_idx]
    slide = prs.slides.add_slide(layout)

    if not _fill_title_placeholder(slide, title):
        # Fallback: draw a textbox
        _add_textbox(slide, M_L, Inches(1.5), SLIDE_W - M_L * 2, Inches(2.0),
                     title, size=Pt(40), bold=True, color=PRIMARY, align=PP_ALIGN.CENTER)

    if subtitle:
        _fill_body_placeholder(slide, [subtitle], 0)


def _add_template_content_slide(
    prs: Presentation, layout_idx: int, title: str, bullets: list[str]
) -> None:
    """Add content slide using the template's content layout."""
    layout = prs.slide_layouts[layout_idx]
    slide = prs.slides.add_slide(layout)

    if not _fill_title_placeholder(slide, title):
        _add_textbox(slide, Inches(0.5), Inches(0.15), SLIDE_W - Inches(1.0), Inches(0.9),
                     title, size=Pt(28), bold=True, color=PRIMARY)

    if not _fill_body_placeholder(slide, bullets, 0):
        # Fallback: render bullets as textbox
        _render_bullet_cards(slide, Inches(0.5), Inches(1.25),
                             SLIDE_W - Inches(1.0), bullets)


def _add_template_two_col_slide(
    prs: Presentation, layout_idx: int, title: str, bullets: list[str]
) -> None:
    """Add two-column slide splitting bullets between both body placeholders."""
    layout = prs.slide_layouts[layout_idx]
    slide = prs.slides.add_slide(layout)

    if not _fill_title_placeholder(slide, title):
        _add_textbox(slide, Inches(0.5), Inches(0.15), SLIDE_W - Inches(1.0), Inches(0.9),
                     title, size=Pt(28), bold=True, color=PRIMARY)

    mid = (len(bullets) + 1) // 2
    filled_left = _fill_body_placeholder(slide, bullets[:mid], 0)
    filled_right = _fill_body_placeholder(slide, bullets[mid:], 1)

    if not filled_left:
        # No two-col layout; dump everything into a single column
        _render_bullet_cards(slide, Inches(0.5), Inches(1.25),
                             SLIDE_W - Inches(1.0), bullets)


def _add_template_picture_slide(
    prs: Presentation,
    layout_idx: int,
    title: str,
    bullets: list[str],
    image_url: str | None,
) -> None:
    """Add a slide that uses the template's picture layout."""
    layout = prs.slide_layouts[layout_idx]
    slide = prs.slides.add_slide(layout)

    _fill_title_placeholder(slide, title)
    _fill_body_placeholder(slide, bullets, 0)

    if image_url:
        img_bytes = _download_image(image_url)
        if img_bytes:
            if not _fill_picture_placeholder(slide, img_bytes):
                # Place image manually if no picture placeholder
                vis_left  = SLIDE_W * 0.6
                vis_w     = SLIDE_W * 0.35
                vis_top   = Inches(1.25)
                vis_h     = SLIDE_H - vis_top - M_B
                try:
                    slide.shapes.add_picture(
                        io.BytesIO(img_bytes), vis_left, vis_top,
                        width=vis_w, height=vis_h
                    )
                except Exception as exc:
                    logger.warning(f"[Template] Manual picture insert failed: {exc}")


# ── Image download ────────────────────────────────────────────────────────────

def _download_image(url: str) -> bytes | None:
    if not url:
        return None
    try:
        headers = {
            "User-Agent": "DeckSmith/1.0",
            "Accept": "image/png, image/jpeg, image/webp, */*",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            if "image" not in resp.headers.get("content-type", ""):
                return None
            return resp.content
    except Exception as exc:
        logger.warning(f"[Template] Image download failed: {type(exc).__name__}: {exc}")
        return None


# ── Custom-draw slide builders (fallback + complex visual layouts) ─────────────
# These use _blank_layout(prs) so they inherit the template background/theme.

def _slide_header(slide, title: str) -> None:
    _add_rect(slide, Inches(0), Inches(0), Inches(0.25), SLIDE_H, SECONDARY)
    _add_textbox(
        slide,
        Inches(0.5), Inches(0.2),
        SLIDE_W - Inches(1.0), Inches(0.85),
        title, size=Pt(28), bold=True, color=PRIMARY,
    )
    _add_rect(slide, Inches(0.5), Inches(1.1), SLIDE_W - Inches(1.0), Inches(0.04), SECONDARY)


def _render_bullet_cards(
    slide, left: Emu, top: Emu, width: Emu, bullets: list[str],
    accent: RGBColor | None = None,
) -> None:
    if accent is None:
        accent = PRIMARY
    if not bullets:
        return
    available_h = SLIDE_H - top - M_B
    card_h = min(Inches(1.1), available_h / len(bullets))
    card_gap = Inches(0.1)
    for i, bullet in enumerate(bullets):
        cy = top + i * (card_h + card_gap)
        if cy + card_h > SLIDE_H - M_B:
            break
        _add_rect(slide, left, cy, width, card_h, CARD_BG)
        _add_rect(slide, left, cy, Inches(0.25), card_h, accent)
        _add_textbox(
            slide, left + Inches(0.03), cy + Inches(0.05),
            Inches(0.19), card_h - Inches(0.1),
            str(i + 1), size=Pt(12), bold=True, color=WHITE, align=PP_ALIGN.CENTER,
        )
        _add_textbox(
            slide, left + Inches(0.35), cy + Inches(0.1),
            width - Inches(0.45), card_h - Inches(0.2),
            bullet, size=Pt(14), color=DARK,
        )


def _insert_image(slide, img_url, left, top, width, height, fallback_color=CARD_BG):
    if img_url:
        img_bytes = _download_image(img_url)
        if img_bytes:
            try:
                slide.shapes.add_picture(io.BytesIO(img_bytes), left, top,
                                         width=width, height=height)
                return
            except Exception as exc:
                logger.warning(f"[Template] Image insert failed: {exc}")
    _add_rect(slide, left, top, width, height, fallback_color)


# Fallback title slide (when template loading fails entirely)
def _add_title_slide(prs: Presentation, title: str, subtitle: str = "") -> None:
    slide = prs.slides.add_slide(_blank_layout(prs))
    header_h = Inches(4.1)
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, header_h, PRIMARY)
    _add_rect(slide, Inches(0), header_h, SLIDE_W, Inches(0.08), SECONDARY)
    _add_textbox(slide, M_L, Inches(0.8), SLIDE_W - M_L - M_R, Inches(2.5),
                 title, size=Pt(40), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _add_textbox(slide, M_L, Inches(3.1), SLIDE_W - M_L - M_R, Inches(0.6),
                 "AI-Generated Presentation",
                 size=Pt(16), color=RGBColor(0xBF, 0xDB, 0xFF), align=PP_ALIGN.CENTER)
    if subtitle:
        _add_textbox(slide, M_L, Inches(4.4), SLIDE_W - M_L - M_R, Inches(0.7),
                     subtitle, size=Pt(20), bold=True, color=DARK, align=PP_ALIGN.CENTER)
    _add_textbox(slide, M_L, SLIDE_H - Inches(0.5), SLIDE_W - M_L - M_R, Inches(0.4),
                 "Generated by DeckSmith",
                 size=Pt(10), color=MID_GRAY, align=PP_ALIGN.CENTER)


def _add_grid2_slide(prs, title, bullets, image_url=None):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:6]
    content_top = Inches(1.25)
    col_gap = Inches(0.3)
    col_w = (SLIDE_W - Inches(0.5) - M_R - col_gap) / 2
    col1_x, col2_x = Inches(0.5), Inches(0.5) + col_w + col_gap
    col_h = SLIDE_H - content_top - M_B
    img_bytes_data = _download_image(image_url) if image_url else None
    if img_bytes_data:
        _render_bullet_cards(slide, col1_x, content_top, col_w, clean, PRIMARY)
        try:
            slide.shapes.add_picture(io.BytesIO(img_bytes_data), col2_x, content_top,
                                     width=col_w, height=col_h)
        except Exception:
            _add_rect(slide, col2_x, content_top, col_w, col_h, CARD_BG)
    else:
        mid = (len(clean) + 1) // 2
        _render_bullet_cards(slide, col1_x, content_top, col_w, clean[:mid], PRIMARY)
        _render_bullet_cards(slide, col2_x, content_top, col_w, clean[mid:], SECONDARY)


def _add_grid3_slide(prs, title, bullets):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:6]
    while len(clean) < 3:
        clean.append("")
    col_gap = Inches(0.25)
    total_w = SLIDE_W - Inches(0.5) - M_R
    col_w = (total_w - 2 * col_gap) / 3
    colors = [PRIMARY, SECONDARY, ACCENT]
    hdr_h = Inches(0.45)
    card_top = Inches(1.25) + hdr_h + Inches(0.15)
    card_h = Inches(1.1)
    for col_idx in range(3):
        cx = Inches(0.5) + col_idx * (col_w + col_gap)
        color = colors[col_idx]
        _add_rect(slide, cx, Inches(1.25), col_w, hdr_h, color)
        _add_textbox(slide, cx, Inches(1.28), col_w, hdr_h - Inches(0.06),
                     f"0{col_idx + 1}", size=Pt(18), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        col_bullets = [b for b in clean[col_idx * 2: col_idx * 2 + 2] if b]
        for i, bullet in enumerate(col_bullets):
            cy = card_top + i * (card_h + Inches(0.12))
            _add_rect(slide, cx, cy, col_w, card_h, CARD_BG)
            _add_rect(slide, cx, cy, Inches(0.22), card_h, color)
            _add_textbox(slide, cx + Inches(0.28), cy + Inches(0.1),
                         col_w - Inches(0.35), card_h - Inches(0.2),
                         bullet, size=Pt(13), color=DARK)


def _add_left_text_right_visual_slide(prs, title, bullets, image_url=None):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:5]
    content_top = Inches(1.25)
    text_w  = Inches(7.2)
    vis_w   = Inches(4.8)
    vis_left = SLIDE_W - vis_w - M_R
    vis_h   = SLIDE_H - content_top - M_B
    if image_url:
        _render_bullet_cards(slide, Inches(0.5), content_top, text_w, clean, PRIMARY)
        _insert_image(slide, image_url, vis_left, content_top, vis_w, vis_h, CARD_BG)
    else:
        _render_bullet_cards(slide, Inches(0.5), content_top, SLIDE_W - Inches(1.0), clean, PRIMARY)


def _add_process_slide(prs, title, bullets):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:4]  # max 4 for readability
    if not clean:
        return
    n = len(clean)
    step_gap = Inches(0.18)
    total_w = SLIDE_W - Inches(0.5) - M_R
    step_w = (total_w - step_gap * (n - 1)) / n
    step_top = Inches(1.4)
    hdr_h = Inches(0.55)
    step_h = SLIDE_H - step_top - M_B
    for i, bullet in enumerate(clean):
        sx = Inches(0.5) + i * (step_w + step_gap)
        _add_rect(slide, sx, step_top, step_w, step_h, CARD_BG)
        _add_rect(slide, sx, step_top, step_w, hdr_h, PRIMARY)
        _add_textbox(slide, sx, step_top + Inches(0.06), step_w, hdr_h - Inches(0.12),
                     str(i + 1), size=Pt(22), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        if i < n - 1:
            arrow_cy = step_top + step_h / 2 - Inches(0.04)
            _add_rect(slide, sx + step_w, arrow_cy, step_gap, Inches(0.08), SECONDARY)
        _add_textbox(slide, sx + Inches(0.1), step_top + hdr_h + Inches(0.15),
                     step_w - Inches(0.2), step_h - hdr_h - Inches(0.25),
                     bullet, size=Pt(13), color=DARK, align=PP_ALIGN.CENTER, word_wrap=True)


def _add_comparison_slide(prs, title, bullets):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:6]
    mid = (len(clean) + 1) // 2
    col_gap = Inches(0.3)
    col_w = (SLIDE_W - Inches(0.5) - M_R - col_gap) / 2
    col1_x, col2_x = Inches(0.5), Inches(0.5) + col_w + col_gap
    hdr_top, hdr_h = Inches(1.25), Inches(0.42)
    _add_rect(slide, col1_x, hdr_top, col_w, hdr_h, PRIMARY)
    _add_textbox(slide, col1_x, hdr_top + Inches(0.04), col_w, hdr_h - Inches(0.08),
                 "Key Points", size=Pt(14), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _add_rect(slide, col2_x, hdr_top, col_w, hdr_h, SECONDARY)
    _add_textbox(slide, col2_x, hdr_top + Inches(0.04), col_w, hdr_h - Inches(0.08),
                 "Insights", size=Pt(14), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    card_top = hdr_top + hdr_h + Inches(0.12)
    _render_bullet_cards(slide, col1_x, card_top, col_w, clean[:mid], PRIMARY)
    _render_bullet_cards(slide, col2_x, card_top, col_w, clean[mid:], SECONDARY)


def _add_centered_slide(prs, title, bullets):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, SLIDE_H, LIGHT_BG)
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.12), PRIMARY)
    _add_rect(slide, Inches(0), SLIDE_H - Inches(0.12), SLIDE_W, Inches(0.12), SECONDARY)
    _add_textbox(slide, M_L, Inches(1.6), SLIDE_W - M_L - M_R, Inches(1.3),
                 title, size=Pt(40), bold=True, color=PRIMARY, align=PP_ALIGN.CENTER)
    underline_w = Inches(3.0)
    _add_rect(slide, (SLIDE_W - underline_w) / 2, Inches(3.05), underline_w, Inches(0.06), SECONDARY)
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:4]
    top = Inches(3.3)
    for bullet in clean:
        _add_textbox(slide, M_L, top, SLIDE_W - M_L - M_R, Inches(0.55),
                     f"• {bullet}", size=Pt(18), color=DARK, align=PP_ALIGN.CENTER)
        top += Inches(0.65)


def _add_chart_slide(prs, title, bullets, chart_entry: dict):
    """
    Render a chart slide.

    Prefers a matplotlib PNG image (chart_entry["chart_image"]) over pptx
    native charts for maximum visual quality and cross-viewer compatibility.
    Falls back to pptx native chart, then bullet cards.

    chart_entry can be either:
      {"chart_image": bytes, "chart_data": {...}}   ← new format
      {"categories": [...], "series": {...}}         ← legacy format (chart_data inline)
    """
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)

    # Normalise: handle both new {"chart_image":…} and old flat dict formats
    if "chart_image" in chart_entry or "chart_data" in chart_entry:
        chart_image = chart_entry.get("chart_image")
        chart_data  = chart_entry.get("chart_data", {})
    else:
        chart_image = None
        chart_data  = chart_entry  # legacy flat format

    # ── Path 1: matplotlib PNG image (best quality) ───────────────────────
    if chart_image:
        try:
            chart_left  = Inches(0.4)
            chart_top   = Inches(1.15)
            chart_width = Inches(8.8)
            chart_h     = SLIDE_H - chart_top - M_B
            slide.shapes.add_picture(
                io.BytesIO(chart_image),
                chart_left, chart_top, chart_width, chart_h,
            )
            # Bullets in right panel
            clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:4]
            if clean:
                panel_x = Inches(9.4)
                _render_bullet_cards(slide, panel_x, Inches(1.25),
                                     SLIDE_W - panel_x - M_R, clean, SECONDARY)
            return
        except Exception as exc:
            logger.warning(f"[Template] Chart image insert failed: {exc}")

    # ── Path 2: pptx native chart (fallback) ─────────────────────────────
    categories  = chart_data.get("categories", [])
    series_dict = chart_data.get("series", {})
    if categories and series_dict:
        cd = ChartData()
        cd.categories = [str(c) for c in categories]
        for sname, vals in series_dict.items():
            numeric_vals = []
            for v in vals:
                try:
                    numeric_vals.append(float(v))
                except (TypeError, ValueError):
                    numeric_vals.append(0.0)
            cd.add_series(str(sname), numeric_vals)
        try:
            chart_frame = slide.shapes.add_chart(
                XL_CHART_TYPE.COLUMN_CLUSTERED,
                Inches(0.5), Inches(1.15), Inches(8.5), Inches(5.9), cd,
            )
            chart_frame.chart.has_legend = len(series_dict) > 1
            chart_frame.chart.chart_title.has_text_frame = False
            clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:4]
            if clean:
                panel_x = Inches(9.2)
                _render_bullet_cards(slide, panel_x, Inches(1.25),
                                     SLIDE_W - panel_x - M_R, clean, SECONDARY)
            return
        except Exception as exc:
            logger.warning(f"[Template] pptx native chart insert failed: {exc}")

    # ── Path 3: bullet cards fallback ────────────────────────────────────
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:5]
    _render_bullet_cards(slide, Inches(0.5), Inches(1.25), SLIDE_W - Inches(1.0), clean)


def _add_table_slide(prs, title, table_data):
    slide = prs.slides.add_slide(_blank_layout(prs))
    _add_rect(slide, Inches(0), Inches(0), Inches(0.25), SLIDE_H, SECONDARY)
    _add_textbox(slide, Inches(0.5), Inches(0.25), SLIDE_W - Inches(1.0), Inches(0.8),
                 title, size=Pt(28), bold=True, color=PRIMARY)
    _add_rect(slide, Inches(0.5), Inches(1.1), SLIDE_W - Inches(1.0), Inches(0.04), SECONDARY)
    headers: list = table_data.get("headers", [])
    rows: list = table_data.get("rows", [])
    if not headers or not rows:
        return
    rows = rows[:6]
    n_cols = len(headers)
    n_rows = len(rows) + 1
    tbl_shape = slide.shapes.add_table(
        n_rows, n_cols, Inches(0.5), Inches(1.3),
        SLIDE_W - Inches(1.0), min(Inches(5.5), Inches(0.55) * n_rows),
    )
    tbl = tbl_shape.table
    for col_idx, header in enumerate(headers):
        cell = tbl.cell(0, col_idx)
        cell.text = str(header)
        _set_cell_bg(cell, PRIMARY)
        for para in cell.text_frame.paragraphs:
            para.alignment = PP_ALIGN.CENTER
            for run in para.runs:
                run.font.bold = True
                run.font.size = Pt(13)
                run.font.color.rgb = WHITE
    for row_idx, row in enumerate(rows):
        bg = LIGHT_BG if row_idx % 2 == 0 else WHITE
        row_values = list(row.values()) if isinstance(row, dict) else list(row)
        for col_idx in range(n_cols):
            cell = tbl.cell(row_idx + 1, col_idx)
            val = row_values[col_idx] if col_idx < len(row_values) else ""
            val = str(val)
            # Strip URLs and long strings that clutter table cells
            val = re.sub(r'https?://\S+', '', val).strip()
            val = re.sub(r'\[.*?\]', '', val).strip()  # strip markdown links
            if len(val) > 60:
                val = val[:57] + "…"
            cell.text = val
            _set_cell_bg(cell, bg)
            for para in cell.text_frame.paragraphs:
                para.alignment = PP_ALIGN.CENTER
                for run in para.runs:
                    run.font.size = Pt(11)
                    run.font.color.rgb = DARK


# ── Visual structure renderers (from Visual Composer) ────────────────────────

def _render_visual_cards_slide(prs: Presentation, title: str, visual_structure: dict) -> None:
    """Render numbered cards from visual structure."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    
    elements = visual_structure.get("elements", [])[:6]
    if not elements:
        return
    
    colors_map = {"primary": PRIMARY, "secondary": SECONDARY, "accent": ACCENT}
    card_h = Inches(1.1)
    card_gap = Inches(0.1)
    content_top = Inches(1.25)
    card_w = SLIDE_W - Inches(1.0)
    
    for i, element in enumerate(elements):
        cy = content_top + i * (card_h + card_gap)
        if cy + card_h > SLIDE_H - M_B:
            break
        
        card_color = colors_map.get(element.get("color", "primary"), PRIMARY)
        card_text = element.get("text", "")
        card_number = element.get("number", "")
        
        _add_rect(slide, Inches(0.5), cy, card_w, card_h, CARD_BG)
        _add_rect(slide, Inches(0.5), cy, Inches(0.25), card_h, card_color)
        
        if card_number:
            _add_textbox(slide, Inches(0.55), cy + Inches(0.15), Inches(0.2), Inches(0.8),
                        card_number, size=Pt(16), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        
        _add_textbox(slide, Inches(0.85), cy + Inches(0.1), card_w - Inches(0.45), card_h - Inches(0.2),
                    card_text, size=Pt(13), color=DARK)


def _render_visual_process_slide(prs: Presentation, title: str, visual_structure: dict) -> None:
    """Render sequential process steps."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    
    elements = visual_structure.get("elements", [])[:4]  # max 4 steps for readability
    if not elements:
        return

    n = len(elements)
    step_gap = Inches(0.2)
    total_w = SLIDE_W - Inches(1.0)
    step_w = (total_w - step_gap * (n - 1)) / n
    step_top = Inches(1.4)
    hdr_h = Inches(0.55)
    step_h = SLIDE_H - step_top - M_B
    
    for i, element in enumerate(elements):
        sx = Inches(0.5) + i * (step_w + step_gap)
        step_num = element.get("number", i + 1)
        step_text = element.get("text", "")
        
        _add_rect(slide, sx, step_top, step_w, step_h, CARD_BG)
        _add_rect(slide, sx, step_top, step_w, hdr_h, PRIMARY)
        _add_textbox(slide, sx, step_top + Inches(0.08), step_w, hdr_h - Inches(0.16),
                    str(step_num), size=Pt(24), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        
        _add_textbox(slide, sx + Inches(0.1), step_top + hdr_h + Inches(0.15),
                    step_w - Inches(0.2), step_h - hdr_h - Inches(0.25),
                    step_text, size=Pt(11), color=DARK, align=PP_ALIGN.CENTER, word_wrap=True)
        
        if i < n - 1:
            arrow_cy = step_top + step_h / 2 - Inches(0.04)
            _add_rect(slide, sx + step_w, arrow_cy, step_gap, Inches(0.08), SECONDARY)


def _render_visual_comparison_slide(prs: Presentation, title: str, visual_structure: dict) -> None:
    """Render before/after comparison."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    
    left_col = visual_structure.get("left_column", {})
    right_col = visual_structure.get("right_column", {})
    
    left_title = left_col.get("title", "Current")
    right_title = right_col.get("title", "Proposed")
    left_items = left_col.get("items", [])
    right_items = right_col.get("items", [])
    
    col_gap = Inches(0.3)
    col_w = (SLIDE_W - Inches(1.0) - col_gap) / 2
    col1_x = Inches(0.5)
    col2_x = Inches(0.5) + col_w + col_gap
    
    hdr_top = Inches(1.25)
    hdr_h = Inches(0.42)
    
    _add_rect(slide, col1_x, hdr_top, col_w, hdr_h, PRIMARY)
    _add_textbox(slide, col1_x, hdr_top + Inches(0.04), col_w, hdr_h - Inches(0.08),
                left_title, size=Pt(14), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    
    _add_rect(slide, col2_x, hdr_top, col_w, hdr_h, SECONDARY)
    _add_textbox(slide, col2_x, hdr_top + Inches(0.04), col_w, hdr_h - Inches(0.08),
                right_title, size=Pt(14), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    
    left_bullets = [item.get("text", "") for item in left_items]
    right_bullets = [item.get("text", "") for item in right_items]
    
    card_top = hdr_top + hdr_h + Inches(0.12)
    _render_bullet_cards(slide, col1_x, card_top, col_w, left_bullets, PRIMARY)
    _render_bullet_cards(slide, col2_x, card_top, col_w, right_bullets, SECONDARY)


def _render_visual_centered_slide(prs: Presentation, title: str, visual_structure: dict) -> None:
    """Render centered takeaway."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, SLIDE_H, LIGHT_BG)
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.12), PRIMARY)
    _add_rect(slide, Inches(0), SLIDE_H - Inches(0.12), SLIDE_W, Inches(0.12), SECONDARY)
    
    _add_textbox(slide, M_L, Inches(1.6), SLIDE_W - M_L - M_R, Inches(1.3),
                title, size=Pt(40), bold=True, color=PRIMARY, align=PP_ALIGN.CENTER)
    
    underline_w = Inches(3.0)
    _add_rect(slide, (SLIDE_W - underline_w) / 2, Inches(3.05), underline_w, Inches(0.06), SECONDARY)
    
    elements = visual_structure.get("elements", [])[:4]
    top = Inches(3.3)
    for element in elements:
        item_text = element.get("text", "")
        _add_textbox(slide, M_L, top, SLIDE_W - M_L - M_R, Inches(0.55),
                    f"• {item_text}", size=Pt(18), color=DARK, align=PP_ALIGN.CENTER)
        top += Inches(0.65)


def _render_visual_chart_slide(prs: Presentation, title: str, visual_structure: dict) -> None:
    """Render chart from visual structure."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    
    chart_data_input = visual_structure.get("data", {})
    categories = chart_data_input.get("categories", [])
    series_dict = chart_data_input.get("series", {})
    
    if not categories or not series_dict:
        return
    
    cd = ChartData()
    cd.categories = [str(c) for c in categories]
    
    for sname, vals in series_dict.items():
        numeric_vals = []
        for v in vals:
            try:
                numeric_vals.append(float(v))
            except (TypeError, ValueError):
                numeric_vals.append(0.0)
        cd.add_series(str(sname), numeric_vals)
    
    try:
        chart_frame = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(0.5), Inches(1.15), Inches(8.5), Inches(5.9), cd,
        )
        chart_frame.chart.has_legend = len(series_dict) > 1
        chart_frame.chart.chart_title.has_text_frame = False
    except Exception as exc:
        logger.warning(f"[Template] Visual chart insert failed: {exc}")


def _render_visual_grid_slide(prs: Presentation, title: str, visual_structure: dict, image_url: str | None = None) -> None:
    """Render generic grid layout — with optional image on right when available."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)

    layout_type = visual_structure.get("layout", "single-column")
    content_top = Inches(1.25)

    if image_url:
        # bullets left, image right
        img_bytes = _download_image(image_url)
        col_gap = Inches(0.3)
        col_w = (SLIDE_W - Inches(1.0) - col_gap) / 2
        col_h = SLIDE_H - content_top - M_B
        elements = visual_structure.get("elements", []) or (
            visual_structure.get("left_column", []) + visual_structure.get("right_column", [])
        )
        bullets = [elem.get("text", "") for elem in elements]
        _render_bullet_cards(slide, Inches(0.5), content_top, col_w, bullets, PRIMARY)
        if img_bytes:
            try:
                slide.shapes.add_picture(io.BytesIO(img_bytes),
                                         Inches(0.5) + col_w + col_gap, content_top,
                                         width=col_w, height=col_h)
            except Exception:
                _add_rect(slide, Inches(0.5) + col_w + col_gap, content_top, col_w, col_h, CARD_BG)
        else:
            _add_rect(slide, Inches(0.5) + col_w + col_gap, content_top, col_w, col_h, CARD_BG)
        return

    if layout_type == "single-column":
        elements = visual_structure.get("elements", [])
        bullets = [elem.get("text", "") for elem in elements]
        _render_bullet_cards(slide, Inches(0.5), content_top, SLIDE_W - Inches(1.0), bullets, PRIMARY)
    else:
        left_elements = visual_structure.get("left_column", [])
        right_elements = visual_structure.get("right_column", [])
        left_bullets = [elem.get("text", "") for elem in left_elements]
        right_bullets = [elem.get("text", "") for elem in right_elements]

        col_gap = Inches(0.3)
        col_w = (SLIDE_W - Inches(1.0) - col_gap) / 2
        col1_x = Inches(0.5)
        col2_x = Inches(0.5) + col_w + col_gap

        _render_bullet_cards(slide, col1_x, content_top, col_w, left_bullets, PRIMARY)
        _render_bullet_cards(slide, col2_x, content_top, col_w, right_bullets, SECONDARY)


def _render_visual_left_text_right_slide(prs: Presentation, title: str, visual_structure: dict, image_url: str | None) -> None:
    """Render text on left, visual on right."""
    slide = prs.slides.add_slide(_blank_layout(prs))
    _slide_header(slide, title)
    
    elements = visual_structure.get("text_items", [])
    bullets = [elem.get("text", "") for elem in elements]
    clean = [_sanitize(b) for b in bullets if b and _sanitize(b)][:5]
    
    content_top = Inches(1.25)
    text_w = Inches(7.2)
    vis_w = Inches(4.8)
    vis_left = SLIDE_W - vis_w - M_R
    vis_h = SLIDE_H - content_top - M_B
    
    if image_url:
        _render_bullet_cards(slide, Inches(0.5), content_top, text_w, clean, PRIMARY)
        _insert_image(slide, image_url, vis_left, content_top, vis_w, vis_h, CARD_BG)
    else:
        # No image — use full width for bullets
        _render_bullet_cards(slide, Inches(0.5), content_top, SLIDE_W - Inches(1.0), clean, PRIMARY)


# ── Layout dispatcher ──────────────────────────────────────────────────────────

def _dispatch_slide(
    prs: Presentation,
    layout_map: dict,
    slide_data: dict,
    slide_idx: int,
    chart_data: dict,
    image_url: str | None,
    use_template_layouts: bool,
) -> None:
    """
    Enhanced dispatcher: checks for visual_structure first (from Visual Composer),
    then falls back to legacy bullet rendering.
    """
    title      = str(slide_data.get("title", f"Slide {slide_idx + 1}")).strip()
    raw_bullets = slide_data.get("content", [])
    bullets    = [_sanitize(b) for b in raw_bullets if b and _sanitize(b)][:5]
    layout     = str(slide_data.get("layout", "grid-2")).strip().lower()
    slide_type = slide_data.get("type", "content")

    logger.debug(
        f"[Template] Slide {slide_idx}: layout='{layout}' "
        f"type='{slide_type}' title='{title[:45]}' bullets={len(bullets)}"
    )

    # ── NEW: Check for visual_structure (from Visual Composer) ───────────
    visual_structure = slide_data.get("visual_structure")
    
    if visual_structure:
        visual_type = visual_structure.get("type", "grid")
        logger.debug(f"[Template] Slide {slide_idx}: Using visual_structure type='{visual_type}'")
        
        try:
            if visual_type == "cards":
                _render_visual_cards_slide(prs, title, visual_structure)
            elif visual_type == "process":
                _render_visual_process_slide(prs, title, visual_structure)
            elif visual_type == "comparison":
                _render_visual_comparison_slide(prs, title, visual_structure)
            elif visual_type == "chart":
                _render_visual_chart_slide(prs, title, visual_structure)
            elif visual_type == "centered":
                _render_visual_centered_slide(prs, title, visual_structure)
            elif visual_type == "left-text-right-visual":
                _render_visual_left_text_right_slide(prs, title, visual_structure, image_url)
            else:  # "grid" or unknown
                _render_visual_grid_slide(prs, title, visual_structure, image_url)
            return  # Success, exit early
            
        except Exception as exc:
            logger.warning(
                f"[Template] Slide {slide_idx}: Visual structure rendering failed ({exc}), "
                f"falling back to bullet rendering"
            )
            # Fall through to legacy rendering below

    # ── LEGACY: Bullet-based rendering (fallback for old data) ──────────
    try:
        # ── Chart layout ─────────────────────────────────────────────────────
        has_chart = bool(
            chart_data.get("chart_image") or
            chart_data.get("chart_data") or
            chart_data.get("categories")
        )
        if layout == "chart" or (slide_type == "chart" and has_chart):
            _add_chart_slide(prs, title, bullets, chart_data)

        # ── Process layout ───────────────────────────────────────────────────
        elif layout == "process":
            _add_process_slide(prs, title, bullets)

        # ── Grid-3 layout ────────────────────────────────────────────────────
        elif layout == "grid-3":
            _add_grid3_slide(prs, title, bullets)

        # ── Comparison layout ─────────────────────────────────────────────────
        elif layout == "comparison":
            if use_template_layouts and layout_map.get("two_col") is not None:
                try:
                    _add_template_two_col_slide(prs, layout_map["two_col"], title, bullets)
                    return
                except Exception as exc:
                    logger.debug(f"[Template] two_col template failed: {exc}, falling back")
            _add_comparison_slide(prs, title, bullets)

        # ── Centered layout ───────────────────────────────────────────────────
        elif layout == "centered":
            if use_template_layouts and layout_map.get("content") is not None:
                try:
                    _add_template_content_slide(prs, layout_map["content"], title, bullets)
                    return
                except Exception as exc:
                    logger.debug(f"[Template] centered template failed: {exc}, falling back")
            _add_centered_slide(prs, title, bullets)

        # ── Left-text-right-visual layout ─────────────────────────────────────
        elif layout == "left-text-right-visual":
            if use_template_layouts and image_url and layout_map.get("picture") is not None:
                try:
                    _add_template_picture_slide(
                        prs, layout_map["picture"], title, bullets, image_url
                    )
                    return
                except Exception as exc:
                    logger.debug(f"[Template] picture template failed: {exc}, falling back")
            _add_left_text_right_visual_slide(prs, title, bullets, image_url)

        # ── Grid-2 (default) ──────────────────────────────────────────────────
        else:
            if use_template_layouts and layout_map.get("content") is not None:
                try:
                    if image_url and layout_map.get("picture") is not None:
                        _add_template_picture_slide(
                            prs, layout_map["picture"], title, bullets, image_url
                        )
                    else:
                        _add_template_content_slide(
                            prs, layout_map["content"], title, bullets
                        )
                    return
                except Exception as exc:
                    logger.debug(f"[Template] content template failed: {exc}, falling back")
            _add_grid2_slide(prs, title, bullets, image_url)

    except Exception as exc:
        logger.warning(f"[Template] Slide {slide_idx} (layout='{layout}') hard failure: {exc} — emergency grid-2")
        try:
            _add_grid2_slide(prs, title, bullets, image_url)
        except Exception:
            pass


# ── Main agent node ───────────────────────────────────────────────────────────

async def template_node(state: dict) -> dict:
    logger.info("[Template] Building PPTX")

    # visual_composer writes to "slides" (last enrichment); critiqued_slides is validator output.
    # Always prefer "slides" — it carries visual_structure from the composer.
    slides_data: list[dict] = state.get("slides") or state.get("critiqued_slides", [])
    charts: list[dict]       = state.get("charts", [])
    images: dict[str, str]   = state.get("images", {})
    template_id: str         = state.get("template_id", "")
    output_id: str           = state.get("output_id", "")
    query: str               = state.get("query", "AI Presentation")

    # ── Load template as base presentation ────────────────────────────────────
    # Loading the template file directly preserves its slide master, theme colours,
    # fonts, and background imagery.  We clear the existing slides and add fresh
    # ones using the template's own layouts.
    prs: Presentation | None = None
    layout_map: dict = {}
    use_template_layouts = False

    try:
        from services.storage_service import download_file
        tmpl_meta  = get_template(template_id)
        tmpl_bytes = download_file(settings.STORAGE_BUCKET_RAW, tmpl_meta["storage_path"])

        # Load template as the base (inherits theme + master)
        prs = Presentation(io.BytesIO(tmpl_bytes))

        # Analyse layouts BEFORE clearing slides
        layout_map = _analyze_template_layouts(prs)
        use_template_layouts = True

        # Remove existing slides (keeps slide master + layouts intact)
        _clear_slides(prs)

        logger.info(
            f"[Template] Loaded template: {len(prs.slide_layouts)} layouts, "
            f"size={prs.slide_width.inches:.2f}x{prs.slide_height.inches:.2f} in"
        )

    except Exception as exc:
        logger.warning(f"[Template] Template load failed ({exc}), using blank fallback")
        prs = Presentation()
        prs.slide_width  = SLIDE_W
        prs.slide_height = SLIDE_H
        use_template_layouts = False
        layout_map = {"title": 0, "content": 0, "two_col": 0, "picture": 0, "blank": 0}

    # ── Title slide ───────────────────────────────────────────────────────────
    # Only add an auto title slide when the planner did NOT already include one
    # (planner now always adds a centered intent="intro" slide as slide 1).
    first_is_title = (
        slides_data and
        slides_data[0].get("intent") == "intro" and
        slides_data[0].get("layout") == "centered" and
        not slides_data[0].get("subsection_id")
    )
    if not first_is_title:
        try:
            if use_template_layouts:
                _add_template_title_slide(
                    prs, layout_map["title"], query,
                    "AI-Generated Presentation  |  DeckSmith"
                )
            else:
                _add_title_slide(prs, query, "AI-Generated Presentation  |  DeckSmith")
        except Exception as exc:
            logger.warning(f"[Template] Auto title slide failed: {exc}")

    # ── Content slides ────────────────────────────────────────────────────────
    # NOTE: Table slides are NOT rendered separately at the end anymore.
    # Tables that belong to a slide are embedded as charts via the chart_agent,
    # so they appear in the correct position within the narrative.
    for i, slide_data in enumerate(slides_data):
        chart_entry = charts[i] if i < len(charts) else {}
        image_url   = images.get(str(i))

        _dispatch_slide(
            prs, layout_map, slide_data, i,
            chart_entry, image_url, use_template_layouts,
        )

    # ── Serialise + upload ────────────────────────────────────────────────────
    buf = io.BytesIO()
    prs.save(buf)
    pptx_bytes = buf.getvalue()

    try:
        from services.storage_service import upload_pptx, get_public_url
        filename   = f"{output_id}.pptx"
        upload_pptx(settings.STORAGE_BUCKET_OUTPUT, filename, pptx_bytes)
        public_url = get_public_url(settings.STORAGE_BUCKET_OUTPUT, filename)
        update_output(output_id, "complete", filename)
        logger.info(f"[Template] Uploaded → {public_url[:80]}")
    except Exception as exc:
        logger.error(f"[Template] Upload failed: {exc}")
        update_output(output_id, "failed")

    return {"pptx_bytes": pptx_bytes, "error": None}
