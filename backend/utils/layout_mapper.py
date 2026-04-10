from utils.content_formatter import format_for_slide


def map_to_slides(parsed, tables, max_slides=10):
    slides = []
    t_idx = 0

    for section in parsed["sections"]:
        for sub in section["subsections"]:

            # ✅ LIMIT SLIDES
            if len(slides) >= max_slides:
                return slides

            slide = {
                "title": sub["subsection_title"],
                "content": format_for_slide(sub["content"]),
                "chart": None
            }

            if t_idx < len(tables):
                slide["chart"] = tables[t_idx]
                t_idx += 1

            slides.append(slide)

    return slides