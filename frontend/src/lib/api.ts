"use client";

/**
 * Typed fetch wrapper. The access token lives only in memory; the refresh token is an httpOnly cookie set by
 * the backend through the same-origin /api proxy, so JavaScript can never read it.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const listeners = new Set<(t: string | null) => void>();
const refreshListeners = new Set<() => void>();

/** Called after a silent refresh. The refresh cookie is shared by every tab, so the refreshed token can belong to a
 * different account (e.g. a student who signed in in another tab); the auth context re-reads /auth/me on this. */
export function onRefreshed(fn: () => void) {
  refreshListeners.add(fn);
  return () => refreshListeners.delete(fn);
}

export function setAccessToken(t: string | null) {
  accessToken = t;
  listeners.forEach((l) => l(t));
}
export function getAccessToken() {
  return accessToken;
}
export function onTokenChange(fn: (t: string | null) => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

export async function refreshAccess(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include" })
      .then(async (r) => {
        if (!r.ok) {
          setAccessToken(null);
          return false;
        }
        setAccessToken((await r.json()).access_token);
        refreshListeners.forEach((l) => l());
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

type Opts = Omit<RequestInit, "body"> & { json?: unknown; form?: FormData; retry?: boolean };

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  const res = await fetch(`${BASE}${path}`, { ...opts, headers, body, credentials: "include" });
  if (res.status === 401 && opts.retry !== false && !path.startsWith("/auth/")) {
    if (await refreshAccess()) return api<T>(path, { ...opts, retry: false });
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = (data as { error?: { code: string; message: string; details?: unknown } }).error;
    throw new ApiError(res.status, err?.code ?? "error", err?.message ?? res.statusText, err?.details);
  }
  return data as T;
}

export async function pollJob(jobId: string, onUpdate?: (status: string) => void, timeoutMs = 180_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await api<{ status: string; error: string | null }>(`/jobs/${jobId}`);
    onUpdate?.(job.status);
    if (job.status === "completed" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("Timed out waiting for job");
}

export function wsUrl(path: string) {
  const base = process.env.NEXT_PUBLIC_WS_BASE;
  if (base) return `${base}${path}`;
  const proto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000${path}`;
}
