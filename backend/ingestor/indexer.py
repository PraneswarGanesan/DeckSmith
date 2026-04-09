from rank_bm25 import BM25Okapi
from utils.ollama_wrapper import ollama_client
from utils.supabase_client import supabase_client
from utils.logger import get_logger

logger = get_logger("ingestor.indexer")


class Indexer:

    def __init__(self):
        self.corpus = []
        self.bm25 = None

    # =========================
    # INDEXING
    # =========================
    async def index(self, chunks, username: str):
        records = []

        for i, chunk in enumerate(chunks):
            try:
                embedding = ollama_client.embed(chunk.content)

                if not embedding:
                    logger.error("Empty embedding, skipping chunk")
                    continue

                record = {
                    "username": username,
                    "asset_id": None,
                    "chunk_index": i,
                    "heading": chunk.metadata.get("heading"),
                    "subheading": None,
                    "content": chunk.content,
                    "keywords": [],
                    "summary": None,
                    "questions": [],
                    "embedding": embedding
                }

                records.append(record)
                self.corpus.append(chunk.content)

            except Exception as e:
                logger.error(f"Embedding failed: {e}")

        # BM25 setup
        if self.corpus:
            tokenized = [doc.split() for doc in self.corpus]
            self.bm25 = BM25Okapi(tokenized)

        # DB insert
        if records:
            res = supabase_client.insert("content_chunks", records)
            if res is None:
                logger.error("Supabase insert failed")

        return len(records)

    # =========================
    # VECTOR SEARCH (pgvector)
    # =========================
    def vector_search(self, query: str, username: str, k=5):
        try:
            query_embedding = ollama_client.embed(query)

            if not query_embedding:
                logger.error("Query embedding failed")
                return []

            response = supabase_client.rpc(
                "match_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_count": k,
                    "username_filter": username
                }
            )

            # ✅ Already a list
            return response or []

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    # =========================
    # BM25 SEARCH
    # =========================
    def bm25_search(self, query: str, k=5):
        try:
            if not self.bm25:
                return []

            scores = self.bm25.get_scores(query.split())
            ranked = sorted(
                range(len(scores)),
                key=lambda i: scores[i],
                reverse=True
            )

            return [self.corpus[i] for i in ranked[:k]]

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    # =========================
    # HYBRID SEARCH
    # =========================
    def hybrid_search(self, query: str, username: str, k=5):
        try:
            vector_results = self.vector_search(query, username, k)
            bm25_results = self.bm25_search(query, k)

            combined = []

            # Vector results (from DB)
            for r in vector_results:
                if isinstance(r, dict) and "content" in r:
                    combined.append(r["content"])

            # BM25 results (local)
            combined.extend(bm25_results)

            # Remove duplicates, preserve order
            unique = list(dict.fromkeys(combined))

            return unique[:k]

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []