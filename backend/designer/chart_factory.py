class ChartFactory:

    def detect_chart_type(self, text: str):
        if "%" in text:
            return "pie"
        if "trend" in text.lower():
            return "line"
        return "bar"

    def create_chart_spec(self, title: str, data: dict):
        return {
            "title": title,
            "type": self.detect_chart_type(title),
            "data": data
        }