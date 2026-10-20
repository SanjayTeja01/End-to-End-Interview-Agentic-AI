"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { cleanSkills, SkillEditor } from "@/components/SkillEditor";
import { Button, Card, ErrorBox, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Interview, KnowledgeDocument, RoleSkill } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function NewInterview() {
  const router = useRouter();
  const docs = useApi<KnowledgeDocument[]>("/knowledge/documents");
  const [f, setF] = useState({
    name: "", target_role: "", job_description: "", duration_minutes: 30, start_time: "", end_time: "",
    interview_type: "technical", question_count: 8, initial_difficulty: "medium", adaptive_mode: true,
    eligibility_mode: "role_match", record_media: false,
  });
  const [mode, setMode] = useState<"infer" | "manual">("infer");
  const [skills, setSkills] = useState<RoleSkill[]>([]);
  const [docIds, setDocIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.type === "number" ? Number(e.target.value) : e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: f.name, target_role: f.target_role, job_description: f.job_description, duration_minutes: f.duration_minutes,
        start_time: f.start_time ? new Date(f.start_time).toISOString() : null,
        end_time: f.end_time ? new Date(f.end_time).toISOString() : null,
        interview_type: f.interview_type, question_count: f.question_count, initial_difficulty: f.initial_difficulty,
        adaptive_mode: f.adaptive_mode, record_media: f.record_media, eligibility_config: { mode: f.eligibility_mode, min_similarity: 0.5 },
        knowledge_document_ids: docIds,
        required_skills: mode === "manual" ? cleanSkills(skills) : [], infer_skills: mode === "infer",
      };
      if (mode === "manual" && !body.required_skills.length) throw new Error("Add at least one skill or let the AI infer them.");
      const r = await api<{ interview: Interview }>("/interviews", { method: "POST", json: body });
      router.push(`/institution/interviews/${r.interview.id}`);
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "Could not create interview");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="max-w-4xl space-y-4">
      <PageHeader title="Create interview" subtitle="Requirements inferred by AI must be reviewed and approved before activation." />
      {error && <ErrorBox message={error} />}
      <Card title="Role & job description">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Interview name"><Input required value={f.name} onChange={set("name")} placeholder="AI/ML Engineer Interview" /></Field>
          <Field label="Target role"><Input required value={f.target_role} onChange={set("target_role")} placeholder="AI/ML Engineer" /></Field>
        </div>
        <div className="mt-4"><Field label="Job description"><Textarea rows={6} value={f.job_description} onChange={set("job_description")} /></Field></div>
      </Card>
      <Card title="Required skills">
        <div className="mb-4 flex gap-2">
          <Button type="button" variant={mode === "infer" ? "primary" : "secondary"} onClick={() => setMode("infer")}>Let AI infer from role & JD</Button>
          <Button type="button" variant={mode === "manual" ? "primary" : "secondary"} onClick={() => setMode("manual")}>Provide skills</Button>
        </div>
        {mode === "infer" ? (
          <p className="text-sm muted">The Role & Skill Agent will propose skills, proficiency levels (0–5), importance and topics using the JD and your knowledge base. You will review, edit and approve them.</p>
        ) : <SkillEditor skills={skills} onChange={setSkills} />}
      </Card>
      <Card title="Configuration">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Interview type"><Select value={f.interview_type} onChange={set("interview_type")}>
            <option value="technical">Technical</option><option value="behavioral">Behavioral</option><option value="mixed">Mixed</option></Select></Field>
          <Field label="Number of questions"><Input type="number" min={1} max={50} value={f.question_count} onChange={set("question_count")} /></Field>
          <Field label="Duration (minutes)"><Input type="number" min={5} max={240} value={f.duration_minutes} onChange={set("duration_minutes")} /></Field>
          <Field label="Initial difficulty"><Select value={f.initial_difficulty} onChange={set("initial_difficulty")}>
            <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Select></Field>
          <Field label="Start time (optional)"><Input type="datetime-local" value={f.start_time} onChange={set("start_time")} /></Field>
          <Field label="End time (optional)"><Input type="datetime-local" value={f.end_time} onChange={set("end_time")} /></Field>
          <Field label="Eligibility"><Select value={f.eligibility_mode} onChange={set("eligibility_mode")}>
            <option value="role_match">Students targeting this role</option><option value="assigned_only">Only assigned students</option>
            <option value="all_students">All students</option></Select></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.adaptive_mode} onChange={set("adaptive_mode")} /> Adaptive interview mode</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.record_media} onChange={set("record_media")} /> Record answer video (stored privately)</label>
        </div>
        <p className="mt-3 text-xs faint">Evaluation uses the default rubric: technical correctness 30%, relevance 20%, completeness 20%, clarity 15%, depth 10%, communication 5% (behavioral interviews weight communication higher).</p>
      </Card>
      {!!docs.data?.length && (
        <Card title="Knowledge sources (optional)">
          <div className="grid gap-2 md:grid-cols-2">
            {docs.data.map((d) => (
              <label key={d.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={docIds.includes(d.id)}
                  onChange={(e) => setDocIds(e.target.checked ? [...docIds, d.id] : docIds.filter((x) => x !== d.id))} />
                {d.title} <span className="faint">({d.document_type})</span>
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs faint">Leave empty to use all of your institution&apos;s active documents.</p>
        </Card>
      )}
      <div className="flex justify-end"><Button type="submit" loading={busy}>Create interview</Button></div>
    </form>
  );
}
