from pptx import Presentation


def analyze_template(path):
    prs = Presentation(path)

    layouts = []

    for i, layout in enumerate(prs.slide_layouts):
        info = {
            "index": i,
            "has_title": False,
            "has_body": False,
            "has_image": False
        }

        for shape in layout.shapes:
            if not shape.is_placeholder:
                continue

            t = shape.placeholder_format.type

            if t == 1:
                info["has_title"] = True
            elif t in [2, 7]:
                info["has_body"] = True
            elif t == 18:
                info["has_image"] = True

        layouts.append(info)

    return layouts