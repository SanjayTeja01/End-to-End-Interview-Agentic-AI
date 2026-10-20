#!/usr/bin/env python
"""(Optional legacy Gemini path — for Grok use check_grok.py) Diagnose Gemini: tries the Gemini Developer API and the Vertex AI endpoint with your key.

    docker compose exec worker python /app/scripts/check_gemini.py
"""
import os

from google import genai
from google.genai import types
from pydantic import BaseModel

key = os.environ.get("GEMINI_API_KEY", "")
model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
emb_model = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
dims = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))
print(f"model={model}  embedding={emb_model}  key present={bool(key)} length={len(key)} prefix={key[:3]!r}\n")


class Probe(BaseModel):
    answer: str
    items: list[str] = []


def run(label, client):  # noqa: ANN001
    print(f"== {label} ==")
    ok = True
    for name, fn in (
        ("text", lambda: client.models.generate_content(model=model, contents="Say OK").text.strip()),
        ("structured JSON", lambda: client.models.generate_content(
            model=model, contents="answer='ok', items=['a']",
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=Probe)).text),
        ("embeddings", lambda: len(client.models.embed_content(
            model=emb_model, contents=["hello"],
            config=types.EmbedContentConfig(output_dimensionality=dims)).embeddings[0].values)),
    ):
        try:
            print(f"  [OK]   {name}: {fn()}")
        except Exception as exc:  # noqa: BLE001
            if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                print(f"  [BUSY] {name}: Google is temporarily overloaded (503) — the app retries automatically")
                continue
            ok = False
            print(f"  [FAIL] {name}: {type(exc).__name__}: {str(exc).replace(key, '***')[:400]}")
    return ok


dev = run("Gemini Developer API (GEMINI_USE_VERTEX=false)", genai.Client(api_key=key))
print()
vtx = run("Vertex AI endpoint (GEMINI_USE_VERTEX=true)", genai.Client(vertexai=True, api_key=key))
print()
if dev:
    print("RESULT: use GEMINI_USE_VERTEX=false")
elif vtx:
    print("RESULT: set GEMINI_USE_VERTEX=true in .env, then: docker compose up -d --build backend worker")
else:
    print("RESULT: neither endpoint accepted the key — paste this output to get help")

print("\n== Models your key can use for text generation ==")
try:
    lister = genai.Client(api_key=key)  # keep a reference so the client stays open while paging
    names = sorted(m.name.removeprefix("models/") for m in lister.models.list()
                   if "generateContent" in (getattr(m, "supported_actions", None) or []))
    for n in names:
        print("  ", n)
    print("\nPick 1-2 'flash' models from this list for GEMINI_FALLBACK_MODELS in .env")
except Exception as exc:  # noqa: BLE001
    print("  could not list models:", str(exc)[:300])
