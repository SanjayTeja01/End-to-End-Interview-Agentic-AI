"use client";

import clsx from "clsx";
import { BookOpen, ClipboardList, FileText, History, LayoutDashboard, LogOut, User, Users, Video } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { isInstitution, useAuth } from "@/lib/auth";
import { Aurora, Logo } from "./fx";
import { Spinner } from "./ui";

const INSTITUTION_NAV = [
  { href: "/institution", label: "Overview", icon: LayoutDashboard },
  { href: "/institution/interviews", label: "Interviews", icon: ClipboardList },
  { href: "/institution/students", label: "Students", icon: Users },
  { href: "/institution/knowledge", label: "Knowledge Base", icon: BookOpen },
];
const STUDENT_NAV = [
  { href: "/student", label: "Overview", icon: LayoutDashboard },
  { href: "/student/profile", label: "My Profile", icon: User },
  { href: "/student/resume", label: "Resume & Skills", icon: FileText },
  { href: "/student/interviews", label: "Available Interviews", icon: Video },
  { href: "/student/history", label: "Interview History", icon: History },
];

export function DashboardShell({ area, children }: { area: "institution" | "student"; children: React.ReactNode }) {
  const { me, loading, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const allowed = me && (area === "institution" ? isInstitution(me) : me.role === "student");

  useEffect(() => {
    if (loading) return;
    if (!me) router.replace(`/login?next=${encodeURIComponent(path)}`);
    else if (!allowed) router.replace(isInstitution(me) ? "/institution" : "/student");
  }, [loading, me, allowed, router, path]);

  if (loading || !allowed) return <div className="flex min-h-screen items-center justify-center"><Aurora subtle grid={false} /><Spinner /></div>;
  const nav = area === "institution" ? INSTITUTION_NAV : STUDENT_NAV;
  const initials = me!.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Aurora subtle grid={false} />
      <aside className="sticky top-0 z-20 flex shrink-0 flex-col border-b border-theme bg-[rgba(9,12,24,0.7)] backdrop-blur-xl md:h-screen md:w-64 md:border-b-0 md:border-r">
        <Link href={`/${area}`} className="flex items-center gap-3 px-5 py-5">
          <Logo />
          <div className="min-w-0">
            <div className="font-display text-sm font-semibold tracking-tight">Interview Agent</div>
            <div className="truncate text-xs faint">{me!.institution_name}</div>
          </div>
        </Link>
        <div className="hidden px-5 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] faint md:block">
          {area === "institution" ? "Institution" : "Student"}
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pl-6">
          {nav.map(({ href, label, icon: Icon }) => {
            const active = href === `/${area}` ? path === href : path.startsWith(href);
            return (
              <Link key={href} href={href}
                className={clsx("nav-link flex items-center gap-3 whitespace-nowrap rounded-xl px-3 py-2.5 text-sm font-medium",
                  active ? "nav-active" : "muted hover:bg-white/[0.06] hover:text-white")}>
                <Icon className={clsx("h-4 w-4", active && "text-violet-300")} /> {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto hidden p-4 md:block">
          <div className="card flex items-center gap-3 p-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-cyan-400 text-xs font-bold text-white">{initials}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{me!.full_name}</div>
              <div className="truncate text-xs faint">{me!.email}</div>
            </div>
            <button aria-label="Sign out" title="Sign out" onClick={async () => { await logout(); router.replace("/login"); }}
              className="rounded-lg p-2 muted transition hover:bg-white/10 hover:text-white"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-10">
        <div className="mx-auto max-w-7xl">{children}</div>
      </main>
    </div>
  );
}
