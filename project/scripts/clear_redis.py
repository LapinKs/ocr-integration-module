#!/usr/bin/env python3
"""
Скрипт для очистки Redis от всех данных, связанных с Formula OCR.
Используется для сброса состояния между тестами.
"""
import os
import sys
from pathlib import Path

# Добавляем путь для импорта shared модулей
sys.path.insert(0, str(Path(__file__).parent.parent))

import redis
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def clear_redis():
    """Очищает все ключи Redis, связанные с Formula OCR"""
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    try:
        r = redis.from_url(redis_url)
        r.ping()
        print(f"Connected to Redis at {redis_url}")

        # Получаем все ключи
        keys = r.keys('*')

        if not keys:
            print("No keys found in Redis")
            return

        # Удаляем ключи по паттернам
        patterns = [
            b'task:*',
            b'page:*',
            b'formula:*',
            b'pending_updates:*',
            b'lock:*'
        ]

        deleted_count = 0
        for pattern in patterns:
            matching_keys = r.keys(pattern)
            for key in matching_keys:
                r.delete(key)
                deleted_count += 1

        print(f"Cleared {deleted_count} keys from Redis")

    except Exception as e:
        print(f"Error connecting to Redis: {e}")
        sys.exit(1)

def clear_all():
    """Очищает ВСЕ ключи в Redis (осторожно!)"""
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    try:
        r = redis.from_url(redis_url)
        r.flushall()
        print("Cleared ALL Redis data (flushall)")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true', help='Clear ALL Redis data')
    args = parser.parse_args()

    if args.all:
        clear_all()
    else:
        clear_redis()
