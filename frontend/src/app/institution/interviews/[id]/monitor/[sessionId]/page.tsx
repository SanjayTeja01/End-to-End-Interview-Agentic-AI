"use client";

import { Camera, CameraOff, Mic, MicOff, Wifi, WifiOff } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, Card, ErrorBox, PageHeader, Progress, Spinner, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { label, mmss, pct } from "@/lib/format";
import type { SessionState, WsEvent } from "@/lib/types";
import { useInterviewSocket } from "@/lib/useInterviewSocket";
import { MonitorViewer } from "@/lib/webrtc";

interface Live {
  candidate: { id: string; full_name: string };
  state: SessionState;
  transcript: { sequence: number; question: string; topic: string | null; difficulty: string; answer: string | null;
    answer_status: string | null; score: number | null; next_question_reason: string | null }[];
  running_score: number | null;
  connection: { candidate_online?: boolean; camera_on?: boolean; mic_on?: boolean };
}

export default function MonitorPage() {
  const { id, sessionId } = useParams<{ id: string; sessionId: string }>();
  const { me } = useAuth();
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [videoOn, setVideoOn] = useState(false);
  const [now, setNow] = useState(Date.now());
  const videoRef = useRef<HTMLVideoElement>(null);
  const viewer = useRef<MonitorViewer | null>(null);
  const sendRef = useRef<(t: string, d: unknown) => void>(() => undefined);

  const load = useCallback(async () => {
    try {
      setLive(await api<Live>(`/monitoring/sessions/${sessionId}`));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [sessionId]);

  useEffect(() => {
    load();
    const t = setInterval(() => setNow(Date.now()), 1000);
    const p = setInterval(load, 10_000); // fallback refresh
    return () => { clearInterval(t); clearInterval(p); viewer.current?.close(); };
  }, [load]);

  const onEvent = useCallback(async (e: WsEvent) => {
    const data = e.data as Record<string, unknown>;
    if (e.type === "signal") return viewer.current?.handleSignal(data);
    if (e.type === "connection_status") {
      setLive((l) => (l ? { ...l, connection: { ...l.connection, ...(data as Live["connection"]) } } : l));
      if (data.candidate_online) viewer.current?.requestOffer();
      return;
    }
    if (["question", "transcript", "evaluation_update", "session_state", "interview_completed", "answer_received"].includes(e.type)) load();
  }, [load]);

  const { connected, send } = useInterviewSocket(sessionId, "monitor", onEvent);
  sendRef.current = send;

  useEffect(() => {
    if (!me || !live) return;
    if (!viewer.current) {
      viewer.current = new MonitorViewer(me.id, (t, d) => sendRef.current(t, d), live.state.ice_servers, (s) => {
        if (videoRef.current) videoRef.current.srcObject = s;
        setVideoOn(true);
      });
    }
  }, [me, live]);

  useEffect(() => {
    if (connected) setTimeout(() => viewer.current?.requestOffer(), 500);
  }, [connected]);

  async function terminate() {
    if (!confirm("Terminate this interview now? The candidate's results so far will be finalised.")) return;
    await api(`/monitoring/sessions/${sessionId}/terminate`, { method: "POST" });
    load();
  }

  if (error && !live) return <ErrorBox message={error} onRetry={load} />;
  if (!live) return <Spinner />;
  const st = live.state;
  const started = st.started_at ? new Date(st.started_at).getTime() : now;
  const elapsed = st.status === "completed" ? st.elapsed_seconds : (now - started) / 1000;
  const c = live.connection;

  return (
    <>
      <PageHeader title={`Live monitoring · ${live.candidate.full_name}`}
        subtitle="The AI conducts this interview autonomously — monitoring is optional and does not affect it."
        action={<div className="flex gap-2">
          <Link href={`/institution/interviews/${id}`}><Button variant="secondary">Back</Button></Link>
          {["in_progress", "initializing"].includes(st.status) && <Button variant="danger" onClick={terminate}>Terminate</Button>}
        </div>} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat label="Status" value={<Badge>{st.status}</Badge>} />
        <Stat label="Question" value={`${st.question_index} / ${st.question_count}`} />
        <Stat label="Topic" value={<span className="text-base">{st.current_topic ?? "–"}</span>} />
        <Stat label="Difficulty" value={label(st.current_difficulty)} />
        <Stat label="Duration" value={mmss(elapsed)} hint={`of ${st.duration_minutes} min`} />
        <Stat label="Running score" value={pct(live.running_score, 1)} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2" title="Candidate video">
          <div className="relative">
            <video ref={videoRef} autoPlay playsInline muted className="aspect-video w-full rounded-lg bg-black object-cover" />
            {!videoOn && <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">Waiting for candidate stream…</div>}
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-xs">
            <span className="flex items-center gap-1">{connected ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4 text-red-600" />} Monitor {connected ? "connected" : "offline"}</span>
            <span className="flex items-center gap-1"><Badge tone={c.candidate_online ? "active" : "failed"}>{c.candidate_online ? "Candidate online" : "Candidate offline"}</Badge></span>
            <span className="flex items-center gap-1">{c.camera_on ? <Camera className="h-4 w-4" /> : <CameraOff className="h-4 w-4 text-red-600" />} Camera</span>
            <span className="flex items-center gap-1">{c.mic_on ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4 text-red-600" />} Microphone</span>
          </div>
          <div className="mt-3"><Progress value={st.progress} /></div>
          {st.current_question && <p className="mt-3 text-sm"><span className="muted">Current question: </span>{st.current_question.text}</p>}
        </Card>
        <Card className="lg:col-span-3" title="Live transcript">
          <ol className="max-h-[60vh] space-y-4 overflow-y-auto pr-2">
            {live.transcript.map((t) => (
              <li key={t.sequence} className="text-sm">
                <div className="flex flex-wrap items-center gap-2 text-xs muted">
                  <span>Q{t.sequence}</span><Badge>{t.topic ?? "General"}</Badge><Badge>{t.difficulty}</Badge>
                  {t.score != null && <span className="tabular-nums">score {t.score.toFixed(0)}</span>}
                </div>
                <p className="mt-1 font-medium">{t.question}</p>
                <p className="mt-1 muted">{t.answer ?? (t.answer_status ? `(${label(t.answer_status)})` : "Awaiting answer…")}</p>
                {t.next_question_reason && <p className="mt-1 text-xs faint">Next-question decision: {t.next_question_reason}</p>}
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </>
  );
}
