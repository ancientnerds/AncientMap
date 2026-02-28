"""
Shared rate limiter with Redis-first + in-memory sliding window fallback.

Usage:
    from api.services.rate_limiter import RateLimiter
    limiter = RateLimiter(max_requests=25, window_seconds=3600)
    if not limiter.check(ip):
        raise HTTPException(429, "Rate limited")
"""

import logging
import os
import time

from fastapi import Request

logger = logging.getLogger(__name__)

# When behind a reverse proxy (nginx), trust X-Forwarded-For.
_BEHIND_PROXY = os.environ.get("TRUSTED_PROXY", "").strip() in ("1", "true", "yes")


def get_client_ip(request: Request) -> str:
    """Extract client IP. Trusts X-Forwarded-For only when TRUSTED_PROXY=1."""
    ip = request.client.host if request.client else "unknown"
    if _BEHIND_PROXY:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
    return ip


# ---------------------------------------------------------------------------
# Module-level Redis client (shared by all RateLimiter instances)
# ---------------------------------------------------------------------------

_redis_client = None

try:
    import redis

    _redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    _redis_client = redis.from_url(_redis_url, decode_responses=True)
    _redis_client.ping()
    logger.info("Redis connected for rate limiting")
except Exception as e:
    logger.warning(f"Redis not available, using in-memory rate limiting: {e}")
    _redis_client = None


class RateLimiter:
    """Rate limiter. Redis path uses fixed-window (INCR+EXPIRE), in-memory path uses sliding-window."""

    def __init__(self, max_requests: int, window_seconds: int = 3600, namespace: str = "default"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.namespace = namespace
        # In-memory fallback state
        self._store: dict[str, list[float]] = {}
        self._last_cleanup = 0.0

    def check(self, ip: str) -> bool:
        """Return True if the request is allowed, False if rate limited."""
        if _redis_client is not None:
            try:
                return self._check_redis(ip)
            except Exception as e:
                logger.error(f"Redis rate limit error, falling back to memory: {e}")

        return self._check_memory(ip)

    def check_with_info(self, ip: str) -> tuple[bool, int, int]:
        """Return (allowed, remaining, reset_seconds) for rate-limit headers."""
        if _redis_client is not None:
            try:
                return self._check_redis_with_info(ip)
            except Exception as e:
                logger.error(f"Redis rate limit error, falling back to memory: {e}")

        return self._check_memory_with_info(ip)

    # -- Redis path --------------------------------------------------------

    def _check_redis(self, ip: str) -> bool:
        assert _redis_client is not None  # caller checks before calling
        key = f"rate_limit:{self.namespace}:{ip}"
        count = _redis_client.incr(key)
        if count == 1:
            _redis_client.expire(key, self.window_seconds)
        return count <= self.max_requests

    def _check_redis_with_info(self, ip: str) -> tuple[bool, int, int]:
        assert _redis_client is not None
        key = f"rate_limit:{self.namespace}:{ip}"
        pipe = _redis_client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if count == 1:
            _redis_client.expire(key, self.window_seconds)
            ttl = self.window_seconds
        remaining = max(0, self.max_requests - count)
        reset_seconds = max(0, ttl) if ttl > 0 else self.window_seconds
        return (count <= self.max_requests, remaining, reset_seconds)

    # -- In-memory path ----------------------------------------------------

    def _check_memory(self, ip: str) -> bool:
        now = time.time()

        # Periodic cleanup every 5 minutes
        if now - self._last_cleanup > 300:
            self._cleanup(now)
            self._last_cleanup = now

        timestamps = self._store.get(ip, [])
        timestamps = [t for t in timestamps if now - t < self.window_seconds]

        if len(timestamps) >= self.max_requests:
            self._store[ip] = timestamps
            return False

        timestamps.append(now)
        self._store[ip] = timestamps
        return True

    def _check_memory_with_info(self, ip: str) -> tuple[bool, int, int]:
        now = time.time()

        if now - self._last_cleanup > 300:
            self._cleanup(now)
            self._last_cleanup = now

        timestamps = self._store.get(ip, [])
        timestamps = [t for t in timestamps if now - t < self.window_seconds]

        if len(timestamps) >= self.max_requests:
            self._store[ip] = timestamps
            oldest = min(timestamps) if timestamps else now
            reset_seconds = int(self.window_seconds - (now - oldest))
            return (False, 0, max(1, reset_seconds))

        timestamps.append(now)
        self._store[ip] = timestamps
        remaining = self.max_requests - len(timestamps)
        oldest = min(timestamps)
        reset_seconds = int(self.window_seconds - (now - oldest))
        return (True, remaining, max(1, reset_seconds))

    def _cleanup(self, now: float) -> None:
        expired = []
        for ip, timestamps in self._store.items():
            self._store[ip] = [t for t in timestamps if now - t < self.window_seconds]
            if not self._store[ip]:
                expired.append(ip)
        for ip in expired:
            del self._store[ip]
