import cv2
import numpy as np
def word_intersects_polygon(word_bbox: dict, polygon: list[list[int]]) -> bool:

    poly = np.array(polygon, dtype=np.int32)
    px, py, pw, ph = cv2.boundingRect(poly)

    poly_rect = {
        "x1": px,
        "y1": py,
        "x2": px + pw,
        "y2": py + ph,
    }

    return not (
        word_bbox["x2"] <= poly_rect["x1"] or
        word_bbox["x1"] >= poly_rect["x2"] or
        word_bbox["y2"] <= poly_rect["y1"] or
        word_bbox["y1"] >= poly_rect["y2"]
    )

def merge_formulas_into_ocr(ocr: dict, formulas: list[dict]) -> dict:
    page = ocr["node"]
    textlines = page["node"]

    for f in formulas:
        fb = {
            "x1": int(f["bbox"][0]),
            "y1": int(f["bbox"][1]),
            "x2": int(f["bbox"][2]),
            "y2": int(f["bbox"][3]),
        }

        f_center_y = (fb["y1"] + fb["y2"]) / 2

        formula_node = {
            "@type": "RIL_FORMULA",
            "@X": str(fb["x1"]),
            "@Y": str(fb["y1"]),
            "@W": str(fb["x2"] - fb["x1"]),
            "@H": str(fb["y2"] - fb["y1"]),
            "@cnf": str(int(f["confidence"] * 100)),
            "#latex": f["latex"]
        }

        inserted = False

        for line in textlines:
            if line.get("@type") != "RIL_TEXTLINE":
                continue

            line_top = int(line["@Y"])
            line_bottom = line_top + int(line["@H"])

            if not (line_top <= f_center_y <= line_bottom):
                continue

            children = line.get("node", [])
            if isinstance(children, dict):
                children = [children]

            filtered_children = []
            for child in children:
                if child.get("@type") == "RIL_WORD":
                    cb = {
                        "x1": int(child["@X"]),
                        "y1": int(child["@Y"]),
                        "x2": int(child["@X"]) + int(child["@W"]),
                        "y2": int(child["@Y"]) + int(child["@H"]),
                    }

                    if f.get("polygon"):
                        if word_intersects_polygon(cb, f["polygon"]):
                            continue
                    else:
                        if not (
                            cb["x2"] <= fb["x1"] or
                            cb["x1"] >= fb["x2"] or
                            cb["y2"] <= fb["y1"] or
                            cb["y1"] >= fb["y2"]
                        ):
                            continue

                filtered_children.append(child)

            new_children = []
            inserted_here = False

            for child in filtered_children:
                if (
                    not inserted_here
                    and int(child["@X"]) > fb["x1"]
                ):
                    new_children.append(formula_node)
                    inserted_here = True

                new_children.append(child)

            if not inserted_here:
                new_children.append(formula_node)

            new_children.sort(key=lambda x: int(x["@X"]))

            line["node"] = new_children
            inserted = True
            break

        if not inserted:
            textlines.append({
                "@type": "RIL_TEXTLINE",
                "@X": str(fb["x1"]),
                "@Y": str(fb["y1"]),
                "@W": str(fb["x2"] - fb["x1"]),
                "@H": str(fb["y2"] - fb["y1"]),
                "node": [formula_node]
            })

    return ocr
