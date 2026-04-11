"""
Markdown parser — fully extracts document structure without losing any content.

Fixes over original:
  1. Section-level content (between ## and first ###) is captured in a
     subsection with index 0 sharing the section title — not dropped.
  2. Tables are detected inline and attached to the subsection they appear in,
     not sequentially matched by cursor.
  3. H4 headings (####) are treated as sub-headings inside content, not lost.
  4. Empty lines preserved for paragraph detection.

Output structure:
{
  "title": str,
  "sections": [
    {
      "section_index": int,
      "section_title": str,
      "subsections": [
        {
          "subsection_index": int,
          "subsection_title": str,
          "content": str,
          "tables": [          # inline tables found in this subsection
            {
              "table_title": str,
              "headers": [str],
              "rows": [dict]
            }
          ]
        }
      ]
    }
  ]
}
"""
from __future__ import annotations
import re


# ── Table extraction helpers ──────────────────────────────────────────────────

def _is_separator_row(line: str) -> bool:
    """Detect markdown table separator: | --- | :---: | etc."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    return all(re.match(r"^:?-+:?$", c) for c in cells if c)


def _parse_table_from_lines(lines: list[str], start: int) -> tuple[dict | None, int]:
    """
    Try to parse a markdown table starting at lines[start].
    Returns (table_dict, end_index) or (None, start) if not a table.
    end_index is the index AFTER the last table row.
    """
    # Need at least header row + separator row
    if start + 1 >= len(lines):
        return None, start

    header_line = lines[start].strip()
    sep_line = lines[start + 1].strip() if start + 1 < len(lines) else ""

    if not header_line.startswith("|") or not _is_separator_row(sep_line):
        return None, start

    headers = [c.strip() for c in header_line.strip("|").split("|")]
    headers = [h for h in headers if h]
    if not headers:
        return None, start

    rows: list[dict] = []
    end = start + 2
    while end < len(lines):
        row_line = lines[end].strip()
        if not row_line.startswith("|"):
            break
        cells = [c.strip() for c in row_line.strip("|").split("|")]
        # Pad or trim to match header count
        while len(cells) < len(headers):
            cells.append("")
        row_dict = {headers[i]: cells[i] for i in range(len(headers))}
        rows.append(row_dict)
        end += 1

    if not rows:
        return None, start

    return {"headers": headers, "rows": rows, "table_title": ""}, end


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_markdown(md: str) -> dict:
    """
    Parse a markdown string into a structured document tree.
    All content is preserved — no section-level text is dropped.
    Tables are attached to the subsection they physically appear within.
    """
    lines = md.split("\n")
    doc: dict = {"title": "", "sections": []}

    current_section: dict | None = None
    current_sub: dict | None = None
    section_index = 0

    def _flush_sub():
        """Append current_sub to current_section if it has content."""
        nonlocal current_sub
        if current_sub is not None and current_section is not None:
            text = current_sub["content"].strip()
            has_tables = bool(current_sub.get("tables"))
            if text or has_tables:
                current_section["subsections"].append(current_sub)
        current_sub = None

    def _flush_section():
        """Flush sub then section."""
        _flush_sub()
        if current_section is not None:
            doc["sections"].append(current_section)

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        # ── Document title (H1) ────────────────────────────────────────────
        if line.startswith("# ") and not line.startswith("## "):
            doc["title"] = line[2:].strip()
            i += 1
            continue

        # ── Section heading (H2) ───────────────────────────────────────────
        if line.startswith("## "):
            _flush_section()
            section_index += 1
            sec_title = line[3:].strip()
            current_section = {
                "section_index": section_index,
                "section_title": sec_title,
                "subsections": [],
            }
            # Create index-0 subsection to capture section-level content
            current_sub = {
                "subsection_index": 0,
                "subsection_title": sec_title,
                "content": "",
                "tables": [],
            }
            i += 1
            continue

        # ── Subsection heading (H3) ────────────────────────────────────────
        if line.startswith("### "):
            _flush_sub()
            if current_section is None:
                # Orphaned subsection — create implicit section
                section_index += 1
                current_section = {
                    "section_index": section_index,
                    "section_title": "Content",
                    "subsections": [],
                }
            sub_idx = len(current_section["subsections"]) + 1
            current_sub = {
                "subsection_index": sub_idx,
                "subsection_title": line[4:].strip(),
                "content": "",
                "tables": [],
            }
            i += 1
            continue

        # ── H4 heading — treat as bold content line ────────────────────────
        if line.startswith("#### "):
            if current_sub is not None:
                current_sub["content"] += f"**{line[5:].strip()}**\n"
            i += 1
            continue

        # ── Markdown table detection ───────────────────────────────────────
        if line.startswith("|") and current_sub is not None:
            table, next_i = _parse_table_from_lines(lines, i)
            if table is not None:
                # Look back for a table title (previous non-empty line)
                for back in range(i - 1, max(i - 4, -1), -1):
                    prev = lines[back].strip()
                    if prev and not prev.startswith("|"):
                        table["table_title"] = prev.lstrip("#").strip()
                        break
                current_sub["tables"].append(table)
                # Also add a placeholder in content so the text flow makes sense
                current_sub["content"] += f"[TABLE: {table['table_title'] or 'Data'}]\n"
                i = next_i
                continue

        # ── Regular content ────────────────────────────────────────────────
        if current_sub is not None:
            current_sub["content"] += raw + "\n"
        elif current_section is not None:
            # Content between H2 and first H3 — should not happen with new
            # section-level subsection logic, but guard anyway
            pass

        i += 1

    # Flush whatever is left
    _flush_section()

    return doc


# ── Convenience: flat table list for backward-compat ─────────────────────────

def extract_all_tables(parsed: dict) -> list[dict]:
    """
    Return a flat list of all tables found in the parsed document,
    each annotated with its subsection_title for association.
    """
    tables = []
    for section in parsed.get("sections", []):
        for sub in section.get("subsections", []):
            for tbl in sub.get("tables", []):
                tables.append({
                    **tbl,
                    "_subsection_title": sub["subsection_title"],
                    "_section_title": section["section_title"],
                })
    return tables
