"use client";

import clsx from "clsx";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Tilt } from "./fx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Button({ variant = "primary", className, loading, children, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; loading?: boolean }) {
  return (
    <button
      {...p}
      disabled={p.disabled || loading}
      className={clsx(
        "btn-3d inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "btn-primary",
        variant === "secondary" && "btn-secondary",
        variant === "danger" && "btn-danger",
        variant === "ghost" && "text-[var(--ink-2)] hover:bg-white/10 hover:text-white",
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("card card-hover p-5", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-2">
          {title && <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide">
            <span className="h-3.5 w-1 rounded-full bg-gradient-to-b from-violet-400 to-cyan-400" />{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <Tilt className="card overflow-hidden p-4" max={12}>
      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-violet-500/20 blur-2xl" />
      <div className="pop-sm">
        <div className="text-xs font-medium uppercase tracking-wider faint">{label}</div>
        <div className="font-display mt-2 text-3xl font-semibold tabular-nums text-gradient">{value ?? "–"}</div>
        {hint && <div className="mt-1 text-xs muted">{hint}</div>}
      </div>
    </Tilt>
  );
}

const BADGE: Record<string, string> = {
  active: "bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/30",
  in_progress: "bg-sky-400/10 text-sky-300 ring-1 ring-sky-400/30",
  completed: "bg-violet-400/10 text-violet-200 ring-1 ring-violet-400/30",
  pending_approval: "bg-amber-400/10 text-amber-200 ring-1 ring-amber-400/30",
  pending: "bg-amber-400/10 text-amber-200 ring-1 ring-amber-400/30",
  failed: "bg-rose-400/10 text-rose-300 ring-1 ring-rose-400/30",
  cancelled: "bg-rose-400/10 text-rose-300 ring-1 ring-rose-400/30",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const key = (tone ?? String(children)).toLowerCase().replace(/ /g, "_");
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
      BADGE[key] ?? "bg-white/10 text-[var(--ink-2)]")}>
      {typeof children === "string" ? children.replace(/_/g, " ") : children}
    </span>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wider muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs faint">{hint}</span>}
    </label>
  );
}

const inputCls = "input-glow w-full rounded-xl border border-theme bg-white/[0.03] px-3.5 py-2.5 text-sm outline-none placeholder:text-[var(--ink-3)]";
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={clsx(inputCls, p.className)} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={clsx(inputCls, p.className)} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={clsx(inputCls, "bg-[var(--card-solid)]", p.className)} />;

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin text-violet-400" /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200 backdrop-blur">
      <span className="flex items-center gap-2"><AlertTriangle className="h-4 w-4" />{message}</span>
      {onRetry && <Button variant="secondary" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-theme bg-white/[0.02] p-8 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="mt-2 text-sm muted">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-3xl font-semibold text-gradient">{title}</h1>
        {subtitle && <p className="mt-1 text-sm muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/10" role="progressbar"
      aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-bar h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(100, value * 100)}%` }} />
    </div>
  );
}

export function Table({ head, rows, empty = "No data yet" }: { head: ReactNode[]; rows: ReactNode[][]; empty?: string }) {
  if (!rows.length) return <Empty title={empty} />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-theme text-[11px] uppercase tracking-wider faint">
          <tr>{head.map((h, i) => <th key={i} className="px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-theme transition-colors last:border-0 hover:bg-white/[0.04]">
              {r.map((c, j) => <td key={j} className="px-3 py-2 align-top">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
