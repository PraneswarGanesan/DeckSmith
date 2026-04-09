import requests
from utils.config import settings


class UnsplashClient:

    def search_image(self, query: str):
        url = f"{settings.UNSPLASH_BASE_URL}/search/photos"

        params = {
            "query": query,
            "client_id": settings.UNSPLASH_ACCESS_KEY,
            "per_page": 1
        }

        res = requests.get(url, params=params)

        if res.status_code != 200:
            return None

        data = res.json()

        if not data["results"]:
            return None

        return data["results"][0]["urls"]["regular"]