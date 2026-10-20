"""Small text helpers shared by domain logic."""
from __future__ import annotations

import re

_ALIASES = {
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "llm": "large language models",
    "llms": "large language models",
    "genai": "generative ai",
}


def normalize_key(value: str) -> str:
    """Canonical key for skill / role / topic matching ("Machine-Learning " -> "machine learning")."""
    v = re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()
    v = re.sub(r"\s+", " ", v)
    return _ALIASES.get(v, v)


def tokens(value: str) -> set[str]:
    stop = {"and", "or", "the", "of", "a", "an", "for", "to", "in", "engineer", "developer"}
    return {t for t in normalize_key(value).replace("/", " ").split() if t and t not in stop}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
