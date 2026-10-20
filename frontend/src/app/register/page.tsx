"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [type, setType] = useState<"student" | "institution">("student");
  const [form, setForm] = useState({ full_name: "", email: "", password: "", institution_code: "", institution_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = { account_type: type, full_name: form.full_name, email: form.email, password: form.password };
      if (type === "student") body.institution_code = form.institution_code;
      else body.institution_name = form.institution_name;
      const me = await register(body);
      router.replace(homeFor(me));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Students join with their institution's code. Institutions can set up in minutes.">
      <form onSubmit={submit} className="space-y-5">
        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-white/[0.04] p-1 ring-1 ring-white/10" role="radiogroup">
          {(["student", "institution"] as const).map((t) => (
            <button key={t} type="button" role="radio" aria-checked={type === t} onClick={() => setType(t)}
              className={`rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-300 ${type === t ? "btn-primary text-white" : "muted hover:text-white"}`}>
              {t === "student" ? "Student / candidate" : "Institution"}
            </button>
          ))}
        </div>
        {error && <ErrorBox message={error} />}
        <Field label="Full name"><Input required value={form.full_name} onChange={set("full_name")} /></Field>
        <Field label="Email"><Input type="email" required value={form.email} onChange={set("email")} /></Field>
        <Field label="Password" hint="At least 10 characters"><Input type="password" minLength={10} required value={form.password} onChange={set("password")} /></Field>
        {type === "student" ? (
          <Field label="Institution code" hint="Provided by your institution"><Input required value={form.institution_code} onChange={set("institution_code")} /></Field>
        ) : (
          <Field label="Institution name"><Input required value={form.institution_name} onChange={set("institution_name")} /></Field>
        )}
        <Button className="shimmer w-full py-3" loading={busy} type="submit">Create account</Button>
        <p className="text-center text-sm muted">Have an account? <Link className="text-brand-500 hover:underline" href="/login">Sign in</Link></p>
      </form>
    </AuthShell>
  );
}
