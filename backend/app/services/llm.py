"""LLM service abstraction. Providers: Grok (xAI), Groq (fast open models) and optional Gemini — chosen by LLM_PROVIDER.

All agent calls go through `generate_structured`, which enforces a Pydantic schema, validates the
response, retries malformed output, and never returns unvalidated free text to callers.
"""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(ServiceUnavailable):
    code = "llm_error"


class LLMRateLimited(LLMError):
    """Provider said 429 Too Many Requests (e.g. Groq free-tier tokens-per-minute). Carries its Retry-After."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _raise_if_rate_limited(resp, provider: str) -> None:  # noqa: ANN001
    if resp.status_code != 429:
        return
    try:
        wait = float(resp.headers.get("retry-after") or 0)
    except ValueError:
        wait = 0.0
    raise LLMRateLimited(f"{provider} rate limit (429)", retry_after=wait or 5.0)


class LLMConfigError(LLMError):
    """Bad key / unknown model: retrying cannot help, so it is never retried."""


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, *, system: str, prompt: str, schema: type[BaseModel], temperature: float) -> str: ...


class GrokProvider:
    """xAI Grok over its OpenAI-compatible REST API (Responses API, schema-constrained JSON output).

    One HTTP call per request: schema mode first; if xAI rejects the schema (HTTP 400) we remember that for the
    schema and send it in the prompt instead. Network errors/timeouts are left to LLMService's short retry loop.
    """

    name = "grok"

    def __init__(self) -> None:
        import httpx

        s = get_settings()
        key = s.xai_api_key.get_secret_value()
        if not key:
            raise LLMConfigError("XAI_API_KEY is not configured")
        self.model = s.xai_model
        self.reasoning_effort = s.xai_reasoning_effort.strip().lower()
        self._client = httpx.Client(base_url=s.xai_base_url.rstrip("/"),
                                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                    timeout=httpx.Timeout(s.llm_timeout_seconds, connect=10.0))
        self._no_schema: set[str] = set()  # schemas xAI refused in json_schema mode

    def _body(self, system: str, prompt: str, schema: type[BaseModel], temperature: float, use_schema: bool) -> dict:
        if not use_schema:
            prompt = f"{prompt}\n\nReturn ONLY a JSON object matching this JSON Schema:\n{json.dumps(schema.model_json_schema())}"
        body: dict = {"model": self.model, "store": False,
                      "input": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if self.reasoning_effort and self.reasoning_effort != "none":
            body["reasoning"] = {"effort": self.reasoning_effort}  # reasoning models ignore temperature
        else:
            body["temperature"] = temperature
        if use_schema:
            body["text"] = {"format": {"type": "json_schema", "name": schema.__name__,
                                       "schema": schema.model_json_schema(), "strict": True}}
        return body

    def complete_json(self, *, system: str, prompt: str, schema: type[BaseModel], temperature: float) -> str:
        use_schema = schema.__name__ not in self._no_schema
        resp = self._client.post("/responses", json=self._body(system, prompt, schema, temperature, use_schema))
        if resp.status_code == 400 and use_schema and not _is_auth_error(resp.text):
            log.warning("llm_schema_rejected", extra={"data": {"schema": schema.__name__, "detail": resp.text[:300]}})
            self._no_schema.add(schema.__name__)
            resp = self._client.post("/responses", json=self._body(system, prompt, schema, temperature, False))
        if resp.status_code in (400, 401, 403, 404):
            # Bad key, unknown XAI_MODEL, or a parameter the model refuses (try XAI_REASONING_EFFORT=none for
            # non-reasoning models). Retrying cannot fix these.
            raise LLMConfigError(f"xAI rejected the request ({resp.status_code}): {resp.text[:300]}")
        _raise_if_rate_limited(resp, "xAI")
        resp.raise_for_status()
        return _responses_text(resp.json())


class GroqProvider:
    """Groq (groq.com — keys start with "gsk_") over its OpenAI-compatible Chat Completions API.

    Very low latency. Best-effort json_schema output (strict mode would reject the optional fields in our schemas);
    if Groq refuses the schema (HTTP 400) we fall back to JSON-object mode with the schema in the prompt.
    """

    name = "groq"

    def __init__(self) -> None:
        import httpx

        s = get_settings()
        key = s.groq_api_key.get_secret_value()
        if not key:
            raise LLMConfigError("GROQ_API_KEY is not configured")
        self.model = s.groq_model
        self.reasoning_effort = s.groq_reasoning_effort.strip().lower()
        self._client = httpx.Client(base_url=s.groq_base_url.rstrip("/"),
                                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                    timeout=httpx.Timeout(s.llm_timeout_seconds, connect=10.0))
        self._no_schema: set[str] = set()

    def _body(self, system: str, prompt: str, schema: type[BaseModel], temperature: float, use_schema: bool) -> dict:
        if use_schema:
            fmt = {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}}
        else:
            prompt = f"{prompt}\n\nReturn ONLY a JSON object matching this JSON Schema:\n{json.dumps(schema.model_json_schema())}"
            fmt = {"type": "json_object"}
        body: dict = {"model": self.model, "temperature": temperature, "response_format": fmt,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if self.reasoning_effort and self.reasoning_effort != "none":
            body["reasoning_effort"] = self.reasoning_effort  # gpt-oss / qwen reasoning models
        return body

    def complete_json(self, *, system: str, prompt: str, schema: type[BaseModel], temperature: float) -> str:
        use_schema = schema.__name__ not in self._no_schema
        resp = self._client.post("/chat/completions", json=self._body(system, prompt, schema, temperature, use_schema))
        if resp.status_code == 400 and use_schema and not _is_auth_error(resp.text):
            log.warning("llm_schema_rejected", extra={"data": {"schema": schema.__name__, "detail": resp.text[:300]}})
            self._no_schema.add(schema.__name__)
            resp = self._client.post("/chat/completions", json=self._body(system, prompt, schema, temperature, False))
        if resp.status_code in (400, 401, 403, 404):
            # Bad key, unknown GROQ_MODEL, or a parameter the model refuses (try GROQ_REASONING_EFFORT=none for
            # non-reasoning models such as llama). Retrying cannot fix these.
            raise LLMConfigError(f"Groq rejected the request ({resp.status_code}): {resp.text[:300]}")
        _raise_if_rate_limited(resp, "Groq")
        resp.raise_for_status()
        choices = resp.json().get("choices") or []
        text = (choices[0].get("message") or {}).get("content") if choices else None
        if not text:
            raise LLMError("Groq returned no text")
        return text


def _is_auth_error(text: str) -> bool:
    low = text.lower()
    return "api key" in low or "api_key" in low or "unauthorized" in low


def _responses_text(data: dict) -> str:
    """Pull the assistant text out of a Responses API payload (reasoning items are skipped)."""
    if isinstance(data.get("output_text"), str) and data["output_text"]:
        return data["output_text"]
    parts = [c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
             for c in item.get("content", []) if c.get("type") in ("output_text", "text")]
    if not parts:
        raise LLMError(f"xAI returned no text (status: {data.get('status')})")
    return "".join(parts)


class GeminiProvider:
    """Optional legacy provider (LLM_PROVIDER=gemini, needs `pip install google-genai`).

    Gemini with resilience: schema mode → JSON mode on the same model → configured fallback models."""

    name = "gemini"

    def __init__(self) -> None:
        from google.genai import types

        from app.services.gemini_client import make_client

        s = get_settings()
        if not s.gemini_api_key.get_secret_value():
            raise LLMError("GEMINI_API_KEY is not configured")
        self._types = types
        self._client = make_client()
        self.model = s.gemini_model
        self.models = [s.gemini_model] + [m.strip() for m in s.gemini_fallback_models.split(",") if m.strip()]

    def _call(self, model: str, system: str, prompt: str, schema: type[BaseModel], temperature: float, use_schema: bool) -> str:
        types = self._types
        if use_schema:
            cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                              response_mime_type="application/json", response_schema=schema)
            contents = prompt
        else:
            cfg = types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                              response_mime_type="application/json")
            contents = f"{prompt}\n\nReturn ONLY JSON matching this JSON Schema:\n{json.dumps(schema.model_json_schema())}"
        resp = self._client.models.generate_content(model=model, contents=contents, config=cfg)
        return resp.text or ""

    def complete_json(self, *, system: str, prompt: str, schema: type[BaseModel], temperature: float) -> str:
        last: Exception | None = None
        for model in self.models:
            for use_schema in (True, False):
                try:
                    out = self._call(model, system, prompt, schema, temperature, use_schema)
                    if model != self.model or not use_schema:
                        log.info("llm_fallback_used", extra={"data": {"model": model, "schema_mode": use_schema}})
                    return out
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    msg = str(exc)
                    busy = "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "RESOURCE_EXHAUSTED" in msg
                    log.warning("llm_attempt_failed", extra={"data": {"model": model, "schema_mode": use_schema,
                                                                      "busy": busy, "detail": _safe_detail(exc)}})
                    if busy:
                        break  # this model is overloaded: move to the next model instead of the other mode
        raise last if last else LLMError("No Gemini model available")


class LLMService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.settings = get_settings()

    def generate_structured(self, *, system: str, prompt: str, schema: type[T], temperature: float = 0.3,
                            purpose: str = "generic") -> T:
        from app.services.rate_limit import wait_for_slot

        attempts = self.settings.llm_max_retries + 1
        last_err: Exception | None = None
        for attempt in range(1, attempts + 1):
            if self.provider.name == "gemini":
                wait_for_slot("llm:gemini", self.settings.llm_rate_limit_per_minute)
            started = time.monotonic()
            try:
                raw = self.provider.complete_json(system=system, prompt=prompt, schema=schema, temperature=temperature)
                result = schema.model_validate_json(_strip_fences(raw))
                log.info("llm_call", extra={"data": {"purpose": purpose, "provider": self.provider.name,
                                                     "model": self.provider.model, "attempt": attempt,
                                                     "ms": int((time.monotonic() - started) * 1000)}})
                return result
            except ValidationError as exc:
                last_err = exc
                log.warning("llm_malformed_output", extra={"data": {"purpose": purpose, "attempt": attempt,
                                                                    "errors": exc.error_count()}})
                prompt = f"{prompt}\n\nYour previous reply did not match the required JSON schema. Reply with valid JSON only."
            except LLMConfigError:
                raise  # wrong key/model: fail fast instead of burning the interview clock on retries
            except Exception as exc:  # noqa: BLE001 — network/timeouts/provider errors
                last_err = exc
                log.warning("llm_provider_error", extra={"data": {"purpose": purpose, "attempt": attempt,
                                                                  "error": type(exc).__name__,
                                                                  "ms": int((time.monotonic() - started) * 1000),
                                                                  "detail": _safe_detail(exc)}})
                if attempt < attempts:
                    # Rate limited: wait what the provider asks (capped so a live turn never stalls for long);
                    # otherwise a short pause.
                    wait = min(exc.retry_after, self.settings.llm_rate_limit_max_wait_seconds) \
                        if isinstance(exc, LLMRateLimited) else min(2 * attempt, 5)
                    time.sleep(wait)
        raise LLMError(f"LLM call failed for {purpose}") from last_err


def _safe_detail(exc: Exception) -> str:
    """Provider error text for diagnosis, with anything that looks like an API key removed."""
    import re

    return re.sub(r"(AIza|AQ\.|xai-|gsk_)[A-Za-z0-9_\-.]{8,}", "***", str(exc))[:500]


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


class ScriptedProvider:
    """Deterministic provider for tests: returns queued JSON or a callable's output per schema name."""

    name = "scripted"
    model = "scripted"

    def __init__(self, handlers: dict[str, object] | None = None) -> None:
        self.handlers = handlers or {}
        self.calls: list[dict] = []

    def complete_json(self, *, system: str, prompt: str, schema: type[BaseModel], temperature: float) -> str:
        self.calls.append({"schema": schema.__name__, "prompt": prompt})
        h = self.handlers.get(schema.__name__)
        if h is None:
            raise LLMError(f"No scripted response for {schema.__name__}")
        out = h(prompt) if callable(h) else h
        return out if isinstance(out, str) else json.dumps(out)


_override: LLMService | None = None


def set_llm(service: LLMService | None) -> None:
    global _override
    _override = service


@lru_cache
def _default() -> LLMService:
    provider = get_settings().llm_provider.strip().lower()
    if provider in ("grok", "xai"):
        return LLMService(GrokProvider())
    if provider == "groq":
        return LLMService(GroqProvider())
    if provider == "gemini":
        return LLMService(GeminiProvider())
    raise LLMError(f"Unknown LLM_PROVIDER '{provider}'")


def get_llm() -> LLMService:
    return _override or _default()
