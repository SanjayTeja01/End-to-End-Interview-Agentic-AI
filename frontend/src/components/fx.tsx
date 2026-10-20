"use client";

import clsx from "clsx";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Animated aurora + perspective grid background, fixed behind the page. */
export function Aurora({ subtle = false, grid = true }: { subtle?: boolean; grid?: boolean }) {
  return (
    <div className={clsx("aurora", subtle && "subtle")} aria-hidden>
      <div className="blob b1" />
      <div className="blob b2" />
      <div className="blob b3" />
      {grid && <div className="grid-floor" />}
      <div className="noise" />
    </div>
  );
}

/** Mouse-tracked 3D tilt with a moving glare highlight. */
export function Tilt({ children, className, max = 10, scale = 1.02, style }:
  { children: ReactNode; className?: string; max?: number; scale?: number; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null);
  const frame = useRef<number>(0);

  function onMove(e: React.PointerEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el || e.pointerType === "touch" || reducedMotion()) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      el.style.transform = `perspective(900px) rotateX(${(0.5 - py) * max}deg) rotateY(${(px - 0.5) * max}deg) scale(${scale})`;
      el.style.setProperty("--gx", `${px * 100}%`);
      el.style.setProperty("--gy", `${py * 100}%`);
    });
  }
  function onLeave() {
    cancelAnimationFrame(frame.current);
    if (ref.current) ref.current.style.transform = "";
  }

  return (
    <div ref={ref} onPointerMove={onMove} onPointerLeave={onLeave} className={clsx("tilt relative", className)} style={style}>
      {children}
      <span className="tilt-glare" aria-hidden />
    </div>
  );
}

/** Fades and un-rotates its children into view when scrolled to. */
export function Reveal({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") { el.classList.add("in"); return; }
    const io = new IntersectionObserver(([en]) => {
      if (en.isIntersecting) { el.classList.add("in"); io.disconnect(); }
    }, { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className={clsx("reveal", className)} style={{ transitionDelay: `${delay}ms` }}>{children}</div>;
}

/** Parallax: the whole stage leans toward the pointer. */
function useParallax<T extends HTMLElement>(strength = 12) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    let raf = 0;
    const move = (e: PointerEvent) => {
      const x = e.clientX / window.innerWidth - 0.5;
      const y = e.clientY / window.innerHeight - 0.5;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => { el.style.transform = `rotateY(${x * strength}deg) rotateX(${-y * strength}deg)`; });
    };
    window.addEventListener("pointermove", move);
    return () => { window.removeEventListener("pointermove", move); cancelAnimationFrame(raf); };
  }, [strength]);
  return ref;
}

const QUESTIONS = [
  "Walk me through how you would design a URL shortener.",
  "Your resume mentions FastAPI. How did you handle authentication?",
  "What happens when a database index is missing on a hot query?",
  "Explain the trade-offs between REST and WebSockets.",
];

/** Types each question out, pauses, deletes it and moves to the next one. */
export function Typewriter({ lines = QUESTIONS, className }: { lines?: string[]; className?: string }) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (reducedMotion()) { setText(lines[0]); return; }
    let line = 0, pos = 0, deleting = false, t: ReturnType<typeof setTimeout>;
    const tick = () => {
      const full = lines[line];
      if (!deleting) {
        pos++;
        setText(full.slice(0, pos));
        if (pos === full.length) { deleting = true; t = setTimeout(tick, 2600); return; }
        t = setTimeout(tick, 32 + Math.random() * 40);
      } else {
        pos = Math.max(0, pos - 3);
        setText(full.slice(0, pos));
        if (pos === 0) { deleting = false; line = (line + 1) % lines.length; t = setTimeout(tick, 400); return; }
        t = setTimeout(tick, 18);
      }
    };
    t = setTimeout(tick, 600);
    return () => clearTimeout(t);
  }, [lines]);
  return <span className={className}>{text}<span className="caret" aria-hidden /></span>;
}

function Gauge({ value, size = 76 }: { value: number; size?: number }) {
  const r = 30, c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 72 72" width={size} height={size} className="-rotate-90">
      <defs>
        <linearGradient id="g-ready" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#a78bfa" /><stop offset="1" stopColor="#22d3ee" /></linearGradient>
      </defs>
      <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="7" />
      <circle cx="36" cy="36" r={r} fill="none" stroke="url(#g-ready)" strokeWidth="7" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} className="gauge-arc" style={{ ["--c" as string]: c } as CSSProperties} />
    </svg>
  );
}

/** Animated AI interviewer: a glowing avatar with voice ripples while it talks. */
export function AIAvatar({ mode = "idle", size = "lg" }: { mode?: "idle" | "speaking" | "listening" | "thinking"; size?: "sm" | "lg" }) {
  return (
    <div className={clsx("ai-avatar", mode, size)} aria-hidden>
      <span className="ripple" /><span className="ripple r2" /><span className="ripple r3" />
      <div className="face">
        <svg viewBox="0 0 48 48" className="h-1/2 w-1/2" fill="none" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="14" width="30" height="22" rx="8" />
          <path d="M24 8v6M17 36v4M31 36v4" />
          <circle cx="18.5" cy="24" r="2" fill="white" className="eye" />
          <circle cx="29.5" cy="24" r="2" fill="white" className="eye" />
          <path d="M19 30.5c3 2 7 2 10 0" className="mouth" />
        </svg>
      </div>
    </div>
  );
}

