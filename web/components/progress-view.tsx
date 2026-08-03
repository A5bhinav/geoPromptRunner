"use client";

import { Loader2, CheckCircle2, XCircle, Ban, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Notice } from "@/components/notice";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { EngineStatus, RunStatus } from "@/lib/api";

function EngineChip({ engine }: { engine: EngineStatus }) {
  // No alert hue in Sable — a failed engine is marked by the glyph and by a
  // heavier navy rule, never by colour.
  const icon =
    engine.state === "done" ? (
      <CheckCircle2 className="h-4 w-4 text-navy" />
    ) : engine.state === "failed" ? (
      <XCircle className="h-4 w-4 text-navy" />
    ) : (
      <Loader2 className="h-4 w-4 animate-spin text-harbour" />
    );
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border border-[var(--rule)] bg-white px-3 py-2",
        engine.state === "failed" && "border-navy/40 bg-navy/[0.04]",
      )}
      title={engine.detail ?? undefined}
    >
      {icon}
      <span className="text-[13px] font-medium text-navy">{engine.name}</span>
      <span className="text-[13px] tabular-nums text-harbour">
        {engine.state === "failed"
          ? (engine.detail ?? "failed")
          : `${engine.completed} / ${engine.total}`}
      </span>
    </div>
  );
}

export function ProgressView({
  status,
  elapsed,
  onCancel,
}: {
  status: RunStatus;
  elapsed: number;
  onCancel: () => void;
}) {
  const pctDone = status.total > 0 ? (status.completed / status.total) * 100 : 0;
  const cancelled = status.state === "cancelled";
  const failed = status.state === "failed";
  const interrupted = status.state === "interrupted";
  const stopped = cancelled || failed || interrupted;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {cancelled ? (
            <Ban className="h-5 w-5 text-harbour" />
          ) : interrupted ? (
            <AlertTriangle className="h-5 w-5 text-navy" />
          ) : failed ? (
            <XCircle className="h-5 w-5 text-navy" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin text-harbour" />
          )}
          {cancelled
            ? "Audit cancelled"
            : interrupted
              ? // "interrupted" is written in exactly one place: the API's
                // startup scan, when it finds a non-terminal row it cannot
                // rebuild. That is TERMINAL and unrecoverable — the old
                // "Audit interrupted" read as transient and retryable.
                "Audit abandoned — cannot resume"
              : failed
                ? "Audit failed"
                : `Running audit — ${status.client_name}`}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {stopped && status.error && <Notice tone="problem">{status.error}</Notice>}

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-[13px] tabular-nums text-harbour">
              {status.completed} / {status.total} engine calls
            </span>
            <span className="text-[13px] font-medium tabular-nums text-navy">
              {pctDone.toFixed(0)}%
            </span>
          </div>
          <Progress value={pctDone} />
        </div>

        <div className="flex flex-wrap gap-2">
          {status.per_engine.map((e) => (
            <EngineChip key={e.name} engine={e} />
          ))}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[13px] tabular-nums text-harbour">
            Elapsed {Math.floor(elapsed / 60)}m {elapsed % 60}s
          </span>
          {(status.state === "running" || status.state === "queued") && (
            <Button variant="outline" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
