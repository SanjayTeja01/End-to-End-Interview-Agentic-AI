"use client";

import { BarsChart, TrendChart } from "./charts";
import { Badge, Card, Empty } from "./ui";

export interface CandidateOverview {
  overall_score: number | null;
  latest_score: number | null;
  completed_interviews: number;
  readiness: null | { overall: number; level: string; components: Record<string, number | null>; role: string };
  score_trend: { delta: number | null; direction: string };
  score_over_time: { date: string; interview: string; score: number }[];
  skill_performance: { skill: string; average: number; count: number }[];
  topic_performance: { topic: string; average: number; count: number }[];
  role_performance: { role: string; average: number; count: number }[];
  strengths: string[];
  improvement_areas: string[];
  recommendations: { area: string; recommendation: string; reason: string; area_type: string }[];
}

export function PerformancePanels({ o }: { o: CandidateOverview }) {
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Score over time"><TrendChart data={o.score_over_time.map((p, i) => ({ ...p, label: `${i + 1}. ${p.interview}` }))} x="label" y="score" /></Card>
        <Card title="Average score by skill"><BarsChart data={o.skill_performance} x="skill" y="average" /></Card>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Average score by role"><BarsChart data={o.role_performance} x="role" y="average" height={160} /></Card>
        <Card title="Topic performance (weakest first)">
          {o.topic_performance.length ? (
            <ul className="space-y-1 text-sm">{o.topic_performance.slice(0, 10).map((t) => (
              <li key={t.topic} className="flex justify-between gap-2"><span>{t.topic}</span><span className="tabular-nums muted">{t.average.toFixed(0)} · {t.count}q</span></li>))}</ul>
          ) : <Empty title="No topics assessed yet" />}
        </Card>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Strengths">{o.strengths.length ? <div className="flex flex-wrap gap-1">{o.strengths.map((s) => <Badge key={s} tone="active">{s}</Badge>)}</div> : <Empty title="Complete an interview to see strengths" />}</Card>
        <Card title="Improvement areas">{o.improvement_areas.length ? <div className="flex flex-wrap gap-1">{o.improvement_areas.map((s) => <Badge key={s} tone="pending">{s}</Badge>)}</div> : <Empty title="None identified yet" />}</Card>
        <Card title="Recommendations">{o.recommendations.length ? (
          <ul className="space-y-2 text-sm">{o.recommendations.slice(0, 4).map((r) => <li key={r.area}><b>{r.area}:</b> {r.recommendation}</li>)}</ul>
        ) : <Empty title="No recommendations yet" />}</Card>
      </div>
    </>
  );
}
