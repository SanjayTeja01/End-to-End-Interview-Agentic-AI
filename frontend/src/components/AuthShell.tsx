"use client";

import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Aurora, InterviewScene, Logo } from "./fx";

export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      <Aurora />
      <div className="relative hidden flex-col justify-between overflow-hidden p-10 lg:flex">
        <Link href="/" className="flex items-center gap-3">
          <Logo />
          <span className="font-display text-base font-semibold tracking-tight">Interview Agent</span>
        </Link>
        <div className="mx-auto w-full max-w-lg">
          <InterviewScene compact />
        </div>
        <ul className="space-y-3 text-sm muted">
          {["Questions that adapt to each answer", "Feedback scored against a clear rubric", "A readiness report after every interview"].map((t) => (
            <li key={t} className="flex items-center gap-3"><CheckCircle2 className="h-4 w-4 text-cyan-300" />{t}</li>
          ))}
        </ul>
      </div>
      <div className="relative flex items-center justify-center p-4 sm:p-8">
        <div className="page-enter w-full max-w-md">
          <Link href="/" className="mb-8 flex items-center gap-3 lg:hidden">
            <Logo />
            <span className="font-display text-base font-semibold tracking-tight">Interview Agent</span>
          </Link>
          <div className="card relative overflow-hidden p-7 sm:p-9">
            <div className="pointer-events-none absolute -top-24 left-1/2 h-48 w-72 -translate-x-1/2 rounded-full bg-violet-600/25 blur-3xl" />
            <div className="relative">
              <h1 className="font-display text-3xl font-semibold text-gradient">{title}</h1>
              <p className="mt-2 text-sm muted">{subtitle}</p>
              <div className="mt-7">{children}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
