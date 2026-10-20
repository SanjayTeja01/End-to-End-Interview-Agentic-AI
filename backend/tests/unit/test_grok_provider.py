"""Grok (xAI) provider: request shape, response parsing, schema fallback and fail-fast on config errors."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.agents.schemas import GeneratedQuestion
from app.core.config import get_settings
from app.services.llm import GrokProvider, LLMConfigError, LLMService

QUESTION = {"question": "How would you version a public REST API?", "spoken_transition": "", "expected_points": ["urls"]}


def _provider(monkeypatch, handler) -> GrokProvider:  # noqa: ANN001
    s = get_settings()
    monkeypatch.setattr(s, "xai_api_key", SecretStr("xai-test"))
    p = GrokProvider()
    p._client = httpx.Client(base_url="https://api.x.ai/v1", transport=httpx.MockTransport(handler))
    return p


def _ok(text: str) -> httpx.Response:
    return httpx.Response(200, json={"status": "completed", "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": text}]}]})


def test_structured_call_shape_and_parse(monkeypatch):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return _ok(json.dumps(QUESTION))

    q = LLMService(_provider(monkeypatch, handler)).generate_structured(system="sys", prompt="p", schema=GeneratedQuestion)
    assert q.question.startswith("How would you")
    body = seen[0]
    assert body["model"] == get_settings().xai_model
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["reasoning"] == {"effort": "low"}
    assert body["input"][0] == {"role": "system", "content": "sys"}


def test_schema_rejection_falls_back_to_prompt_schema_once(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        calls.append(body)
        if "text" in body:
            return httpx.Response(400, json={"error": "unsupported schema"})
        return _ok("```json\n" + json.dumps(QUESTION) + "\n```")

    p = _provider(monkeypatch, handler)
    svc = LLMService(p)
    svc.generate_structured(system="s", prompt="p", schema=GeneratedQuestion)
    svc.generate_structured(system="s", prompt="p", schema=GeneratedQuestion)
    assert len(calls) == 3  # second call skips the rejected schema mode
    assert "JSON Schema" in calls[-1]["input"][1]["content"]


def test_bad_key_fails_fast_without_retries(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "invalid api key"})

    with pytest.raises(LLMConfigError):
        LLMService(_provider(monkeypatch, handler)).generate_structured(system="s", prompt="p", schema=GeneratedQuestion)
    assert len(calls) == 1


def test_timeouts_retry_only_briefly(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return _ok(json.dumps(QUESTION))

    monkeypatch.setattr("app.services.llm.time.sleep", lambda _s: None)
    q = LLMService(_provider(monkeypatch, handler)).generate_structured(system="s", prompt="p", schema=GeneratedQuestion)
    assert q.question and len(calls) == 2


def _groq(monkeypatch, handler):  # noqa: ANN001, ANN202
    from app.services.llm import GroqProvider

    monkeypatch.setattr(get_settings(), "groq_api_key", SecretStr("gsk_test"))
    p = GroqProvider()
    p._client = httpx.Client(base_url="https://api.groq.com/openai/v1", transport=httpx.MockTransport(handler))
    return p


def test_groq_chat_completions_shape_and_fallback(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        calls.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "invalid schema"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(QUESTION)}}]})

    q = LLMService(_groq(monkeypatch, handler)).generate_structured(system="s", prompt="p", schema=GeneratedQuestion)
    assert q.question.startswith("How would you")
    assert calls[0]["model"] == get_settings().groq_model and calls[0]["reasoning_effort"] == "low"
    assert calls[1]["response_format"] == {"type": "json_object"}


def test_groq_bad_key_is_not_mistaken_for_schema_error(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": "Incorrect API key provided"})

    with pytest.raises(LLMConfigError):
        LLMService(_groq(monkeypatch, handler)).generate_structured(system="s", prompt="p", schema=GeneratedQuestion)
    assert len(calls) == 1


def test_rate_limit_waits_retry_after(monkeypatch):
    import httpx

    from app.agents.schemas import ReportNarrative
    from app.core.config import get_settings
    from app.services import llm as llm_mod

    monkeypatch.setattr(get_settings(), "groq_api_key", __import__("pydantic").SecretStr("gsk_test"))
    p = llm_mod.GroqProvider()
    calls = {"n": 0}

    def post(url, json):  # noqa: A002
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, request=httpx.Request("POST", url))
        body = '{"summary": "s", "final_assessment": "a"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": body}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(p._client, "post", post)
    slept = []
    monkeypatch.setattr(llm_mod.time, "sleep", slept.append)
    out = llm_mod.LLMService(p).generate_structured(system="s", prompt="p", schema=ReportNarrative)
    assert out.summary == "s" and slept == [3.0]
