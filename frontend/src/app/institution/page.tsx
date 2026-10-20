"use client";

import Link from "next/link";
import { BarsChart, TrendChart } from "@/components/charts";
import { Badge, Card, ErrorBox, PageHeader, Spinner, Stat, Table } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { dt, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface Overview {
  total_students: number;
  active_interviews: number;
  completed_interviews: number;
  live_sessions: number;
  average_score: number | null;
  interviews_today: number;
  performance_over_time: { date: string; average: number; count: number }[];
  role_performance: { role: string; average: number; count: number }[];
  participation: { eligible: number; participated: number; completed: number; rate: number | null };
  recent_activity: { session_id: string; candidate: string; interview: string; status: string; updated_at: string }[];
}

export default function InstitutionOverview() {
  const { me } = useAuth();
  const { data, error, loading, reload } = useApi<Overview>("/overview/institution");
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const o = data!;
  return (
    <>
      <PageHeader title="Overview" subtitle={`Student registration code: ${me?.institution_join_code ?? "–"}`} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Total students" value={o.total_students} />
        <Stat label="Active interviews" value={o.active_interviews} hint={`${o.live_sessions} live now`} />
        <Stat label="Completed interviews" value={o.completed_interviews} />
        <Stat label="Average score" value={pct(o.average_score, 1)} hint="out of 100" />
        <Stat label="Interviews today" value={o.interviews_today} />
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="Average interview score over time">
          <TrendChart data={o.performance_over_time} x="date" y="average" />
        </Card>
        <Card title="Average score by role">
          <BarsChart data={o.role_performance} x="role" y="average" />
        </Card>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Participation">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="muted">Eligible candidates</dt><dd className="tabular-nums">{o.participation.eligible}</dd></div>
            <div className="flex justify-between"><dt className="muted">Participated</dt><dd className="tabular-nums">{o.participation.participated}</dd></div>
            <div className="flex justify-between"><dt className="muted">Completed</dt><dd className="tabular-nums">{o.participation.completed}</dd></div>
            <div className="flex justify-between"><dt className="muted">Participation rate</dt>
              <dd className="tabular-nums">{o.participation.rate == null ? "–" : `${Math.round(o.participation.rate * 100)}%`}</dd></div>
          </dl>
        </Card>
        <Card title="Recent activity" className="lg:col-span-2">
          <Table head={["Candidate", "Interview", "Status", "Updated"]} empty="No interview activity yet"
            rows={o.recent_activity.map((a) => [a.candidate, a.interview, <Badge key="s">{a.status}</Badge>, dt(a.updated_at)])} />
          <Link href="/institution/interviews" className="mt-3 inline-block text-sm text-brand-500 hover:underline">Manage interviews →</Link>
        </Card>
      </div>
    </>
  );
}
