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
import threading
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
            ip = forwarded.split(",")[-1].strip()
    return ip


# ---------------------------------------------------------------------------
# Module-level Redis client (shared by all RateLimiter instances).
# Lazy connect with a failure cooldown: a boot-time Redis outage no longer
# pins in-memory limiting for the process lifetime — we retry every 30s.
# ---------------------------------------------------------------------------

_REDIS_RETRY_COOLDOWN = 30.0  # seconds between reconnect attempts

_redis_client = None
_redis_failed_at: float | None = None  # monotonic time of last failed attempt
_redis_state = "init"  # "init" | "connected" | "lost" — for state-change logging
_redis_lock = threading.Lock()


def _get_redis():
    """Return a connected Redis client, or None while unavailable/in cooldown."""
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
                    f"Redis unavailable for rate limiting, using in-memory "
                    f"(retrying every {_REDIS_RETRY_COOLDOWN:.0f}s): {e}"
                )
            return None
        _redis_client = client
        _redis_failed_at = None
        _redis_state = "connected"
        logger.warning("Redis connected for rate limiting")
        return client


def _mark_redis_lost(exc: Exception) -> None:
    """Drop the client after a runtime error and start the retry cooldown."""
    global _redis_client, _redis_failed_at, _redis_state
    with _redis_lock:
        _redis_client = None
        _redis_failed_at = time.monotonic()
        if _redis_state != "lost":
            _redis_state = "lost"
            logger.warning(
                f"Redis lost for rate limiting, using in-memory "
                f"(retrying every {_REDIS_RETRY_COOLDOWN:.0f}s): {exc}"
            )


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
        allowed, _, _ = self.check_with_info(ip)
        return allowed

    def check_with_info(self, ip: str) -> tuple[bool, int, int]:
        """Return (allowed, remaining, reset_seconds) for rate-limit headers."""
        client = _get_redis()
        if client is not None:
            try:
                return self._check_redis_with_info(client, ip)
            except Exception as e:
                _mark_redis_lost(e)

        return self._check_memory_with_info(ip)

    # -- Redis path --------------------------------------------------------

    def _check_redis_with_info(self, client, ip: str) -> tuple[bool, int, int]:
        key = f"rate_limit:{self.namespace}:{ip}"
        # Atomic fixed window: SET NX EX creates the key WITH its TTL in the
        # same MULTI/EXEC transaction as INCR, so the window expiry can never
        # be lost between INCR and a separate EXPIRE call (the old two-call
        # pattern could leave a key without TTL = permanently limited IP).
        pipe = client.pipeline(transaction=True)
        pipe.set(key, 0, nx=True, ex=self.window_seconds)
        pipe.incr(key)
        pipe.ttl(key)
        _, count, ttl = pipe.execute()
        if ttl < 0:
            # Key without TTL left over from the pre-fix INCR/EXPIRE race:
            # repair it so the IP is not limited forever.
            client.expire(key, self.window_seconds)
            ttl = self.window_seconds
        remaining = max(0, self.max_requests - count)
        return (count <= self.max_requests, remaining, ttl)

    # -- In-memory path ----------------------------------------------------

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
