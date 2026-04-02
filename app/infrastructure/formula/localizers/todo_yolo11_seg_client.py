#mask commit
from app.application.ports.formula_localizer import FormulaLocalizer
from ultralytics import YOLO
from PIL import Image
import numpy as np
import cv2
from typing import List, Dict, Any, Tuple
from .todo_mask_utils import mask_to_bbox, mask_to_rle, apply_nms_masks, postprocess_mask

class YOLO11SegClient(FormulaLocalizer):
    """
    Клиент для YOLO11-Seg с поддержкой масок.
    Адаптирован под (скользящее окно, NMS по маскам). не используется на данный момент из за долгого времени работы.
    """

    def __init__(self, model_path: str, device: str = "cpu",
                 window_size: int = 768, conf_threshold: float = 0.25,
                 iou_threshold: float = 0.5, mask_threshold: float = 0.5):
        self.model = YOLO(model_path)
        self.device = device
        self.window_size = window_size
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.mask_threshold = mask_threshold

        self.formula_class_ids = [0, 1]

    def _sliding_windows(self, width: int, height: int) -> List[Tuple[int, int, int, int]]:
        stride = self.window_size // 2
        xs = list(range(0, max(width - self.window_size, 0) + 1, stride))
        ys = list(range(0, max(height - self.window_size, 0) + 1, stride))

        if xs and xs[-1] != width - self.window_size:
            xs.append(max(width - self.window_size, 0))
        if ys and ys[-1] != height - self.window_size:
            ys.append(max(height - self.window_size, 0))

        windows = []
        for y in ys:
            for x in xs:
                windows.append((x, y, x + self.window_size, y + self.window_size))
        return windows

    def _process_sliding_window(self, image: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        h, w = image.shape[:2]
        windows = self._sliding_windows(w, h)

        all_masks = []
        all_scores = []
        all_classes = []
        all_boxes = []

        for x1, y1, x2, y2 in windows:
            win = image[y1:y2, x1:x2]
            if win.shape[0] < self.window_size or win.shape[1] < self.window_size:
                win = cv2.copyMakeBorder(
                    win, 0, self.window_size - win.shape[0],
                    0, self.window_size - win.shape[1],
                    cv2.BORDER_CONSTANT, value=0
                )

            results = self.model(win, conf=self.conf_threshold, iou=self.iou_threshold,
                                device=self.device, verbose=False)

            if results[0].masks is None:
                continue

            masks = results[0].masks.data.cpu().numpy()
            boxes = results[0].boxes.data.cpu().numpy()

            for i, mask in enumerate(masks):
                if mask.shape[0] != self.window_size or mask.shape[1] != self.window_size:
                    mask = cv2.resize(mask, (self.window_size, self.window_size),
                                     interpolation=cv2.INTER_NEAREST)

                y_end = min(h, y1 + self.window_size)
                x_end = min(w, x1 + self.window_size)
                mask_crop = mask[:y_end - y1, :x_end - x1]

                global_mask = np.zeros((h, w), dtype=np.float32)
                global_mask[y1:y_end, x1:x_end] = mask_crop
                all_masks.append(global_mask)

                score = float(boxes[i][4])
                cls = int(boxes[i][5])

                bx1, by1, bx2, by2 = boxes[i][:4]
                bx1_global = max(0, int(x1 + bx1))
                by1_global = max(0, int(y1 + by1))
                bx2_global = min(w, int(x1 + bx2))
                by2_global = min(h, int(y1 + by2))

                all_scores.append(score)
                all_classes.append(cls)
                all_boxes.append([bx1_global, by1_global, bx2_global, by2_global])

        if not all_masks:
            return np.zeros((h, w), dtype=np.uint8), []

        keep = apply_nms_masks(all_masks, all_scores, all_classes, iou_threshold=0.5)

        combined = np.zeros((h, w), np.float32)
        final_detections = []

        for idx in keep:
            combined = np.maximum(combined, all_masks[idx])
            final_detections.append({
                "bbox": all_boxes[idx],
                "class_id": all_classes[idx],
                "class_name": "formula",
                "confidence": all_scores[idx]
            })

        final_mask = (combined > self.mask_threshold).astype(np.uint8)
        final_mask = postprocess_mask(final_mask, close_kernel=3, min_area=100)

        return final_mask, final_detections

    def detect(self, images: List[Image.Image]) -> List[List[Dict[str, Any]]]:
        all_regions = []

        for img in images:
            img_np = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

            final_mask, detections = self._process_sliding_window(img_np)

            regions = []
            for det in detections:
                bbox = det["bbox"]
                x1, y1, x2, y2 = bbox

                regions.append({
                    "bbox": [x1, y1, x2, y2],
                    "mask": mask_to_rle(final_mask),
                    "class_id": det["class_id"],
                    "class_name": det["class_name"],
                    "confidence": det["confidence"]
                })

            all_regions.append(regions)

        return all_regions

    def detect_formulas_batch(self, images: List[Image.Image]) -> List[List[Dict[str, Any]]]:
        all_regions = self.detect(images)
        result = []

        for regions in all_regions:
            formulas = [
                r for r in regions
                if r["class_id"] in self.formula_class_ids
                and r["confidence"] > 0.5
            ]
            result.append(formulas)

        return result
