from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    checks: dict[str, bool] = {}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:  # noqa: BLE001
        checks["postgres"] = False
    try:
        from app.services.rate_limit import redis_client

        checks["redis"] = bool(redis_client().ping())
    except Exception:  # noqa: BLE001
        checks["redis"] = False
    try:
        from storage.minio.client import get_storage

        checks["minio"] = get_storage().ping()
    except Exception:  # noqa: BLE001
        checks["minio"] = False
    try:
        from rag.retrieval.vector_store import get_vector_store

        checks["chroma"] = get_vector_store().ping()
    except Exception:  # noqa: BLE001
        checks["chroma"] = False
    ok = all(checks.values())
    return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)
