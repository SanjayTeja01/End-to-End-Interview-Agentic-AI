"use client";

import Link from "next/link";
import { TrendChart } from "@/components/charts";
import { Badge, Card, ErrorBox, PageHeader, Spinner, Table } from "@/components/ui";
import { d, label, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface H { session_id: string; interview_name: string; target_role: string; status: string; started_at: string | null;
  overall_score: number | null; readiness: number | null; readiness_level: string | null; questions: number }

export default function HistoryPage() {
  const { data, error, loading, reload } = useApi<H[]>("/performance/history");
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const done = (data ?? []).filter((h) => h.overall_score != null).reverse();
  return (
    <>
      <PageHeader title="Interview History" />
      <Card title="Score trend"><TrendChart data={done.map((h, i) => ({ label: `${i + 1}. ${h.interview_name}`, score: h.overall_score }))} x="label" y="score" /></Card>
      <Card className="mt-4">
        <Table head={["Interview", "Role", "Date", "Questions", "Status", "Score", "Readiness", ""]} empty="You haven't taken any interviews yet"
          rows={(data ?? []).map((h) => [h.interview_name, h.target_role, d(h.started_at), h.questions, <Badge key="s">{h.status}</Badge>,
            pct(h.overall_score, 1), h.readiness != null ? `${h.readiness.toFixed(0)} (${label(h.readiness_level)})` : "–",
            h.status === "completed" ? <Link key="l" href={`/student/history/${h.session_id}`} className="text-brand-500 hover:underline">Results</Link>
              : ["in_progress", "initializing"].includes(h.status) ? <Link key="l" href={`/interview/${h.session_id}`} className="text-brand-500 hover:underline">Resume</Link> : ""])} />
      </Card>
    </>
  );
}
