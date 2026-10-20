#!/usr/bin/env python
"""Time every step of one interview turn inside the worker: speech-to-text, answer evaluation, next question, voice.

    docker compose exec worker python /app/scripts/check_pipeline.py

The slowest line is what holds up the interview.
"""
import io
import pathlib
import sys
import time
import wave

for c in (pathlib.Path(__file__).resolve().parents[1] / "backend", pathlib.Path("/app")):
    if (c / "app").exists():
        sys.path.insert(0, str(c))
        break

from app.agents.answer_evaluation import AnswerEvaluationAgent  # noqa: E402
from app.agents.base import SYSTEM_GUARDRAILS  # noqa: E402
from app.agents.schemas import GeneratedQuestion  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain import rubric  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from app.services.speech import get_stt, get_tts  # noqa: E402

ANSWER = ("I would design the orders API with plural resource names, use GET to list and fetch orders, POST to create, "
          "PATCH to update and DELETE to cancel. I would return 201 on create, 404 when an order is missing, add cursor "
          "pagination and put the version in the URL like slash v1.")


def step(name, fn):  # noqa: ANN001, ANN201
    t = time.monotonic()
    try:
        out = fn()
        print(f"[OK]   {name:<34} {time.monotonic() - t:6.1f}s")
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name:<34} {time.monotonic() - t:6.1f}s  {type(exc).__name__}: {str(exc)[:300]}")
        return None


s = get_settings()
print(f"llm={s.llm_provider} stt={s.stt_model}/{s.stt_device}/beam{s.stt_beam_size} tts={s.tts_provider}\n")
tts = step("load voice (Piper)", get_tts)
wav = step("speak a 30-word answer (TTS)", lambda: tts.synthesize(ANSWER)) if tts else None
if not wav:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(b"\0\0" * 16000 * 15)
    wav = buf.getvalue()
    print("       (no voice available: using 15 s of silence for the STT test)")
stt = step("load speech-to-text model", get_stt)
tr = step("transcribe the answer (STT)", lambda: stt.transcribe(wav, "wav")) if stt else None
if tr:
    print(f"       heard: {tr.text[:120]!r}")
question = {"text": "How would you design a REST API for orders?", "question_type": "technical", "topic": "REST APIs",
            "difficulty": "medium", "expected_points": ["resources", "methods", "status codes", "pagination", "versioning"]}
weights = {c: 1 / len(rubric.CRITERIA) for c in rubric.CRITERIA}
ev = step("evaluate the answer (LLM)", lambda: AnswerEvaluationAgent().evaluate(
    question=question, transcript=(tr.text if tr and tr.text else ANSWER), weights=weights, role="Backend Developer"))
if ev:
    print(f"       score: {ev['overall_score']} ({ev['band']})")
step("write the next question (LLM)", lambda: get_llm().generate_structured(
    system=SYSTEM_GUARDRAILS, schema=GeneratedQuestion, purpose="check_pipeline",
    prompt="Role: Backend Developer. Topic: databases. Difficulty: medium. Write ONE spoken-friendly question."))
