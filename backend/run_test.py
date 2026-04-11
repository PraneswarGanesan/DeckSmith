import asyncio
import io
import json
from pptx import Presentation

from utils.markdown_parser import parse_markdown

async def test():
    print("\n" + "="*60)
    print(">>> DECKSMITH PIPELINE WORKFLOW TRACE")
    print("="*60 + "\n")
    
    print("[1] PARSING MARKDOWN: templates/sample.md")
    with open("templates/sample.md", "r", encoding="utf-8") as f:
        md = f.read()
    parsed = parse_markdown(md)
    grouped = [{"section_title": s["section_title"], "subsections": s["subsections"]} for s in parsed.get("sections", [])]
    print(f"    [OK] Found {len(grouped)} structural sections.\n")

    state = {
        "doc_id": "test",
        "template_id": "test",
        "query": "Executive AI Strategy Presentation",
        "user_id": "test",
        
        "grouped": grouped,
        "plan": [],
        "slides": [],
        "charts": [],
        "images": {},
        "template_schema": [],
        "critiqued_slides": [],
        "pptx_bytes": b"",
        "error": None
    }
    
    print("[2] EXECUTING PLANNER AGENT (Designing Story Arc)...")
    from agents.planner_agent import planner_node
    res = await planner_node(state)
    state.update(res)
    
    if state.get("error"):
        print(f"[ERROR] PLANNER FAILED: {state['error']}")
        return
        
    print(f"    [OK] Story Arc planned with {len(state['plan'])} slides.")
    for i, p in enumerate(state['plan']):
        print(f"      - Slide {i+1}: [{p.get('intent', '').upper()}] '{p.get('title')}' (Visual: {p.get('visual_type')})")
    print()

    print("[3] EXECUTING CONTENT AGENT (McKinsey Copywriting)...")
    from agents.content_agent import content_node
    res = await content_node(state)
    state.update(res)
    
    if state.get("error"):
        print(f"[ERROR] CONTENT AGENT FAILED: {state['error']}")
        return
        
    print(f"    [OK] Generated professional copy for {len(state['slides'])} slides.")
    for i, s in enumerate(state['slides']):
        print(f"      - '{s.get('title')}': {len(s.get('content', []))} bullet points.")
    print()
    
    print("[4] TEMPLATE ANALYZER (Extracting Native Schema)...")
    from agents.template_analyzer_agent import _analyze_layouts
    prs = Presentation("train/temp2.pptx")
    schema = _analyze_layouts(prs)
    state["template_schema"] = schema
    print(f"    [OK] Found {len(schema)} valid layouts in master template (temp2.pptx).\n")
    
    print("[5] EXECUTING VISUAL COMPOSER STYLIST (Semantic Layout Mapping)...")
    from agents.visual_composer_agent import visual_composer_node
    res = await visual_composer_node(state)
    state.update(res)
    
    if state.get("error"):
        print(f"[ERROR] STYLIST FAILED: {state['error']}")
        return
        
    mapped_count = sum(1 for s in state['slides'] if "native_mapping" in s)
    print(f"    [OK] Successfully styled {mapped_count}/{len(state['slides'])} slides into native PowerPoint layouts.")
    for i, s in enumerate(state['slides']):
        mapping = s.get('native_mapping')
        if mapping:
            print(f"      - '{s.get('title')}': Mapped to Layout #{mapping.get('layout_index')} with {len(mapping.get('mappings', {}))} placeholders filled.")
        else:
            print(f"      - '{s.get('title')}': FALLBACK (No native mapping).")
    print()

    print("[6] TEMPLATE EXECUTION (Injecting into PPTX)...")
    from agents.template_agent import _clear_slides, _render_native_slide, _render_fallback_slide
    _clear_slides(prs)
    
    for i, slide_data in enumerate(state.get("slides", [])):
        if "native_mapping" in slide_data:
            _render_native_slide(prs, slide_data, i, None, {})
        else:
            _render_fallback_slide(prs, slide_data, None)
            
    out_file = "debug_output.pptx"
    prs.save(out_file)
    print(f"    [OK] Finished assembling! Saved perfectly completely file to {out_file}.\n")
    print(">>> PIPELINE WORKFLOW COMPLETE!\n")

if __name__ == "__main__":
    asyncio.run(test())
