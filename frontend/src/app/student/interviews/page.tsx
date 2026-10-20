"use client";

import Link from "next/link";
import { Badge, Button, Empty, ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { dt, label } from "@/lib/format";
import type { CandidateInterview } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AvailableInterviews() {
  const { data, error, loading, reload } = useApi<CandidateInterview[]>("/interviews");
  return (
    <>
      <PageHeader title="Available Interviews" subtitle="Only interviews you are eligible for are shown (based on your target roles and your institution's settings)." />
      {loading && !data && <Spinner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && !data.length && <Empty title="No eligible interviews right now">Add target roles in My Profile to see matching interviews.</Empty>}
      <div className="grid gap-4 md:grid-cols-2">
        {data?.map((i) => (
          <div key={i.id} className="card p-5">
            <div className="flex items-start justify-between gap-2">
              <div><h3 className="font-semibold">{i.name}</h3><p className="text-sm muted">{i.target_role} · {label(i.interview_type)}</p></div>
              <Badge>{i.participation_status === "not_started" ? i.status : i.participation_status}</Badge>
            </div>
            <p className="mt-3 text-sm muted">{i.question_count} questions · {i.duration_minutes} minutes</p>
            {(i.start_time || i.end_time) && <p className="text-xs faint">Window: {dt(i.start_time)} – {dt(i.end_time)}</p>}
            <p className="mt-1 text-xs faint">{i.eligibility_reason}</p>
            <div className="mt-4 flex justify-end">
              {i.participation_status === "completed" ? (
                <Link href={`/student/history/${i.session_id}`}><Button variant="secondary">View results</Button></Link>
              ) : i.joinable ? (
                <Link href={i.session_id ? `/interview/${i.session_id}` : `/interview/prejoin?interview=${i.id}`}><Button>{i.session_id ? "Resume interview" : "Join interview"}</Button></Link>
              ) : <Button disabled>Opens at start time</Button>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
