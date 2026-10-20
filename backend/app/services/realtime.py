"""Real-time event fan-out via Redis pub/sub. Workers publish; WebSocket handlers subscribe.

The interview never depends on a subscriber existing — publishing to an empty channel is a no-op, so
the AI continues autonomously whether or not an institution user is watching.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.services.rate_limit import redis_client

log = logging.getLogger(__name__)

_events: list[dict] | None = None  # captured in tests when set


def capture_events(enabled: bool = True) -> list[dict]:
    global _events
    _events = [] if enabled else None
    return _events  # type: ignore[return-value]


def session_channel(session_id: uuid.UUID | str) -> str:
    return f"interview:session:{session_id}"


def signal_channel(session_id: uuid.UUID | str, role: str) -> str:
    """WebRTC signalling: role is 'candidate' or 'monitor' (the recipient)."""
    return f"interview:signal:{session_id}:{role}"


def publish(session_id: uuid.UUID | str, event_type: str, payload: dict | None = None) -> None:
    msg = {"type": event_type, "session_id": str(session_id), "ts": datetime.now(timezone.utc).isoformat(),
           "data": payload or {}}
    if _events is not None:
        _events.append(msg)
        return
    try:
        redis_client().publish(session_channel(session_id), json.dumps(msg, default=str))
    except Exception:  # noqa: BLE001 — real-time is best-effort; state is persisted in Postgres
        log.warning("realtime_publish_failed", extra={"data": {"event": event_type, "session_id": str(session_id)}})


_async_client = None


def redis_client_async():  # noqa: ANN201
    global _async_client
    if _async_client is None:
        import redis.asyncio as aioredis

        from app.core.config import get_settings

        _async_client = aioredis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _async_client


async def publish_signal_async(session_id, recipient_role: str, payload: dict) -> None:  # noqa: ANN001
    msg = json.dumps({"type": "signal", "session_id": str(session_id), "data": payload})
    await redis_client_async().publish(signal_channel(session_id, recipient_role), msg)
