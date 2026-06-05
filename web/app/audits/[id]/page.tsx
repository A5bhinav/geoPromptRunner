"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { ProgressView } from "@/components/progress-view";
import { ReportView } from "@/components/report-view";
import {
  cancelAudit,
  getReport,
  getStatus,
  type ReportPayload,
  type RunStatus,
} from "@/lib/api";

const POLL_MS = 1200;

export default function AuditPage({ params }: { params: { id: string } }) {
  const runId = params.id;
  const [status, setStatus] = React.useState<RunStatus | null>(null);
  const [report, setReport] = React.useState<ReportPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [elapsed, setElapsed] = React.useState(0);
  const startRef = React.useRef<number>(Date.now());

  // Poll status until the run reaches a terminal state.
  React.useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const st = await getStatus(runId);
        if (!active) return;
        setStatus(st);
        setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
        if (st.state === "done") {
          const rep = await getReport(runId);
          if (active) setReport(rep);
          return;
        }
        if (st.state === "failed" || st.state === "cancelled") return;
        timer = setTimeout(tick, POLL_MS);
      } catch {
        if (active) setError("Run not found, or the API is unreachable.");
      }
    };
    tick();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [runId]);

  const onCancel = async () => {
    await cancelAudit(runId);
  };

  return (
    <div className="space-y-6">
      <Link
        href="/"
        className="no-print inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> New audit
      </Link>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {!error && !status && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      )}

      {status && status.state === "done" && report && <ReportView report={report} />}

      {status && status.state === "done" && !report && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Assembling report…
        </div>
      )}

      {status && status.state !== "done" && (
        <ProgressView status={status} elapsed={elapsed} onCancel={onCancel} />
      )}
    </div>
  );
}
