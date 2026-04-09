import asyncio
from ingestor.agent import IngestorAgent
from utils.supabase_client import supabase_client

TEST_USER_NAME = "test_user_123"


async def run_test():
    agent = IngestorAgent()

    md_text = """
# AI Overview
AI is transforming industries.

## Applications
AI is used in healthcare and finance.
"""

    template_xml = "<p:sldMaster xmlns:p='p' xmlns:a='a'></p:sldMaster>"

    # -----------------------------
    # CLEAN OLD DATA
    # -----------------------------
    supabase_client.client.table("content_chunks") \
        .delete() \
        .eq("username", TEST_USER_NAME) \
        .execute()
    # -----------------------------
    # RUN INGESTION
    # -----------------------------
    result = await agent.run(md_text, template_xml, TEST_USER_NAME)

    print("\n--- INGEST RESULT ---")
    print(result)

    # -----------------------------
    # RETRIEVAL TEST
    # -----------------------------
    query = "AI in healthcare"

    results = agent.indexer.hybrid_search(query, TEST_USER_NAME, k=3)

    print("\n--- RETRIEVAL RESULTS ---")
    for r in results:
        print("-", r)

    # -----------------------------
    # ASSERTIONS
    # -----------------------------
    assert result.status == "success"
    assert len(results) > 0

    print("\n✅ INDEX + RETRIEVAL WORKING")


if __name__ == "__main__":
    asyncio.run(run_test())