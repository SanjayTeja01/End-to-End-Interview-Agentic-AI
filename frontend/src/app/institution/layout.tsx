import { DashboardShell } from "@/components/shell";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <DashboardShell area="institution">{children}</DashboardShell>;
}
