import os
import sys
import cv2
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
import asyncio
from dataclasses import dataclass

try:
    from GeoSeg.geoseg.models.UNetFormer import UNetFormer
except ImportError:
    pass

def limit_threads(num_threads: int = 2):
    torch.set_num_threads(num_threads)
    cv2.setNumThreads(num_threads)
    try:
        import mkl
        mkl.set_num_threads(num_threads)
    except ImportError:
        pass
    print(f"[THREADS] Ограничено до {num_threads} потоков CPU (threads)")

class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)

limit_threads(8)

@dataclass
class UNetFormerConfig:
    tile_size: int = 640
    infer_overlap: float = 0.25
    infer_sw_batch_size: int = 6
    infer_force_tiled: bool = True
    infer_gaussian_sigma_scale: float = 0.125
    use_tta: bool = False
    postprocess_threshold: float = 0.45
    post_min_area: int = 2
    post_max_hole_area: int = 0
    post_morph_close_ksize: int = 3
    post_morph_open_ksize: int = 0
    post_dilate_ksize: int = 0
    post_empty_fallback: bool = True
    post_empty_fallback_trigger: float = 0.18
    post_empty_fallback_min_threshold: float = 0.16
    post_empty_fallback_relative_to_max: float = 0.75
    post_empty_fallback_seed_delta: float = 0.08
    norm_mean: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    norm_std: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    device: str = "cuda"
    use_amp: bool = True
    cpu_threads: int = 4

