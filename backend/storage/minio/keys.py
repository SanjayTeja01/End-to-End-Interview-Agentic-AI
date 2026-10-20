"""Structured, private, institution-aware MinIO object keys. Postgres stores these keys — never public URLs."""
from __future__ import annotations

import re
import uuid

_EXT = re.compile(r"^[a-z0-9]{1,8}$")


def _ext(ext: str) -> str:
    e = ext.lower().lstrip(".")
    if not _EXT.match(e):
        raise ValueError(f"invalid extension {ext!r}")
    return e


def _id(v) -> str:  # noqa: ANN001
    return str(uuid.UUID(str(v)))  # validates and normalises


def resume_key(institute_id, candidate_id, ext: str) -> str:
    return f"resumes/{_id(institute_id)}/{_id(candidate_id)}/{uuid.uuid4()}.{_ext(ext)}"


def knowledge_key(institute_id, document_id, version: int, ext: str) -> str:
    return f"knowledge/{_id(institute_id)}/{_id(document_id)}/version-{int(version)}.{_ext(ext)}"


def interview_media_key(institute_id, interview_id, candidate_id, kind: str, ext: str) -> str:
    if kind not in ("audio", "video", "tts"):
        raise ValueError("kind must be audio, video or tts")
    return f"interviews/{_id(institute_id)}/{_id(interview_id)}/{_id(candidate_id)}/{kind}/{uuid.uuid4()}.{_ext(ext)}"


def report_key(institute_id, candidate_id, interview_id, version: int, ext: str = "pdf") -> str:
    return f"reports/{_id(institute_id)}/{_id(candidate_id)}/{_id(interview_id)}/report-v{int(version)}.{_ext(ext)}"


def key_institute(object_key: str) -> str | None:
    """Extract the institution id embedded in a key (defence-in-depth check before presigning)."""
    parts = object_key.split("/")
    if len(parts) >= 2:
        try:
            return str(uuid.UUID(parts[1]))
        except ValueError:
            return None
    return None
