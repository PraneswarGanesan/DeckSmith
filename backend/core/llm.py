"""
Unified LLM + Embedding abstraction.

Switch providers with a single env var:
  LLM_PROVIDER=ollama   → local Ollama (dev/testing)
  LLM_PROVIDER=gemini   → Google Gemini API (production/submission)

Gemini models used:
  generate  → gemini-2.0-flash  (fast, high quality, free tier available)
  embed     → text-embedding-004 (768-dim, best-in-class)

Ollama models used (from .env):
  generate  → OLLAMA_LLM_MODEL   (e.g. tinyllama, mistral)
  embed     → OLLAMA_EMBED_MODEL (e.g. nomic-embed-text)
"""
from __future__ import annotations

import os
import json
import httpx

from config import settings
from logger import get_logger

logger = get_logger(__name__)

# ── Provider selection ────────────────────────────────────────────────────────
PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()   # "ollama" | "gemini" | "openrouter"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
GEMINI_LLM_MODEL = os.getenv("GEMINI_LLM_MODEL", "gemini-2.0-flash")
GEMINI_EMB_MODEL = os.getenv("GEMINI_EMB_MODEL", "text-embedding-004")
GEMINI_BASE      = "https://generativelanguage.googleapis.com/v1beta/models"

if PROVIDER == "gemini" and not GEMINI_API_KEY:
    raise EnvironmentError(
        "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set in .env"
    )

logger.info(f"[LLM] Provider = {PROVIDER.upper()}")


# ── OpenRouter ────────────────────────────────────────────────────────────────

async def _openrouter_generate(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "DeckSmith",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# ── Gemini ────────────────────────────────────────────────────────────────────

async def _gemini_generate(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    url = f"{GEMINI_BASE}/{GEMINI_LLM_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _gemini_embed(text: str) -> list[float] | None:
    url = f"{GEMINI_BASE}/{GEMINI_EMB_MODEL}:embedContent?key={GEMINI_API_KEY}"
    payload = {
        "model": f"models/{GEMINI_EMB_MODEL}",
        "content": {"parts": [{"text": text}]},
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]
    except Exception as exc:
        logger.warning(f"[LLM] Gemini embed failed: {exc}")
        return None


# ── Ollama ────────────────────────────────────────────────────────────────────

async def _ollama_generate(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": settings.OLLAMA_LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        resp.raise_for_status()
        return resp.json()["response"]


async def _ollama_embed(text: str) -> list[float] | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
    except Exception as exc:
        logger.warning(f"[LLM] Ollama embed failed: {exc}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def generate(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Generate text from a prompt. Raises on hard failure."""
    if PROVIDER == "openrouter":
        return await _openrouter_generate(prompt, temperature, max_tokens)
    elif PROVIDER == "gemini":
        return await _gemini_generate(prompt, temperature, max_tokens)
    return await _ollama_generate(prompt, temperature, max_tokens)


async def embed(text: str) -> list[float] | None:
    """Return embedding vector, or None if unavailable (BM25 will cover it)."""
    if PROVIDER == "gemini":
        return await _gemini_embed(text)
    return await _ollama_embed(text)
