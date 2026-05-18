#!/usr/bin/env python3
import sys
import os
import io
import pickle
import json
from pathlib import Path
from typing import List
from celery import Celery

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.infrastructure.redis_client import redis_client
from shared.infrastructure.minio_client import minio_client
from shared.merge.tree_merger import TreeMerger

BUCKET_TREES = "merged-trees"

app = Celery('update', broker=os.environ.get('REDIS_URL', 'redis://redis:6379/0'))

def get_node_by_path(node, path):
    """Находит узел в дереве по пути из индексов"""
    current = node
    for idx in path:
        if idx < len(current.children):
            current = current.children[idx]
        else:
            return None
    return current

@app.task(queue='update', bind=True, max_retries=3)
def update_placeholders(self, task_id: str, page_index: int, formula_ids: List[int]):
    """Обновление плейсхолдеров на реальный LaTeX"""
    try:
        # 1. Получаем путь к дереву из Redis
        tree_path_bytes = redis_client.hget(f"page:{task_id}:{page_index}", "tree_path")
        if not tree_path_bytes:
            # Дерева ещё нет, сохраняем в отдельный set для будущего обновления
            for formula_id in formula_ids:
                redis_client.sadd(f"pending_updates:{task_id}:{page_index}", formula_id)
            return {"status": "tree_not_ready", "pending": len(formula_ids), "saved_to_pending": True}

        tree_path = tree_path_bytes.decode()

        # 2. Загружаем дерево из MinIO
        tree_data = minio_client.get_object(BUCKET_TREES, tree_path)
        tree = pickle.loads(tree_data.read())
        tree_data.close()

        updated_count = 0
        failed_formulas = []

        for formula_id in formula_ids:
            key = f"formula:{task_id}:{page_index}:{formula_id}"

            # Проверяем, не обновлена ли уже формула
            status = redis_client.hget(key, "status")
            if status == b"merged":
                continue

            # Загружаем LaTeX и путь к плейсхолдеру
            latex = redis_client.hget(key, "latex")
            placeholder_path_json = redis_client.hget(key, "placeholder_path")

            if not latex or not placeholder_path_json:
                failed_formulas.append(formula_id)
                continue

            latex_str = latex.decode() if isinstance(latex, bytes) else latex
            placeholder_path = json.loads(placeholder_path_json.decode() if isinstance(placeholder_path_json, bytes) else placeholder_path_json)

            # Находим узел и заменяем плейсхолдер
            node = get_node_by_path(tree, placeholder_path)
            if node:
                node.data['latex'] = latex_str
                node.data['recognition_status'] = 'completed'
                updated_count += 1

                # Обновляем статус в Redis
                redis_client.hset(key, "status", "merged")
                redis_client.hset(key, "merged_at", str(time.time()))
            else:
                failed_formulas.append(formula_id)

        # 3. Сохраняем обновлённое дерево (если были изменения)
        if updated_count > 0:
            # Сортируем дерево перед сохранением
            merger = TreeMerger(use_adaptive_index=True)
            merger._sort_tree(tree)

            tree_bytes = pickle.dumps(tree)
            new_tree_path = f"{task_id}/{page_index}/tree_updated_{int(time.time())}.pkl"
            minio_client.put_object(
                BUCKET_TREES,
                new_tree_path,
                io.BytesIO(tree_bytes),
                len(tree_bytes)
            )
            redis_client.hset(f"page:{task_id}:{page_index}", "tree_path", new_tree_path)

        # 4. Проверяем, все ли формулы готовы
        total = int(redis_client.hget(f"page:{task_id}:{page_index}", "total_formulas") or 0)
        pattern = f"formula:{task_id}:{page_index}:*"
        keys = redis_client.keys(pattern)
        merged_count = 0
        for key in keys:
            if redis_client.hget(key, "status") == b"merged":
                merged_count += 1

        if merged_count >= total and total > 0:
            redis_client.hset(f"page:{task_id}:{page_index}", "status", "completed")
            # Триггерим PDF генерацию
            from services.pdf.worker import generate_pdf
            generate_pdf.delay(task_id, page_index)

        return {
            "task_id": task_id,
            "page_index": page_index,
            "updated": updated_count,
            "failed": failed_formulas
        }

    except Exception as e:
        # Повторяем задачу при ошибке
        raise self.retry(exc=e, countdown=10, max_retries=3)


@app.task(queue='update')
def process_pending_updates(task_id: str, page_index: int):
    """Обрабатывает все отложенные обновления для страницы (когда дерево готово)"""
    pending_key = f"pending_updates:{task_id}:{page_index}"
    formula_ids = list(redis_client.smembers(pending_key))

    if not formula_ids:
        return {"status": "no_pending"}

    # Преобразуем байты в int
    formula_ids = [int(fid) for fid in formula_ids]

    # Выполняем обновление
    result = update_placeholders(task_id, page_index, formula_ids)

    # Очищаем pending set
    redis_client.delete(pending_key)

    return result
