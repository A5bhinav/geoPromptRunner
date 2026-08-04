"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { Page, PageHeader, Panel } from "@/components/page";
import { SidebarSlot } from "@/components/app-shell";
import { AreaChart, Donut, MeterRow, RAMP } from "@/components/marks";
import { cn } from "@/lib/utils";
import type { EngineStatus, RunStatus } from "@/lib/api";

/**
 * The Running screen.
 *
 * It answers three questions and refuses to answer a fourth: how far along, what
 * is stuck, and how much is left. It does NOT show partial results — a mention
 * rate computed off 204 of 348 calls is not a smaller version of the real
 * number, it is a different number, and putting one on screen mid-run is how a
 * figure nobody stands behind ends up quoted in a meeting.
 */

function elapsedLabel(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/** One surface's progress. A FAILED surface gets the hatched track, because its
 * bar is not "0% done" — it is a measurement that will not arrive, and a flat
 * empty track says the former. */
function SurfaceRow({ engine }: { engine: EngineStatus }) {
  const failed = engine.state === "failed";
  const pct = engine.total > 0 ? (engine.completed / engine.total) * 100 : 0;
  return (
    <MeterRow
      label={engine.name}
      labelWidth={92}
      valueWidth={62}
      pct={pct}
      striped={failed}
      // Done is the darkest step, in flight is the next one down: the eye should
      // land on what is finished, not on what is still moving.
      tone={engine.state === "done" ? RAMP[0] : RAMP[1]}
      emphasis={failed}
      value={failed ? "stopped" : `${engine.completed}/${engine.total}`}
    />
  );
}

/** The four-step plan. Only the first step is observable from a run's status, so
 * the other three are drawn as PENDING and never as done — the screen would
 * otherwise be claiming a judge pass happened because the layout has a row for
 * it. */
function PipelineStep({
  label,
  state,
  last,
}: {
  label: string;
  state: "done" | "current" | "pending";
  last?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex shrink-0 flex-col items-center">
        <span
          className={cn(
            "h-3 w-3 rounded-full",
            state === "done" && "bg-navy",
            state === "current" && "border-2 border-navy bg-white",
            state === "pending" && "border-2 border-navy/25 bg-white",
          )}
        />
        {last ? null : (
          <span
            className="w-0.5"
            style={{
              height: 26,
              background: state === "done" ? RAMP[0] : "rgb(14 35 64 / 0.15)",
            }}
          />
        )}
      </span>
      <span className={cn("text-[13px]", state === "pending" ? "text-harbour" : "font-medium")}>
        {label}
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
  const pct = status.total > 0 ? (status.completed / status.total) * 100 : 0;
  const cancelled = status.state === "cancelled";
  const failed = status.state === "failed";
  const interrupted = status.state === "interrupted";
  const stopped = cancelled || failed || interrupted;
  const live = status.state === "running" || status.state === "queued";

  // The curve is sampled from the poll, not fetched: the API has no time series
  // for a run in flight, and one built here is honest about being a view of what
  // this tab has seen. It resets on reload, which is why the exact figure sits
  // above it at 38px where the chart cannot mislead about it.
  const [series, setSeries] = React.useState<number[]>([]);
  React.useEffect(() => {
    setSeries((prev) =>
      prev.length && prev[prev.length - 1] === status.completed
        ? prev
        : [...prev, status.completed].slice(-60),
    );
  }, [status.completed]);

  const surfacesLive = status.per_engine.filter((e) => e.state === "running").length;
  const stalled = status.per_engine.filter((e) => e.state === "failed");

  const eyebrow = cancelled
    ? "Cancelled"
    : interrupted
      ? "Abandoned"
      : failed
        ? "Failed"
        : `Running · ${elapsedLabel(elapsed)}`;

  return (
    <Page>
      {/* The rail carries the run while you are on another screen. */}
      <SidebarSlot slot="footer">
        <div>
          <div className="mb-[7px] flex items-baseline justify-between gap-2">
            <span className="truncate text-[12.5px]">{status.client_name}</span>
            <span
              className="shrink-0 text-[12px] tabular-nums"
              style={{ color: "var(--sky)" }}
            >
              {Math.round(pct)}%
            </span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-white/[0.16]">
            <div
              className="h-full"
              style={{ width: `${pct}%`, background: "var(--sky)" }}
            />
          </div>
        </div>
      </SidebarSlot>

      <PageHeader
        eyebrow={eyebrow}
        title={status.client_name}
        actions={
          live ? (
            <Button variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          ) : null
        }
      />

      {stopped && status.error ? (
        <Notice
          tone="problem"
          title={
            interrupted
              ? // "interrupted" is written in exactly one place: the API's startup
                // scan, when it finds a non-terminal row it cannot rebuild. That
                // is TERMINAL — "interrupted" alone reads as retryable.
                "This run was abandoned and cannot be resumed"
              : cancelled
                ? "This run was cancelled"
                : "This run failed"
          }
        >
          {status.error}
        </Notice>
      ) : null}

      <div className="flex gap-5">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <Panel className="flex items-center gap-7 p-5">
            <Donut pct={pct} caption={`${status.completed} of ${status.total}`} />
            <div className="flex flex-1 flex-col gap-3">
              {status.per_engine.length === 0 ? (
                <p className="text-[13px] text-harbour">Waiting for the first surface to start…</p>
              ) : (
                status.per_engine.map((e) => <SurfaceRow key={e.name} engine={e} />)
              )}
              {stalled.map((e) => (
                // 3px navy left rule + the sentence. There is no Retry: nothing
                // in the API can restart one surface of a live run, and a button
                // that silently does nothing is worse than its absence.
                <div
                  key={e.name}
                  className="flex items-center gap-2.5 border-l-[3px] border-navy pl-3 text-[12.5px]"
                >
                  <span>
                    {e.name} stopped{e.detail ? ` — ${e.detail}` : ""}
                  </span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel className="px-5 py-[18px]">
            <div className="mb-3 flex items-baseline justify-between">
              <span className="section-label">Calls completed</span>
              <span className="text-[38px] font-semibold leading-[0.95] tracking-[-0.02em] tabular-nums">
                {status.completed}
              </span>
            </div>
            <AreaChart
              values={series}
              ariaLabel={`${status.completed} of ${status.total} calls completed so far`}
            />
          </Panel>
        </div>

        <div className="flex w-[300px] shrink-0 flex-col gap-4">
          <Panel className="px-5 py-[18px]">
            <p className="mb-4 text-[14px] font-medium">Pipeline</p>
            <PipelineStep
              label="Answers"
              state={status.state === "done" ? "done" : live ? "current" : "pending"}
            />
            <PipelineStep label="Judge" state="pending" />
            <PipelineStep label="Site crawl" state="pending" />
            <PipelineStep label="Report" state="pending" last />
          </Panel>

          <Panel className="flex flex-col gap-3 px-5 py-[18px]">
            <span className="text-[14px] font-medium">This run</span>
            <Stat label="Elapsed" value={elapsedLabel(elapsed)} />
            <Stat label="Calls left" value={Math.max(0, status.total - status.completed)} />
            <Stat
              label="Surfaces live"
              value={`${surfacesLive} of ${status.per_engine.length}`}
            />
          </Panel>
        </div>
      </div>
    </Page>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between text-[12.5px]">
      <span className="text-harbour">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </div>
  );
}
