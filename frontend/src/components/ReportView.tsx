"use client";

import { Download } from "lucide-react";
import { BarsChart, DifficultyChart } from "./charts";
import { Badge, Button, Card, Empty, ErrorBox, Spinner, Stat } from "./ui";
import { label, pct } from "@/lib/format";
import type { QuestionDetail, Report } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export function ReportView({ sessionId }: { sessionId: string }) {
  const rep = useApi<Report>(`/interview/${sessionId}/report`);
  const qs = useApi<QuestionDetail[]>(`/interview/${sessionId}/questions`);
  if (rep.loading) return <Spinner />;
  if (rep.error) return <ErrorBox message={rep.error === "Report not available yet" ? "The report is still being generated — check back shortly." : rep.error} onRetry={rep.reload} />;
  const c = rep.data!.content;
  const crit = Object.entries(c.criterion_scores ?? {}).map(([k, v]) => ({ criterion: label(k), score: v ?? 0 }));
  const topics = Object.entries(c.topic_performance ?? {}).map(([k, v]) => ({ topic: k, score: v.average ?? 0 }));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{c.interview.name}</h1>
          <p className="text-sm muted">{c.candidate.name} · {c.interview.target_role} · {label(c.interview.type)}</p>
        </div>
        {rep.data!.download_url && <a href={rep.data!.download_url} target="_blank" rel="noreferrer"><Button variant="secondary"><Download className="h-4 w-4" /> PDF</Button></a>}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Overall score" value={pct(c.overall_score, 1)} hint="out of 100" />
        <Stat label="Readiness" value={pct(c.readiness.overall, 0)} hint={label(c.readiness.level)} />
        <Stat label="Questions" value={c.questions.length} />
        <Stat label="Ended because" value={<span className="text-base">{label(c.stop_reason)}</span>} />
      </div>
      <Card title="Summary"><p className="text-sm">{c.summary}</p><p className="mt-3 text-sm">{c.final_assessment}</p>
        <p className="mt-3 text-xs faint">{c.disclaimer}</p></Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Score by rubric criterion"><BarsChart data={crit} x="criterion" y="score" /></Card>
        <Card title="Score by topic"><BarsChart data={topics} x="topic" y="score" /></Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Strengths">{c.strengths.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{c.strengths.map((s) => <li key={s}>{s}</li>)}</ul> : <Empty title="None recorded" />}</Card>
        <Card title="Weaknesses">{c.weaknesses.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{c.weaknesses.map((s) => <li key={s}>{s}</li>)}</ul> : <Empty title="None recorded" />}</Card>
        <Card title="Missing concepts">{c.missing_concepts.length ? <div className="flex flex-wrap gap-1">{c.missing_concepts.map((s) => <Badge key={s}>{s}</Badge>)}</div> : <Empty title="None recorded" />}</Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Question difficulty progression"><DifficultyChart data={c.adaptive_progression ?? []} /></Card>
        <Card title="Readiness components">
          <dl className="space-y-2 text-sm">{Object.entries(c.readiness.components).map(([k, v]) => (
            <div key={k} className="flex justify-between"><dt className="muted">{label(k)}</dt><dd className="tabular-nums">{v == null ? "not assessed" : v.toFixed(0)}</dd></div>))}
          </dl>
        </Card>
      </div>
      <Card title="Interview-improvement recommendations">
        {c.recommendations.length ? (
          <ul className="space-y-3">{c.recommendations.map((r) => (
            <li key={r.area} className="text-sm"><div className="font-medium">{r.area} <Badge>{r.area_type}</Badge></div>
              <p>{r.recommendation}</p><p className="text-xs faint">Why: {r.reason}</p></li>))}</ul>
        ) : <Empty title="No recommendations" />}
      </Card>
      <Card title="Questions & answers">
        {qs.loading ? <Spinner /> : (
          <ol className="space-y-5">{(qs.data ?? []).map((q) => (
            <li key={q.id} className="text-sm">
              <div className="flex flex-wrap items-center gap-2 text-xs muted"><span>Q{q.sequence}</span><Badge>{q.topic ?? "General"}</Badge><Badge>{q.difficulty}</Badge>
                {q.evaluation && <span className="tabular-nums font-semibold">{q.evaluation.overall_score.toFixed(0)}/100 · {q.evaluation.band}</span>}</div>
              <p className="mt-1 font-medium">{q.text}</p>
              {q.reason && <p className="text-xs faint">Why this question: {q.reason}</p>}
              <p className="mt-2 rounded-lg bg-black/5 p-2 dark:bg-white/5">{q.transcript ?? "No answer"}</p>
              {q.evaluation && (
                <details className="mt-2"><summary className="cursor-pointer text-xs muted">Evaluation details</summary>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    <div>{Object.entries(q.evaluation.criteria).map(([k, v]) => <div key={k} className="flex justify-between text-xs"><span className="muted">{label(k)}</span><span className="tabular-nums">{v}/10</span></div>)}
                      <div className="mt-1 text-xs faint">Confidence {Math.round(q.evaluation.confidence * 100)}%</div></div>
                    <div className="space-y-1 text-xs">
                      {q.evaluation.evidence?.summary && <p>{q.evaluation.evidence.summary}</p>}
                      {q.evaluation.strengths.map((s) => <p key={s.point}>+ {s.point}{s.evidence && <span className="faint"> — “{s.evidence}”</span>}</p>)}
                      {q.evaluation.weaknesses.map((s) => <p key={s.point}>− {s.point}</p>)}
                      {q.evaluation.improvement_actions.map((s) => <p key={s}>→ {s}</p>)}
                      {q.evaluation.suggested_answer_structure && <p className="faint">Suggested structure: {q.evaluation.suggested_answer_structure}</p>}
                      {q.evaluation.next_question_reason && <p className="faint">Next-question decision: {q.evaluation.next_question_reason}</p>}
                    </div>
                  </div>
                </details>)}
            </li>))}</ol>)}
      </Card>
    </div>
  );
}
