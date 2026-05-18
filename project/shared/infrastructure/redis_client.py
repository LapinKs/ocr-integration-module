"""Redis client configuration and helpers."""
import redis
from typing import Optional
import json
import pickle


_redis_client: Optional[redis.Redis] = None


def create_redis_client(url: str, decode_responses: bool = False) -> redis.Redis:
    """
    Создаёт и возвращает клиент Redis.

    Args:
        url: URL для подключения (redis://host:port/db)
        decode_responses: Декодировать ли ответы в строки

    Returns:
        Настроенный Redis клиент
    """
    global _redis_client
    _redis_client = redis.from_url(url, decode_responses=decode_responses)
    return _redis_client


def get_redis_client() -> redis.Redis:
    """Возвращает глобальный клиент Redis."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call create_redis_client first.")
    return _redis_client


class RedisStateStore:
    """Утилиты для работы с состояниями в Redis."""

    def __init__(self, client: redis.Redis = None, ttl: int = 3600):
        self.client = client or get_redis_client()
        self.ttl = ttl

    def _get_page_key(self, task_id: str, page_index: int) -> str:
        return f"page:{task_id}:{page_index}"

    def _get_formula_key(self, task_id: str, page_index: int, formula_id: int) -> str:
        return f"formula:{task_id}:{page_index}:{formula_id}"

    def save_page_metadata(self, task_id: str, page_index: int, data: dict):
        """Сохраняет метаданные страницы."""
        key = self._get_page_key(task_id, page_index)
        self.client.hset(key, mapping=data)
        self.client.expire(key, self.ttl)

    def load_page_metadata(self, task_id: str, page_index: int) -> Optional[dict]:
        """Загружает метаданные страницы."""
        key = self._get_page_key(task_id, page_index)
        data = self.client.hgetall(key)
        if not data:
            return None
        return {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()}

    def save_formula(self, task_id: str, page_index: int, formula_id: int, data: dict):
        """Сохраняет данные формулы."""
        key = self._get_formula_key(task_id, page_index, formula_id)
        self.client.hset(key, mapping=data)
        self.client.expire(key, self.ttl)

    def load_formula(self, task_id: str, page_index: int, formula_id: int) -> Optional[dict]:
        """Загружает данные формулы."""
        key = self._get_formula_key(task_id, page_index, formula_id)
        data = self.client.hgetall(key)
        if not data:
            return None
        return {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()}

    def update_formula_latex(self, task_id: str, page_index: int, formula_id: int, latex: str):
        """Обновляет LaTeX для формулы."""
        key = self._get_formula_key(task_id, page_index, formula_id)
        self.client.hset(key, "latex", latex)
        self.client.hset(key, "status", "latex_ready")
        self.client.hincrby(self._get_page_key(task_id, page_index), "recognized_count", 1)

    def update_formula_placeholder_path(self, task_id: str, page_index: int,
                                         formula_id: int, path: list):
        """Обновляет путь к плейсхолдеру."""
        key = self._get_formula_key(task_id, page_index, formula_id)
        self.client.hset(key, "placeholder_path", json.dumps(path))
        self.client.hset(key, "status", "placeholder_inserted")

    def update_formula_merged(self, task_id: str, page_index: int, formula_id: int, path: list):
        """Отмечает формулу как вставленную."""
        key = self._get_formula_key(task_id, page_index, formula_id)
        self.client.hset(key, "merged_path", json.dumps(path))
        self.client.hset(key, "status", "merged")
        self.client.hincrby(self._get_page_key(task_id, page_index), "merged_count", 1)

    def clear_task(self, task_id: str):
        """Очищает все данные задачи."""
        patterns = [f"page:{task_id}:*", f"formula:{task_id}:*"]
        for pattern in patterns:
            for key in self.client.scan_iter(match=pattern):
                self.client.delete(key)
