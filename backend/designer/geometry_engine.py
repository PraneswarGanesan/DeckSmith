from typing import List, Dict


class GeometryEngine:

    def split_vertical(self, width, height, parts):
        box_height = height // parts

        return [
            {
                "x": 0,
                "y": i * box_height,
                "width": width,
                "height": box_height
            }
            for i in range(parts)
        ]

    def split_horizontal(self, width, height, parts):
        box_width = width // parts

        return [
            {
                "x": i * box_width,
                "y": 0,
                "width": box_width,
                "height": height
            }
            for i in range(parts)
        ]

    def grid(self, width, height, rows, cols):
        cell_w = width // cols
        cell_h = height // rows

        grid = []
        for r in range(rows):
            for c in range(cols):
                grid.append({
                    "x": c * cell_w,
                    "y": r * cell_h,
                    "width": cell_w,
                    "height": cell_h
                })

        return grid