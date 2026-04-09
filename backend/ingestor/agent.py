from ingestor.md_parser import MarkdownParser
from ingestor.template_analyzer import TemplateAnalyzer
from ingestor.indexer import Indexer
from ingestor.schemas import IngestResult
from utils.logger import get_logger

logger = get_logger("ingestor.agent")


class IngestorAgent:

    def __init__(self):
        self.parser = MarkdownParser()
        self.template = TemplateAnalyzer()
        self.indexer = Indexer()

    async def run(self, md_text: str, template_xml: str, username: str):

        logger.info("Starting ingestion pipeline")

        # Step 1: Parse markdown
        chunks = self.parser.parse(md_text)

        # Step 2: Analyze template
        layout = self.template.parse_layout(template_xml)

        # Step 3: Index (embedding + DB)
        stored_count = await self.indexer.index(chunks, username)

        logger.info(f"Ingested {stored_count} chunks")

        return IngestResult(
            total_chunks=len(chunks),
            layout_elements=len(layout),
            status="success"
        )