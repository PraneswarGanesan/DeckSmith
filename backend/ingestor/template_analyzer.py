from lxml import etree
from typing import List
from ingestor.schemas import TemplateElement


class TemplateAnalyzer:

    def parse_layout(self, xml_content: str) -> List[TemplateElement]:
        root = etree.fromstring(xml_content.encode())
        ns = root.nsmap

        elements = []

        for shape in root.findall(".//p:sp", namespaces=ns):
            try:
                xfrm = shape.find(".//a:xfrm", namespaces=ns)

                off = xfrm.find("a:off", namespaces=ns)
                ext = xfrm.find("a:ext", namespaces=ns)

                elements.append(
                    TemplateElement(
                        type="shape",
                        x=int(off.get("x")),
                        y=int(off.get("y")),
                        width=int(ext.get("cx")),
                        height=int(ext.get("cy")),
                    )
                )
            except Exception:
                continue

        return elements