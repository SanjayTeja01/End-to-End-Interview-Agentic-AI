from __future__ import annotations

import logging

from app.services.llm import LLMService, get_llm

SYSTEM_GUARDRAILS = (
    "You are part of an institution-controlled AI interview platform. Be professional and factual. "
    "Never invent facts about the candidate. Never infer personality, emotion, appearance or any protected "
    "attribute. Base every judgement only on the provided text. Output must follow the JSON schema exactly. "
    "Do not reveal internal reasoning; give concise evidence-based explanations only."
)


class Agent:
    name = "agent"

    def __init__(self, llm: LLMService | None = None) -> None:
        self._llm = llm
        self.log = logging.getLogger(f"agents.{self.name}")

    @property
    def llm(self) -> LLMService:
        return self._llm or get_llm()
