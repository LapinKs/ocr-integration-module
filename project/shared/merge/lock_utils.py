import uuid
from shared.infrastructure.redis_client import get_redis_client

def try_acquire_merge_lock(redis_client, task_id: str, page_index: int, ttl: int = 60) -> bool:
    lock_key = f"merge_lock:{task_id}:{page_index}"
    lock_value = str(uuid.uuid4())
    acquired = redis_client.set(lock_key, lock_value, nx=True, ex=ttl)
    if acquired:
        redis_client.hset(f"page:{task_id}:{page_index}", "merge_lock_owner", lock_value)
    return bool(acquired)

def release_merge_lock(redis_client, task_id: str, page_index: int) -> bool:
    lock_key = f"merge_lock:{task_id}:{page_index}"
    expected_value = redis_client.hget(f"page:{task_id}:{page_index}", "merge_lock_owner")
    if not expected_value:
        return False
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    result = redis_client.eval(lua_script, 1, lock_key, expected_value)
    return result == 1


def check_lock_owner(redis_client, task_id: str, page_index: int) -> bool:
    lock_key = f"merge_lock:{task_id}:{page_index}"
    expected_value = redis_client.hget(f"page:{task_id}:{page_index}", "merge_lock_owner")
    if not expected_value:
        return False
    current_value = redis_client.get(lock_key)
    return current_value == expected_value
