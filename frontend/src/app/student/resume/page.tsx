"use client";

import { useRef, useState } from "react";
import { LEVELS } from "@/components/SkillEditor";
import { Badge, Button, Card, ErrorBox, PageHeader, Spinner, Table } from "@/components/ui";
import { api, ApiError, pollJob } from "@/lib/api";
import { d } from "@/lib/format";
import { useApi } from "@/lib/useApi";

interface ResumeRow { id: string; version: number; is_current: boolean; processing_status: string; error: string | null; created_at: string }
interface Analysis extends ResumeRow {
  analysis: { technical_skills?: { skill: string; estimated_level: number; evidence: string; confidence: number }[];
    projects?: { name: string; technologies: string[] }[]; technologies?: string[]; certifications?: string[] };
  extraction_meta: { sections_detected?: string[]; chars?: number };
}

export default function ResumePage() {
  const resumes = useApi<ResumeRow[]>("/resume");
  const current = resumes.data?.find((r) => r.is_current);
  const analysis = useApi<Analysis>(current ? `/resume/${current.id}/analysis` : null, [current?.processing_status]);
  const skills = useApi<{ skill: string; proficiency: number; source: string; confidence: number }[]>("/skills");
  const gaps = useApi<{ skill: string; required_level: number; candidate_level: number; gap: number; priority: number }[]>("/skills/gaps");
  const fileRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    setError(null);
    setStatus("uploading");
    try {
      const form = new FormData();
      form.append("file", f);
      const r = await api<{ job: { id: string } }>("/resume/upload", { method: "POST", form });
      const job = await pollJob(r.job.id, setStatus);
      if (job.status === "failed") setError(job.error ?? "Processing failed");
      await Promise.all([resumes.reload(), skills.reload()]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setStatus(null);
    }
  }

  return (
    <>
      <PageHeader title="Resume & Skills" subtitle="Your resume is private to you and your institution. Claims are treated as evidence the interviewer may ask about." />
      <Card title="Upload resume" action={current && <Badge>{`v${current.version} · ${current.processing_status}`}</Badge>}>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".pdf,.docx" className="text-sm" />
          <Button onClick={upload} loading={!!status}>{status ? `Processing (${status})…` : "Upload & analyse"}</Button>
        </div>
        <p className="mt-2 text-xs faint">PDF or DOCX, up to 20 MB. Scanned image-only PDFs cannot be read.</p>
        {error && <div className="mt-3"><ErrorBox message={error} /></div>}
        {current?.error && <div className="mt-3"><ErrorBox message={current.error} /></div>}
      </Card>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Extracted skills (from resume)">
          {analysis.loading ? <Spinner /> : (
            <Table head={["Skill", "Estimated level", "Evidence"]} empty="Upload a resume to extract skills"
              rows={(analysis.data?.analysis.technical_skills ?? []).map((s) => [s.skill, `${s.estimated_level} – ${LEVELS[s.estimated_level]}`,
                <span key="e" className="text-xs muted">“{s.evidence}”</span>])} />)}
          {analysis.data?.extraction_meta.sections_detected && <p className="mt-2 text-xs faint">Sections detected: {analysis.data.extraction_meta.sections_detected.join(", ")}</p>}
        </Card>
        <Card title="Skill gaps (vs. interviews you've joined)">
          <Table head={["Skill", "Required", "Estimated", "Gap", "Priority"]} empty="Gaps are computed when you join an interview"
            rows={(gaps.data ?? []).map((g) => [g.skill, g.required_level, g.candidate_level.toFixed(1), g.gap.toFixed(1), g.priority.toFixed(2)])} />
          <p className="mt-2 text-xs faint">Gap = required − estimated level (0–5). Priority = gap × importance.</p>
        </Card>
      </div>
      <Card className="mt-4" title="All skill evidence">
        <Table head={["Skill", "Level", "Source", "Confidence"]} empty="No skills yet"
          rows={(skills.data ?? []).map((s) => [s.skill, `${s.proficiency} – ${LEVELS[s.proficiency]}`, <Badge key="s">{s.source}</Badge>, `${Math.round(s.confidence * 100)}%`])} />
      </Card>
      <Card className="mt-4" title="Resume versions">
        <Table head={["Version", "Uploaded", "Status"]} rows={(resumes.data ?? []).map((r) => [`v${r.version}${r.is_current ? " (current)" : ""}`, d(r.created_at), <Badge key="b">{r.processing_status}</Badge>])} />
      </Card>
    </>
  );
}
