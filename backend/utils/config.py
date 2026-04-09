import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # APP
    ENV = os.getenv("ENV", "dev")

    # SUPABASE
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # OLLAMA
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

    # EMBEDDING
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

    # UNSPLASH
    UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
    UNSPLASH_BASE_URL = os.getenv("UNSPLASH_BASE_URL")

    # RATE LIMIT
    UNSPLASH_RATE_LIMIT = int(os.getenv("UNSPLASH_RATE_LIMIT_PER_MINUTE", 10))


settings = Settings()