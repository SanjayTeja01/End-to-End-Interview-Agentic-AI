"""Single place that builds the google-genai client (Gemini Developer API or Vertex AI express mode)."""
from __future__ import annotations

from app.core.config import get_settings


def make_client():  # noqa: ANN201
    from google import genai
    from google.genai import types

    s = get_settings()
    key = s.gemini_api_key.get_secret_value()
    opts = types.HttpOptions(timeout=s.llm_timeout_seconds * 1000)
    if s.gemini_use_vertex:
        return genai.Client(vertexai=True, api_key=key, http_options=opts)
    return genai.Client(api_key=key, http_options=opts)
