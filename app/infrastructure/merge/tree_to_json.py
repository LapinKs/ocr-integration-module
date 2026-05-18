from typing import Dict, Any
from .domain.page_node import PageNode
from .domain.bbox import BBox

class TreeToJsonConverter:
    @staticmethod
    def convert(node: PageNode) -> Dict[str, Any]:
        result = {
            "@type": TreeToJsonConverter._type_to_string(node.type),
        }
        result["@X"] = str(node.bbox.x1)
        result["@Y"] = str(node.bbox.y1)
        result["@W"] = str(node.bbox.width)
        result["@H"] = str(node.bbox.height)
        for key, value in node.attrs.items():
            if key not in result:
                result[key] = value

        if node.children:
            result["node"] = [TreeToJsonConverter.convert(child) for child in node.children]

        if node.type == "FORMULA" and node.formula_polygon:
            result["contour"] = node.formula_polygon.to_json()
            result["latex"] = node.latex
        return result

    @staticmethod
    def _type_to_string(node_type) -> str:
        mapping = {
            "PAGE": "RIL_PAGE",
            "TEXT_BLOCK": "RIL_TEXT",
            "TEXT_LINE": "RIL_TEXTLINE",
            "WORD": "RIL_WORD",
            "FORMULA": "RIL_FORMULA",
            "PICTURE": "RIL_PICTURE",
            "TABLE": "RIL_TABLE",
            "LIST_ITEM": "RIL_LIST_ITEM",
        }
        return mapping.get(node_type, "RIL_UNKNOWN")
