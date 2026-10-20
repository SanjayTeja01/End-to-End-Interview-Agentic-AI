"use client";

import { Camera, Mic } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AIOrb, Aurora, Tilt } from "@/components/fx";
import { StudentGuard } from "@/components/StudentGuard";
import { Badge, Button, Card, ErrorBox, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { CandidateInterview } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Prejoin() {
  const interviewId = useSearchParams().get("interview");
  const router = useRouter();
  const iv = useApi<CandidateInterview>(interviewId ? `/interviews/${interviewId}` : null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [devices, setDevices] = useState<{ cam: boolean; mic: boolean; error?: string }>({ cam: false, mic: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);

  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices?.getUserMedia({ video: true, audio: true })
      .then((s) => {
        stream = s;
        if (videoRef.current) videoRef.current.srcObject = s;
        setDevices({ cam: s.getVideoTracks().length > 0, mic: s.getAudioTracks().length > 0 });
      })
      .catch((e) => setDevices({ cam: false, mic: false, error: e?.message ?? "Camera/microphone unavailable" }));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  async function join() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ session_id: string }>(`/interviews/${interviewId}/start`, { method: "POST" });
      router.push(`/interview/${r.session_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not join the interview");
      setBusy(false);
    }
  }

  if (iv.loading) return <Spinner />;
  if (iv.error || !iv.data) return <ErrorBox message={iv.error ?? "Interview not available"} />;
  const d = iv.data;
  return (
    <div className="page-enter mx-auto max-w-5xl space-y-6 p-4 md:p-10">
      <Aurora subtle />
      <div className="flex flex-wrap items-center gap-6">
        <div className="scale-75"><AIOrb mode="idle" /></div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Get ready</p>
          <h1 className="font-display mt-1 text-3xl font-semibold text-gradient">{d.name}</h1>
          <p className="mt-1 text-sm muted">{d.target_role} · {d.question_count} questions · about {d.duration_minutes} minutes</p>
        </div>
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <Tilt className="card overflow-hidden" max={6} scale={1.01}>
          <video ref={videoRef} autoPlay muted playsInline className="aspect-video w-full bg-black object-cover" />
          <div className="flex gap-3 p-3 text-sm">
            <span className="flex items-center gap-1"><Camera className="h-4 w-4" /> <Badge tone={devices.cam ? "active" : "failed"}>{devices.cam ? "Camera ready" : "No camera"}</Badge></span>
            <span className="flex items-center gap-1"><Mic className="h-4 w-4" /> <Badge tone={devices.mic ? "active" : "failed"}>{devices.mic ? "Mic ready" : "No microphone"}</Badge></span>
          </div>
        </Tilt>
        <Card title="Before you start">
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed muted marker:text-violet-400">
            <li>An AI interviewer will ask one question at a time, out loud.</li>
            <li>Answer naturally by speaking, then press <b>Done answering</b>.</li>
            <li>Questions adapt to your answers, resume and target role.</li>
            <li>Your camera is used for the live interview and institution monitoring only — it is not analysed for facial or emotional traits.</li>
            <li>If you lose connection, rejoin from Available Interviews to resume.</li>
          </ul>
          <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-theme bg-white/[0.03] p-3 text-sm">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1 h-4 w-4 accent-violet-500" />
            I understand my answers are recorded, transcribed and evaluated by AI for my institution.
          </label>
        </Card>
      </div>
      {devices.error && <ErrorBox message={`${devices.error}. You can still join and type answers if needed.`} />}
      {error && <ErrorBox message={error} />}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => router.back()}>Back</Button>
        <Button className="shimmer px-6" onClick={join} loading={busy} disabled={!consent || !d.joinable}>{d.session_id ? "Resume interview" : "Join interview"}</Button>
      </div>
    </div>
  );
}

export default function Page() {
  return <StudentGuard><Suspense><Prejoin /></Suspense></StudentGuard>;
}
