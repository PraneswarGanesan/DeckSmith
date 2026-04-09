from utils.supabase_client import supabase_client
from utils.ollama_wrapper import ollama_client
from utils.rate_limiter import rate_limiter
import requests
import os
from utils.config import settings
def test_supabase():
    print("\n--- Testing Supabase ---")

    data = supabase_client.insert("user_assets", {
        "username": "test_user",
        "file_name": "demo.md",
        "file_type": "markdown",
        "raw_content": "Hello AI system"
    })

    print("Insert result:", data)

    res = supabase_client.query("user_assets", {
        "username": "test_user"
    })

    print("Query result:", res)
def test_unsplash():
    print("\n--- Testing Unsplash ---")
    # RESET limiter
    from utils.rate_limiter import RateLimiter
    local_limiter = RateLimiter()
    if not rate_limiter.allow():
        print("❌ Rate limited")
        return

    try:
        res = requests.get(
            f"{settings.UNSPLASH_BASE_URL}/search/photos",
            headers={
                "Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"
            },
            params={
                "query": "AI technology",
                "per_page": 1
            }
        )

        data = res.json()

        if data.get("results"):
            img = data["results"][0]

            print("✅ Image fetched")
            print("URL:", img["urls"]["regular"])
            print("Author:", img["user"]["name"])
        else:
            print("❌ No image found")

    except Exception as e:
        print("❌ Unsplash error:", e)

def test_ollama():
    print("\n--- Testing Ollama ---")

    text = ollama_client.generate("Explain AI in one short sentence")
    print("Generated:", text)

    embedding = ollama_client.embed("AI is transforming industries")

    print("Embedding length:", len(embedding))

    if len(embedding) == 0:
        print("❌ Embedding failed")
    else:
        print("✅ Embedding success")


def test_rate_limiter():
    print("\n--- Testing Rate Limiter ---")

    for i in range(12):
        allowed = rate_limiter.allow()
        print(f"Request {i+1}: {'✅ Allowed' if allowed else '❌ Blocked'}")


if __name__ == "__main__":
    # test_supabase()
    # test_ollama()
    # test_rate_limiter()
    # test_unsplash()