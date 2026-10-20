"""RAG Knowledge Agent — decides when retrieval is useful and retrieves tenant-filtered context."""
from __future__ import annotations

from app.agents.base import Agent
from rag.retrieval.retriever import hits_to_context, retrieve


class RAGKnowledgeAgent(Agent):
    name = "rag_knowledge"

    @staticmethod
    def needs_retrieval(state: dict) -> bool:
        decision = state.get("decision") or {}
        if not state.get("knowledge_available"):
            return False
        if decision.get("action") != "ask":
            return False
        # Retrieve for new topics and deeper follow-ups; foundational follow-ups reuse prior context.
        if decision.get("category") == "behavioral" and not state.get("has_behavioral_guidelines"):
            return False
        return decision.get("kind") in ("new_topic", "follow_up_deeper") or not state.get("retrieved_context")

    def retrieve_for_topic(self, state: dict) -> dict:
        d = state["decision"]
        query = f"{state['target_role']} interview: {d.get('topic')} ({d.get('skill') or ''}) {d.get('difficulty')}"
        hits = retrieve(institute_id=state["institution_id"], query=query, role=state["target_role"],
                        topic=d.get("topic"), skill=d.get("skill"),
                        doc_ids=state["interview_config"].get("knowledge_document_ids") or None, k=4)
        context, sources = hits_to_context(hits, max_chars=3500)
        return {"retrieved_context": context, "retrieved_sources": sources}

    def retrieve_for_requirements(self, *, institute_id: str, role: str, job_description: str, doc_ids=None) -> tuple[str, list]:  # noqa: ANN001
        hits = retrieve(institute_id=institute_id, query=f"{role} required skills responsibilities {job_description[:500]}",
                        role=role, doc_ids=doc_ids, k=6)
        return hits_to_context(hits, max_chars=6000)
