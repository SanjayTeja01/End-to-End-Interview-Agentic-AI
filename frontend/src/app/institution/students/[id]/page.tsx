"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { type CandidateOverview, PerformancePanels } from "@/components/PerformancePanels";
import { LEVELS } from "@/components/SkillEditor";
import { Badge, Button, Card, ErrorBox, PageHeader, Spinner, Stat, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d, label, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface Detail {
  student: { id: string; full_name: string; email: string };
  profile: null | Record<string, unknown> & { target_roles: string[]; technical_skills: string[]; projects: { name: string; description?: string }[];
    education: { institution: string; degree?: string }[]; headline: string | null };
  resume: null | { id: string; version: number; processing_status: string };
  skills: { skill: string; proficiency: number; source: string; confidence: number }[];
  skill_gaps: { skill: string; required_level: number; candidate_level: number; gap: number; priority: number }[];
  performance: CandidateOverview;
  history: { session_id: string; interview_name: string; target_role: string; status: string; started_at: string | null; overall_score: number | null; readiness: number | null }[];
  active_session_id: string | null;
}

export default function StudentDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi<Detail>(`/students/${id}`);
  const [resumeErr, setResumeErr] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const { me } = useAuth();
  const router = useRouter();
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const s = data!;
  const openResume = async () => {
    try {
      const { url } = await api<{ url: string }>(`/resume/${s.resume!.id}/download`);
      window.open(url, "_blank", "noopener");
    } catch (e) { setResumeErr((e as Error).message); }
  };
  const remove = async () => {
    if (!confirm(`Permanently remove ${s.student.full_name} (${s.student.email})? Their account, resume, interviews, answers and reports will be deleted. This cannot be undone.`)) return;
    setRemoving(true);
    try {
      await api(`/students/${s.student.id}`, { method: "DELETE" });
      router.replace("/institution/students");
    } catch (e) {
      setResumeErr((e as Error).message);
      setRemoving(false);
    }
  };
  return (
    <>
      <PageHeader title={s.student.full_name} subtitle={s.student.email}
        action={<div className="flex gap-2">
          {s.resume && <Button variant="secondary" onClick={openResume}>View resume (v{s.resume.version})</Button>}
          {me?.role === "institution_admin" && <Button variant="danger" loading={removing} onClick={remove}>Remove student</Button>}
        </div>} />
      {resumeErr && <ErrorBox message={resumeErr} />}
      {s.active_session_id && <div className="mb-4 rounded-lg border border-blue-300 bg-blue-50 p-3 text-sm dark:border-blue-800 dark:bg-blue-950/40">
        Interview in progress. {(() => { const h = s.history.find((x) => x.session_id === s.active_session_id); return h ? `(${h.interview_name})` : ""; })()}</div>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Average score" value={pct(s.performance.overall_score, 1)} />
        <Stat label="Latest score" value={pct(s.performance.latest_score, 1)} />
        <Stat label="Completed interviews" value={s.performance.completed_interviews} />
        <Stat label="Readiness" value={pct(s.performance.readiness?.overall ?? null)} hint={label(s.performance.readiness?.level)} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Profile">
          <p className="text-sm">{s.profile?.headline ?? "–"}</p>
          <p className="mt-2 text-xs muted">Target roles</p>
          <div className="mt-1 flex flex-wrap gap-1">{(s.profile?.target_roles ?? []).map((r) => <Badge key={r}>{r}</Badge>)}</div>
          <p className="mt-3 text-xs muted">Education</p>
          <ul className="text-sm">{(s.profile?.education ?? []).map((e, i) => <li key={i}>{e.institution}{e.degree ? ` — ${e.degree}` : ""}</li>)}</ul>
          <p className="mt-3 text-xs muted">Projects</p>
          <ul className="text-sm">{(s.profile?.projects ?? []).map((p, i) => <li key={i}>{p.name}</li>)}</ul>
        </Card>
        <Card title="Skills (with evidence source)">
          <Table head={["Skill", "Level", "Source"]} empty="No skills yet"
            rows={s.skills.map((k) => [k.skill, `${k.proficiency} – ${LEVELS[k.proficiency]}`, <Badge key="s">{k.source}</Badge>])} />
        </Card>
        <Card title="Skill gaps">
          <Table head={["Skill", "Required", "Current", "Priority"]} empty="No gaps computed yet"
            rows={s.skill_gaps.map((g) => [g.skill, g.required_level, g.candidate_level.toFixed(1), g.priority.toFixed(2)])} />
        </Card>
      </div>
      <div className="mt-4"><PerformancePanels o={s.performance} /></div>
      <Card className="mt-4" title="Interview history">
        <Table head={["Interview", "Role", "Date", "Status", "Score", "Readiness", ""]} empty="No interviews yet"
          rows={s.history.map((h) => [h.interview_name, h.target_role, d(h.started_at), <Badge key="s">{h.status}</Badge>, pct(h.overall_score, 1), pct(h.readiness),
            h.status === "completed" ? <Link key="r" className="text-brand-500 hover:underline" href={`/institution/reports/${h.session_id}`}>Report</Link> : ""])} />
      </Card>
    </>
  );
}
