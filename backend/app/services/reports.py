"""Report data assembly and PDF export (stored in MinIO, never in the project folder)."""
from __future__ import annotations

import io
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Answer, Evaluation, Question, Report
from app.services.files import store_generated
from storage.minio.keys import report_key


def session_questions(db: Session, session_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(Question, Answer, Evaluation)
        .outerjoin(Answer, Answer.question_id == Question.id)
        .outerjoin(Evaluation, Evaluation.answer_id == Answer.id)
        .where(Question.session_id == session_id).order_by(Question.sequence)).all()
    out = []
    for q, a, e in rows:
        out.append({
            "id": str(q.id), "sequence": q.sequence, "text": q.text, "topic": q.topic, "skill": q.skill,
            "difficulty": q.difficulty, "question_type": q.question_type,
            "reason": (q.context_meta or {}).get("decision", {}).get("reason"),
            "transcript": a.transcript if a else None, "answer_status": a.status if a else None,
            "evaluation": None if e is None else {
                "overall_score": e.overall_score, "band": e.band, "confidence": e.confidence,
                "criteria": {c: getattr(e, c) for c in ("technical_correctness", "relevance", "completeness",
                                                       "clarity", "depth", "communication")},
                "strengths": e.strengths, "weaknesses": e.weaknesses, "missing_concepts": e.missing_concepts,
                "improvement_actions": e.improvement_actions, "suggested_answer_structure": e.suggested_answer_structure,
                "practice_topics": e.practice_topics, "next_question_reason": e.next_question_reason,
                "evidence": e.evidence,
            },
        })
    return out


def render_pdf(content: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Interview Report")
    ss = getSampleStyleSheet()
    esc = lambda s: str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    el = [Paragraph(f"Interview Report — {esc(content['interview']['name'])}", ss["Title"]),
          Paragraph(f"Candidate: {esc(content['candidate'].get('name'))} · Role: {esc(content['interview']['target_role'])}", ss["Normal"]),
          Spacer(1, 6),
          Paragraph(f"<b>Overall score:</b> {content.get('overall_score')}/100 &nbsp; "
                    f"<b>Readiness:</b> {content['readiness'].get('overall')}/100 ({esc(content['readiness'].get('level', '')).replace('_', ' ')})", ss["Normal"]),
          Spacer(1, 6), Paragraph(esc(content.get("summary")), ss["BodyText"]), Spacer(1, 8)]
    crit = content.get("criterion_scores") or {}
    if crit:
        t = Table([["Criterion", "Score"]] + [[k.replace("_", " ").title(), f"{v:.0f}" if v is not None else "–"] for k, v in crit.items()],
                  colWidths=[90 * mm, 30 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        el += [Paragraph("Criterion scores", ss["Heading2"]), t]
    for title, key in (("Strengths", "strengths"), ("Weaknesses", "weaknesses"), ("Missing concepts", "missing_concepts")):
        if content.get(key):
            el.append(Paragraph(title, ss["Heading2"]))
            el += [Paragraph(f"• {esc(x)}", ss["BodyText"]) for x in content[key]]
    if content.get("recommendations"):
        el.append(Paragraph("Improvement recommendations", ss["Heading2"]))
        el += [Paragraph(f"• <b>{esc(r['area'])}</b>: {esc(r['recommendation'])}", ss["BodyText"]) for r in content["recommendations"]]
    el.append(Paragraph("Questions", ss["Heading2"]))
    for q in content.get("questions", []):
        el.append(Paragraph(f"<b>Q{q['sequence']}</b> [{esc(q.get('topic'))} · {q['difficulty']}] — score {q.get('score')}", ss["BodyText"]))
        el.append(Paragraph(esc(q["question"]), ss["BodyText"]))
    el += [Spacer(1, 6), Paragraph("Final assessment", ss["Heading2"]), Paragraph(esc(content.get("final_assessment")), ss["BodyText"]),
           Spacer(1, 6), Paragraph(f"<i>{esc(content.get('disclaimer'))}</i>", ss["Italic"])]
    doc.build(el)
    return buf.getvalue()


def export_report(db: Session, report_id: uuid.UUID) -> uuid.UUID:
    report = db.get(Report, report_id)
    pdf = render_pdf(report.content)
    key = report_key(report.institute_id, report.candidate_id, report.interview_id, report.version)
    f = store_generated(db, pdf, key=key, mime="application/pdf", owner_id=report.candidate_id,
                        institute_id=report.institute_id, file_type="report", filename="interview-report.pdf")
    report.file_id = f.id
    report.export_status = "completed"
    db.flush()
    return f.id
