"""Initial schema: identity, files, resumes, skills, roles, interviews, sessions, results, knowledge base.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
UUID = sa.Uuid(as_uuid=True)
TS = sa.DateTime(timezone=True)


def _id():
    return sa.Column("id", UUID, primary_key=True)


def _timestamps():
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def _created():
    return sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False)


def _fk(name, target, *, nullable=False, ondelete="CASCADE", index=False, unique=False):
    return sa.Column(name, UUID, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index, unique=unique)


def _inst(index=True):
    return _fk("institute_id", "institutions.id", index=index)


def _json(name, default="[]"):
    return sa.Column(name, JSON, nullable=False, server_default=sa.text(f"'{default}'"))


def upgrade() -> None:
    op.create_table(
        "institutions", _id(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("join_code", sa.String(32), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        _json("settings", "{}"),
        *_timestamps(),
    )
    op.create_table(
        "users", _id(),
        _fk("institute_id", "institutions.id", nullable=True, index=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", TS),
        *_timestamps(),
    )
    op.create_table(
        "candidate_profiles", _id(),
        _fk("user_id", "users.id", unique=True),
        _inst(),
        sa.Column("headline", sa.String(300)),
        sa.Column("summary", sa.Text()),
        _json("education"), _json("experience"), _json("projects"), _json("technical_skills"),
        _json("non_technical_skills"), _json("technologies"), _json("certifications"), _json("achievements"),
        _json("target_roles"), _json("preferences", "{}"),
        *_timestamps(),
    )
    op.create_table(
        "files", _id(),
        _fk("owner_id", "users.id", nullable=True, ondelete="SET NULL", index=True),
        _inst(index=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("file_type", sa.String(32), nullable=False),
        sa.Column("deleted_at", TS),
        *_timestamps(),
    )
    op.create_index("ix_files_institute_type", "files", ["institute_id", "file_type"])
    op.create_table(
        "jobs", _id(), _inst(),
        _fk("owner_id", "users.id", nullable=True, ondelete="SET NULL"),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("entity_id", UUID, index=True),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("error", sa.Text()),
        _json("result", "{}"),
        *_timestamps(),
    )
    op.create_table(
        "resumes", _id(),
        _fk("candidate_id", "users.id", index=True), _inst(),
        _fk("file_id", "files.id", ondelete="RESTRICT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="pending"),
        _json("extraction_meta", "{}"), _json("sections", "{}"), _json("analysis", "{}"),
        sa.Column("error", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("candidate_id", "version", name="uq_resume_candidate_version"),
    )
    op.create_table(
        "candidate_skills", _id(),
        _fk("candidate_id", "users.id", index=True), _inst(),
        sa.Column("skill", sa.String(120), nullable=False),
        sa.Column("skill_key", sa.String(120), nullable=False),
        sa.Column("proficiency", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        _json("evidence"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        *_timestamps(),
        sa.UniqueConstraint("candidate_id", "skill_key", "source", name="uq_candidate_skill_source"),
        sa.CheckConstraint("proficiency BETWEEN 0 AND 5", name="ck_candidate_skill_level"),
    )
    op.create_table(
        "roles", _id(), _inst(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("normalized_name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        _json("metadata", "{}"),
        *_timestamps(),
        sa.UniqueConstraint("institute_id", "normalized_name", name="uq_role_institute_name"),
    )
    op.create_table(
        "interviews", _id(), _inst(),
        _fk("role_id", "roles.id", ondelete="RESTRICT", index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_role", sa.String(160), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("start_time", TS),
        sa.Column("end_time", TS),
        sa.Column("interview_type", sa.String(20), nullable=False, server_default="technical"),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("initial_difficulty", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("adaptive_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
        _json("evaluation_config", "{}"), _json("readiness_config", "{}"), _json("eligibility_config", "{}"),
        _json("knowledge_document_ids"),
        sa.Column("record_media", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft", index=True),
        sa.Column("skill_approval_state", sa.String(20), nullable=False, server_default="not_required"),
        _fk("created_by", "users.id", nullable=True, ondelete="SET NULL"),
        *_timestamps(),
        sa.CheckConstraint("question_count BETWEEN 1 AND 50", name="ck_interview_question_count"),
        sa.CheckConstraint("duration_minutes BETWEEN 5 AND 240", name="ck_interview_duration"),
    )
    op.create_table(
        "role_skills", _id(),
        _fk("role_id", "roles.id", index=True),
        _fk("interview_id", "interviews.id", nullable=True, index=True),
        _inst(),
        sa.Column("skill", sa.String(120), nullable=False),
        sa.Column("skill_key", sa.String(120), nullable=False),
        sa.Column("required_level", sa.Integer(), nullable=False),
        sa.Column("importance_weight", sa.Float(), nullable=False, server_default="1.0"),
        _json("topics"), _json("question_categories"),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("rationale", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("role_id", "interview_id", "skill_key", name="uq_role_skill"),
        sa.CheckConstraint("required_level BETWEEN 0 AND 5", name="ck_role_skill_level"),
    )
    op.create_table(
        "skill_gaps", _id(),
        _fk("candidate_id", "users.id", index=True),
        _fk("role_id", "roles.id"),
        _fk("interview_id", "interviews.id", nullable=True),
        _inst(),
        sa.Column("skill", sa.String(120), nullable=False),
        sa.Column("skill_key", sa.String(120), nullable=False),
        sa.Column("required_level", sa.Integer(), nullable=False),
        sa.Column("candidate_level", sa.Float(), nullable=False),
        sa.Column("gap", sa.Float(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        _json("evidence"),
        sa.Column("computed_at", TS, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "role_id", "interview_id", "skill_key", name="uq_skill_gap"),
    )
    op.create_table(
        "interview_candidates", _id(),
        _fk("interview_id", "interviews.id", index=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("eligibility_status", sa.String(20), nullable=False, server_default="eligible"),
        sa.Column("eligibility_reason", sa.Text()),
        sa.Column("match_score", sa.Float()),
        sa.Column("participation_status", sa.String(20), nullable=False, server_default="not_started"),
        _fk("invited_by", "users.id", nullable=True, ondelete="SET NULL"),
        *_timestamps(),
        sa.UniqueConstraint("interview_id", "candidate_id", name="uq_interview_candidate"),
    )
    op.create_table(
        "interview_sessions", _id(),
        _fk("interview_id", "interviews.id", index=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("status", sa.String(20), nullable=False, server_default="initializing", index=True),
        sa.Column("started_at", TS),
        sa.Column("ended_at", TS),
        sa.Column("current_question_id", UUID),  # FK added after questions table exists
        sa.Column("current_topic", sa.String(160)),
        sa.Column("current_difficulty", sa.String(10)),
        sa.Column("question_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        _json("state", "{}"), _json("connection", "{}"),
        sa.Column("termination_reason", sa.String(64)),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.UniqueConstraint("interview_id", "candidate_id", name="uq_session_interview_candidate"),
    )
    op.create_table(
        "questions", _id(),
        _fk("session_id", "interview_sessions.id", index=True),
        _fk("interview_id", "interviews.id"),
        _inst(),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("spoken_text", sa.Text()),
        sa.Column("topic", sa.String(160)),
        sa.Column("skill", sa.String(120)),
        sa.Column("difficulty", sa.String(10), nullable=False),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("role", sa.String(160)),
        sa.Column("source", sa.String(32), nullable=False, server_default="generated"),
        _json("context_meta", "{}"),
        _fk("tts_file_id", "files.id", nullable=True, ondelete="SET NULL"),
        sa.Column("asked_at", TS),
        _created(),
        sa.UniqueConstraint("session_id", "sequence", name="uq_question_sequence"),
    )
    op.create_foreign_key("fk_session_current_question", "interview_sessions", "questions",
                          ["current_question_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "answers", _id(),
        _fk("question_id", "questions.id", unique=True),
        _fk("session_id", "interview_sessions.id", index=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("transcript", sa.Text()),
        sa.Column("started_at", TS),
        sa.Column("ended_at", TS),
        sa.Column("duration_seconds", sa.Float()),
        _fk("audio_file_id", "files.id", nullable=True, ondelete="SET NULL"),
        _fk("video_file_id", "files.id", nullable=True, ondelete="SET NULL"),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("idempotency_key", sa.String(80), nullable=False, unique=True),
        _json("metadata", "{}"),
        sa.Column("error", sa.Text()),
        *_timestamps(),
    )
    op.create_table(
        "evaluations", _id(),
        _fk("answer_id", "answers.id", unique=True),
        _fk("question_id", "questions.id"),
        _fk("session_id", "interview_sessions.id", index=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("topic", sa.String(160)),
        sa.Column("skill", sa.String(120)),
        sa.Column("difficulty", sa.String(10), nullable=False),
        *[sa.Column(c, sa.Float(), nullable=False) for c in (
            "technical_correctness", "relevance", "completeness", "clarity", "depth", "communication",
            "overall_score", "confidence")],
        sa.Column("band", sa.String(10), nullable=False),
        _json("strengths"), _json("weaknesses"), _json("missing_concepts"), _json("improvement_actions"),
        sa.Column("suggested_answer_structure", sa.Text()),
        _json("practice_topics"),
        sa.Column("next_question_reason", sa.Text()),
        _json("evidence", "{}"), _json("rubric_weights", "{}"),
        sa.Column("rubric_version", sa.String(20), nullable=False),
        _created(),
    )
    op.create_table(
        "performance", _id(),
        _fk("session_id", "interview_sessions.id", unique=True),
        _fk("interview_id", "interviews.id", index=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("role_name", sa.String(160), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        _json("criterion_scores", "{}"), _json("topic_performance", "{}"), _json("skill_performance", "{}"),
        _json("difficulty_progression"),
        sa.Column("method_version", sa.String(20), nullable=False),
        _created(),
    )
    op.create_table(
        "readiness", _id(),
        _fk("session_id", "interview_sessions.id", nullable=True, unique=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        _fk("role_id", "roles.id", nullable=True, ondelete="SET NULL"),
        sa.Column("role_name", sa.String(160), nullable=False),
        _json("components", "{}"),
        sa.Column("overall", sa.Float(), nullable=False),
        sa.Column("level", sa.String(32), nullable=False),
        _json("evidence", "{}"), _json("weights", "{}"),
        sa.Column("method_version", sa.String(20), nullable=False),
        sa.Column("assessed_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "reports", _id(),
        _fk("session_id", "interview_sessions.id", index=True),
        _fk("interview_id", "interviews.id", index=True),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _json("content", "{}"),
        _fk("file_id", "files.id", nullable=True, ondelete="SET NULL"),
        sa.Column("export_status", sa.String(20), nullable=False, server_default="pending"),
        _json("metadata", "{}"),
        _created(),
        sa.UniqueConstraint("session_id", "version", name="uq_report_session_version"),
    )
    op.create_table(
        "interview_history", _id(),
        _fk("session_id", "interview_sessions.id", unique=True),
        _fk("interview_id", "interviews.id"),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        sa.Column("role_name", sa.String(160), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        _json("weak_topics"), _json("strong_topics"), _json("difficulty_responses"),
        _json("question_summaries"), _json("repeated_mistakes"),
        sa.Column("completed_at", TS, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "interview_recommendations", _id(),
        _fk("candidate_id", "users.id", index=True),
        _inst(),
        _fk("session_id", "interview_sessions.id", nullable=True, index=True),
        sa.Column("area", sa.String(160), nullable=False),
        sa.Column("area_type", sa.String(20), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _json("evidence", "{}"),
        sa.Column("priority", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        _created(),
    )
    op.create_table(
        "knowledge_documents", _id(), _inst(),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("document_type", sa.String(40), nullable=False),
        sa.Column("role", sa.String(160)),
        sa.Column("topic", sa.String(160)),
        sa.Column("skill", sa.String(120)),
        sa.Column("difficulty", sa.String(10)),
        _fk("source_file_id", "files.id", nullable=True, ondelete="SET NULL"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        _fk("created_by", "users.id", nullable=True, ondelete="SET NULL"),
        *_timestamps(),
    )
    op.create_table(
        "knowledge_document_versions", _id(),
        _fk("document_id", "knowledge_documents.id", index=True),
        _inst(),
        sa.Column("version", sa.Integer(), nullable=False),
        _fk("source_file_id", "files.id", ondelete="RESTRICT"),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("indexing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(120)),
        sa.Column("embedding_version", sa.String(40)),
        sa.Column("error", sa.Text()),
        _created(),
        sa.Column("indexed_at", TS),
        sa.UniqueConstraint("document_id", "version", name="uq_doc_version"),
    )


def downgrade() -> None:
    op.drop_constraint("fk_session_current_question", "interview_sessions", type_="foreignkey")
    for table in (
        "knowledge_document_versions", "knowledge_documents", "interview_recommendations", "interview_history",
        "reports", "readiness", "performance", "evaluations", "answers", "questions", "interview_sessions",
        "interview_candidates", "skill_gaps", "role_skills", "interviews", "roles", "candidate_skills",
        "resumes", "jobs", "files", "candidate_profiles", "users", "institutions",
    ):
        op.drop_table(table)
