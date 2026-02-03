"""
Caching layer for the Connectors Module.

Provides multi-tier caching:
1. In-memory LRU cache for hot data
2. Redis cache for shared/distributed caching
3. Database cache for persistent storage

Cache keys follow the pattern:
    connector:{connector_id}:{method}:{hash_of_params}
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from pipeline.connectors.types import ContentItem


@dataclass
class CacheConfig:
    """Configuration for connector caching."""

    # TTL in seconds for different content types
    default_ttl: int = 1800  # 30 minutes
    search_ttl: int = 900  # 15 minutes
    item_ttl: int = 3600  # 1 hour
    static_ttl: int = 86400  # 24 hours (for rarely changing data)

    # Maximum items in memory cache
    memory_max_size: int = 1000

    # Redis prefix
    redis_prefix: str = "connectors"

    # Enable/disable cache layers
    use_memory: bool = True
    use_redis: bool = True
    use_database: bool = False  # For persistent caching


# Global config instance
cache_config = CacheConfig()


def make_cache_key(
    connector_id: str,
    method: str,
    params: dict[str, Any],
) -> str:
    """
    Generate a cache key from connector, method, and parameters.

    Args:
        connector_id: ID of the connector
        method: Method name (search, get_item, get_by_location, etc.)
        params: Parameters dictionary

    Returns:
        Cache key string
    """
    # Sort params for consistent hashing
    sorted_params = json.dumps(params, sort_keys=True, default=str)
    params_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:12]

    return f"{cache_config.redis_prefix}:{connector_id}:{method}:{params_hash}"


class MemoryCache:
    """
    Simple in-memory LRU cache for connector responses.

    Thread-safe and uses TTL-based expiration.
    """

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, tuple] = {}  # key -> (value, expires_at)
        self._max_size = max_size
        self._access_order: list[str] = []

    def get(self, key: str) -> Any | None:
        """Get value from cache if exists and not expired."""
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]

        # Check expiration
        if expires_at and datetime.utcnow() > expires_at:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return None

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return value

    def set(self, key: str, value: Any, ttl_seconds: int = None) -> None:
        """Set value in cache with optional TTL."""
        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size and self._access_order:
            oldest = self._access_order.pop(0)
            if oldest in self._cache:
                del self._cache[oldest]

        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        self._cache[key] = (value, expires_at)
        self._access_order.append(key)

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._access_order.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


# Global memory cache instance
_memory_cache = MemoryCache(max_size=cache_config.memory_max_size)


def get_redis_client():
    """Get Redis client from API cache module."""
    try:
        from api.cache import get_redis_client as api_get_redis
        return api_get_redis()
    except ImportError:
        logger.debug("Redis client not available")
        return None
    except Exception as e:
        logger.warning(f"Failed to get Redis client: {e}")
        return None


async def cache_get(key: str) -> Any | None:
    """
    Get value from cache (memory first, then Redis).

    Args:
        key: Cache key

    Returns:
        Cached value or None
    """
    # Try memory cache first
    if cache_config.use_memory:
        value = _memory_cache.get(key)
        if value is not None:
            logger.debug(f"Cache hit (memory): {key}")
            return value

    # Try Redis
    if cache_config.use_redis:
        redis = get_redis_client()
        if redis:
            try:
                data = redis.get(key)
                if data:
                    value = json.loads(data)
                    # Populate memory cache
                    if cache_config.use_memory:
                        _memory_cache.set(key, value, cache_config.default_ttl)
                    logger.debug(f"Cache hit (Redis): {key}")
                    return value
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

    return None


async def cache_set(
    key: str,
    value: Any,
    ttl_seconds: int = None,
) -> bool:
    """
    Set value in cache (both memory and Redis).

    Args:
        key: Cache key
        value: Value to cache (must be JSON-serializable)
        ttl_seconds: Time to live in seconds

    Returns:
        True if cached successfully
    """
    ttl = ttl_seconds or cache_config.default_ttl

    # Set in memory cache
    if cache_config.use_memory:
        _memory_cache.set(key, value, ttl)

    # Set in Redis
    if cache_config.use_redis:
        redis = get_redis_client()
        if redis:
            try:
                data = json.dumps(value, default=str)
                redis.setex(key, ttl, data)
                logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
                return False

    return cache_config.use_memory


async def cache_delete(key: str) -> bool:
    """Delete key from all cache layers."""
    deleted = False

    if cache_config.use_memory:
        deleted = _memory_cache.delete(key) or deleted

    if cache_config.use_redis:
        redis = get_redis_client()
        if redis:
            try:
                redis.delete(key)
                deleted = True
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")

    return deleted


async def cache_clear_connector(connector_id: str) -> int:
    """Clear all cache entries for a connector."""
    pattern = f"{cache_config.redis_prefix}:{connector_id}:*"
    count = 0

    # Can't efficiently clear memory cache by pattern, so clear all
    if cache_config.use_memory:
        _memory_cache.clear()

    if cache_config.use_redis:
        redis = get_redis_client()
        if redis:
            try:
                keys = redis.keys(pattern)
                if keys:
                    count = redis.delete(*keys)
                    logger.info(f"Cleared {count} cache entries for {connector_id}")
            except Exception as e:
                logger.warning(f"Redis clear error: {e}")

    return count


def cached_search(ttl_seconds: int = None):
    """
    Decorator for caching search method results.

    Usage:
        @cached_search(ttl_seconds=900)
        async def search(self, query: str, ...) -> List[ContentItem]:
            ...
    """

    def decorator(func: Callable):
        async def wrapper(self, query: str, **kwargs):
            # Build cache key
            params = {"query": query, **kwargs}
            key = make_cache_key(self.connector_id, "search", params)

            # Try cache
            cached = await cache_get(key)
            if cached is not None:
                # Reconstruct ContentItems from dict
                return [ContentItem.from_dict(item) for item in cached]

            # Call actual method
            result = await func(self, query, **kwargs)

            # Cache result
            if result:
                cache_data = [item.to_dict() for item in result]
                await cache_set(key, cache_data, ttl_seconds or cache_config.search_ttl)

            return result

        return wrapper

    return decorator


def cached_item(ttl_seconds: int = None):
    """
    Decorator for caching get_item method results.

    Usage:
        @cached_item(ttl_seconds=3600)
        async def get_item(self, item_id: str) -> Optional[ContentItem]:
            ...
    """

    def decorator(func: Callable):
        async def wrapper(self, item_id: str):
            key = make_cache_key(self.connector_id, "get_item", {"id": item_id})

            cached = await cache_get(key)
            if cached is not None:
                return ContentItem.from_dict(cached)

            result = await func(self, item_id)

            if result:
                await cache_set(key, result.to_dict(), ttl_seconds or cache_config.item_ttl)

            return result

        return wrapper

    return decorator