/** The 3D hero scene: a live AI interview in a tilted video-call window with floating evaluation cards. */
export function InterviewScene({ compact = false }: { compact?: boolean }) {
  const ref = useParallax<HTMLDivElement>(10);
  return (
    <div className={clsx("scene mx-auto", compact && "compact")} aria-hidden>
      <div ref={ref} className="absolute inset-0 preserve-3d transition-transform duration-300 ease-out">
        <div className="scene-inner">
          {/* video call window */}
          <div className="call card">
            <div className="flex items-center justify-between border-b border-theme px-4 py-2.5">
              <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-rose-400/80" /><span className="h-2.5 w-2.5 rounded-full bg-amber-300/80" /><span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" /></div>
              <div className="hidden text-[11px] font-medium muted sm:block">Live interview · Backend Developer</div>
              <span className="flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-300">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-400" />Live</span>
            </div>
            <div className="grid grid-cols-2 gap-3 p-3">
              <div className="tile relative flex flex-col items-center justify-center">
                <AIAvatar mode="speaking" size="sm" />
                <div className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-violet-200">AI Interviewer <Wave /></div>
              </div>
              <div className="tile candidate relative flex items-end justify-center overflow-hidden">
                <svg viewBox="0 0 120 100" className="h-[85%] w-auto" fill="none">
                  <circle cx="60" cy="38" r="18" fill="rgba(167,139,250,0.35)" />
                  <path d="M22 100c4-24 20-36 38-36s34 12 38 36" fill="rgba(103,232,249,0.22)" />
                </svg>
                <span className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-rose-600/90 px-2 py-0.5 text-[9px] font-semibold text-white">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />REC</span>
                <span className="absolute bottom-2 left-2 rounded-md bg-black/50 px-1.5 py-0.5 text-[10px]">You</span>
              </div>
            </div>
            <div className="mx-3 mb-3 rounded-xl border border-theme bg-white/[0.03] p-3">
              <div className="mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider faint">
                <span>Question 3 of 8</span><span className="text-cyan-300">System design · medium</span>
              </div>
              <div className="mb-2 h-1 overflow-hidden rounded-full bg-white/10"><div className="progress-bar h-full w-[38%] rounded-full" /></div>
              <Typewriter className="font-display block min-h-[2.6em] text-[13px] leading-snug text-white" />
            </div>
          </div>

          {/* floating: answer evaluation */}
          <div className="float-card fc-eval">
            <div className="card w-[210px] p-3.5">
              <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider faint"><span>Answer evaluation</span><span className="text-emerald-300">Strong</span></div>
              {[["Correctness", 86], ["Depth", 72], ["Communication", 91]].map(([k, v], i) => (
                <div key={k} className="mb-1.5 last:mb-0">
                  <div className="flex justify-between text-[11px]"><span className="muted">{k}</span><span className="tabular-nums">{v}</span></div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div className="bar-fill h-full rounded-full bg-gradient-to-r from-violet-400 to-cyan-300" style={{ width: `${v}%`, animationDelay: `${i * 0.25}s` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* floating: readiness gauge */}
          <div className="float-card fc-ready">
            <div className="card flex items-center gap-3 p-3 pr-4">
              <div className="relative"><Gauge value={82} size={compact ? 60 : 68} />
                <span className="font-display absolute inset-0 flex items-center justify-center text-lg font-semibold">82</span></div>
              <div><div className="text-[10px] font-semibold uppercase tracking-wider faint">Readiness</div>
                <div className="text-sm font-semibold text-emerald-300">Nearly ready</div></div>
            </div>
          </div>

          {/* floating: resume skills */}
          <div className="float-card fc-resume">
            <div className="card p-3">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider faint">From your resume</div>
              <div className="flex max-w-[180px] flex-wrap gap-1">
                {["Python", "FastAPI", "SQL", "Docker"].map((t) => (
                  <span key={t} className="rounded-full bg-violet-400/15 px-2 py-0.5 text-[10px] text-violet-200 ring-1 ring-violet-400/30">{t}</span>
                ))}
              </div>
            </div>
          </div>

          {/* floating: adaptive next step */}
          <div className="float-card fc-next">
            <div className="card flex items-center gap-2 px-3 py-2 text-[11px]">
              <span className="flex h-5 w-5 items-center justify-center rounded-md bg-cyan-400/20 text-cyan-200">↑</span>
              <span>Next: <b className="text-cyan-200">harder follow-up</b></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Kept for existing imports: the AI interviewer shown in the live room. */
export function AIOrb({ mode }: { mode: "idle" | "speaking" | "listening" | "thinking" }) {
  return <AIAvatar mode={mode} />;
}

export function Wave() {
  return <span className="wave" aria-hidden><span /><span /><span /><span /><span /></span>;
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("relative inline-flex h-9 w-9 items-center justify-center rounded-xl", className)}
      style={{ background: "linear-gradient(135deg,#8b6cff,#22d3ee)", boxShadow: "0 8px 24px -6px rgba(124,92,255,.8), inset 0 1px 0 rgba(255,255,255,.35)" }}>
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
        <path d="M19 11a7 7 0 0 1-14 0M12 18v3" />
      </svg>
    </span>
  );
}
