import json
from domain.item import DocumentItem
from domain.text import TextBlock
from domain.formula import Formula
from xml.etree.ElementTree import Element, SubElement, tostring
from domain.text import TextBlock
from domain.formula import Formula

class Serializer:

    def to_xml(self, items):
        root = Element("document")

        for item in items:
            if isinstance(item, TextBlock):
                el = SubElement(root, "text")
                el.set("x1", str(item.bbox.x1))
                el.set("y1", str(item.bbox.y1))
                el.set("x2", str(item.bbox.x2))
                el.set("y2", str(item.bbox.y2))
                el.text = item.text

            elif isinstance(item, Formula):
                el = SubElement(root, "formula")
                el.set("x1", str(item.bbox.x1))
                el.set("y1", str(item.bbox.y1))
                el.set("x2", str(item.bbox.x2))
                el.set("y2", str(item.bbox.y2))
                el.text = item.latex

        return tostring(root, encoding="unicode")


    def to_json(self, items: list[DocumentItem]) -> str:
        data = []

        for item in items:
            if isinstance(item, TextBlock):
                data.append({
                    "type": "text",
                    "text": item.text,
                    "bbox": [item.bbox.x1, item.bbox.y1, item.bbox.x2, item.bbox.y2],
                })

            elif isinstance(item, Formula):
                data.append({
                    "type": "formula",
                    "latex": item.latex,
                    "bbox": [item.bbox.x1, item.bbox.y1, item.bbox.x2, item.bbox.y2],
                })

        return json.dumps(data, ensure_ascii=False, indent=2)
