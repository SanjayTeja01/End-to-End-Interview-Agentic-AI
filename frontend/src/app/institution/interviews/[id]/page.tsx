"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { cleanSkills, SkillEditor } from "@/components/SkillEditor";
import { Badge, Button, Card, ErrorBox, PageHeader, Progress, Spinner, Stat, Table } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dt, label, pct } from "@/lib/format";
import type { Interview, RoleSkill } from "@/lib/types";
import { useApi } from "@/lib/useApi";

interface CandidateRow {
  candidate_id: string; full_name: string; email: string; eligibility_status: string; participation_status: string;
  match_score: number | null; session_id: string | null; session_status: string | null; score: number | null; progress: number | null;
}
const EDITABLE = ["draft", "requirements_prepared", "pending_approval", "approved"];

export default function InterviewDetail() {
  const { id } = useParams<{ id: string }>();
  const iv = useApi<Interview>(`/interviews/${id}`);
  const cands = useApi<CandidateRow[]>(`/interviews/${id}/candidates`);
  const students = useApi<{ items: { id: string; full_name: string; email: string }[] }>("/students?limit=500");
  const [skills, setSkills] = useState<RoleSkill[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [assignId, setAssignId] = useState("");

  useEffect(() => {
    if (iv.data?.skills && !dirty) setSkills(iv.data.skills);
  }, [iv.data, dirty]);

  // Poll while the Role & Skill Agent is generating requirements
  useEffect(() => {
    if (iv.data?.skill_approval_state !== "generating") return;
    const t = setInterval(iv.reload, 3000);
    return () => clearInterval(t);
  }, [iv.data?.skill_approval_state, iv.reload]);

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setError(null);
    try {
      await fn();
      setDirty(false);
      await iv.reload();
      await cands.reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  if (iv.loading && !iv.data) return <Spinner />;
  if (iv.error) return <ErrorBox message={iv.error} onRetry={iv.reload} />;
  const d = iv.data!;
  const status = d.effective_status ?? d.status;
  const editable = EDITABLE.includes(d.status);
  const needsApproval = d.skill_approval_state === "pending";

  return (
    <>
      <PageHeader title={d.name} subtitle={`${d.target_role} · ${label(d.interview_type)} · ${d.question_count} questions · ${d.duration_minutes} min`}
        action={
          <div className="flex flex-wrap gap-2">
            {needsApproval && <Button loading={busy === "approve"} disabled={dirty}
              onClick={() => act("approve", () => api(`/interviews/${id}/approve`, { method: "POST" }))}>Approve requirements</Button>}
            {["approved", "scheduled"].includes(d.status) && d.status !== "scheduled" && (
              <Button loading={busy === "activate"} onClick={() => act("activate", () => api(`/interviews/${id}/activate`, { method: "POST" }))}>
                {d.start_time && new Date(d.start_time) > new Date() ? "Schedule" : "Activate"}</Button>)}
            {["active", "scheduled", "completed"].includes(status) && (
              <Button variant="secondary" loading={busy === "close"} onClick={() => act("close", () => api(`/interviews/${id}/close`, { method: "POST" }))}>Close</Button>)}
            {editable && <Button variant="danger" loading={busy === "cancel"} onClick={() => act("cancel", () => api(`/interviews/${id}/cancel`, { method: "POST" }))}>Cancel</Button>}
          </div>
        } />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat label="Status" value={<Badge>{status}</Badge>} />
        <Stat label="Candidates" value={d.stats?.candidate_count ?? 0} />
        <Stat label="Participated" value={d.stats?.participated ?? 0} />
        <Stat label="In progress" value={d.stats?.in_progress ?? 0} />
        <Stat label="Completed" value={d.stats?.completed ?? 0} />
        <Stat label="Average score" value={pct(d.stats?.average_score ?? null, 1)} />
      </div>

      <Card className="mt-4" title={<span>Required skills <Badge tone={needsApproval ? "pending" : undefined}>{label(d.skill_approval_state)}</Badge></span>}
        action={editable && (
          <div className="flex gap-2">
            <Button variant="secondary" loading={busy === "infer"} onClick={() => act("infer", () => api(`/interviews/${id}/infer-skills`, { method: "POST" }))}>Re-infer with AI</Button>
            {dirty && <Button loading={busy === "save"} onClick={() => act("save", () => api(`/interviews/${id}/skills`, { method: "PUT", json: { skills: cleanSkills(skills) } }))}>Save changes</Button>}
          </div>
        )}>
        {d.skill_approval_state === "generating" ? <Spinner label="Role & Skill Agent is analysing the role and job description…" /> :
          <SkillEditor skills={skills} readOnly={!editable} onChange={(s) => { setSkills(s); setDirty(true); }} />}
        {needsApproval && <p className="mt-3 text-xs faint">AI-proposed requirements must be approved before the interview can be activated.</p>}
      </Card>

      <Card className="mt-4" title="Candidates" action={
        <div className="flex gap-2">
          <select className="rounded-lg border border-theme bg-[var(--card)] px-2 py-1 text-sm" value={assignId} onChange={(e) => setAssignId(e.target.value)} aria-label="Student to assign">
            <option value="">Assign a student…</option>
            {students.data?.items.map((s) => <option key={s.id} value={s.id}>{s.full_name} ({s.email})</option>)}
          </select>
          <Button variant="secondary" disabled={!assignId} loading={busy === "assign"}
            onClick={() => act("assign", () => api(`/interviews/${id}/candidates`, { method: "POST", json: { candidate_ids: [assignId] } }))}>Assign</Button>
        </div>}>
        <Table head={["Candidate", "Eligibility", "Status", "Progress", "Score", ""]} empty="No eligible candidates yet"
          rows={(cands.data ?? []).map((c) => [
            <div key="n"><div className="font-medium">{c.full_name}</div><div className="text-xs muted">{c.email}</div></div>,
            <Badge key="e">{c.eligibility_status}</Badge>,
            <Badge key="s">{c.session_status ?? c.participation_status}</Badge>,
            <div key="p" className="w-24">{c.progress != null ? <Progress value={c.progress} /> : "–"}</div>,
            pct(c.score, 1),
            <div key="a" className="flex gap-2 text-sm">
              {c.session_id && ["initializing", "in_progress"].includes(c.session_status ?? "") &&
                <Link className="text-brand-500 hover:underline" href={`/institution/interviews/${id}/monitor/${c.session_id}`}>Live monitor</Link>}
              {c.session_id && c.session_status === "completed" &&
                <Link className="text-brand-500 hover:underline" href={`/institution/reports/${c.session_id}`}>Report</Link>}
              {c.eligibility_status !== "revoked" && !c.session_id &&
                <button className="text-red-600 hover:underline" onClick={() => act("revoke", () => api(`/interviews/${id}/candidates`, { method: "POST", json: { candidate_ids: [c.candidate_id], action: "revoke" } }))}>Revoke</button>}
            </div>,
          ])} />
      </Card>

      <Card className="mt-4" title="Configuration">
        <dl className="grid gap-3 text-sm md:grid-cols-3">
          {[["Initial difficulty", label(d.initial_difficulty)], ["Adaptive mode", d.adaptive_mode ? "On" : "Off"],
            ["Eligibility", label(d.eligibility_config?.mode)], ["Start", dt(d.start_time)], ["End", dt(d.end_time)],
            ["Video recording", d.record_media ? "On" : "Off"]].map(([k, v]) => (
            <div key={k}><dt className="text-xs muted">{k}</dt><dd>{v}</dd></div>))}
        </dl>
        {d.job_description && <details className="mt-4 text-sm"><summary className="cursor-pointer muted">Job description</summary>
          <p className="mt-2 whitespace-pre-wrap">{d.job_description}</p></details>}
      </Card>
    </>
  );
}
