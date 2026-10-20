"""Resume Analyzer Agent — structured extraction with anti-hallucination evidence checks."""
from __future__ import annotations

import re

from app.agents.base import SYSTEM_GUARDRAILS, Agent
from app.agents.schemas import EvidencedSkill, ResumeAnalysis

SECTION_PATTERNS = {
    "education": r"education|academic|qualifications",
    "experience": r"experience|employment|work history|internships?",
    "projects": r"projects?|personal projects|academic projects",
    "skills": r"skills|technical skills|core competencies|technologies|tools",
    "certifications": r"certifications?|licenses|courses",
    "achievements": r"achievements|awards|honou?rs|accomplishments",
    "summary": r"summary|objective|profile|about me",
}


def detect_sections(text: str) -> dict[str, str]:
    """Deterministic heading-based section detection."""
    lines = text.split("\n")
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        stripped = line.strip().strip(":").strip()
        matched = None
        if 0 < len(stripped) <= 40:
            for name, pat in SECTION_PATTERNS.items():
                if re.fullmatch(rf"({pat})", stripped, re.I):
                    matched = name
                    break
        if matched:
            current = matched
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _supported(text_lower: str, skill: EvidencedSkill) -> bool:
    ev = re.sub(r"\s+", " ", skill.evidence.lower()).strip()
    return (skill.skill.lower() in text_lower) or (len(ev) >= 8 and ev[:60] in text_lower)


class ResumeAnalyzerAgent(Agent):
    name = "resume_analyzer"

    def analyze(self, text: str, sections: dict[str, str]) -> ResumeAnalysis:
        prompt = (
            "Extract a structured candidate profile from the resume below. Only include information explicitly "
            "present. For each skill give a short verbatim evidence quote and a conservative 0-5 level estimate "
            "(resume claims are evidence to investigate, not proof). Use null/empty lists when absent.\n\n"
            f"DETECTED SECTIONS: {', '.join(sections)}\n\nRESUME TEXT:\n{text[:24000]}"
        )
        result = self.llm.generate_structured(system=SYSTEM_GUARDRAILS, prompt=prompt, schema=ResumeAnalysis,
                                              temperature=0.1, purpose="resume_analysis")
        return self.verify(result, text)

    @staticmethod
    def verify(result: ResumeAnalysis, text: str) -> ResumeAnalysis:
        """Drop anything the model claims that is not grounded in the resume text."""
        low = re.sub(r"\s+", " ", text.lower())
        result.technical_skills = [s for s in result.technical_skills if _supported(low, s)]
        result.non_technical_skills = [s for s in result.non_technical_skills if _supported(low, s)]
        result.technologies = [t for t in result.technologies if t.lower() in low]
        result.certifications = [c for c in result.certifications if c.lower()[:25] in low]
        result.projects = [p for p in result.projects if p.name.lower()[:25] in low]
        result.education = [e for e in result.education if e.institution.lower()[:25] in low]
        result.experience = [e for e in result.experience if e.organization.lower()[:25] in low]
        return result
