"""Structured JSON logging with correlation ids and secret redaction."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone

correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

_REDACT_KEYS = re.compile(r"(password|secret|token|api[_-]?key|authorization|cookie)", re.I)


def redact(value):  # noqa: ANN001, ANN201
    if isinstance(value, dict):
        return {k: ("***" if _REDACT_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        cid = correlation_id.get()
        if cid:
            payload["correlation_id"] = cid
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload.update(redact(extra))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    # sys.__stdout__, not sys.stdout: inside Celery worker processes sys.stdout is Celery's logging proxy, and a root
    # handler writing to it feeds every record back into logging, where Celery's recursion guard silently drops it.
    # That hid every worker-side log line (LLM calls, evaluations, errors, tracebacks).
    handler = logging.StreamHandler(sys.__stdout__)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "urllib3", "chromadb", "botocore"):
        logging.getLogger(noisy).setLevel("WARNING")


def log_event(logger: logging.Logger, event: str, **data) -> None:  # noqa: ANN003
    """Log an audit-friendly event. Never pass raw secrets or full resumes/transcripts."""
    logger.info(event, extra={"data": data})
