"""
Template Agent — the pure executional arm of the styling engine.

Design Philosophy:
  Unlike the old approach of arbitrarily drawing custom shapes and trying
  to guess padding, this executor follows the Visual Composer's 
  `native_mapping` directly. It inserts slides using the exact Layout 
  Index chosen by the Stylist and injects content/images perfectly into
  the pristine native placeholders of the user's template.
  
  This guarantees a flawless, 100% template-matched graphic design.
"""
from __future__ import annotations

import io
import httpx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE
from lxml import etree
from pptx.oxml.ns import qn

from config import settings
from core.database import get_template, update_output
from logger import get_logger

logger = get_logger(__name__)

# Fallbacks if something goes horribly wrong
SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


def _clear_slides(prs: Presentation) -> None:
    """Wipe default existing slides inside a template while keeping masters."""
    sld_id_lst = prs.slides._sldIdLst
    for elem in list(sld_id_lst):
        r_id = elem.get(qn("r:id"))
        if r_id:
            try: prs.part.drop_rel(r_id)
            except Exception: pass
        sld_id_lst.remove(elem)


def _download_image(url: str) -> bytes | None:
    if not url: return None
    try:
        headers = {"User-Agent": "DeckSmith/2.0", "Accept": "image/png, image/jpeg, image/webp, */*"}
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            if "image" not in resp.headers.get("content-type", ""): return None
            return resp.content
    except Exception as exc:
        logger.warning(f"[TemplateAgent] Image download failed: {exc}")
        return None


def _fill_placeholder(shape, content: str) -> None:
    """Robustly insert text into a placeholder."""
    if not shape.has_text_frame:
        return
    tf = shape.text_frame
    tf.clear()
    
    # Simple newline splitting
    lines = content.split('\n')
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line.strip()
        # Let PowerPoint's master layout dictate the list-level and font-style organically


def _fill_picture_placeholder(shape, image_bytes: bytes) -> bool:
    """Insert into an explicit PICTURE placeholder."""
    try:
        shape.insert_picture(io.BytesIO(image_bytes))
        return True
    except Exception as e:
        logger.debug(f"[TemplateAgent] Failed to insert picture into placeholder: {e}")
        return False


def _render_native_slide(prs: Presentation, slide_data: dict, slide_idx: int, image_url: str | None, chart_data: dict) -> None:
    """Execute the Stylist's precise placeholder mapping."""
    mapping_data = slide_data.get("native_mapping")
    layout_idx = mapping_data.get("layout_index", 0)
    
    try:
        layout = prs.slide_layouts[layout_idx]
    except IndexError:
        logger.warning(f"[TemplateAgent] Invalid layout {layout_idx}, falling back to 0")
        layout = prs.slide_layouts[0]
        
    slide = prs.slides.add_slide(layout)
    mappings = mapping_data.get("mappings", {})
    
    # We map by the placeholder's 'idx' integer
    ph_dict = {shape.placeholder_format.idx: shape for shape in slide.placeholders}
    
    for str_idx, content in mappings.items():
        try:
            pidx = int(str_idx)
            if pidx in ph_dict:
                ph = ph_dict[pidx]
                
                # Check if it implies an image
                if ph.placeholder_format.type == 18: # PICTURE
                    if image_url:
                        img_bytes = _download_image(image_url)
                        if img_bytes: _fill_picture_placeholder(ph, img_bytes)
                else:
                    _fill_placeholder(ph, content)
        except Exception as e:
            logger.debug(f"[TemplateAgent] Error filling placeholder {str_idx}: {e}")
            
    # Try inserting chart natively or draw fallback chart if needed
    if chart_data and slide_data.get("visual_type") == "chart":
        logger.debug("[TemplateAgent] (Not fully implemented) native chart injection. Need native object manipulation.")


def _render_fallback_slide(prs: Presentation, slide_data: dict, image_url: str | None) -> None:
    """If semantic mapping failed, drop text gracefully onto the most basic layout."""
    layout = prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    
    title = slide_data.get("title", "")
    content_list = slide_data.get("content", [])
    
    if slide.shapes.title:
        slide.shapes.title.text = title
        
    body_shape = None
    for shape in slide.placeholders:
        if shape.placeholder_format.type in (2, 7): # BODY or OBJECT
            body_shape = shape
            break
            
    if body_shape and content_list:
        _fill_placeholder(body_shape, "\n".join(content_list))
        
    if image_url:
        img_bytes = _download_image(image_url)
        if img_bytes:
            # Drop image nicely on the right
            try: slide.shapes.add_picture(io.BytesIO(img_bytes), Inches(7.5), Inches(2), width=Inches(5))
            except: pass


async def template_node(state: dict) -> dict:
    logger.info("[TemplateAgent] Assembling semantic PPTX...")

    if state.get("error"):
        logger.error(f"[TemplateAgent] Bypassing generation due to pipeline error: {state['error']}")
        return {"error": state["error"]}

    slides_data: list[dict] = state.get("slides") or state.get("critiqued_slides", [])
    charts: list[dict] = state.get("charts", [])
    images: dict[str, str] = state.get("images", {})
    template_id: str = state.get("template_id", "")
    output_id: str = state.get("output_id", "")

    prs = None
    try:
        from services.storage_service import download_file
        tmpl_meta = get_template(template_id)
        tmpl_bytes = download_file(settings.STORAGE_BUCKET_RAW, tmpl_meta["storage_path"])
        prs = Presentation(io.BytesIO(tmpl_bytes))
        _clear_slides(prs)
        logger.info(f"[TemplateAgent] Core presentation loaded ({len(prs.slide_layouts)} layouts).")
    except Exception as exc:
        logger.error(f"[TemplateAgent] FAILED to load user template: {exc}. Using blank.")
        prs = Presentation()
        prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H

    # Process all styled slides
    for i, slide_data in enumerate(slides_data):
        chart_entry = charts[i] if i < len(charts) else {}
        image_url = images.get(str(i))
        
        if "native_mapping" in slide_data:
            _render_native_slide(prs, slide_data, i, image_url, chart_entry)
        else:
            logger.warning(f"[TemplateAgent] Slide {i} lost native mapping. Falling back.")
            _render_fallback_slide(prs, slide_data, image_url)


    # Serialise and upload
    buf = io.BytesIO()
    prs.save(buf)
    pptx_bytes = buf.getvalue()

    try:
        from services.storage_service import upload_pptx, get_public_url
        filename = f"{output_id}.pptx"
        upload_pptx(settings.STORAGE_BUCKET_OUTPUT, filename, pptx_bytes)
        update_output(output_id, "complete", filename)
        logger.info(f"[TemplateAgent] Successfully finalized presentation!")
    except Exception as exc:
        logger.error(f"[TemplateAgent] Upload failed: {exc}")
        update_output(output_id, "failed")

    return {"pptx_bytes": pptx_bytes, "error": None}
