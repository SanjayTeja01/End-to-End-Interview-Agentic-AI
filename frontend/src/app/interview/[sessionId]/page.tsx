"use client";

import clsx from "clsx";
import { Camera, CameraOff, Mic, MicOff, Wifi, WifiOff } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AIOrb, Aurora, Logo, Tilt, Wave } from "@/components/fx";
import { StudentGuard } from "@/components/StudentGuard";
import { Badge, Button, ErrorBox, Progress, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { label, mmss, uid } from "@/lib/format";
import { AnswerRecorder, extFor } from "@/lib/recorder";
import { LiveTranscriber } from "@/lib/speech";
import type { QuestionView, SessionState, TurnStatus, WsEvent } from "@/lib/types";
import { useInterviewSocket } from "@/lib/useInterviewSocket";
import { CandidatePublisher } from "@/lib/webrtc";

type Phase = "connecting" | "waiting" | "speaking" | "answering" | "uploading" | "processing" | "completed" | "error";

function Room() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [state, setState] = useState<SessionState | null>(null);
  const [question, setQuestion] = useState<QuestionView | null>(null);
  const [phase, setPhase] = useState<Phase>("connecting");
  const [heard, setHeard] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [cam, setCam] = useState(false);
  const [mic, setMic] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [typed, setTyped] = useState("");
  const [showTyped, setShowTyped] = useState(false);
  const [pendingUpload, setPendingUpload] = useState<FormData | null>(null);
  const [ending, setEnding] = useState(false);
  const [turn, setTurn] = useState<TurnStatus | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorder = useRef(new AnswerRecorder());
  const transcriber = useRef(new LiveTranscriber());
  const autoEnded = useRef(false);
  const presented = useRef<string | null>(null);
  const keys = useRef<Record<string, string>>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const publisher = useRef<CandidatePublisher | null>(null);
  const sendRef = useRef<(t: string, d: unknown) => void>(() => undefined);

  const keyFor = (qid: string) => (keys.current[qid] ??= uid());

  // ---------------- media
  useEffect(() => {
    navigator.mediaDevices?.getUserMedia({ video: { width: 640, height: 360 }, audio: { echoCancellation: true, noiseSuppression: true } })
      .then((s) => {
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
        setCam(s.getVideoTracks().length > 0);
        setMic(s.getAudioTracks().length > 0);
      })
      .catch(() => {
        setNotice("Camera or microphone unavailable — you can type your answers instead.");
        setShowTyped(true);
      });
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(t);
      streamRef.current?.getTracks().forEach((tr) => tr.stop());
      publisher.current?.close();
      window.speechSynthesis?.cancel();
    };
  }, []);

  const refresh = useCallback(async () => {
    const st = await api<SessionState>(`/interview/${sessionId}/state`);
    setState(st);
    return st;
  }, [sessionId]);

  // ---------------- question presentation (TTS → answer)
  const startAnswering = useCallback(() => {
    setPhase("answering");
    if (streamRef.current && streamRef.current.getAudioTracks().length) {
      recorder.current.start(streamRef.current, !!state?.record_media);
      transcriber.current.onText = (t) => setHeard(t || null);
      transcriber.current.start();
    }
  }, [state?.record_media]);

  const present = useCallback((q: QuestionView, awaiting: string) => {
    setQuestion(q);
    if (awaiting !== "answer") {
      setPhase("processing");
      return;
    }
    if (presented.current === q.id) return;
    presented.current = q.id;
    setHeard(null);
    setPhase("speaking");
    const spoken = q.spoken_text || q.text;
    const done = () => startAnswering();
    if (q.tts_url) {
      const a = new Audio(q.tts_url);
      audioRef.current = a;
      a.onended = done;
      a.onerror = () => speakFallback(spoken, done);
      a.play().catch(() => speakFallback(spoken, done));
    } else {
      speakFallback(spoken, done);
    }
  }, [startAnswering]);

  const applyState = useCallback((st: SessionState) => {
    setState(st);
    setTurn(st.turn ?? null);
    if (st.status === "completed") { setPhase("completed"); setNotice(null); }
    else if (st.current_question) present(st.current_question, st.awaiting);
    else setPhase("waiting");
  }, [present]);

  // ---------------- realtime
  const onEvent = useCallback(async (e: WsEvent) => {
    const data = e.data as Record<string, unknown>;
    switch (e.type) {
      case "snapshot":
        applyState((data as { state: SessionState }).state);
        break;
      case "question":
      case "session_state":
        applyState(await refresh());
        break;
      case "turn_status":
        setTurn((t) => ({ ...(t ?? {}), ...(data as unknown as TurnStatus) }));
        break;
      case "transcript":
        setHeard(String(data.text ?? ""));
        break;
      case "interview_finalizing":
        setPhase("processing");
        setNotice("Wrapping up the interview…");
        break;
      case "interview_completed":
        setNotice(null);
        setClosing(String(data.closing ?? ""));
        speakFallback(String(data.closing ?? ""), () => undefined);
        setPhase("completed");
        break;
      case "error":
        setNotice(String(data.message ?? "Something went wrong"));
        if (data.retry_allowed && question) {
          presented.current = null;
          delete keys.current[question.id];
          setPhase("answering");
          startAnswering();
        }
        break;
      case "signal":
        await publisher.current?.handleSignal(data);
        break;
    }
  }, [applyState, refresh, question, startAnswering]);

  const { connected, send } = useInterviewSocket(sessionId, "candidate", onEvent);
  sendRef.current = send;

  useEffect(() => {
    publisher.current = new CandidatePublisher(() => streamRef.current, (t, d) => sendRef.current(t, d), state?.ice_servers ?? []);
  }, [state?.ice_servers]);

  useEffect(() => {
    send("status", { camera_on: cam, mic_on: mic, connected });
  }, [cam, mic, connected]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll as a safety net if a WebSocket event is missed
  useEffect(() => {
    if (phase !== "processing" && phase !== "waiting" && phase !== "connecting") return;
    const t = setInterval(() => refresh().then(applyState).catch(() => undefined), 3000);
    return () => clearInterval(t);
  }, [phase, refresh, applyState]);

  // ---------------- answer submission
  async function upload(form: FormData) {
    setPhase("uploading");
    try {
      await api(`/interview/${sessionId}/answer`, { method: "POST", form });
      setPendingUpload(null);
      setPhase("processing");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setPendingUpload(null);
        applyState(await refresh());
        return;
      }
      setPendingUpload(form); // keep the recording; retry reuses the same idempotency key
      setNotice("Upload failed — check your connection and retry. Your answer has not been lost.");
      setPhase("error");
    }
  }

  async function finishAnswer() {
    if (!question) return;
    if (!recorder.current.recording) {
      setShowTyped(true);
      return;
    }
    const spoken = transcriber.current.stop();
    const rec = await recorder.current.stop();
    const form = new FormData();
    if (spoken.split(/\s+/).length >= 3) form.append("transcript", spoken); // lets the server skip slow STT
    form.append("question_id", question.id);
    form.append("idempotency_key", keyFor(question.id));
    form.append("started_at", rec.startedAt.toISOString());
    form.append("ended_at", rec.endedAt.toISOString());
    form.append("audio", rec.audio, `answer.${extFor(rec.audio.type)}`);
    if (rec.video) form.append("video", rec.video, "answer.webm");
    await upload(form);
  }

  async function submitTyped() {
    if (!question || !typed.trim()) return;
    if (recorder.current.recording) { transcriber.current.stop(); await recorder.current.stop(); }
    setPhase("uploading");
    try {
      await api(`/interview/${sessionId}/answer/text`, { method: "POST",
        json: { question_id: question.id, transcript: typed.trim(), idempotency_key: keyFor(question.id) } });
      setTyped("");
      setPhase("processing");
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not submit answer");
      setPhase("answering");
    }
  }

  async function retryEvaluation() {
    if (!turn?.answer_id) return;
    setTurn({ ...turn, phase: "evaluating", retry_allowed: false });
    try {
      await api(`/interview/${sessionId}/answer/${turn.answer_id}/retry`, { method: "POST" });
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not retry. Check your connection.");
    }
  }

  async function stopEverything() {
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    transcriber.current.stop();
    if (recorder.current.recording) await recorder.current.stop().catch(() => undefined);
  }

  async function endInterview() {
    if (ending || !confirm("End the interview now? Unanswered questions will not be asked.")) return;
    setEnding(true);
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    await stopEverything();
    setPhase("processing");
    setNotice("Ending the interview and preparing your report…");
    try {
      await api(`/interview/${sessionId}/complete`, { method: "POST", json: { reason: "ended_by_candidate" } });
      applyState(await refresh());
    } catch (e) {
      setEnding(false);
      setNotice(e instanceof ApiError ? `Could not end the interview: ${e.message}` : "Could not end the interview — check your connection and try again.");
    }
  }

  const toggle = (kind: "audio" | "video") => {
    const tracks = kind === "audio" ? streamRef.current?.getAudioTracks() : streamRef.current?.getVideoTracks();
    tracks?.forEach((t) => (t.enabled = !t.enabled));
    if (kind === "audio") setMic((m) => !m); else setCam((c) => !c);
  };

  // ---------------- derived
  const started = state?.started_at ? new Date(state.started_at).getTime() : null;
  const elapsed = started ? (now - started) / 1000 : state?.elapsed_seconds ?? 0;
  const remaining = state ? state.duration_minutes * 60 - elapsed : 0;
  const speaking = phase === "speaking";
  const evalFailed = phase === "processing" && turn?.phase === "evaluation_failed";
  const busyLabel = phase === "uploading" ? "Sending…" : ending ? "Wrapping up…" : ({
    transcribing: "Transcribing your answer…",
    evaluating: (turn?.attempts ?? 0) > 1 ? `Evaluating your answer (attempt ${turn?.attempts})…` : "Evaluating your answer…",
    retrying: "Still evaluating your answer…",
    choosing_next: "Choosing your next question…",
  } as Record<string, string>)[turn?.phase ?? ""] ?? "Evaluating your answer…";

  // Time is up: end automatically (the server also ends it on its own a few seconds later as a safety net).
  useEffect(() => {
    if (!state || remaining > 0 || autoEnded.current || phase === "completed" || state.status === "completed") return;
    autoEnded.current = true;
    setEnding(true);
    setPhase("processing");
    setNotice("Time is up. Ending the interview and preparing your report…");
    stopEverything()
      .then(() => api(`/interview/${sessionId}/complete`, { method: "POST", json: { reason: "duration_reached" } }))
      .then(() => refresh().then(applyState))
      .catch(() => undefined); // the server-side clock ends it anyway; polling picks up the result
  }, [remaining, state, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex min-h-screen flex-col">
      <Aurora subtle grid={false} />
      <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-theme bg-[rgba(7,10,20,0.6)] px-4 py-3 backdrop-blur-xl md:px-6">
        <div className="flex items-center gap-3">
          <Logo className="h-8 w-8" />
          <div className="font-display text-sm font-semibold">Live interview</div>
          <span className="flex items-center gap-1.5 rounded-full bg-rose-500/15 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-rose-300 ring-1 ring-rose-400/30">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-400" />Live</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {[
            { on: connected, icon: connected ? Wifi : WifiOff, text: connected ? "Connected" : "Reconnecting…" },
            { on: mic, icon: mic ? Mic : MicOff, text: mic ? "Mic on" : "Mic off" },
            { on: cam, icon: cam ? Camera : CameraOff, text: cam ? "Camera on" : "Camera off" },
          ].map(({ on, icon: Icon, text }) => (
            <span key={text} className={clsx("flex items-center gap-1.5 rounded-full px-2.5 py-1 ring-1",
              on ? "bg-emerald-400/10 text-emerald-200 ring-emerald-400/25" : "bg-rose-400/10 text-rose-200 ring-rose-400/25")}>
              <Icon className="h-3.5 w-3.5" />{text}</span>
          ))}
          <span className={clsx("font-display rounded-full px-3 py-1 text-sm font-semibold tabular-nums ring-1",
            remaining < 120 ? "bg-rose-500/15 text-rose-300 ring-rose-400/40" : "bg-white/5 ring-white/10")} aria-label="Time remaining">⏱ {mmss(remaining)}</span>
        </div>
      </header>

      <div className="grid flex-1 gap-5 p-4 md:p-6 lg:grid-cols-2">
        <Tilt className="card flex min-h-[300px] flex-col items-center justify-center overflow-hidden p-6" max={5} scale={1}>
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(400px_260px_at_50%_45%,rgba(124,92,255,0.22),transparent)]" />
          <div className="pop">
            <AIOrb mode={speaking ? "speaking" : phase === "answering" ? "listening" : phase === "processing" || phase === "uploading" ? "thinking" : "idle"} />
          </div>
          <div className="pop-sm mt-6 flex flex-col items-center">
            <div className="font-display text-base font-semibold">AI Interviewer</div>
            <div className="mt-2 flex items-center gap-2 text-xs muted">
              {(speaking || phase === "answering") && <Wave />}
              {speaking ? "Speaking…" : phase === "answering" ? "Listening…" : phase === "processing" ? (evalFailed ? "Waiting for you" : busyLabel) : label(phase)}
            </div>
          </div>
        </Tilt>
        <div className={clsx("card relative min-h-[300px] overflow-hidden transition-shadow duration-500",
          phase === "answering" && "shadow-[0_0_0_2px_rgba(244,63,94,0.55),0_0_60px_-10px_rgba(244,63,94,0.6)]")}>
          <video ref={videoRef} autoPlay muted playsInline className="h-full min-h-[300px] w-full bg-black object-cover" />
          <span className="absolute bottom-3 left-3 rounded-lg bg-black/50 px-2.5 py-1 text-xs font-medium backdrop-blur">You</span>
          {phase === "answering" && <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-rose-600/90 px-3 py-1 text-xs font-semibold text-white shadow-lg backdrop-blur"><span className="h-2 w-2 animate-pulse rounded-full bg-white" />Recording answer</span>}
        </div>
      </div>

      <div className="space-y-4 px-4 pb-6 md:px-6">
        {state && (
          <div className="card p-5 md:p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs muted">
              <span className="font-semibold uppercase tracking-wider">Question {state.question_index || "–"} of {state.question_count}</span>
              {question && <span className="flex gap-2"><Badge>{question.topic ?? "General"}</Badge><Badge>{question.difficulty}</Badge></span>}
            </div>
            <Progress value={state.progress} />
            <p key={phase === "completed" ? "done" : question?.id ?? "none"} className="page-enter font-display mt-5 text-xl leading-snug md:text-2xl" aria-live="polite">
              {phase === "completed" ? (closing || "The interview is complete.") : question?.text ?? "Preparing your first question…"}</p>
            {heard && <p className="mt-4 rounded-xl border border-theme bg-white/[0.04] p-3 text-sm"><span className="muted">We heard: </span>{heard}</p>}
          </div>
        )}
        {evalFailed && (
          <div role="alert" className="rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100">
            We couldn&apos;t evaluate your answer just now. Your answer is saved, and the next question is chosen from its
            evaluation, so press <b>Retry evaluation</b> to try again.
          </div>
        )}
        {notice && (ending
          ? <div role="status" className="flex items-center gap-3 rounded-xl border border-violet-400/30 bg-violet-500/10 p-3 text-sm text-violet-100"><Wave />{notice}</div>
          : <ErrorBox message={notice} />)}

        {phase === "completed" ? (
          <div className="flex justify-end"><Link href={`/student/history/${sessionId}`}><Button className="shimmer px-6 py-3">View results</Button></Link></div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => toggle("audio")}>{mic ? "Mute" : "Unmute"}</Button>
              <Button variant="secondary" onClick={() => toggle("video")}>{cam ? "Stop camera" : "Start camera"}</Button>
              <Button variant="danger" onClick={endInterview} disabled={ending}>{ending ? "Ending…" : "End interview"}</Button>
            </div>
            <div className="flex gap-2">
              {speaking && <Button variant="secondary" onClick={() => { audioRef.current?.pause(); window.speechSynthesis?.cancel(); startAnswering(); }}>Skip to answer</Button>}
              {phase === "error" && pendingUpload && <Button onClick={() => upload(pendingUpload)}>Retry upload</Button>}
              {phase === "answering" && <Button onClick={finishAnswer}>Done answering</Button>}
              {evalFailed && turn?.retry_allowed && <Button onClick={retryEvaluation}>Retry evaluation</Button>}
              {(phase === "uploading" || phase === "processing") && !evalFailed && <Button loading disabled>{busyLabel}</Button>}
              {phase === "answering" && !showTyped && <Button variant="ghost" onClick={() => setShowTyped(true)}>Type instead</Button>}
            </div>
          </div>
        )}
        {showTyped && phase === "answering" && (
          <div className="card space-y-2 p-4">
            <Textarea rows={4} value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type your answer (fallback if your microphone isn't working)" />
            <div className="flex justify-end"><Button onClick={submitTyped} disabled={!typed.trim()}>Submit typed answer</Button></div>
          </div>
        )}
      </div>
    </div>
  );
}

function speakFallback(text: string, onEnd: () => void) {
  // Used only when server-side TTS audio is unavailable.
  if (typeof window === "undefined" || !window.speechSynthesis || !text) return onEnd();
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1;
  u.onend = onEnd;
  u.onerror = onEnd;
  window.speechSynthesis.speak(u);
}

export default function Page() {
  return <StudentGuard><Room /></StudentGuard>;
}
