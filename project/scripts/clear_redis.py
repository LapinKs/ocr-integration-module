import os
import redis
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

def clear_redis():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    try:
        r = redis.from_url(redis_url)
        r.ping()
        print(f"Connected to Redis at {redis_url}")
        keys = r.keys('*')
        if not keys:
            print("No keys found in Redis")
            return
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
