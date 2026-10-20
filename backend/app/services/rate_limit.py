"""Redis-backed fixed-window rate limiting (login attempts, LLM calls). Redis is infrastructure only."""
from __future__ import annotations

import logging
import time
from functools import lru_cache

from app.core.config import get_settings
from app.core.errors import RateLimited

log = logging.getLogger(__name__)


@lru_cache
def redis_client():  # noqa: ANN201
    import redis

    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=3, socket_connect_timeout=3,
                                decode_responses=True)


def hit(key: str, limit: int, window_seconds: int) -> bool:
    """Return True if allowed. Fails open (logged) if Redis is unreachable so interviews are not blocked."""
    try:
        r = redis_client()
        bucket = f"rl:{key}:{int(time.time() // window_seconds)}"
        pipe = r.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, window_seconds + 1)
        count, _ = pipe.execute()
        return int(count) <= limit
    except Exception:  # noqa: BLE001
        log.warning("rate_limit_backend_unavailable", extra={"data": {"key": key}})
        return True


def enforce(key: str, limit: int, window_seconds: int, message: str = "Too many requests") -> None:
    if not hit(key, limit, window_seconds):
        raise RateLimited(message)


def wait_for_slot(key: str, limit: int, window_seconds: int = 60, max_wait: float = 30.0) -> None:
    """Block (up to max_wait) until a slot is free — used to smooth Gemini calls across workers."""
    deadline = time.monotonic() + max_wait
    while not hit(key, limit, window_seconds):
        if time.monotonic() > deadline:
            raise RateLimited("LLM rate limit reached")
        time.sleep(1.0)
