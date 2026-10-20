"use client";

import Link from "next/link";
import { type CandidateOverview, PerformancePanels } from "@/components/PerformancePanels";
import { Badge, Button, Card, ErrorBox, PageHeader, Spinner, Stat, Table } from "@/components/ui";
import { d, label, pct } from "@/lib/format";
import type { CandidateInterview } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function StudentOverview() {
  const ov = useApi<CandidateOverview>("/overview/student");
  const ivs = useApi<CandidateInterview[]>("/interviews");
  const hist = useApi<{ session_id: string; interview_name: string; status: string; started_at: string | null; overall_score: number | null }[]>("/performance/history");
  if (ov.loading && !ov.data) return <Spinner />;
  if (ov.error) return <ErrorBox message={ov.error} onRetry={ov.reload} />;
  const o = ov.data!;
  return (
    <>
      <PageHeader title="Overview" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Overall score" value={pct(o.overall_score, 1)} hint="average across interviews" />
        <Stat label="Readiness" value={pct(o.readiness?.overall ?? null)} hint={o.readiness ? `${label(o.readiness.level)} · ${o.readiness.role}` : "after your first interview"} />
        <Stat label="Completed interviews" value={o.completed_interviews} />
        <Stat label="Latest score" value={pct(o.latest_score, 1)}
          hint={o.score_trend.delta != null ? `${o.score_trend.delta > 0 ? "+" : ""}${o.score_trend.delta} vs previous` : undefined} />
      </div>
      <p className="mt-2 text-xs faint">Readiness is an evidence-based indicator of interview preparedness, not a guarantee of any hiring outcome.</p>
      <div className="mt-4"><PerformancePanels o={o} /></div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Eligible interviews" action={<Link href="/student/interviews" className="text-sm text-brand-500 hover:underline">All</Link>}>
          <Table head={["Interview", "Role", "Status", ""]} empty="No interviews available right now"
            rows={(ivs.data ?? []).slice(0, 5).map((i) => [i.name, i.target_role, <Badge key="s">{i.status}</Badge>,
              i.joinable ? <Link key="j" href={`/interview/prejoin?interview=${i.id}`}><Button>{i.session_id ? "Resume" : "Join"}</Button></Link> : ""])} />
        </Card>
        <Card title="Recent interviews" action={<Link href="/student/history" className="text-sm text-brand-500 hover:underline">History</Link>}>
          <Table head={["Interview", "Date", "Score", ""]} empty="No interviews yet"
            rows={(hist.data ?? []).slice(0, 5).map((h) => [h.interview_name, d(h.started_at), pct(h.overall_score, 1),
              h.status === "completed" ? <Link key="r" className="text-brand-500 hover:underline" href={`/student/history/${h.session_id}`}>Results</Link> : <Badge key="b">{h.status}</Badge>])} />
        </Card>
      </div>
    </>
  );
}
