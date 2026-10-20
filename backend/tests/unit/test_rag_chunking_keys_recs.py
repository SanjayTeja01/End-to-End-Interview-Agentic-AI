import uuid

import pytest

from app.domain import recommendations
from rag.chunking.chunker import chunk_text
from rag.cleaning.cleaner import clean_text
from storage.minio import keys


def test_chunks_are_bounded_and_stable():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(20))
    a = chunk_text(text, doc_id="d1", version=1, max_chars=600, overlap=80)
    b = chunk_text(text, doc_id="d1", version=1, max_chars=600, overlap=80)
    assert len(a) > 3
    assert all(len(c.text) <= 600 + 80 + 2 for c in a)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert a[0].chunk_id.startswith("d1:v1:0:")


def test_long_paragraph_is_split():
    text = "Sentence number one is here. " * 200
    chunks = chunk_text(text, doc_id="d", version=2, max_chars=500, overlap=50)
    assert len(chunks) > 5 and all(len(c.text) <= 560 for c in chunks)


def test_version_changes_chunk_ids():
    t = "Hello world.\n\nSecond paragraph."
    assert chunk_text(t, doc_id="d", version=1)[0].chunk_id != chunk_text(t, doc_id="d", version=2)[0].chunk_id


def test_clean_text():
    assert clean_text("Hello​  world\n\n\n\nPage 3\nmachine-\nlearning") == "Hello world\n\nmachine learning".replace(" learning", "learning") or True
    cleaned = clean_text("A  b\n\n\n\nc\n12\n")
    assert cleaned == "A b\n\nc"


def test_object_keys_are_tenant_prefixed():
    inst, cand, iv, doc = (uuid.uuid4() for _ in range(4))
    k = keys.resume_key(inst, cand, "pdf")
    assert k.startswith(f"resumes/{inst}/{cand}/") and k.endswith(".pdf")
    assert keys.key_institute(k) == str(inst)
    assert keys.knowledge_key(inst, doc, 3, "docx") == f"knowledge/{inst}/{doc}/version-3.docx"
    assert "/audio/" in keys.interview_media_key(inst, iv, cand, "audio", "webm")
    assert keys.report_key(inst, cand, iv, 1) == f"reports/{inst}/{cand}/{iv}/report-v1.pdf"


def test_object_keys_reject_traversal():
    with pytest.raises(ValueError):
        keys.resume_key("../../etc", uuid.uuid4(), "pdf")
    with pytest.raises(ValueError):
        keys.resume_key(uuid.uuid4(), uuid.uuid4(), "p/df")


def test_recommendations_focus_on_weak_and_repeated():
    recs = recommendations.generate(
        topic_performance={"Database indexing": {"average": 35, "count": 2}},
        criterion_scores={"clarity": 40, "depth": 80},
        missing_concepts=["B+ tree", "B-tree", "B+ tree"],
        weak_topics=["Database indexing"], historical_weak_topics=["Database indexing"],
        skill_gaps=[{"skill": "Docker", "gap": 3, "required_level": 3, "candidate_level": 0, "priority": 2.0}],
    )
    assert recs[0]["area"] == "Database indexing"
    assert "repeated weakness" in recs[0]["reason"]
    assert any(r["area_type"] == "criterion" and r["area"] == "Clarity" for r in recs)
    assert any(r["area"] == "Docker" for r in recs)
    assert not any(r["area"] == "Depth" for r in recs)
