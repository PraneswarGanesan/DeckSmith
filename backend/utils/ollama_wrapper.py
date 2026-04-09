import requests
from utils.config import settings
from utils.logger import get_logger
import time

logger = get_logger("ollama")


class OllamaClient:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL

    def _post(self, endpoint, payload, retries=2):
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries + 1):
            try:
                res = requests.post(url, json=payload, timeout=30)
                res.raise_for_status()
                return res.json()
            except Exception as e:
                logger.error(f"Ollama error (attempt {attempt}): {e}")
                time.sleep(1)

        return {}

    # =========================
    # TEXT GENERATION
    # =========================
    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        data = self._post("/api/generate", payload)

        return data.get("response", "")

    # =========================
    # EMBEDDINGS
    # =========================
    def embed(self, text: str):
        payload = {
            "model": self.embedding_model,
            "prompt": text
        }

        data = self._post("/api/embeddings", payload)

        embedding = data.get("embedding", [])

        if not embedding:
            logger.error("Empty embedding returned")

        return embedding


ollama_client = OllamaClient()