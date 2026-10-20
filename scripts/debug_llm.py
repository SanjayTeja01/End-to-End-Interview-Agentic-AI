#!/usr/bin/env python
"""(Gemini only — for Grok use check_grok.py) Runs the real resume-analysis LLM call once and prints the exact error, step by step.

    docker compose exec worker python /app/scripts/debug_llm.py
"""
import json
import pathlib
import sys
import traceback

for c in (pathlib.Path(__file__).resolve().parents[1] / "backend", pathlib.Path("/app")):
    if (c / "app").exists():
        sys.path.insert(0, str(c))
        break

from app.agents.base import SYSTEM_GUARDRAILS  # noqa: E402
from app.agents.schemas import ResumeAnalysis  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.llm import GeminiProvider  # noqa: E402

s = get_settings()
key = s.gemini_api_key.get_secret_value()
print(f"model={s.gemini_model} vertex={s.gemini_use_vertex} retries={s.llm_max_retries}")
TEXT = ("Jane Doe\nEducation\nTest University, B.Tech Computer Science\nProjects\nChat App: built with Python and FastAPI\n"
        "Skills\nPython, SQL, Machine Learning")
p = GeminiProvider()

print("\n--- 1) schema-constrained call (what the app does) ---")
try:
    raw = p.complete_json(system=SYSTEM_GUARDRAILS, prompt="Extract a structured profile.\n\n" + TEXT,
                          schema=ResumeAnalysis, temperature=0.1)
    print("raw reply (first 600 chars):", raw[:600])
    try:
        ResumeAnalysis.model_validate_json(raw.strip().strip("`").removeprefix("json"))
        print("[OK] reply matches the schema")
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] reply did not validate:", str(exc)[:1500])
except Exception as exc:  # noqa: BLE001
    print("[FAIL] call raised:", type(exc).__name__, str(exc).replace(key, "***")[:1500])
    traceback.print_exc(limit=3)

print("\n--- 2) plain JSON mode (schema in prompt) ---")
try:
    from google.genai import types

    cfg = types.GenerateContentConfig(system_instruction=SYSTEM_GUARDRAILS, temperature=0.1, response_mime_type="application/json")
    r = p._client.models.generate_content(
        model=s.gemini_model, config=cfg,
        contents="Extract a structured profile. Return ONLY JSON matching this schema:\n"
                 + json.dumps(ResumeAnalysis.model_json_schema()) + "\n\n" + TEXT)
    print("raw reply (first 600 chars):", (r.text or "")[:600])
    ResumeAnalysis.model_validate_json(r.text or "")
    print("[OK] JSON-mode reply matches the schema")
except Exception as exc:  # noqa: BLE001
    print("[FAIL]", type(exc).__name__, str(exc).replace(key, "***")[:1500])
