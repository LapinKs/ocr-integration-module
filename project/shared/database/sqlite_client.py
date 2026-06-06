import sqlite3
import json
import asyncio
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List


class SQLiteClient:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.environ.get('SQLITE_DB_PATH', '/app/data/tasks.db')
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()


    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    total_pages INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    result_pdf_path TEXT,
                    result_json_path TEXT
                )
            """)
            conn.commit()
            print(f"[SQLite] Database initialized at {self.db_path}")


    async def create_task(self, task_id: str, total_pages: int) -> str:
        def _create():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO tasks (task_id, total_pages) VALUES (?, ?)",
                    (task_id, total_pages)
                )
                conn.commit()
        await asyncio.to_thread(_create)
        return task_id


    async def update_task_result(self, task_id: str, pdf_path: str, json_path: str):
        def _update():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE tasks SET completed_at = ?, result_pdf_path = ?, result_json_path = ? WHERE task_id = ?",
                    (datetime.now().isoformat(), pdf_path, json_path, task_id)
                )
                conn.commit()
        await asyncio.to_thread(_update)


    async def get_task(self, task_id: str) -> Optional[Dict]:
        def _get():
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        return await asyncio.to_thread(_get)


_sqlite_client = None


def get_sqlite_client() -> SQLiteClient:
    global _sqlite_client
    if _sqlite_client is None:
        _sqlite_client = SQLiteClient()
    return _sqlite_client
