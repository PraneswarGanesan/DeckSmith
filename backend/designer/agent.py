from designer.geometry_engine import GeometryEngine
from designer.infographic_gen import InfographicGenerator
from designer.chart_factory import ChartFactory
from designer.unsplash_client import UnsplashClient


class DesignerAgent:

    def __init__(self):
        self.geometry = GeometryEngine()
        self.infographic = InfographicGenerator()
        self.chart = ChartFactory()
        self.unsplash = UnsplashClient()

    def run(self, chunks: list[dict]):
        slides = []

        for chunk in chunks:
            content = chunk["content"]

            layout = self.geometry.split_vertical(1000, 600, 2)

            bullets = self._extract_bullets(content)

            infographic = self.infographic.bullets_to_flow(bullets)

            image = self.unsplash.search_image(chunk.get("heading", "presentation"))

            slides.append({
                "layout": layout,
                "content": content,
                "infographic": infographic,
                "image": image
            })

        return slides

    def _extract_bullets(self, text: str):
        lines = text.split("\n")
        return [l.strip("- ") for l in lines if l.startswith("-")]