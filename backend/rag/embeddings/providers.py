"""Embedding provider abstraction. Model + version are configuration and are stored with every vector."""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings


class EmbeddingProvider(Protocol):
    model: str
    version: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class GeminiEmbeddings:
    """Optional (EMBEDDING_PROVIDER=gemini, needs google-genai and GEMINI_API_KEY)."""

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        s = get_settings()
        self._types = types
        from app.services.gemini_client import make_client

        self._client = make_client()
        self.model = s.embedding_model
        self.version = s.embedding_version
        self.dims = s.embedding_dimensions

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        from app.services.rate_limit import wait_for_slot

        out: list[list[float]] = []
        for i in range(0, len(texts), 64):  # batch to stay within request limits
            wait_for_slot("llm:gemini:embed", get_settings().llm_rate_limit_per_minute)
            resp = self._client.models.embed_content(
                model=self.model, contents=texts[i:i + 64],
                config=self._types.EmbedContentConfig(task_type=task, output_dimensionality=self.dims))
            out.extend(_normalise(e.values) for e in resp.embeddings)
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class LocalEmbeddings:
    """all-MiniLM-L6-v2 (384-d) via the ONNX runtime that ships with chromadb. Runs on CPU, no API key or quota.
    The model (~80 MB) is baked into the Docker image at build time, otherwise downloaded on first use."""

    def __init__(self) -> None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        s = get_settings()
        self._fn = DefaultEmbeddingFunction()
        self.model = s.embedding_model if s.embedding_model and not s.embedding_model.startswith("gemini") \
            else "all-MiniLM-L6-v2"
        self.version = s.embedding_version
        self.dims = 384

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            out.extend(_normalise(v) for v in self._fn(texts[i:i + 64]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashEmbeddings:
    """Deterministic bag-of-words hashing embeddings — offline tests only, never production."""

    def __init__(self, dims: int = 256) -> None:
        self.model, self.version, self.dims = "hash-bow", "test", dims

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        for tok in text.lower().split():
            tok = "".join(ch for ch in tok if ch.isalnum())
            if tok:
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dims] += 1.0
        return _normalise(v)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def _normalise(v) -> list[float]:  # noqa: ANN001
    v = list(v)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


_override: EmbeddingProvider | None = None


def set_embeddings(p: EmbeddingProvider | None) -> None:
    global _override
    _override = p


@lru_cache
def _default() -> EmbeddingProvider:
    provider = get_settings().embedding_provider.strip().lower()
    if provider == "local":
        return LocalEmbeddings()
    if provider == "gemini":
        return GeminiEmbeddings()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER '{provider}'")


def get_embeddings() -> EmbeddingProvider:
    return _override or _default()
