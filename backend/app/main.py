"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    auth,
    health,
    interviews,
    jobs,
    knowledge,
    monitoring,
    performance,
    profile,
    results,
    resume,
    runtime,
    students,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, correlation_id
from app.websocket import interview_ws

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("app")


def _sweep_once() -> None:
    from app.core.database import SessionLocal
    from app.services.runtime import sweep_overdue_sessions

    db = SessionLocal()
    try:
        sweep_overdue_sessions(db)
    finally:
        db.close()


async def _interview_clock() -> None:
    """Ends interviews whose time is up (checked every 10 s), independent of the browser and Celery timers."""
    from starlette.concurrency import run_in_threadpool

    while True:
        await asyncio.sleep(10)
        try:
            await run_in_threadpool(_sweep_once)
        except Exception:  # noqa: BLE001 — keep the clock running
            log.exception("interview_clock_failed")


@asynccontextmanager
async def lifespan(_: FastAPI):  # noqa: ANN201
    clock = None
    if settings.app_env != "test":
        clock = asyncio.create_task(_interview_clock())
        settings.require_secrets()
        try:
            from storage.minio.client import get_storage

            get_storage().ensure_bucket()
        except Exception:  # noqa: BLE001 — readiness endpoint reports it
            log.exception("minio_bucket_init_failed")
    yield
    if clock:
        clock.cancel()


app = FastAPI(
    title="End-to-End Interview Agent API",
    description="Institution-controlled, multi-tenant, autonomous AI video interview platform.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type",
                                                                                  "X-Request-ID"])


@app.middleware("http")
async def request_context(request: Request, call_next):  # noqa: ANN001, ANN201
    cid = request.headers.get("x-request-id") or uuid.uuid4().hex
    token = correlation_id.set(cid[:64])
    try:
        response = await call_next(request)
    finally:
        correlation_id.reset(token)
    response.headers["X-Request-ID"] = cid[:64]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                        status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse({"error": {"code": "validation_failed", "message": "Invalid request", "details": {"errors": errors}}},
                        status_code=422)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", extra={"data": {"type": type(exc).__name__}})
    return JSONResponse({"error": {"code": "internal_error", "message": "Internal server error"}}, status_code=500)


for r in (health.router, auth.router, profile.router, resume.router, interviews.router, runtime.router, results.router,
          performance.router, students.router, monitoring.router, knowledge.router, jobs.router):
    app.include_router(r)
app.include_router(interview_ws.router)
