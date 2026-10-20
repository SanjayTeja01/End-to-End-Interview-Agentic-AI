"use client";

import { ArrowRight, BarChart3, Brain, FileSearch, GraduationCap, Mic, ShieldCheck, Sparkles, Video, Building2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Aurora, InterviewScene, Logo, Reveal, Tilt } from "@/components/fx";
import { homeFor, useAuth } from "@/lib/auth";

const FEATURES = [
  { icon: Brain, title: "Adaptive AI interviewer", text: "Every question adapts to the candidate's last answer, their resume and the target role. Strong answers go deeper, weak ones get a gentler follow-up." },
  { icon: Mic, title: "Natural voice conversation", text: "The interviewer speaks each question aloud and listens to spoken answers, so it feels like a real interview rather than a quiz." },
  { icon: FileSearch, title: "Resume-aware questions", text: "Resumes are parsed into skills and projects, so questions focus on what the candidate has actually built." },
  { icon: BarChart3, title: "Rubric-based scoring", text: "Every answer is scored on clear criteria, with strengths, gaps and missing concepts written down for each one." },
  { icon: Video, title: "Live monitoring", text: "Institutions can watch sessions live, follow progress question by question and step in when needed." },
  { icon: ShieldCheck, title: "Fair by design", text: "There's no facial or emotion analysis. Candidates are scored only on what they say." },
];

const STEPS = [
  { n: "01", title: "Create", text: "The institution sets the role, topics, difficulty and number of questions." },
  { n: "02", title: "Interview", text: "Students join from their browser and talk with the AI interviewer." },
  { n: "03", title: "Improve", text: "Detailed reports show readiness, topic strengths and what to practise next." },
];

