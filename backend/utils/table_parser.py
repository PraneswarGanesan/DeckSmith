def extract_tables(md: str):
    lines = md.split("\n")

    tables = []
    buffer = []

    for line in lines:
        if "|" in line:
            buffer.append(line.strip())
        else:
            if buffer:
                tables.append(parse_table(buffer))
                buffer = []

    if buffer:
        tables.append(parse_table(buffer))

    return tables


def parse_table(lines):
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]
    rows = []

    for line in lines[2:]:
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) == len(headers):
            rows.append(dict(zip(headers, cols)))

    return {
        "headers": headers,
        "rows": rows
    }