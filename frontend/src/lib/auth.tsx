"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, onRefreshed, refreshAccess, setAccessToken } from "./api";
import type { Me } from "./types";

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  register: (body: Record<string, string>) => Promise<Me>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setMe(await api<Me>("/auth/me"));
    } catch {
      setMe(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (await refreshAccess()) await reload();
      setLoading(false);
    })();
  }, [reload]);

  // A refresh can hand this tab another account's token; re-read who we are so the shell redirects instead of
  // showing one account's pages with another account's permissions ("Institution access required").
  useEffect(() => {
    const off = onRefreshed(() => void reload());
    return () => {
      off();
    };
  }, [reload]);

  const login = async (email: string, password: string) => {
    const t = await api<{ access_token: string }>("/auth/login", { method: "POST", json: { email, password } });
    setAccessToken(t.access_token);
    const m = await api<Me>("/auth/me");
    setMe(m);
    return m;
  };

  const register = async (body: Record<string, string>) => {
    const t = await api<{ access_token: string }>("/auth/register", { method: "POST", json: body });
    setAccessToken(t.access_token);
    const m = await api<Me>("/auth/me");
    setMe(m);
    return m;
  };

  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setAccessToken(null);
    setMe(null);
  };

  return <Ctx.Provider value={{ me, loading, login, register, logout, reload }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}

export const isInstitution = (m: Me | null) => !!m && (m.role === "institution_admin" || m.role === "institution_staff");
export const homeFor = (m: Me) => (isInstitution(m) ? "/institution" : "/student");
