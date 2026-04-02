from app.infrastructure.merge.domain.page import Page
from app.infrastructure.merge.domain.line import Line
from app.infrastructure.merge.domain.word import Word
from app.infrastructure.merge.domain.bbox import BBox

def normalize_ocr_json(ocr_json: dict) -> dict:

    def normalize_node(node):
        if not isinstance(node, dict):
            return node

        node_type = node.get("@type")


        if node_type == "RIL_TEXTLINE":
            children = node.get("node", [])
            if isinstance(children, dict):
                children = [children]

            if not children:
                return node


            bbox_groups = {}
            for child in children:
                if child.get("@type") == "RIL_WORD":

                    key = f"{child.get('@X')}_{child.get('@Y')}_{child.get('@W')}_{child.get('@H')}"
                    if key not in bbox_groups:
                        bbox_groups[key] = []
                    bbox_groups[key].append(child)


            if len(bbox_groups) == len(children):
                return node


            new_children = []
            for key, group in bbox_groups.items():
                if len(group) == 1:
                    new_children.append(group[0])
                else:

                    merged_text = "".join(w.get("#text", "") for w in group)

                    first = group[0]
                    merged_word = {
                        "@type": "RIL_WORD",
                        "@X": first.get("@X"),
                        "@Y": first.get("@Y"),
                        "@W": first.get("@W"),
                        "@H": first.get("@H"),
                        "#text": merged_text,
                        "@cnf": first.get("@cnf", "0")
                    }
                    new_children.append(merged_word)

            node["node"] = new_children

        for key, value in node.items():
            if isinstance(value, (dict, list)):
                node[key] = normalize_node(value)

        return node

    return normalize_node(ocr_json)


def ocr_json_to_page(ocr_json: dict) -> Page:
    normalized_ocr_json = normalize_ocr_json(ocr_json)

    page_node = normalized_ocr_json["node"]

    lines = []

    def extract_lines(node):
        if not isinstance(node, dict):
            return

        node_type = node.get("@type")

        if node_type == "RIL_TEXTLINE":
            lx = int(node["@X"])
            ly = int(node["@Y"])
            lw = int(node["@W"])
            lh = int(node["@H"])

            words = []

            children = node.get("node", [])
            if isinstance(children, dict):
                children = [children]

            for child in children:
                if child.get("@type") != "RIL_WORD":
                    continue

                x = int(child["@X"])
                y = int(child["@Y"])
                w = int(child["@W"])
                h = int(child["@H"])

                words.append(
                    Word(
                        bbox=BBox(x, y, x + w, y + h),
                        text=child.get("#text", "")
                    )
                )

            lines.append(
                Line(
                    bbox=BBox(lx, ly, lx + lw, ly + lh),
                    words=words,
                    angle=float(node.get("@angle", 0.0))
                )
            )

        children = node.get("node", [])
        if isinstance(children, dict):
            children = [children]

        for child in children:
            extract_lines(child)

    extract_lines(page_node)

    width = int(page_node.get("@W", 1))
    height = int(page_node.get("@H", 1))

    return Page(lines=lines, width=width, height=height)
