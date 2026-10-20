"use client";

import Link from "next/link";
import { useState } from "react";
import { ErrorBox, Input, PageHeader, Spinner, Table } from "@/components/ui";
import { pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface Row { id: string; full_name: string; email: string; target_roles: string[]; average_score: number | null; completed_interviews: number }

export default function StudentsPage() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const { data, error, loading, reload } = useApi<{ total: number; items: Row[] }>(`/students?q=${encodeURIComponent(query)}`);
  return (
    <>
      <PageHeader title="Students" subtitle={data ? `${data.total} students` : undefined}
        action={<form onSubmit={(e) => { e.preventDefault(); setQuery(q); }}><Input placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} /></form>} />
      {loading && !data && <Spinner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <div className="card p-2">
          <Table head={["Student", "Target roles", "Completed interviews", "Average score"]} empty="No students have registered yet"
            rows={data.items.map((s) => [
              <Link key="n" href={`/institution/students/${s.id}`} className="font-medium text-brand-500 hover:underline">{s.full_name}<div className="text-xs muted">{s.email}</div></Link>,
              s.target_roles.join(", ") || "–", s.completed_interviews, pct(s.average_score, 1)])} />
        </div>
      )}
    </>
  );
}
