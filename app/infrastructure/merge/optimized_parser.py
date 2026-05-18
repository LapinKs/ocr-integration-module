from typing import Tuple, List
from .domain.node import Node
from .domain.bbox import BBox


class OptimizedPageParser:
    VERTICAL_CONTAINERS = {
        "RIL_PAGE", "RIL_PAGE_HEADER", "RIL_PAGE_FOOTER",
        "RIL_TEXT", "RIL_LIST_ITEM", "RIL_SECTION_HEADER"
    }
    # HORIZONTAL_CONTAINERS = {"RIL_TEXTLINE"}
    @staticmethod
    def parse(json_data: dict) -> Tuple[Node, int, int]:
        page_node = json_data.get("node", {})
        width = int(page_node.get("@W", 0))
        height = int(page_node.get("@H", 0))

        root = OptimizedPageParser._parse_node(page_node, None)
        OptimizedPageParser._sort_tree(root)

        return root, width, height

    @staticmethod
    def _parse_node(node_json: dict, parent: Node = None) -> Node:
        node_type = node_json.get("@type", "UNKNOWN")
        bbox = OptimizedPageParser._parse_bbox(node_json)
        node = Node(
            type=node_type,
            bbox=bbox,
            parent=parent,
            data=dict(node_json)
        )
        children = node_json.get("node", [])
        if isinstance(children, dict):
            children = [children]
        for child_json in children:
            child_node = OptimizedPageParser._parse_node(child_json, node)
            node.children.append(child_node)
        return node

    @staticmethod
    def _parse_bbox(node_json: dict) -> BBox:
        x = int(node_json.get("@X", 0))
        y = int(node_json.get("@Y", 0))
        w = int(node_json.get("@W", 0))
        h = int(node_json.get("@H", 0))
        return BBox(x, y, x + w, y + h)

    @staticmethod
    def _sort_tree(node: Node):
        if not node.children:
            return

        if node.type in OptimizedPageParser.VERTICAL_CONTAINERS:
            node.children.sort(key=lambda n: n.bbox.y1)

        # elif node.type in OptimizedPageParser.HORIZONTAL_CONTAINERS:
        #     node.children.sort(key=lambda n: n.bbox.x1)

        for child in node.children:
            OptimizedPageParser._sort_tree(child)
