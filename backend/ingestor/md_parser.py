import re
from typing import List
from ingestor.schemas import Chunk
from ingestor.utils import generate_id


class MarkdownParser:

    def parse(self, md_text: str) -> List[Chunk]:
        sections = re.split(r'(?=^#)', md_text, flags=re.MULTILINE)

        chunks = []

        for sec in sections:
            if not sec.strip():
                continue

            heading = self._get_heading(sec)
            tables = self._extract_tables(sec)

            chunks.append(
                Chunk(
                    id=generate_id(),
                    content=sec.strip(),
                    metadata={
                        "heading": heading,
                        "has_table": bool(tables),
                        "length": len(sec)
                    }
                )
            )

        return chunks

    def _get_heading(self, text: str):
        match = re.match(r'^(#+)\s+(.*)', text)
        return match.group(2) if match else "No Heading"

    def _extract_tables(self, text):
        pattern = r'(\|.*\|\n\|[-:]+\|.*\n(?:\|.*\|\n?)*)'
        return re.findall(pattern, text)