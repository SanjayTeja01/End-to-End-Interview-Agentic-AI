"use client";

import Link from "next/link";
import { Badge, Button, Empty, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { label, pct } from "@/lib/format";
import type { Interview } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function InterviewsPage() {
  const { data, error, loading, reload } = useApi<Interview[]>("/interviews");
  return (
    <>
      <PageHeader title="Interviews" subtitle="Create, configure and monitor interview campaigns"
        action={<Link href="/institution/interviews/new"><Button>Create interview</Button></Link>} />
      {loading && !data && <Spinner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && !data.length && <Empty title="No interviews yet">Create your first interview campaign.</Empty>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((iv) => (
          <Link key={iv.id} href={`/institution/interviews/${iv.id}`} className="card block p-5 transition hover:shadow-md">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-semibold">{iv.name}</h3>
                <p className="text-sm muted">{iv.target_role} · {label(iv.interview_type)}</p>
              </div>
              <Badge>{iv.effective_status ?? iv.status}</Badge>
            </div>
            <dl className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
              {[["Candidates", iv.stats?.candidate_count], ["Participated", iv.stats?.participated],
                ["In progress", iv.stats?.in_progress], ["Completed", iv.stats?.completed],
                ["Avg score", pct(iv.stats?.average_score ?? null, 1)], ["Questions", iv.question_count]].map(([k, v]) => (
                <div key={k as string} className="rounded-lg bg-black/5 p-2 dark:bg-white/5">
                  <dt className="muted">{k}</dt><dd className="mt-0.5 text-sm font-semibold tabular-nums">{v ?? 0}</dd>
                </div>
              ))}
            </dl>
          </Link>
        ))}
      </div>
    </>
  );
}
