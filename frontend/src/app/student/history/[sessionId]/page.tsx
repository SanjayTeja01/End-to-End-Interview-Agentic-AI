"use client";

import { useParams } from "next/navigation";
import { ReportView } from "@/components/ReportView";

export default function Page() {
  const { sessionId } = useParams<{ sessionId: string }>();
  return <ReportView sessionId={sessionId} />;
}
