"""
Redis caching utilities for API endpoints.

Provides simple caching with TTL for expensive database queries.
Falls back to in-memory cache when Redis is unavailable.
"""

import json
import logging
import os
import time
from functools import wraps
from typing import Any, Callable, Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# Redis client singleton
_redis_client = None
_redis_available = False

# In-memory fallback cache when Redis is unavailable
# Format: {key: (value, expiry_timestamp)}
_memory_cache: Dict[str, Tuple[Any, float]] = {}
_MEMORY_CACHE_MAX_ENTRIES = 50  # Limit memory usage


def _cleanup_memory_cache():
    """Remove expired entries from memory cache."""
    global _memory_cache
    now = time.time()
    # Remove expired entries
    _memory_cache = {k: v for k, v in _memory_cache.items() if v[1] > now}

    # If still over limit, remove oldest entries
    if len(_memory_cache) > _MEMORY_CACHE_MAX_ENTRIES:
        sorted_items = sorted(_memory_cache.items(), key=lambda x: x[1][1])
        _memory_cache = dict(sorted_items[-_MEMORY_CACHE_MAX_ENTRIES:])


def get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client, _redis_available

    if _redis_client is not None:
        return _redis_client if _redis_available else None

    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        _redis_available = True
        return _redis_client
    except Exception:
        _redis_available = False
        _redis_client = None
        return None


def cache_get(key: str) -> Optional[Any]:
    """Get value from cache (Redis with in-memory fallback)."""
    # Try Redis first
    client = get_redis_client()
    if client:
        try:
            value = client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.warning(f"Cache get error for {key}: {e}")

    # Fallback to in-memory cache
    if key in _memory_cache:
        value, expiry = _memory_cache[key]
        if time.time() < expiry:
            logger.debug(f"Memory cache hit: {key}")
            return value
        else:
            del _memory_cache[key]

    return None


def cache_set(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set value in cache with TTL (Redis with in-memory fallback)."""
    # Try Redis first
    client = get_redis_client()
    if client:
        try:
            client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.warning(f"Cache set error for {key}: {e}")

    # Fallback to in-memory cache
    _cleanup_memory_cache()
    _memory_cache[key] = (value, time.time() + ttl)
    logger.debug(f"Memory cache set: {key} (TTL: {ttl}s)")
    return True


def cache_delete(key: str) -> bool:
    """Delete value from cache (Redis and in-memory)."""
    deleted = False

    # Try Redis
    client = get_redis_client()
    if client:
        try:
            client.delete(key)
            deleted = True
        except Exception as e:
            logger.warning(f"Cache delete error for {key}: {e}")

    # Also delete from memory cache
    if key in _memory_cache:
        del _memory_cache[key]
        deleted = True

    return deleted


def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern (Redis and in-memory)."""
    count = 0

    # Try Redis
    client = get_redis_client()
    if client:
        try:
            keys = client.keys(pattern)
            if keys:
                count += client.delete(*keys)
        except Exception as e:
            logger.warning(f"Cache delete pattern error for {pattern}: {e}")

    # Also delete from memory cache (simple prefix match)
    import fnmatch
    keys_to_delete = [k for k in _memory_cache.keys() if fnmatch.fnmatch(k, pattern)]
    for key in keys_to_delete:
        del _memory_cache[key]
        count += 1

    return count


def cached(key_prefix: str, ttl: int = 3600):
    """
    Decorator for caching function results.

    Usage:
        @cached("sources", ttl=3600)
        async def get_sources():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from prefix and arguments
            cache_key = f"{key_prefix}"
            if args:
                cache_key += ":" + ":".join(str(a) for a in args if a is not None)
            if kwargs:
                sorted_kwargs = sorted((k, v) for k, v in kwargs.items() if v is not None)
                if sorted_kwargs:
                    cache_key += ":" + ":".join(f"{k}={v}" for k, v in sorted_kwargs)

            # Try cache first
            cached_value = cache_get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Call function and cache result
            result = await func(*args, **kwargs)
            cache_set(cache_key, result, ttl)
            logger.debug(f"Cache miss, stored: {cache_key}")

            return result

        return wrapper
    return decorator
