from app.domain.formula import Formula
from app.domain.geometry import BoundingBox
import numpy as np
import cv2


def yolo_region_to_formula(region: dict, latex: str) -> Formula:

    bbox = BoundingBox(
        x1=int(region["bbox"][0]),
        y1=int(region["bbox"][1]),
        x2=int(region["bbox"][2]),
        y2=int(region["bbox"][3]),
    )

    polygon = region.get("polygon")

    return Formula(
        bbox=bbox,
        polygon=polygon,
        latex=latex,
        confidence=region["confidence"]
    )


def polygon_to_bbox(polygon: list[list[int]]) -> dict:

    pts = np.array(polygon, dtype=np.int32)
    x, y, w, h = cv2.boundingRect(pts)

    return {
        "x1": x,
        "y1": y,
        "x2": x + w,
        "y2": y + h
    }
