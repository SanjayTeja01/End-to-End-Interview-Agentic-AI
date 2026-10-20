#!/usr/bin/env python
"""Check the LLM setup (LLM_PROVIDER=grok or groq) end to end: key, model, structured output and how long one question takes.

    docker compose exec worker python /app/scripts/check_grok.py
"""
import pathlib
import sys
import time

for c in (pathlib.Path(__file__).resolve().parents[1] / "backend", pathlib.Path("/app")):
    if (c / "app").exists():
        sys.path.insert(0, str(c))
        break

from app.agents.base import SYSTEM_GUARDRAILS  # noqa: E402
from app.agents.schemas import GeneratedQuestion  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.llm import _default  # noqa: E402

s = get_settings()
groq = s.llm_provider.strip().lower() == "groq"
key = (s.groq_api_key if groq else s.xai_api_key).get_secret_value()
print(f"provider={s.llm_provider} model={s.groq_model if groq else s.xai_model} "
      f"timeout={s.llm_timeout_seconds}s retries={s.llm_max_retries} key_set={bool(key)} key_prefix={key[:4]!r}")
if key.startswith("gsk_") and not groq:
    print("NOTE: a key starting with gsk_ is a Groq key, not an xAI Grok key. Set LLM_PROVIDER=groq and GROQ_API_KEY.")
llm = _default()
started = time.monotonic()
try:
    q = llm.generate_structured(system=SYSTEM_GUARDRAILS, schema=GeneratedQuestion, purpose="check_grok",
                                prompt="Role: Backend Developer. Topic: REST APIs. Difficulty: medium. "
                                       "Write ONE spoken-friendly interview question under 60 words and list key points.")
except Exception as exc:  # noqa: BLE001
    print(f"[FAIL] after {time.monotonic() - started:.1f}s: {type(exc).__name__}: {exc} / {exc.__cause__!r}"[:1500])
    raise SystemExit(1)
print(f"[OK] question generated in {time.monotonic() - started:.1f}s")
print("Q:", q.question)
print("Key points:", q.expected_points)
