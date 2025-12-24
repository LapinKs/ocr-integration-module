from domain.text import TextBlock
from domain.bbox import BoundingBox

def parse_ocr_page(page_json: dict) -> list[TextBlock]:
    blocks = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("@type") == "RIL_WORD":
                blocks.append(
                    TextBlock(
                        text=node["#text"],
                        bbox=BoundingBox(
                            x1=int(node["@X"]),
                            y1=int(node["@Y"]),
                            x2=int(node["@X"]) + int(node["@W"]),
                            y2=int(node["@Y"]) + int(node["@H"]),
                        )
                    )
                )
            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(page_json)
    return blocks
