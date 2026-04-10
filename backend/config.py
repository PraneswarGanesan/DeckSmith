import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # =========================
    # SUPABASE CONFIG
    # =========================
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY")

    # =========================
    # OLLAMA CONFIG
    # =========================
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "mistral")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # =========================
    # UNSPLASH CONFIG
    # =========================
    UNSPLASH_ACCESS_KEY: str = os.getenv("UNSPLASH_ACCESS_KEY")
    UNSPLASH_BASE_URL: str = os.getenv("UNSPLASH_BASE_URL", "https://api.unsplash.com")

    # =========================
    # STORAGE CONFIG
    # =========================
    STORAGE_BUCKET_RAW: str = os.getenv("STORAGE_BUCKET_RAW", "raw-assets")
    STORAGE_BUCKET_OUTPUT: str = os.getenv("STORAGE_BUCKET_OUTPUT", "generated-output")
    STORAGE_BUCKET_IMAGES: str = os.getenv("STORAGE_BUCKET_IMAGES", "images")

    # =========================
    # APP CONFIG
    # =========================
    APP_ENV: str = os.getenv("APP_ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True") == "True"

    # =========================
    # AUTH CONFIG
    # =========================
    JWT_SECRET: str = os.getenv("JWT_SECRET", "supersecretkey")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", 60))


settings = Settings()


def validate_settings():
    required_fields = {
        "SUPABASE_URL": settings.SUPABASE_URL,
        "SUPABASE_KEY": settings.SUPABASE_KEY,
        "SUPABASE_SERVICE_KEY": settings.SUPABASE_SERVICE_KEY,
        "UNSPLASH_ACCESS_KEY": settings.UNSPLASH_ACCESS_KEY,
    }

    missing = [key for key, value in required_fields.items() if not value]

    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")


validate_settings()


class UserContext:
    def __init__(self, user_id: str, username: str):
        if not user_id or not username:
            raise ValueError("user_id and username are required")

        self.user_id = user_id
        self.username = username

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username
        }