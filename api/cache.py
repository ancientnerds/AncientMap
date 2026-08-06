"""
Redis caching utilities for API endpoints.

Provides simple caching with TTL for expensive database queries.
Falls back to in-memory cache when Redis is unavailable.
"""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# Redis client singleton — lazy connect with a failure cooldown: on any Redis
# error we skip Redis for 30s instead of paying a reconnect attempt per call.
_REDIS_RETRY_COOLDOWN = 30.0  # seconds between reconnect attempts

_redis_client = None
_redis_failed_at: float | None = None  # monotonic time of last failure
_redis_state = "init"  # "init" | "connected" | "lost" — for state-change logging
_redis_lock = threading.Lock()

# In-memory fallback cache when Redis is unavailable
# Format: {key: (value, expiry_timestamp)}
_memory_cache: dict[str, tuple[Any, float]] = {}
_memory_lock = threading.Lock()
_MEMORY_CACHE_MAX_ENTRIES = 50  # Limit memory usage


def _cleanup_memory_cache():
    """Remove expired entries from memory cache. Caller must hold _memory_lock."""
    global _memory_cache
    now = time.time()
    # Remove expired entries
    _memory_cache = {k: v for k, v in _memory_cache.items() if v[1] > now}

    # If still over limit, remove oldest entries
    if len(_memory_cache) > _MEMORY_CACHE_MAX_ENTRIES:
        sorted_items = sorted(_memory_cache.items(), key=lambda x: x[1][1])
        _memory_cache = dict(sorted_items[-_MEMORY_CACHE_MAX_ENTRIES:])


def get_redis_client():
    """Get or create the Redis client singleton (lazy, with 30s failure cooldown)."""
    global _redis_client, _redis_failed_at, _redis_state

    client = _redis_client
    if client is not None:
        return client

    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        now = time.monotonic()
        if _redis_failed_at is not None and now - _redis_failed_at < _REDIS_RETRY_COOLDOWN:
            return None
        try:
            import redis

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
        except Exception as e:
            _redis_failed_at = now
            if _redis_state != "lost":
                _redis_state = "lost"
                logger.warning(
                    f"Redis unavailable for caching, using in-memory "
                    f"(retrying every {_REDIS_RETRY_COOLDOWN:.0f}s): {e}"
                )
            return None
        _redis_client = client
        _redis_failed_at = None
        _redis_state = "connected"
        logger.warning("Redis connected for caching")
        return client


def _mark_redis_lost(context: str, exc: Exception) -> None:
    """Drop the client after a runtime error and start the retry cooldown."""
    global _redis_client, _redis_failed_at, _redis_state
    with _redis_lock:
        _redis_client = None
        _redis_failed_at = time.monotonic()
        if _redis_state != "lost":
            _redis_state = "lost"
            logger.warning(
                f"Redis lost for caching on {context}, using in-memory "
                f"(retrying every {_REDIS_RETRY_COOLDOWN:.0f}s): {exc}"
            )


def cache_get(key: str) -> Any | None:
    """Get value from cache (Redis with in-memory fallback)."""
    # Try Redis first
    client = get_redis_client()
    if client:
        try:
            value = client.get(key)
            if value is not None:
                return json.loads(value)
        except (TypeError, ValueError) as e:
            # Corrupt cached JSON — not a Redis outage, keep the connection
            logger.warning(f"Cache get error for {key}: {e}")
        except Exception as e:
            _mark_redis_lost(f"get {key}", e)

    # Fallback to in-memory cache
    with _memory_lock:
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
        except (TypeError, ValueError) as e:
            # Unserializable value — not a Redis outage, keep the connection
            logger.warning(f"Cache set error for {key}: {e}")
        except Exception as e:
            _mark_redis_lost(f"set {key}", e)

    # Fallback to in-memory cache
    with _memory_lock:
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
            _mark_redis_lost(f"delete {key}", e)

    # Also delete from memory cache
    with _memory_lock:
        if key in _memory_cache:
            del _memory_cache[key]
            deleted = True

    return deleted


def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern (Redis and in-memory)."""
    count = 0

    # Try Redis using SCAN (non-blocking) instead of KEYS
    client = get_redis_client()
    if client:
        try:
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor, match=pattern, count=100)
                if keys:
                    count += client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            _mark_redis_lost(f"delete pattern {pattern}", e)

    # Also delete from memory cache (simple prefix match)
    import fnmatch

    with _memory_lock:
        keys_to_delete = [k for k in _memory_cache.keys() if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_delete:
            del _memory_cache[key]
            count += 1

    return count


def cached(key_prefix: str, ttl: int = 3600) -> Callable:
    """
    Decorator for caching function results.

    Usage:
        @cached("sources", ttl=3600)
        async def get_sources():
            ...
    """

    def decorator(func: Callable) -> Callable:
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
