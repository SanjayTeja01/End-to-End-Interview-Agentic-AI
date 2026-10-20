"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { Spinner } from "./ui";

export function StudentGuard({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (!loading && (!me || me.role !== "student")) router.replace(me ? "/institution" : `/login?next=${encodeURIComponent(path)}`);
  }, [loading, me, router, path]);
  if (loading || !me || me.role !== "student") return <div className="p-8"><Spinner /></div>;
  return <>{children}</>;
}