class FinetunedUNetFormer:
    def __init__(self,
                 model_path: Union[str, Path],
                 config: UNetFormerConfig = None,
                 backbone_name: str = "timm_efficientnet_b5",
                 num_classes: int = 2):
        self.config = config or UNetFormerConfig()
        self.device = torch.device(self.config.device if torch.cuda.is_available() else "cpu")
        self.backbone_name = backbone_name
        self.num_classes = num_classes

        if self.device.type == "cpu":
            torch.set_num_threads(self.config.cpu_threads)
            cv2.setNumThreads(self.config.cpu_threads)
            print(f"[UNetFormer] CPU режим: {self.config.cpu_threads} потоков")
        else:
            print(f"[UNetFormer] GPU режим: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA'}")

        print(f"[UNetFormer] Загрузка модели из {model_path}")
        self.model = self._build_model()
        self._load_weights(model_path)
        self.model = self.model.to(self.device)
        self.model.eval()
        self._weight_cache = {}
        print(f"[UNetFormer] Модель загружена на {self.device}")

    def _build_model(self):
        try:
            import sys
            from pathlib import Path
            geoseg_path = Path(__file__).parent.parent.parent.parent / "GeoSeg"
            if geoseg_path.exists() and str(geoseg_path) not in sys.path:
                sys.path.insert(0, str(geoseg_path))
            from GeoSeg.geoseg.models.UNetFormer import UNetFormer
            model = UNetFormer(
                num_classes=self.num_classes,
                backbone_name=self.backbone_name,
                pretrained=False
            )
            print(f"[UNetFormer] Используется GeoSeg модель с энкодером {self.backbone_name}")
            return model
        except ImportError as e:
            print(f"[UNetFormer] GeoSeg не найден: {e}")

        import segmentation_models_pytorch as smp
        encoder_mapping = {
            "tf_efficientnet_b0": "timm-efficientnet-b0",
            "tf_efficientnet_b1": "timm-efficientnet-b1",
            "tf_efficientnet_b2": "timm-efficientnet-b2",
            "tf_efficientnet_b3": "timm-efficientnet-b3",
            "tf_efficientnet_b4": "timm-efficientnet-b4",
            "tf_efficientnet_b5": "timm-efficientnet-b5",
            "tf_efficientnet_b6": "timm-efficientnet-b6",
            "tf_efficientnet_b7": "timm-efficientnet-b7",
        }
        encoder_name_smp = encoder_mapping.get(self.backbone_name, self.backbone_name)
        model = smp.Unet(
            encoder_name=encoder_name_smp,
            encoder_weights=None,
            in_channels=3,
            classes=self.num_classes,
        )
        print(f"[UNetFormer] Используется smp.Unet с энкодером {encoder_name_smp}")
        return model

    def _patch_attention_padding(self, model):
        import torch.nn.functional as F
        for m in model.modules():
            if hasattr(m, "pad") and hasattr(m, "ws"):
                def patched(self, x, ps):
                    _, _, H, W = x.size()
                    pad_h, pad_w = (ps - H % ps) % ps, (ps - W % ps) % ps
                    if pad_h > 0 or pad_w > 0:
                        x = F.pad(x, (0, pad_w, 0, pad_h), mode='constant', value=0)
                    return x
                m.pad = patched.__get__(m, m.__class__)

    def _load_weights(self, model_path: Union[str, Path]):
        state_dict = torch.load(str(model_path), map_location="cpu")
        cleaned = {}
        for k, v in state_dict.items():
            nk = k
            if nk.startswith("module."):
                nk = nk[len("module."):]
            if nk.startswith("_orig_mod."):
                nk = nk[len("_orig_mod."):]
            cleaned[nk] = v
        self.model.load_state_dict(cleaned, strict=True)

    def _normalize(self, img: np.ndarray) -> torch.Tensor:
        x = img.astype(np.float32) / 255.0
        mean = np.array(self.config.norm_mean).reshape(1, 1, 3)
        std = np.array(self.config.norm_std).reshape(1, 1, 3)
        x = (x - mean) / std
        return torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))).float()

    def _crop_with_pad(self, arr: np.ndarray, x: int, y: int, tile_size: int, pad_value: int):
        h, w = arr.shape[:2]
        x2, y2 = min(x + tile_size, w), min(y + tile_size, h)
        crop = arr[y:y2, x:x2]
        vh, vw = y2 - y, x2 - x
        if arr.ndim == 3:
            out = np.full((tile_size, tile_size, arr.shape[2]), pad_value, dtype=arr.dtype)
        else:
            out = np.full((tile_size, tile_size), pad_value, dtype=arr.dtype)
        out[:vh, :vw] = crop
        return out, vh, vw

    def _sliding_positions(self, length: int, tile_size: int, overlap: float) -> List[int]:
        if length <= tile_size:
            return [0]
        stride = max(1, int(round(tile_size * (1 - overlap))))
        stride = min(stride, tile_size)
        positions = list(range(0, max(length - tile_size, 0) + 1, stride))
        if positions[-1] != length - tile_size:
            positions.append(length - tile_size)
        return positions

    def _get_weight_map(self, tile_size: int, sigma_scale: float) -> np.ndarray:
        key = (tile_size, sigma_scale)
        if key in self._weight_cache:
            return self._weight_cache[key]
        coords = np.arange(tile_size, dtype=np.float32)
        center = (tile_size - 1) / 2
        sigma = max(tile_size * sigma_scale, 1.0)
        g = np.exp(-0.5 * ((coords - center) / sigma) ** 2).astype(np.float32)
        w = np.outer(g, g).astype(np.float32)
        w /= max(float(w.max()), 1e-6)
        w = np.maximum(w, 1e-3)
        self._weight_cache[key] = w
        return w

    def _kernel(self, size: int):
        return None if size <= 1 else cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))

    def _fill_small_holes(self, mask: np.ndarray, max_area: int) -> np.ndarray:
        if max_area <= 0:
            return mask
        inv = (mask == 0).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(inv, 8)
        out = mask.copy()
        h, w = mask.shape
        for i in range(1, n):
            x, y, ww, hh, area = stats[i]
            if not (x == 0 or y == 0 or x + ww >= w or y + hh >= h) and area <= max_area:
                out[labels == i] = 1
        return out

    def _remove_small_components(self, mask: np.ndarray, min_area: int) -> np.ndarray:
        if min_area <= 1:
            return mask
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        out = np.zeros_like(mask, dtype=np.uint8)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= min_area:
                out[labels == i] = 1
        return out

    def _seeded_hysteresis_mask(self, prob: np.ndarray, low_thr: float, high_thr: float) -> np.ndarray:
        low = (prob >= low_thr).astype(np.uint8)
        high = (prob >= high_thr).astype(np.uint8)
        if low.sum() == 0 or high.sum() == 0:
            return low
        n, labels, stats, _ = cv2.connectedComponentsWithStats(low, 8)
        keep = set(np.unique(labels[high > 0]).tolist()) - {0}
        out = np.zeros_like(low, dtype=np.uint8)
        for lbl in keep:
            if int(stats[int(lbl), cv2.CC_STAT_AREA]) > 0:
                out[labels == lbl] = 1
        return out

    def _postprocess(self, prob: np.ndarray) -> np.ndarray:
        cfg = self.config
        prob = np.nan_to_num(prob, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)
        prob = np.clip(prob, 0, 1)
        semantic = (prob >= cfg.postprocess_threshold).astype(np.uint8)
        if semantic.sum() == 0 and cfg.post_empty_fallback:
            maxp = float(prob.max())
            if maxp >= cfg.post_empty_fallback_trigger:
                low_thr = max(
                    cfg.post_empty_fallback_min_threshold,
                    min(cfg.postprocess_threshold - 1e-6, maxp * cfg.post_empty_fallback_relative_to_max)
                )
                high_thr = min(
                    cfg.postprocess_threshold,
                    max(low_thr + cfg.post_empty_fallback_seed_delta, maxp - 1e-6)
                )
                high_thr = max(low_thr, high_thr)
                semantic = self._seeded_hysteresis_mask(prob, low_thr, high_thr)
        for kname in ["post_morph_close_ksize", "post_dilate_ksize", "post_morph_open_ksize"]:
            ksize = getattr(cfg, kname)
            k = self._kernel(ksize)
            if k is not None and semantic.sum() > 0:
                if "close" in kname:
                    semantic = cv2.morphologyEx(semantic, cv2.MORPH_CLOSE, k)
                elif "dilate" in kname:
                    semantic = cv2.dilate(semantic, k, iterations=1)
                elif "open" in kname:
                    semantic = cv2.morphologyEx(semantic, cv2.MORPH_OPEN, k)
        semantic = self._fill_small_holes(semantic, cfg.post_max_hole_area)
        semantic = self._remove_small_components(semantic, cfg.post_min_area)
        return semantic.astype(np.uint8)

    @torch.inference_mode()
    def _predict_logits(self, imgs: torch.Tensor) -> torch.Tensor:
        if self.config.use_amp and self.device.type == "cuda":
            with torch.autocast(device_type="cuda"):
                out = self.model(imgs)
        else:
            out = self.model(imgs)
        logits = out[0] if isinstance(out, (tuple, list)) else out
        if self.config.use_tta:
            xf = torch.flip(imgs, dims=[3])
            outf = self.model(xf)
            logits_f = outf[0] if isinstance(outf, (tuple, list)) else outf
            logits = 0.5 * (logits + torch.flip(logits_f, dims=[3]))
        return logits

    @torch.inference_mode()
    def _infer_probability(self, img: np.ndarray) -> np.ndarray:
        work = img.copy()
        h, w = work.shape[:2]
        tile_size = self.config.tile_size
        if (not self.config.infer_force_tiled) and h <= tile_size and w <= tile_size:
            tile, vh, vw = self._crop_with_pad(work, 0, 0, tile_size, 255)
            x = self._normalize(tile).unsqueeze(0).to(self.device)
            logits = self._predict_logits(x)
            prob = torch.softmax(logits, dim=1)[0, 1].cpu().numpy()[:vh, :vw]
            return np.clip(prob.astype(np.float32), 0, 1)
        xs = self._sliding_positions(w, tile_size, self.config.infer_overlap)
        ys = self._sliding_positions(h, tile_size, self.config.infer_overlap)
        weight = self._get_weight_map(tile_size, self.config.infer_gaussian_sigma_scale)
        prob_sum = np.zeros((h, w), dtype=np.float32)
        weight_sum = np.zeros((h, w), dtype=np.float32)
        batch_tensors = []
        batch_meta = []
        def flush():
            if not batch_tensors:
                return
            batch = torch.stack(batch_tensors).to(self.device)
            logits = self._predict_logits(batch)
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            for i, (x0, y0, vh, vw) in enumerate(batch_meta):
                p = np.nan_to_num(probs[i], nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)[:vh, :vw]
                w_local = weight[:vh, :vw]
                prob_sum[y0:y0+vh, x0:x0+vw] += p * w_local
                weight_sum[y0:y0+vh, x0:x0+vw] += w_local
            batch_tensors.clear()
            batch_meta.clear()
        for y0 in ys:
            for x0 in xs:
                tile, vh, vw = self._crop_with_pad(work, x0, y0, tile_size, 255)
                batch_tensors.append(self._normalize(tile))
                batch_meta.append((x0, y0, vh, vw))
                if len(batch_tensors) >= self.config.infer_sw_batch_size:
                    flush()
        flush()
        prob = prob_sum / np.maximum(weight_sum, 1e-6)
        return np.clip(prob.astype(np.float32), 0, 1)

    def predict_mask(self, image: np.ndarray) -> np.ndarray:
        prob = self._infer_probability(image)
        mask = self._postprocess(prob)
        return mask

    def predict_probability(self, image: np.ndarray) -> np.ndarray:
        return self._infer_probability(image)

    def extract_formula_regions(self, image: np.ndarray, margin: int = 10,
                                merge_distance: int = 30,
                                horizontal_gap: int = 40,
                                vertical_overlap: int = 5,
                                min_formula_area: int = 50,
                                use_dsu: bool = True) -> List[Dict]:
        mask = self.predict_mask(image)
        prob = self._infer_probability(image)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        components = []
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < min_formula_area:
                continue
            comp_mask = np.zeros_like(mask, dtype=np.uint8)
            cv2.drawContours(comp_mask, [contour], -1, 1, -1)
            components.append({
                'id': i,
                'bbox': (x, y, x + w, y + h),
                'center': (x + w // 2, y + h // 2),
                'mask': comp_mask,
                'area': area,
                'contour': contour
            })
        if not components:
            return []
        if use_dsu and len(components) > 1:
            n = len(components)
            dsu = DSU(n)
            components.sort(key=lambda c: c['bbox'][1])
            window_size = min(15, n)
            for i in range(n):
                for j in range(i + 1, min(i + window_size, n)):
                    if self._should_merge(components[i], components[j]):
                        dsu.union(i, j)
            clusters = {}
            for i in range(n):
                root = dsu.find(i)
                clusters.setdefault(root, []).append(components[i])
            formulas = self._build_formulas_from_clusters(clusters, image, prob, mask, margin)
        else:
            formulas = self._build_formulas_legacy(components, image, prob, mask, margin, merge_distance)
        formulas.sort(key=lambda f: (f['bbox'][1], f['bbox'][0]))
        return formulas

    def _should_merge(self, comp1: Dict, comp2: Dict) -> bool:
        b1 = comp1['bbox']
        b2 = comp2['bbox']
        dx, dy = self._normalized_distance(b1, b2)
        if dx < 1.5 and self._y_aligned(b1, b2):
            return True
        if self._masks_touch(comp1['mask'], comp2['mask']):
            return True
        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        overlap = self._bbox_overlap(b1, b2)
        if overlap > 0 and overlap / min(area1, area2) > 0.1:
            return True
        return False

    def _normalized_distance(self, b1: Tuple, b2: Tuple) -> Tuple[float, float]:
        cx1 = (b1[0] + b1[2]) / 2
        cy1 = (b1[1] + b1[3]) / 2
        cx2 = (b2[0] + b2[2]) / 2
        cy2 = (b2[1] + b2[3]) / 2
        dx = abs(cx1 - cx2)
        dy = abs(cy1 - cy2)
        scale = max(b1[2] - b1[0], b2[2] - b2[0], 1)
        return dx / scale, dy / scale

    def _y_aligned(self, b1: Tuple, b2: Tuple, threshold: float = 0.3) -> bool:
        y1_mid = (b1[1] + b1[3]) / 2
        y2_mid = (b2[1] + b2[3]) / 2
        h = max(b1[3] - b1[1], b2[3] - b2[1])
        return abs(y1_mid - y2_mid) < threshold * h

    def _masks_touch(self, mask1: np.ndarray, mask2: np.ndarray, dilation: int = 5) -> bool:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (dilation, dilation))
        m1 = cv2.dilate(mask1, kernel)
        overlap = np.logical_and(m1 > 0, mask2 > 0)
        return overlap.sum() > 0

    def _bbox_overlap(self, b1: Tuple, b2: Tuple) -> float:
        x1 = max(b1[0], b2[0])
        y1 = max(b1[1], b2[1])
        x2 = min(b1[2], b2[2])
        y2 = min(b1[3], b2[3])
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _build_formulas_from_clusters(self, clusters: dict, image: np.ndarray,
                                    prob: np.ndarray, full_mask: np.ndarray,
                                    margin: int) -> List[Dict]:
        formulas = []
        for cluster_idx, comps in enumerate(clusters.values()):
            combined_mask = np.zeros_like(full_mask, dtype=np.uint8)
            for comp in comps:
                combined_mask = np.maximum(combined_mask, comp['mask'])
            ys, xs = np.where(combined_mask > 0)
            if len(xs) == 0:
                continue
            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
            x1 = max(0, x1 - margin)
            y1 = max(0, y1 - margin)
            x2 = min(image.shape[1], x2 + margin)
            y2 = min(image.shape[0], y2 + margin)
            formula_mask = combined_mask[y1:y2, x1:x2].copy()
            if formula_mask.sum() == 0:
                continue
            prob_crop = prob[y1:y2, x1:x2]
            area_mask = formula_mask > 0
            confidence = float(prob_crop[area_mask].mean()) if area_mask.sum() > 0 else 0.0
            formulas.append({
                'id': cluster_idx,
                'bbox': (x1, y1, x2, y2),
                'mask': formula_mask,
                'confidence': confidence,
                'area': (x2 - x1) * (y2 - y1),
                'num_components': len(comps)
            })
        return formulas

    def _build_formulas_legacy(self, components: List[Dict], image: np.ndarray,
                                prob: np.ndarray, full_mask: np.ndarray,
                                margin: int, merge_distance: int) -> List[Dict]:
        remaining = components.copy()
        remaining.sort(key=lambda c: c['bbox'][1])
        groups = []
        used = [False] * len(remaining)
        for i in range(len(remaining)):
            if used[i]:
                continue
            group = [remaining[i]]
            used[i] = True
            for j in range(len(remaining)):
                if used[j]:
                    continue
                cx1, cy1 = group[0]['center']
                cx2, cy2 = remaining[j]['center']
                distance = np.sqrt((cx1 - cx2)**2 + (cy1 - cy2)**2)
                y1_min, y1_max = group[0]['bbox'][1], group[0]['bbox'][3]
                y2_min, y2_max = remaining[j]['bbox'][1], remaining[j]['bbox'][3]
                y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
                if distance < merge_distance or y_overlap > 5:
                    group.append(remaining[j])
                    used[j] = True
                    all_bboxes = [c['bbox'] for c in group]
                    x1 = min(b[0] for b in all_bboxes)
                    y1 = min(b[1] for b in all_bboxes)
                    x2 = max(b[2] for b in all_bboxes)
                    y2 = max(b[3] for b in all_bboxes)
                    group[0]['bbox'] = (x1, y1, x2, y2)
                    group[0]['center'] = ((x1 + x2) // 2, (y1 + y2) // 2)
            groups.append(group)
        formulas = []
        for group_idx, group in enumerate(groups):
            x1, y1, x2, y2 = group[0]['bbox']
            combined_mask = np.zeros_like(full_mask, dtype=np.uint8)
            for comp in group:
                combined_mask = np.maximum(combined_mask, comp['mask'])
            x1 = max(0, x1 - margin)
            y1 = max(0, y1 - margin)
            x2 = min(image.shape[1], x2 + margin)
            y2 = min(image.shape[0], y2 + margin)
            formula_mask = combined_mask[y1:y2, x1:x2].copy()
            if formula_mask.sum() == 0:
                continue
            prob_crop = prob[y1:y2, x1:x2]
            area_mask = formula_mask > 0
            confidence = float(prob_crop[area_mask].mean()) if area_mask.sum() > 0 else 0.0
            formulas.append({
                'id': group_idx,
                'bbox': (x1, y1, x2, y2),
                'mask': formula_mask,
                'confidence': confidence,
                'area': (x2 - x1) * (y2 - y1),
                'num_components': len(group)
            })
        return formulas

    async def detect_formulas_batch(self, images: List[np.ndarray]) -> List[List[Dict]]:
        loop = asyncio.get_event_loop()
        async def process_one(img):
            return await loop.run_in_executor(None, self.extract_formula_regions, img)
        tasks = [process_one(img) for img in images]
        return await asyncio.gather(*tasks)

    def extract_formulas_for_recognition(self, image: np.ndarray, margin: int = 10) -> List[Dict]:
        mask = self.predict_mask(image)
        prob = self._infer_probability(image)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        formulas = []
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(image.shape[1], x + w + margin)
            y2 = min(image.shape[0], y + h + margin)
            formula_mask = np.zeros_like(mask, dtype=np.uint8)
            cv2.drawContours(formula_mask, [contour], -1, 1, -1)
            if formula_mask.sum() == 0:
                continue
            area_mask = formula_mask > 0
            confidence = float(prob[area_mask].mean()) if area_mask.sum() > 0 else 0.0
            formulas.append({
                'id': i,
                'bbox': (x1, y1, x2, y2),
                'mask': formula_mask,
                'confidence': confidence,
                'area': int(w * h)
            })
        formulas.sort(key=lambda f: (f['bbox'][1], f['bbox'][0]))
        return formulas

    def prepare_crop_for_recognition(self, image: np.ndarray, formula: Dict,
                                      background_color: Tuple[int, int, int] = (255, 255, 255)) -> np.ndarray:
        x1, y1, x2, y2 = formula['bbox']
        mask = formula['mask']
        crop = image[y1:y2, x1:x2].copy()
        crop_mask = mask[y1:y2, x1:x2]
        if background_color is not None:
            for c in range(3):
                crop[:, :, c][crop_mask == 0] = background_color[c]
        return crop

    async def process_batch_for_recognition(self, images: List[np.ndarray],
                                             margin: int = 10) -> List[List[Dict]]:
        loop = asyncio.get_event_loop()
        async def process_one(img):
            return await loop.run_in_executor(None, self.extract_formulas_for_recognition, img, margin)
        tasks = [process_one(img) for img in images]
        return await asyncio.gather(*tasks)

    def prepare_for_recognition(self, image: np.ndarray, margin: int = 10,
                                merge_distance: int = 30) -> List[Dict]:
        formulas = self.extract_formula_regions(image, margin, merge_distance)
        prepared = []
        for f in formulas:
            x1, y1, x2, y2 = f['bbox']
            mask = f['mask']
            crop = image[y1:y2, x1:x2].copy()
            for c in range(3):
                crop[:, :, c][mask == 0] = 255
            prepared.append({
                'id': f['id'],
                'bbox': f['bbox'],
                'crop': crop,
                'mask': mask,
                'confidence': f['confidence'],
                'area': f['area'],
                'num_components': f['num_components'] if 'num_components' in f else 1
            })
        return prepared
