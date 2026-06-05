"use client";

import { Loader2, CheckCircle2, XCircle, Ban } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { EngineStatus, RunStatus } from "@/lib/api";

function EngineChip({ engine }: { engine: EngineStatus }) {
  const icon =
    engine.state === "done" ? (
      <CheckCircle2 className="h-4 w-4 text-[hsl(var(--success))]" />
    ) : engine.state === "failed" ? (
      <XCircle className="h-4 w-4 text-destructive" />
    ) : (
      <Loader2 className="h-4 w-4 animate-spin text-primary" />
    );
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border px-3 py-2",
        engine.state === "failed" && "border-destructive/30 bg-destructive/5",
      )}
      title={engine.detail ?? undefined}
    >
      {icon}
      <span className="font-medium">{engine.name}</span>
      <span className="text-sm text-muted-foreground">
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
          {cancelled || interrupted ? (
            <Ban className="h-5 w-5 text-[hsl(var(--warning))]" />
          ) : failed ? (
            <XCircle className="h-5 w-5 text-destructive" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          )}
          {cancelled
            ? "Audit cancelled"
            : interrupted
              ? "Audit interrupted"
              : failed
                ? "Audit failed"
                : `Running audit — ${status.client_name}`}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {stopped && status.error && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {status.error}
          </p>
        )}

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">
              {status.completed} / {status.total} engine calls
            </span>
            <span className="tabular-nums text-sm font-medium">{pctDone.toFixed(0)}%</span>
          </div>
          <Progress value={pctDone} />
        </div>

        <div className="flex flex-wrap gap-2">
          {status.per_engine.map((e) => (
            <EngineChip key={e.name} engine={e} />
          ))}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground tabular-nums">
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
