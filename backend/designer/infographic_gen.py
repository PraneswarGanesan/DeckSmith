class InfographicGenerator:

    def bullets_to_flow(self, bullets: list[str]):
        return [
            {
                "type": "node",
                "text": b,
                "shape": "rounded_rect"
            }
            for b in bullets
        ]

    def bullets_to_hierarchy(self, bullets: list[str]):
        return {
            "root": bullets[0] if bullets else "",
            "children": bullets[1:]
        }