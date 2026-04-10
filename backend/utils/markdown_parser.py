def parse_markdown(md: str):
    lines = md.split("\n")

    doc = {"title": "", "sections": []}
    current_section = None
    current_sub = None

    section_index = 0
    subsection_index = 0

    for line in lines:
        line = line.strip()

        if line.startswith("# "):
            doc["title"] = line.replace("# ", "")

        elif line.startswith("## "):
            if current_section:
                if current_sub:
                    current_section["subsections"].append(current_sub)
                    current_sub = None
                doc["sections"].append(current_section)

            section_index += 1
            subsection_index = 0

            current_section = {
                "section_index": section_index,
                "section_title": line.replace("## ", ""),
                "subsections": []
            }

        elif line.startswith("### "):
            if current_sub:
                current_section["subsections"].append(current_sub)

            subsection_index += 1

            current_sub = {
                "subsection_index": subsection_index,
                "subsection_title": line.replace("### ", ""),
                "content": ""
            }

        else:
            if current_sub:
                current_sub["content"] += line + "\n"

    # flush last
    if current_sub and current_section:
        current_section["subsections"].append(current_sub)

    if current_section:
        doc["sections"].append(current_section)

    return doc