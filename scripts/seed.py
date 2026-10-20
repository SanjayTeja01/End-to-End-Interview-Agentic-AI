#!/usr/bin/env python
"""Optional SYNTHETIC demo data. Every name, email and document here is fake.

    docker compose exec backend python /app/scripts/seed.py

Creates: a demo institution, an institution admin, two students, a role, an approved + active interview and two
knowledge documents (indexed through the normal RAG pipeline). Credentials are printed once; change them after use.
"""
from __future__ import annotations

import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
for candidate in (ROOT / "backend", pathlib.Path("/app")):
    if (candidate / "app").exists():
        sys.path.insert(0, str(candidate))
        break

DOCS = {
    "AI/ML Interview Guidelines": ("interview_guideline", "AI/ML Engineer", b"""# AI/ML interview guidelines (synthetic)

Probe understanding of the bias-variance trade-off, overfitting and regularisation.

Strong candidates explain how they evaluate models: train/validation/test splits, cross-validation, and metrics such as
precision, recall, F1 and ROC-AUC, and when each is appropriate for imbalanced data.

For system design, ask how a model is served, monitored for drift and retrained.
"""),
    "Evaluation rubric notes": ("evaluation_guideline", None, b"""# Evaluation notes (synthetic)

Reward answers that state assumptions, give a concrete example and discuss trade-offs.
Do not reward buzzwords without explanation.
"""),
}


def main() -> int:
    from sqlalchemy import select

    from app.api.deps import CurrentUser
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models import CandidateProfile, Institution, User
    from app.models.enums import UserRole
    from app.schemas.interview import InterviewCreate, RequiredSkillIn
    from app.services import interviews, knowledge
    from rag.ingestion.pipeline import ingest_version

    db = SessionLocal()
    try:
        if db.execute(select(Institution).where(Institution.slug == "demo-institute")).scalar_one_or_none():
            print("Demo data already present.")
            return 0
        inst = Institution(name="Demo Institute of Technology (synthetic)", slug="demo-institute", join_code="DEMO2026")
        db.add(inst)
        db.flush()
        password = secrets.token_urlsafe(10)
        admin = User(institute_id=inst.id, email="admin@demo.example", password_hash=hash_password(password),
                     full_name="Demo Admin", role=UserRole.INSTITUTION_ADMIN)
        db.add(admin)
        for i, roles in enumerate((["AI/ML Engineer", "Agentic AI Engineer"], ["DevOps Engineer"]), start=1):
            u = User(institute_id=inst.id, email=f"student{i}@demo.example", password_hash=hash_password(password),
                     full_name=f"Demo Student {i}", role=UserRole.STUDENT)
            db.add(u)
            db.flush()
            db.add(CandidateProfile(user_id=u.id, institute_id=inst.id, target_roles=roles))
        db.flush()
        cu = CurrentUser(id=admin.id, institute_id=inst.id, role=admin.role, email=admin.email, full_name=admin.full_name)

        for title, (dtype, role, body) in DOCS.items():
            _, v = knowledge.create_document(db, cu, data=body, filename=f"{title}.md", title=title, document_type=dtype,
                                             description="Synthetic demo document", role=role, topic=None, skill=None,
                                             difficulty=None)
            db.commit()
            try:
                ingest_version(db, v.id)
            except Exception as exc:  # noqa: BLE001
                print(f"Indexing '{title}' failed ({exc}); re-run scripts/reindex_chroma.py once services are up.")

        iv, _ = interviews.create_interview(db, cu, InterviewCreate(
            name="AI/ML Engineer Interview (demo)", target_role="AI/ML Engineer",
            job_description="Design, train and evaluate ML models in Python; deploy and monitor them.",
            question_count=6, duration_minutes=25, interview_type="mixed",
            required_skills=[
                RequiredSkillIn(skill="Machine Learning", required_level=4, importance_weight=1.0,
                                topics=["Overfitting and regularisation", "Model evaluation metrics"]),
                RequiredSkillIn(skill="Python", required_level=3, importance_weight=0.7, topics=["Python for data processing"]),
                RequiredSkillIn(skill="MLOps", required_level=2, importance_weight=0.5, topics=["Model deployment and monitoring"]),
            ]))
        db.flush()
        interviews.activate(db, cu, iv.id)
        db.commit()
        print("Synthetic demo data created.")
        print(f"  Institution join code : {inst.join_code}")
        print(f"  Admin                 : admin@demo.example / {password}")
        print(f"  Students              : student1@demo.example, student2@demo.example / {password}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
