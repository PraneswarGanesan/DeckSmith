"""
Scans a PPTX and returns a JSON dictionary describing its layouts.
"""
from pptx import Presentation
import json
import sys

def get_template_schema(pptx_bytes):
    import io
    prs = Presentation(io.BytesIO(pptx_bytes))
    layouts = []
    
    for i, layout in enumerate(prs.slide_layouts):
        l_info = {
            "layout_index": i,
            "name": layout.name,
            "placeholders": []
        }
        for shape in layout.shapes:
            if shape.is_placeholder:
                ph = shape.placeholder_format
                l_info["placeholders"].append({
                    "idx": ph.idx,
                    "type": str(ph.type).split('.')[-1] if '.' in str(ph.type) else str(ph.type)
                })
        # Filter out master slides that are completely empty
        if len(l_info["placeholders"]) > 0:
            layouts.append(l_info)
            
    return layouts
