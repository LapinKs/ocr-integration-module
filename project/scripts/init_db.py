#!/usr/bin/env python3
"""
Скрипт для инициализации PostgreSQL базы данных.
Создаёт необходимые таблицы для отслеживания задач.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Конфигурация БД
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/formula_ocr')

# SQL для создания таблиц
CREATE_TABLES_SQL = """
-- Таблица задач
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(64) UNIQUE NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    total_pages INTEGER NOT NULL,
    pages_processed INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Таблица страниц
CREATE TABLE IF NOT EXISTS pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(64) NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    page_index INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    width INTEGER,
    height INTEGER,
    total_formulas INTEGER DEFAULT 0,
    recognized_count INTEGER DEFAULT 0,
    merged_count INTEGER DEFAULT 0,
    ocr_path TEXT,
    tree_path TEXT,
    pdf_path TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE(task_id, page_index)
);

-- Таблица формул (опционально, для детального анализа)
CREATE TABLE IF NOT EXISTS formulas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id VARCHAR(64) NOT NULL,
    page_index INTEGER NOT NULL,
    formula_id INTEGER NOT NULL,
    bbox JSONB,
    status VARCHAR(32),
    latex TEXT,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (task_id, page_index) REFERENCES pages(task_id, page_index) ON DELETE CASCADE,
    UNIQUE(task_id, page_index, formula_id)
);

-- Индексы для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks(task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_pages_task_id ON pages(task_id);
CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(status);
CREATE INDEX IF NOT EXISTS idx_formulas_task_page ON formulas(task_id, page_index);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для tasks
DROP TRIGGER IF EXISTS update_tasks_updated_at ON tasks;
CREATE TRIGGER update_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Представление для мониторинга
CREATE OR REPLACE VIEW task_progress AS
SELECT
    t.task_id,
    t.status as task_status,
    t.total_pages,
    COUNT(p.id) as pages_total,
    SUM(CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END) as pages_completed,
    SUM(CASE WHEN p.status = 'failed' THEN 1 ELSE 0 END) as pages_failed,
    SUM(p.total_formulas) as total_formulas,
    SUM(p.recognized_count) as formulas_recognized,
    SUM(p.merged_count) as formulas_merged
FROM tasks t
LEFT JOIN pages p ON p.task_id = t.task_id
GROUP BY t.task_id, t.status, t.total_pages;
"""

async def init_database():
    """Инициализирует базу данных"""
    try:
        # Подключаемся к БД
        conn = await asyncpg.connect(DATABASE_URL)
        print(f"Connected to database at {DATABASE_URL}")

        # Выполняем SQL
        await conn.execute(CREATE_TABLES_SQL)
        print("✓ Tables created successfully")

        # Проверяем созданные таблицы
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)

        print("\nCreated tables:")
        for table in tables:
            print(f"  - {table['table_name']}")

        await conn.close()

    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)

async def drop_database():
    """Удаляет все таблицы (осторожно!)"""
    DROP_TABLES_SQL = """
    DROP TABLE IF EXISTS formulas CASCADE;
    DROP TABLE IF EXISTS pages CASCADE;
    DROP TABLE IF EXISTS tasks CASCADE;
    DROP VIEW IF EXISTS task_progress CASCADE;
    DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;
    """

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(DROP_TABLES_SQL)
        print("All tables dropped successfully")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument('--drop', action='store_true', help='Drop all tables')
    args = parser.parse_args()

    if args.drop:
        asyncio.run(drop_database())
    else:
        asyncio.run(init_database())