export default function Home() {
  const { me, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && me) router.replace(homeFor(me));
  }, [me, loading, router]);

  return (
    <div className="relative overflow-x-hidden">
      <Aurora />

      {/* nav */}
      <header className="sticky top-0 z-30 border-b border-white/5 bg-[rgba(7,10,20,0.55)] backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 md:px-8">
          <Link href="/" className="flex items-center gap-3">
            <Logo />
            <span className="font-display hidden text-base font-semibold tracking-tight sm:inline">Interview Agent</span>
          </Link>
          <nav className="hidden items-center gap-8 text-sm muted md:flex">
            <a href="#features" className="transition hover:text-white">Features</a>
            <a href="#how" className="transition hover:text-white">How it works</a>
            <a href="#who" className="transition hover:text-white">Who it&apos;s for</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/login" className="whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium muted transition hover:bg-white/10 hover:text-white sm:px-4">Sign in</Link>
            <Link href="/register" className="btn-3d btn-primary shimmer inline-flex items-center gap-2 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold">
              Get started <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>

      {/* hero */}
      <section className="mx-auto grid max-w-7xl items-center gap-10 px-4 pb-16 pt-12 md:px-8 lg:grid-cols-2 lg:pt-20">
        <div className="stagger">
          <span className="inline-flex items-center gap-2 rounded-full border border-violet-400/30 bg-violet-500/10 px-3 py-1 text-xs font-medium text-violet-200">
            <Sparkles className="h-3.5 w-3.5" /> AI video interviews for institutions
          </span>
          <h1 className="font-display mt-6 text-4xl font-bold leading-[1.05] sm:text-5xl lg:text-6xl">
            Interviews that <span className="text-gradient">adapt, listen</span> and help students get ready.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed muted sm:text-lg">
            An autonomous AI interviewer that runs realistic, role-specific video interviews, scores every answer against a clear rubric
            and turns the results into practical feedback.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/register" className="btn-3d btn-primary shimmer inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold">
              Create a free account <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/login" className="btn-3d btn-secondary inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold">
              I already have an account
            </Link>
          </div>
          <div className="mt-10 flex flex-wrap gap-8 text-sm">
            {[["Adaptive", "question flow"], ["Rubric", "based scoring"], ["Real-time", "monitoring"]].map(([a, b]) => (
              <div key={a}><div className="font-display text-xl font-semibold text-white">{a}</div><div className="faint">{b}</div></div>
            ))}
          </div>
        </div>
        <div className="relative px-8 sm:px-4">
          <InterviewScene />
        </div>
      </section>

      {/* features */}
      <section id="features" className="mx-auto max-w-7xl scroll-mt-24 px-4 py-20 md:px-8">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Features</p>
          <h2 className="font-display mt-3 text-3xl font-bold sm:text-4xl">Everything a real interview needs</h2>
          <p className="mt-4 muted">From the first question to the final report, every step is handled for you.</p>
        </Reveal>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={i * 80}>
              <Tilt className="card h-full overflow-hidden p-6" max={10}>
                <div className="pop">
                  <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500/30 to-cyan-400/20 ring-1 ring-white/10">
                    <f.icon className="h-6 w-6 text-violet-200" />
                  </span>
                  <h3 className="font-display mt-5 text-lg font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed muted">{f.text}</p>
                </div>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      {/* how it works */}
      <section id="how" className="mx-auto max-w-7xl scroll-mt-24 px-4 py-20 md:px-8">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">How it works</p>
          <h2 className="font-display mt-3 text-3xl font-bold sm:text-4xl">Three steps from setup to feedback</h2>
        </Reveal>
        <div className="relative mt-14 grid gap-6 md:grid-cols-3">
          <div className="absolute left-0 right-0 top-1/2 hidden h-px bg-gradient-to-r from-transparent via-violet-400/40 to-transparent md:block" />
          {STEPS.map((s, i) => (
            <Reveal key={s.n} delay={i * 120}>
              <Tilt className="card relative p-7" max={8}>
                <div className="pop">
                  <div className="font-display text-5xl font-bold text-gradient">{s.n}</div>
                  <h3 className="font-display mt-4 text-xl font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed muted">{s.text}</p>
                </div>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      {/* audiences */}
      <section id="who" className="mx-auto grid max-w-7xl scroll-mt-24 gap-6 px-4 py-20 md:px-8 lg:grid-cols-2">
        {[
          { icon: Building2, tag: "For institutions", title: "Run placement-ready interviews at scale",
            points: ["Create interviews by role, topic and difficulty", "Watch live sessions and step in at any time", "See cohort analytics and download reports"] },
          { icon: GraduationCap, tag: "For students", title: "Practise with an interviewer that adapts to you",
            points: ["Upload your resume and get questions about it", "Speak your answers naturally from your browser", "Get a readiness score and a clear plan for what to practise"] },
        ].map((a, i) => (
          <Reveal key={a.tag} delay={i * 120}>
            <Tilt className="card h-full overflow-hidden p-8" max={6} scale={1.01}>
              <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-violet-600/20 blur-3xl" />
              <div className="pop">
                <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">
                  <a.icon className="h-4 w-4" /> {a.tag}
                </span>
                <h3 className="font-display mt-4 text-2xl font-semibold">{a.title}</h3>
                <ul className="mt-6 space-y-3">
                  {a.points.map((p) => (
                    <li key={p} className="flex items-start gap-3 text-sm muted">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300 shadow-[0_0_10px_#22d3ee]" />{p}
                    </li>
                  ))}
                </ul>
              </div>
            </Tilt>
          </Reveal>
        ))}
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-5xl px-4 pb-24 pt-6 md:px-8">
        <Reveal>
          <div className="card relative overflow-hidden px-6 py-14 text-center md:px-16">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_200px_at_50%_0%,rgba(124,92,255,0.35),transparent)]" />
            <h2 className="font-display relative text-3xl font-bold sm:text-4xl">Ready for your next interview?</h2>
            <p className="relative mx-auto mt-4 max-w-xl muted">Join with your institution code, or set up your institution in a couple of minutes.</p>
            <div className="relative mt-8 flex flex-wrap justify-center gap-3">
              <Link href="/register" className="btn-3d btn-primary shimmer inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold">
                Get started <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/login" className="btn-3d btn-secondary inline-flex items-center rounded-xl px-6 py-3 text-sm font-semibold">Sign in</Link>
            </div>
          </div>
        </Reveal>
      </section>

      <footer className="border-t border-white/5 py-8 text-center text-xs faint">
        © {new Date().getFullYear()} Interview Agent · Readiness scores show how prepared a student is. They don&apos;t guarantee a hiring outcome.
      </footer>
    </div>
  );
}
