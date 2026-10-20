from tests.conftest import register_institution


def _upload(client, inst, text: bytes, **meta):
    data = {"title": meta.pop("title", "Guide"), "document_type": meta.pop("document_type", "technical"), **meta}
    r = client.post("/knowledge/documents", headers=inst["h"], data=data, files={"file": ("doc.md", text, "text/markdown")})
    assert r.status_code == 202, r.text
    return r.json()


def test_ingest_retrieve_version_delete_reindex(client, _services):
    vectors = _services["vectors"]
    inst = register_institution(client)
    body = _upload(client, inst, b"# Indexing\n\nB-tree and B+ tree indexes speed up range queries.\n\nHash indexes suit equality.",
                   role="Software Engineer", topic="Database indexing")
    doc_id = body["document"]["id"]
    assert body["job"]["status"] == "completed"
    detail = client.get(f"/knowledge/documents/{doc_id}", headers=inst["h"]).json()
    v1 = detail["latest"]
    assert v1["indexing_status"] == "completed" and v1["chunk_count"] >= 1 and v1["embedding_model"] == "hash-bow"
    meta = next(iter(vectors.rows.values()))[2]
    for key in ("doc_id", "institute_id", "source_key", "version", "chunk_id", "embedding_model", "embedding_version",
                "source_title", "topic", "role", "content_type"):
        assert key in meta, key
    assert meta["source_key"].startswith(f"knowledge/{inst['me']['institute_id']}/{doc_id}/version-1")

    hits = client.post("/rag/query", headers=inst["h"], json={"query": "B+ tree range queries", "role": "Software Engineer"}).json()
    assert hits and hits[0]["doc_id"] == doc_id

    # New version replaces the old vectors
    r = client.post(f"/knowledge/documents/{doc_id}/versions", headers=inst["h"],
                    files={"file": ("doc.md", b"Version two talks about LSM trees and compaction.", "text/markdown")})
    assert r.status_code == 202
    assert all(m["version"] == 2 for _, _, m in vectors.rows.values())
    versions = client.get(f"/knowledge/documents/{doc_id}", headers=inst["h"]).json()["versions"]
    assert [v["indexing_status"] for v in versions] == ["completed", "superseded"]

    # Disposable index: wipe and rebuild from Postgres + MinIO
    before = vectors.count()
    vectors.reset()
    assert vectors.count() == 0
    from app.core.database import SessionLocal
    from rag.reindexing.reindex import reindex_all

    db = SessionLocal()
    summary = reindex_all(db, reset=True)
    db.close()
    assert summary["indexed"] == 1 and vectors.count() == before

    # Deletion removes vectors
    assert client.delete(f"/knowledge/documents/{doc_id}", headers=inst["h"]).status_code == 204
    assert vectors.count() == 0
    assert client.get("/knowledge/documents", headers=inst["h"]).json() == []


def test_deactivated_document_not_retrieved(client, _services):
    inst = register_institution(client)
    doc_id = _upload(client, inst, b"Kubernetes pods and deployments explained.")["document"]["id"]
    client.put(f"/knowledge/documents/{doc_id}", headers=inst["h"], json={"status": "inactive"})
    hits = client.post("/rag/query", headers=inst["h"], json={"query": "kubernetes pods"}).json()
    assert hits == []


def test_rejects_unsupported_upload(client):
    inst = register_institution(client)
    r = client.post("/knowledge/documents", headers=inst["h"], data={"title": "x", "document_type": "technical"},
                    files={"file": ("x.exe", b"MZ\x90\x00\x03\x00\x00\x00\xff\xfe\x00\x81", "application/pdf")})
    assert r.status_code == 422
