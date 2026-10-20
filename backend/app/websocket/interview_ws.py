"""Authenticated WebSocket channel for a live interview session.

* Candidate: receives questions, transcripts, progress, completion; sends device/connection status and
  WebRTC signalling for its camera stream.
* Institution monitor: receives the same events plus live snapshots; exchanges WebRTC signalling with the
  candidate to view the live video. Monitors are passive — the interview never waits for them.

Auth happens in the first message ({"type": "auth", "token": ...}) so tokens never appear in URLs/logs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, resolve_user
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.models import InterviewSession
from app.services import realtime
from app.services.analytics import live_session_snapshot
from app.services.runtime import session_state

log = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_CLIENT_TYPES = {"signal", "status", "ping"}
MAX_MSG = 64 * 1024


def _authorize(token: str, session_id: uuid.UUID, requested_role: str) -> tuple[CurrentUser, str, dict]:
    db = SessionLocal()
    try:
        user = resolve_user(db, token)
        s = db.get(InterviewSession, session_id)
        if s is None or s.institute_id != user.institute_id:
            raise AppError("Session not found", code="not_found")
        if requested_role == "candidate":
            if not user.is_student or s.candidate_id != user.id:
                raise AppError("Not your session", code="forbidden")
        elif requested_role == "monitor":
            if not user.is_institution:
                raise AppError("Monitoring requires institution access", code="forbidden")
        else:
            raise AppError("Unknown role", code="bad_request")
        snapshot = {"state": json.loads(json.dumps(session_state(db, s), default=str))}
        if requested_role == "monitor":
            snapshot["live"] = live_session_snapshot(db, s)
        return user, requested_role, snapshot
    finally:
        db.close()


def _update_connection(session_id: uuid.UUID, patch: dict) -> None:
    db = SessionLocal()
    try:
        s = db.get(InterviewSession, session_id)
        if s:
            s.connection = {**(s.connection or {}), **patch}
            db.commit()
    finally:
        db.close()


@router.websocket("/ws/interview/{session_id}")
async def interview_socket(ws: WebSocket, session_id: uuid.UUID) -> None:
    origin = ws.headers.get("origin")
    if origin and origin not in get_settings().cors_origin_list:
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
        if first.get("type") != "auth" or not first.get("token"):
            raise AppError("Authentication required", code="unauthorized")
        user, role, snapshot = await run_in_threadpool(_authorize, first["token"], session_id, first.get("role", "candidate"))
    except (AppError, asyncio.TimeoutError, json.JSONDecodeError, KeyError) as exc:
        await ws.send_json({"type": "error", "data": {"message": getattr(exc, "message", "Unauthorized")}})
        await ws.close(code=4401)
        return

    await ws.send_json({"type": "snapshot", "data": snapshot})
    other = "monitor" if role == "candidate" else "candidate"
    pubsub = realtime.redis_client_async().pubsub()
    await pubsub.subscribe(realtime.session_channel(session_id), realtime.signal_channel(session_id, role))
    if role == "candidate":
        await run_in_threadpool(_update_connection, session_id, {"candidate_online": True})
        realtime.publish(session_id, "connection_status", {"candidate_online": True})
    else:
        # Ask the candidate client to (re)offer its camera stream to this monitor.
        await realtime.publish_signal_async(session_id, "candidate", {"kind": "monitor_joined", "monitor_id": str(user.id)})

    async def pump_redis() -> None:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await ws.send_text(msg["data"] if isinstance(msg["data"], str) else msg["data"].decode())
            except Exception:  # noqa: BLE001
                return

    async def pump_client() -> None:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MSG:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind not in ALLOWED_CLIENT_TYPES:
                continue
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "signal":
                payload = msg.get("data") or {}
                payload["from"] = role
                payload["sender_id"] = str(user.id)
                await realtime.publish_signal_async(session_id, other, payload)
            elif kind == "status" and role == "candidate":
                status = {k: bool(v) for k, v in (msg.get("data") or {}).items()
                          if k in ("camera_on", "mic_on", "connected", "speaking")}
                await run_in_threadpool(_update_connection, session_id, status)
                realtime.publish(session_id, "connection_status", status)

    tasks = [asyncio.create_task(pump_redis()), asyncio.create_task(pump_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        await pubsub.unsubscribe()
        await pubsub.aclose()
        if role == "candidate":
            await run_in_threadpool(_update_connection, session_id, {"candidate_online": False})
            realtime.publish(session_id, "connection_status", {"candidate_online": False})
