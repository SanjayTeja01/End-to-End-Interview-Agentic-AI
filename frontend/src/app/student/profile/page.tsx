"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, PageHeader, Spinner, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";

interface Profile {
  headline: string | null; summary: string | null; target_roles: string[]; technical_skills: string[]; non_technical_skills: string[];
  technologies: string[]; certifications: string[]; achievements: string[];
  education: { institution: string; degree?: string; field?: string; start?: string; end?: string }[];
  experience: { organization: string; title?: string; start?: string; end?: string; highlights: string[] }[];
  projects: { name: string; description?: string; technologies: string[] }[];
  preferences: Record<string, unknown>;
}
const LISTS = ["target_roles", "technical_skills", "non_technical_skills", "technologies", "certifications", "achievements"] as const;

export default function ProfilePage() {
  const { data, error, loading, reload } = useApi<Profile>("/profile");
  const recs = useApi<{ area: string; recommendation: string; reason: string }[]>("/recommendations");
  const [p, setP] = useState<Profile | null>(null);
  const [lists, setLists] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setP(data);
      setLists(Object.fromEntries(LISTS.map((k) => [k, (data[k] ?? []).join(", ")])));
    }
  }, [data]);

  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!p) return null;

  async function save() {
    setSaving(true); setErr(null); setMsg(null);
    try {
      const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
      await api("/profile", { method: "PUT", json: {
        headline: p!.headline, summary: p!.summary, education: p!.education, experience: p!.experience, projects: p!.projects,
        ...Object.fromEntries(LISTS.map((k) => [k, split(lists[k] ?? "")])) } });
      setMsg("Profile saved. Eligible interviews were refreshed for your target roles.");
      reload();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Save failed"); } finally { setSaving(false); }
  }

  return (
    <div className="max-w-4xl">
      <PageHeader title="My Profile" subtitle="Fields extracted from your resume can be corrected here." action={<Button onClick={save} loading={saving}>Save</Button>} />
      {msg && <p className="mb-3 text-sm text-emerald-700 dark:text-emerald-400">{msg}</p>}
      {err && <ErrorBox message={err} />}
      <Card title="Basics">
        <div className="grid gap-4">
          <Field label="Headline"><Input value={p.headline ?? ""} onChange={(e) => setP({ ...p, headline: e.target.value })} /></Field>
          <Field label="Summary"><Textarea rows={3} value={p.summary ?? ""} onChange={(e) => setP({ ...p, summary: e.target.value })} /></Field>
          <Field label="Target roles" hint="Comma separated — determines which interviews you are eligible for">
            <Input value={lists.target_roles ?? ""} onChange={(e) => setLists({ ...lists, target_roles: e.target.value })} placeholder="AI/ML Engineer, Agentic AI Engineer" /></Field>
        </div>
      </Card>
      <Card className="mt-4" title="Skills & technologies">
        <div className="grid gap-4 md:grid-cols-2">
          {LISTS.filter((k) => k !== "target_roles").map((k) => (
            <Field key={k} label={k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())} hint="Comma separated">
              <Textarea rows={2} value={lists[k] ?? ""} onChange={(e) => setLists({ ...lists, [k]: e.target.value })} /></Field>))}
        </div>
      </Card>
      <Card className="mt-4" title="Education">
        {p.education.map((e, i) => (
          <div key={i} className="mb-2 grid gap-2 md:grid-cols-3">
            <Input value={e.institution} onChange={(ev) => setP({ ...p, education: p.education.map((x, j) => j === i ? { ...x, institution: ev.target.value } : x) })} placeholder="Institution" />
            <Input value={e.degree ?? ""} onChange={(ev) => setP({ ...p, education: p.education.map((x, j) => j === i ? { ...x, degree: ev.target.value } : x) })} placeholder="Degree" />
            <Input value={e.field ?? ""} onChange={(ev) => setP({ ...p, education: p.education.map((x, j) => j === i ? { ...x, field: ev.target.value } : x) })} placeholder="Field" />
          </div>))}
        <Button variant="secondary" onClick={() => setP({ ...p, education: [...p.education, { institution: "" }] })}>Add education</Button>
      </Card>
      <Card className="mt-4" title="Experience">
        {p.experience.map((e, i) => (
          <div key={i} className="mb-2 grid gap-2 md:grid-cols-2">
            <Input value={e.organization} onChange={(ev) => setP({ ...p, experience: p.experience.map((x, j) => j === i ? { ...x, organization: ev.target.value } : x) })} placeholder="Organization" />
            <Input value={e.title ?? ""} onChange={(ev) => setP({ ...p, experience: p.experience.map((x, j) => j === i ? { ...x, title: ev.target.value } : x) })} placeholder="Title" />
          </div>))}
        <Button variant="secondary" onClick={() => setP({ ...p, experience: [...p.experience, { organization: "", highlights: [] }] })}>Add experience</Button>
      </Card>
      <Card className="mt-4" title="Projects">
        {p.projects.map((pr, i) => (
          <div key={i} className="mb-3 grid gap-2">
            <Input value={pr.name} onChange={(ev) => setP({ ...p, projects: p.projects.map((x, j) => j === i ? { ...x, name: ev.target.value } : x) })} placeholder="Project name" />
            <Textarea rows={2} value={pr.description ?? ""} onChange={(ev) => setP({ ...p, projects: p.projects.map((x, j) => j === i ? { ...x, description: ev.target.value } : x) })} placeholder="Description" />
          </div>))}
        <Button variant="secondary" onClick={() => setP({ ...p, projects: [...p.projects, { name: "", technologies: [] }] })}>Add project</Button>
      </Card>
      <Card className="mt-4" title="Interview-improvement recommendations">
        {recs.data?.length ? <ul className="space-y-2 text-sm">{recs.data.slice(0, 8).map((r, i) => (
          <li key={i}><Badge>{r.area}</Badge> {r.recommendation}<div className="text-xs faint">{r.reason}</div></li>))}</ul>
          : <p className="text-sm muted">Recommendations appear after your first interview.</p>}
      </Card>
    </div>
  );
}
