"use client";

import { useEffect, useRef, useState } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, PageHeader, Select, Spinner, Table, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { d, label } from "@/lib/format";
import type { KnowledgeDocument } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const TYPES = ["job_description", "role_document", "interview_guideline", "technical", "question_bank", "institution_info",
  "domain_info", "evaluation_guideline", "other"];

export default function KnowledgePage() {
  const docs = useApi<KnowledgeDocument[]>("/knowledge/documents");
  const fileRef = useRef<HTMLInputElement>(null);
  const versionRef = useRef<HTMLInputElement>(null);
  const [versionFor, setVersionFor] = useState<string | null>(null);
  const [meta, setMeta] = useState({ title: "", document_type: "technical", role: "", topic: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ chunk_id: string; text: string; score: number; source_title: string; version: number }[] | null>(null);

  const processing = docs.data?.some((x) => x.latest && ["pending", "processing"].includes(x.latest.indexing_status));
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(docs.reload, 3000);
    return () => clearInterval(t);
  }, [processing, docs.reload]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try { await fn(); await docs.reload(); } catch (e) { setError(e instanceof ApiError ? e.message : "Request failed"); } finally { setBusy(false); }
  }

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return setError("Choose a PDF, DOCX, TXT or Markdown file");
    const form = new FormData();
    form.append("file", file);
    Object.entries(meta).forEach(([k, v]) => v && form.append(k, v));
    await run(() => api("/knowledge/documents", { method: "POST", form }));
    setMeta({ ...meta, title: "", description: "" });
    if (fileRef.current) fileRef.current.value = "";
  }

  async function newVersion(file: File) {
    const form = new FormData();
    form.append("file", file);
    await run(() => api(`/knowledge/documents/${versionFor}/versions`, { method: "POST", form }));
    setVersionFor(null);
  }

  return (
    <>
      <PageHeader title="Knowledge Base" subtitle="Documents are stored privately; their text is indexed for your institution's interviews only."
        action={<Button variant="secondary" loading={busy} onClick={() => run(() => api("/knowledge/reindex", { method: "POST" }))}>Re-index all</Button>} />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      <Card title="Upload document">
        <form onSubmit={upload} className="grid gap-4 md:grid-cols-3">
          <Field label="Title"><Input required value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} /></Field>
          <Field label="Type"><Select value={meta.document_type} onChange={(e) => setMeta({ ...meta, document_type: e.target.value })}>
            {TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}</Select></Field>
          <Field label="Role (optional)"><Input value={meta.role} onChange={(e) => setMeta({ ...meta, role: e.target.value })} placeholder="AI/ML Engineer" /></Field>
          <Field label="Topic (optional)"><Input value={meta.topic} onChange={(e) => setMeta({ ...meta, topic: e.target.value })} /></Field>
          <Field label="Description"><Textarea rows={1} value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} /></Field>
          <Field label="File" hint="PDF, DOCX, TXT or MD — max 20 MB"><input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" className="text-sm" /></Field>
          <div className="md:col-span-3 flex justify-end"><Button type="submit" loading={busy}>Upload & index</Button></div>
        </form>
      </Card>
      <input ref={versionRef} type="file" accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(e) => e.target.files?.[0] && newVersion(e.target.files[0])} />
      <Card className="mt-4" title="Documents">
        {docs.loading && !docs.data ? <Spinner /> : (
          <Table head={["Document", "Type", "Role", "Version", "Uploaded", "Processing", "Indexing", ""]} empty="No documents uploaded yet"
            rows={(docs.data ?? []).map((x) => [
              <div key="t"><div className="font-medium">{x.title}</div>{x.latest?.error && <div className="text-xs text-red-600">{x.latest.error}</div>}</div>,
              label(x.document_type), x.role ?? "–", `v${x.current_version}`, d(x.created_at),
              <Badge key="p">{x.latest?.processing_status ?? "–"}</Badge>,
              <span key="i"><Badge>{x.status === "inactive" ? "inactive" : x.latest?.indexing_status ?? "–"}</Badge> {x.latest?.chunk_count ? <span className="text-xs muted">{x.latest.chunk_count} chunks</span> : null}</span>,
              <div key="a" className="flex flex-wrap gap-2 text-xs">
                <button className="text-brand-500 hover:underline" onClick={() => { setVersionFor(x.id); versionRef.current?.click(); }}>New version</button>
                <button className="text-brand-500 hover:underline" onClick={() => run(() => api(`/knowledge/documents/${x.id}/reindex`, { method: "POST" }))}>Re-index</button>
                <button className="text-brand-500 hover:underline" onClick={() => run(() => api(`/knowledge/documents/${x.id}`, { method: "PUT", json: { status: x.status === "active" ? "inactive" : "active" } }))}>{x.status === "active" ? "Deactivate" : "Activate"}</button>
                <button className="text-red-600 hover:underline" onClick={() => confirm(`Delete "${x.title}"?`) && run(() => api(`/knowledge/documents/${x.id}`, { method: "DELETE" }))}>Delete</button>
              </div>,
            ])} />)}
      </Card>
      <Card className="mt-4" title="Test retrieval">
        <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); setHits(await api("/rag/query", { method: "POST", json: { query, k: 5 } })); }}>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. how should candidates explain overfitting?" />
          <Button type="submit" disabled={query.length < 2}>Search</Button>
        </form>
        {hits && <ul className="mt-4 space-y-3 text-sm">{hits.length ? hits.map((h) => (
          <li key={h.chunk_id}><div className="text-xs muted">{h.source_title} v{h.version} · similarity {h.score.toFixed(2)}</div><p className="mt-1 line-clamp-3">{h.text}</p></li>
        )) : <li className="muted">No matching content.</li>}</ul>}
      </Card>
    </>
  );
}
