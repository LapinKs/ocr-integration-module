#!/usr/bin/env python3
import sys
import os
import pickle
import json
from pathlib import Path
from typing import List, Dict
from celery import Celery
import io
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import redis_client
from shared.infrastructure.minio_client import minio_client
from shared.merge.optimized_parser import OptimizedPageParser
from shared.merge.smart_mergerv2 import SpatialIndex,TreeMerger,FormulaNodeBuilder

BUCKET_OCR = "ocr-results"
BUCKET_TREES = "merged-trees"
BUCKET_MASKS = "formula-masks"

app = Celery('merge', broker=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

def get_node_path(node, target_node, current_path=None):
    if current_path is None:
        current_path = []
    if node is target_node:
        return current_path
    for i, child in enumerate(node.children):
        result = get_node_path(child, target_node, current_path + [i])
        if result:
            return result
    return None

@app.task(queue='merge')
def merge_with_placeholders(task_id: str, page_index: int):
    """Создание дерева с плейсхолдерами"""
    try:
        # Проверяем, не выполнен ли уже мердж
        status = redis_client.hget(f"page:{task_id}:{page_index}", "status")
        if status == b"merged":
            return {"status": "already_merged"}

        # Загружаем OCR JSON из MinIO
        ocr_path = f"{task_id}/{page_index}/ocr.json"
        ocr_data = minio_client.get_object(BUCKET_OCR, ocr_path)
        ocr_json = json.loads(ocr_data.read())

        # Парсим в дерево
        parser = OptimizedPageParser()
        tree, width, height = parser.parse(ocr_json)

        # Загружаем все формулы страницы
        pattern = f"formula:{task_id}:{page_index}:*"
        keys = redis_client.keys(pattern)

        formulas_data = []
        for key in keys:
            formula_id = int(key.decode().split(':')[-1])
            bbox = (
                int(redis_client.hget(key, "bbox_x1")),
                int(redis_client.hget(key, "bbox_y1")),
                int(redis_client.hget(key, "bbox_x2")),
                int(redis_client.hget(key, "bbox_y2"))
            )
            latex = redis_client.hget(key, "latex")
            status = redis_client.hget(key, "status")

            formulas_data.append({
                "id": formula_id,
                "bbox": bbox,
                "latex": latex.decode() if latex else None,
                "status": status.decode() if status else "segmented"
            })

        formulas_data.sort(key=lambda f: f["id"])

        # MERGE с плейсхолдерами
        merger = TreeMerger(use_adaptive_index=True)

        for f in formulas_data:
            mask_path = redis_client.hget(f"formula:{task_id}:{page_index}:{f['id']}", "mask_path")
            mask = None
            if mask_path:
                mask_data = minio_client.get_object(BUCKET_MASKS, mask_path.decode())
                import numpy as np
                mask = np.load(mask_data)

            if f["latex"]:
                formula_node = FormulaNodeBuilder.create_node(
                    f["id"], f["bbox"], latex=f["latex"], recognition_status="completed"
                )
            else:
                placeholder_latex = f"[FORMULA_{f['id']}_PENDING]"
                formula_node = FormulaNodeBuilder.create_node(
                    f["id"], f["bbox"], latex=placeholder_latex, recognition_status="pending"
                )

            merger._merge_one_formula(tree, formula_node, mask, use_mask=True)

            if not f["latex"]:
                path = get_node_path(tree, formula_node)
                if path:
                    redis_client.hset(f"formula:{task_id}:{page_index}:{f['id']}",
                                     "placeholder_path", json.dumps(path))

        merger._sort_tree(tree)

        # Сохраняем дерево
        tree_bytes = pickle.dumps(tree)
        tree_path = f"{task_id}/{page_index}/tree_with_placeholders.pkl"
        minio_client.put_object(BUCKET_TREES, tree_path, io.BytesIO(tree_bytes), len(tree_bytes))

        redis_client.hset(f"page:{task_id}:{page_index}", "tree_path", tree_path)
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "merged")

        # Триггерим UPDATE для уже готовых формул
        ready_formulas = [f["id"] for f in formulas_data if f["latex"]]
        if ready_formulas:
            from services.update.worker import update_placeholders
            update_placeholders.delay(task_id, page_index, ready_formulas)

        return {"task_id": task_id, "page_index": page_index, "formulas": len(formulas_data)}

    except Exception as e:
        redis_client.hset(f"page:{task_id}:{page_index}", "status", "merge_failed")
        raise e
