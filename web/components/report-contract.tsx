"use client";

import * as React from "react";
import { CardLabel, Panel, PanelCell, PanelGrid } from "@/components/page";
import { MeterRow, RAMP, SegmentedBar, TrendChart, rampAt } from "@/components/marks";
import { IntentBadge, SeverityBadge, SeveritySummaryBar } from "@/components/badges";
import { engineLabel } from "@/components/report-panels";
import { pct } from "@/lib/utils";
import { NO_PRIOR } from "@/lib/format";
import { getAnswerCell, type EvidenceRow, type FindingGroupRow, type ReportPayload } from "@/lib/api";
import { useIsPrint } from "@/lib/render-mode";
import type { BrandConfig } from "@/lib/brand";

/**
 * The report contract's sections, one component each.
 *
 * These are the ONLY place report content is rendered. The order they appear in
 * is not decided here — `web/lib/report-sections.tsx` is the registry, and a
 * component that renders itself outside it is invisible to reordering, tiering
 * and the thin-data rules (spec TR-T11).
 *
 * Voice, per the contract: sections 1–7, 10 and 11 are DESCRIPTIVE. They state
 * what was measured. Interpretation and recommendation live only in sections 8
 * (priority actions) and 9 (accuracy findings), which are labelled as such.
 */

export interface SectionContext {
  report: ReportPayload;
  runId?: string;
  clientName: string;
  /** The client-facing skin. One object, so an agency white-label replaces the
   * entire brand rather than an accent colour — and it is threaded to the
   * SECTIONS rather than held by the chrome, because the cover and the
   * methodology footer are the two places a tenant name actually appears. */
  brand: BrandConfig;
  /** Filters are report-wide client state, owned by the view and threaded here
   * so the findings section and the losing-query table cannot disagree about
   * what is being shown. */
  engineFilter: string;
  intentFilter: string;
  setEngineFilter: (v: string) => void;
  setIntentFilter: (v: string) => void;
  onSeeAllFindings: () => void;
}

/** The quiet one-liner a section uses to say why it is not showing a number.
 * Never an empty box: "we have one cycle" is information, and a blank space
 * reads as a rendering bug. */
export function ThinData({ children }: { children: React.ReactNode }) {
  return <p className="text-[13px] text-harbour">{children}</p>;
}

function SectionShell({
  title,
  note,
  children,
}: {
  title: string;
  note?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="report-section space-y-3">
      <CardLabel note={note}>{title}</CardLabel>
      {children}
    </section>
  );
}

/** A rate, always with its count. The percentage is parenthetical and secondary,
 * which is the house format and the reason `label` is pre-formatted server-side:
 * every surface says it the same way. */
function Rate({ rate }: { rate: { label: string; n: number } }) {
  return <span className="tabular-nums">{rate.label}</span>;
}

/** The delta chip. Shape AND text, never colour alone — the palette is a single
 * navy ramp with no up/down hue to spend. A delta with no passing significance
 * gate renders flat: an arrow is a claim that something happened. */
function Delta({
  value,
  direction,
  title,
}: {
  value: string;
  direction?: string;
  title?: string;
}) {
  if (!value || value === NO_PRIOR) {
    return <span className="text-[11.5px] text-harbour">{value || "—"}</span>;
  }
  const flat = direction === "flat" || direction === "unknown" || !direction;
  const glyph = flat ? "—" : direction === "up" ? "▲" : "▼";
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium"
      style={
        flat
          ? { backgroundColor: "var(--rule-soft)", color: "var(--harbour)" }
          : { backgroundColor: "var(--navy)", color: "#fff" }
      }
    >
      <span aria-hidden="true">{glyph}</span>
      {value}
    </span>
  );
}

/* ------------------------------------------------------------ §0 cover --- */

/**
 * The deliverable's first page. Client, cycle, no data.
 *
 * PRINT ONLY, and that is a design decision rather than an oversight: the PDF
 * and the workbench are different artifacts. The deliverable opens on a
 * full-bleed navy masthead — the ONE place Sky is legal in the whole report, the
 * single bright note in the system, which loses its job if used twice — while
 * the screen opens on the app's own eyebrow/title block, because a navy band
 * immediately under a navy rail is a wall.
 */
export function CoverSection({ ctx }: { ctx: SectionContext }) {
  const isPrint = useIsPrint();
  const { report, brand } = ctx;
  if (!isPrint) return null;
  return (
    <div className="on-navy report-section px-6 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="label" style={{ color: "var(--on-navy-accent)" }}>
            AI visibility report
          </p>
          <h1 className="display-lg mt-2">{report.client_name}</h1>
          <p className="mt-3 text-[14px]" style={{ color: "var(--on-navy-accent)" }}>
            Prepared for {report.client_name} · Cycle of {report.run_date}
          </p>
        </div>
        {brand.showMark && (
          <span className="wordmark text-lg" style={{ color: "var(--on-navy-accent)" }}>
            {brand.name}
          </span>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------- §1 exec snapshot --- */

export function ExecSnapshotSection({ ctx }: { ctx: SectionContext }) {
  const snapshot = ctx.report.exec_snapshot;
  if (!snapshot) return null;
  return (
    <SectionShell title="Executive snapshot">
      <PanelGrid cols="repeat(3, minmax(0, 1fr))" className="lg:grid-cols-6">
        {snapshot.tiles.map((tile) => (
          <PanelCell key={tile.key}>
            <p className="section-label mb-1.5">{tile.label}</p>
            <p className="text-[20px] font-semibold leading-tight tracking-[-0.01em]">
              {tile.value}
            </p>
            {tile.secondary ? (
              <p className="mt-1.5 text-[11.5px] leading-snug text-harbour">{tile.secondary}</p>
            ) : null}
          </PanelCell>
        ))}
      </PanelGrid>
      {/* Neutral. The action clause opens section 8. */}
      <p className="display text-lg leading-snug">{snapshot.summary}</p>
    </SectionShell>
  );
}

/* ------------------------------------------------- §2 what changed --- */

export function WhatChangedSection({ ctx }: { ctx: SectionContext }) {
  const changed = ctx.report.what_changed;
  const oldest = ctx.report.scorecard.oldest_open;
  const open = ctx.report.scorecard.open_findings;
  if (!changed?.available) return null;
  return (
    <SectionShell
      title={`What changed since ${changed.prior_run_date || "the last cycle"}`}
      note={`${changed.cycles_considered} cycles considered`}
    >
      <Panel className="space-y-4 p-6">
        {/* The sentence that determines renewal. Its arithmetic closes exactly:
            opening = resolved + still_open, closing = still_open + new + regressed. */}
        <p className="text-[15px] font-medium">{changed.accountability}</p>

        <PanelGrid cols="repeat(2, minmax(0, 1fr))" className="border-0">
          <PanelCell className="px-0">
            <p className="section-label mb-1.5">Open findings</p>
            <p className="text-[28px] font-semibold leading-none tabular-nums">
              {open?.themes ?? 0}
            </p>
            <p className="mt-1.5 text-[11.5px] text-harbour">
              {open?.critical ?? 0} Critical · {open?.instances ?? 0} observations behind them
            </p>
          </PanelCell>
          <PanelCell>
            <p className="section-label mb-1.5">Oldest still open</p>
            <p className="text-[28px] font-semibold leading-none tabular-nums">
              {oldest ? `${oldest.cycles_open} ${oldest.cycles_open === 1 ? "cycle" : "cycles"}` : "—"}
            </p>
            <p className="mt-1.5 text-[11.5px] text-harbour">
              {oldest ? oldest.title : "Nothing has been open for a full cycle yet."}
            </p>
          </PanelCell>
        </PanelGrid>

        {changed.movements.length > 0 && (
          <div>
            <p className="section-label mb-2">By surface</p>
            <ul className="space-y-1.5">
              {/* Flat cells are LISTED, not omitted. A weekly product that
                  manufactures news in flat weeks destroys itself faster than one
                  that reports nothing happened. */}
              {changed.movements.map((m) => (
                <li key={m.key} className="flex flex-wrap items-center gap-2 text-[13px]">
                  <Delta
                    value={
                      m.direction === "flat"
                        ? "Held steady"
                        : m.direction === "unknown"
                          ? "not comparable"
                          : `${m.direction === "up" ? "Up" : "Down"} from ${m.before_successes} of ${m.before_n}`
                    }
                    direction={m.direction}
                    title={m.flat_reason || undefined}
                  />
                  <span>{m.phrase.replace(/^[^:]+:\s*/, "")}</span>
                  <span className="text-harbour">{engineLabel(m.key)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>
    </SectionShell>
  );
}

/* ---------------------------------------------- §3 visibility trend --- */

export function TrendSection({ ctx }: { ctx: SectionContext }) {
  const trend = ctx.report.trend;
  if (!trend) return null;
  const points = trend.points.map((p) => ({
    label: p.run_date.slice(5),
    value: Math.round(p.mention.rate * 100),
  }));
  return (
    <SectionShell title="Visibility trend" note={`${trend.cycles} cycles`}>
      {trend.cycles < 2 ? (
        <ThinData>{trend.statement}</ThinData>
      ) : (
        <Panel className="p-6">
          <TrendChart
            points={points}
            ariaLabel="Mention rate by cycle"
            drawLine={trend.draw_line}
            caption={trend.statement}
          />
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-left text-harbour">
                  <th className="py-1.5 font-normal">Cycle</th>
                  <th className="py-1.5 font-normal">Mentioned in</th>
                  <th className="py-1.5 font-normal">Share of model</th>
                  <th className="py-1.5 font-normal">Cited in</th>
                  <th className="py-1.5 font-normal">Typical position</th>
                </tr>
              </thead>
              <tbody>
                {trend.points.map((p) => (
                  <tr key={p.run_id} className="border-t border-[var(--rule-inner)]">
                    <td className="py-1.5">
                      {p.run_date}
                      {p.is_current ? " (this cycle)" : ""}
                    </td>
                    <td className="py-1.5">
                      <Rate rate={p.mention} />
                    </td>
                    <td className="py-1.5 tabular-nums">{pct(p.share_of_model)}</td>
                    <td className="py-1.5">
                      {p.citation ? <Rate rate={p.citation} /> : "—"}
                    </td>
                    <td className="py-1.5">{p.prominence_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </SectionShell>
  );
}

/* ----------------------------------------- §4 results by question type --- */

export function QuestionTypeSection({ ctx }: { ctx: SectionContext }) {
  const section = ctx.report.question_types;
  if (!section?.rows.length) return null;
  return (
    <SectionShell
      title="Results by question type"
      note={section.family === "local" ? "Local-service intents" : undefined}
    >
      <Panel className="space-y-4 p-6">
        <div className="space-y-2.5">
          {section.rows.map((row) => (
            <MeterRow
              key={row.bucket}
              label={row.label}
              // A suppressed point estimate draws no fill: the bar IS the point
              // estimate, and drawing it while refusing to print it would be
              // the same claim made in a different medium.
              striped={row.suppress_point || row.mention.n === 0}
              pct={row.mention.rate * 100}
              labelWidth={160}
              valueWidth={140}
              value={
                row.mention.n === 0
                  ? "not measured"
                  : row.suppress_point
                    ? `${row.mention.successes} of ${row.mention.n} (${pct(row.mention.ci_low)}–${pct(row.mention.ci_high)})`
                    : row.mention.label
              }
            />
          ))}
        </div>
        <p className="text-[12.5px] text-harbour">
          Strongest: {section.best} · Weakest: {section.weakest}
        </p>
        {section.note ? <ThinData>{section.note}</ThinData> : null}
      </Panel>
    </SectionShell>
  );
}

/* --------------------------------------------- §5 results by surface --- */

export function SurfaceSection({ ctx }: { ctx: SectionContext }) {
  const section = ctx.report.surfaces;
  if (!section?.rows.length) return null;
  return (
    <SectionShell title="Results by surface">
      <Panel className="p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-harbour">
                <th className="py-1.5 font-normal">Surface</th>
                <th className="py-1.5 font-normal">Mentioned in</th>
                <th className="py-1.5 font-normal">Change</th>
                <th className="py-1.5 font-normal">Answered / attempted</th>
                <th className="py-1.5 font-normal">Model</th>
              </tr>
            </thead>
            <tbody>
              {section.rows.map((row) => (
                <tr key={row.engine_name} className="border-t border-[var(--rule-inner)]">
                  <td className="py-1.5 font-medium">
                    {row.label}
                    {!row.coverage_ok && (
                      <span className="ml-2 text-[11px] text-harbour">incomplete coverage</span>
                    )}
                  </td>
                  <td className="py-1.5">
                    <Rate rate={row.mention} />
                  </td>
                  <td className="py-1.5">
                    <Delta value={row.delta} direction={row.direction} />
                  </td>
                  <td className="py-1.5 tabular-nums">
                    {row.answered_cells} / {row.attempted_cells}
                  </td>
                  <td className="py-1.5 text-harbour">{row.model_id || "not recorded"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {section.dead.length > 0 && (
          <ThinData>
            {section.dead.join(", ")} returned no answer at all this cycle, so nothing was
            measured there. That is a fact about the run&rsquo;s coverage, not a zero.
          </ThinData>
        )}
        {section.note ? <ThinData>{section.note}</ThinData> : null}
      </Panel>
    </SectionShell>
  );
}

/* ------------------------------------------- §6 competitive position --- */

/** Prominence as a 100% stacked bar — NOT a donut. Arc-angle comparison across
 * non-adjacent segments is a known perceptual weak point, and the five levels
 * are exactly the case where a reader has to compare two non-adjacent bands. */
function ProminenceBar({ distribution }: { distribution: Record<string, number> }) {
  const ORDER = ["recommended_first", "mid_pack", "buried", "also_ran", "absent"];
  const LABELS: Record<string, string> = {
    recommended_first: "Recommended first",
    mid_pack: "Mid-pack",
    buried: "Buried",
    also_ran: "Also-ran",
    absent: "Absent",
  };
  const segments = ORDER.filter((k) => (distribution[k] ?? 0) > 0).map((k, i) => ({
    label: LABELS[k],
    value: distribution[k] ?? 0,
    tone: rampAt(i),
  }));
  if (!segments.length) return <ThinData>Position was not measured.</ThinData>;
  return <SegmentedBar segments={segments} height={22} ariaLabel="Position across answers" />;
}

export function CompetitiveSection({ ctx }: { ctx: SectionContext }) {
  const section = ctx.report.competitive;
  if (!section?.rows.length) return null;
  const client = section.rows.find((r) => r.is_client);
  return (
    <SectionShell title="Competitive position">
      <Panel className="space-y-5 p-6">
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-harbour">
                <th className="py-1.5 font-normal">Brand</th>
                <th className="py-1.5 font-normal">Mentioned in</th>
                <th className="py-1.5 font-normal">Share of model</th>
                <th className="py-1.5 font-normal">Change</th>
                <th className="py-1.5 font-normal">Typical position</th>
              </tr>
            </thead>
            <tbody>
              {/* Ordered by mention rate — a measured quantity with a
                  denominator — never by a composite (spec TR-T0). */}
              {section.rows.map((row) => (
                <tr key={row.brand} className="border-t border-[var(--rule-inner)]">
                  <td className="py-1.5 font-medium">
                    {row.brand}
                    {row.is_client && <span className="ml-2 text-[11px] text-harbour">you</span>}
                  </td>
                  <td className="py-1.5">
                    <Rate rate={row.mention} />
                  </td>
                  <td className="py-1.5 tabular-nums">{pct(row.share_of_model)}</td>
                  <td className="py-1.5">
                    <Delta value={row.delta} direction={row.direction} />
                  </td>
                  <td className="py-1.5">{row.prominence_label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {client && (
          <div>
            <p className="section-label mb-2">Where you land, across every answer</p>
            <ProminenceBar distribution={client.prominence_distribution} />
          </div>
        )}
        <ThinData>{section.note}</ThinData>
      </Panel>
    </SectionShell>
  );
}

/* -------------------------------------------------- §7 citations --- */

/** The Pareto read: bars by count, with the cumulative share as a step line.
 * Answers "are we dependent on 2 sources or 20", which a descending bar chart
 * on its own cannot (Phase 2 remainder of P2-T6). */
function ParetoChart({ rows }: { rows: { domain: string; count: number; cumulative_share: number }[] }) {
  const top = rows.slice(0, 12);
  const max = Math.max(...top.map((r) => r.count), 1);
  const W = 1180;
  const H = 220;
  const BASE = 170;
  const TOP = 16;
  const barW = W / Math.max(top.length, 1);
  const y = (share: number) => BASE - share * (BASE - TOP);
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={220}
      role="img"
      aria-label="Citation concentration by domain"
      className="report-chart"
    >
      <line x1={0} y1={BASE} x2={W} y2={BASE} stroke="rgb(14 35 64 / 0.12)" />
      {top.map((r, i) => {
        const h = (r.count / max) * (BASE - TOP);
        return (
          <rect
            key={r.domain}
            x={i * barW + barW * 0.18}
            y={BASE - h}
            width={barW * 0.64}
            height={h}
            fill={RAMP[1]}
          />
        );
      })}
      <polyline
        points={top.map((r, i) => `${i * barW + barW / 2},${y(r.cumulative_share)}`).join(" ")}
        fill="none"
        stroke={RAMP[0]}
        strokeWidth="2"
        strokeDasharray="4 3"
      />
      {top.map((r, i) => (
        <circle
          key={r.domain}
          cx={i * barW + barW / 2}
          cy={y(r.cumulative_share)}
          r={3}
          fill={RAMP[0]}
        />
      ))}
      {top.map((r, i) => (
        <text
          key={r.domain}
          x={i * barW + barW / 2}
          y={BASE + 18}
          textAnchor="middle"
          fontFamily="Libre Franklin, sans-serif"
          fontSize="10.5"
          fill={RAMP[2]}
        >
          {r.domain.length > 16 ? `${r.domain.slice(0, 15)}…` : r.domain}
        </text>
      ))}
      {top.map((r, i) => (
        <text
          key={`${r.domain}-c`}
          x={i * barW + barW / 2}
          y={BASE + 32}
          textAnchor="middle"
          fontFamily="Libre Franklin, sans-serif"
          fontSize="10"
          fill={RAMP[3]}
        >
          {r.count}
        </text>
      ))}
    </svg>
  );
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  owned: "Your own pages",
  earned: "Earned coverage",
  directory: "Directories & review sites",
  social: "Social & forums",
  video: "Video",
  competitor: "Competitor pages",
};

export function CitationSection({ ctx }: { ctx: SectionContext }) {
  const section = ctx.report.citations;
  if (!section) return null;
  if (!section.total_citations) {
    return (
      <SectionShell title="Citation results">
        <ThinData>
          No surface returned a citation this cycle. Several surfaces answer from memory and
          cite nothing at all, so this is a property of the surfaces as much as of the site.
        </ThinData>
      </SectionShell>
    );
  }
  return (
    <SectionShell title="Citation results" note={`${section.total_citations} citations`}>
      <Panel className="space-y-5 p-6">
        {section.client_rate && (
          <p className="text-[13px]">
            Your own domains were cited in <Rate rate={section.client_rate} />, across{" "}
            {section.client_citations} citation{section.client_citations === 1 ? "" : "s"}.
          </p>
        )}
        <ParetoChart rows={section.domains} />
        {/* DESCRIPTIVE. "youtube.com was cited 31 times" — never "you need a
            YouTube strategy". The recommendation is section 8's job. */}
        <p className="text-[13px]">{section.concentration}</p>
        <div>
          <p className="section-label mb-2">By kind of source</p>
          <div className="space-y-2">
            {Object.entries(section.by_source_type)
              .filter(([, count]) => count > 0)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count], i) => (
                <MeterRow
                  key={type}
                  label={SOURCE_TYPE_LABELS[type] ?? type}
                  pct={(count / section.total_citations) * 100}
                  tone={rampAt(i)}
                  labelWidth={190}
                  value={count}
                />
              ))}
          </div>
        </div>
        {section.note ? <ThinData>{section.note}</ThinData> : null}
      </Panel>
    </SectionShell>
  );
}

/* --------------------------------------------- §8 priority actions --- */

/**
 * The plan. This section and section 9 are the ONLY places the report
 * interprets or recommends — everything above states what was measured.
 *
 * It sits ABOVE the findings deliberately (answer-first): a reader who stops
 * after one section should stop after the plan, not after the evidence.
 */
export function PriorityActionsSection({ ctx }: { ctx: SectionContext }) {
  const actions = ctx.report.priority_actions ?? [];
  if (!actions.length) return null;
  return (
    <SectionShell title="This cycle's priority actions" note={`${actions.length} of 7 slots`}>
      <Panel className="p-6">
        <p className="mb-4 text-[15px] font-medium">
          Start with: {actions[0].action}{" "}
          <span className="font-normal text-harbour">
            (Owner: {actions[0].owner} · Effort: {actions[0].effort})
          </span>
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-harbour">
                <th className="py-1.5 font-normal">Action</th>
                <th className="py-1.5 font-normal">Severity</th>
                <th className="py-1.5 font-normal">Owner</th>
                <th className="py-1.5 font-normal">Effort</th>
              </tr>
            </thead>
            <tbody>
              {actions.map((a) => (
                <tr key={a.theme} className="border-t border-[var(--rule-inner)]">
                  <td className="py-2">
                    <span className="font-medium">{a.title}</span>
                    <br />
                    <span className="text-harbour">{a.action}</span>
                  </td>
                  <td className="py-2">
                    <SeverityBadge severity={a.severity} />
                  </td>
                  <td className="py-2">{a.owner}</td>
                  <td className="py-2 tabular-nums">{a.effort}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </SectionShell>
  );
}

/* -------------------------------------------- §9 accuracy findings --- */

/** The full stored answer behind one observation, with the flagged sentence
 * highlighted (P3-T1). Fetched on expand and cached per cell — the answers are
 * already stored, so this is retrieval, never a re-measurement. */
function AnswerPanel({ runId, evidence }: { runId: string; evidence: EvidenceRow }) {
  type PanelState =
    | { status: "idle" }
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ok"; text: string };
  const [state, setState] = React.useState<PanelState>({ status: "idle" });

  const load = React.useCallback(() => {
    if (state.status !== "idle") return;
    setState({ status: "loading" });
    getAnswerCell(runId, evidence.query_id ?? "", evidence.engine_name, evidence.run_index ?? 0)
      .then((cell) => setState({ status: "ok", text: cell.response ?? "" }))
      .catch(() => setState({ status: "error", message: "Could not load the full answer." }));
  }, [runId, evidence, state.status]);

  if (state.status === "idle") {
    return (
      <button
        type="button"
        onClick={load}
        className="no-print text-xs underline"
        style={{ color: "var(--blue)" }}
      >
        Show the full answer
      </button>
    );
  }
  if (state.status === "loading") return <span className="text-xs text-harbour">Loading…</span>;
  if (state.status === "error") return <span className="text-xs text-harbour">{state.message}</span>;

  const at = state.text.indexOf(evidence.excerpt);
  return (
    <div
      className="mt-2 max-h-80 overflow-auto rounded border p-2 text-xs"
      style={{ borderColor: "var(--rule)", whiteSpace: "pre-wrap" }}
    >
      {at >= 0 ? (
        <>
          {state.text.slice(0, at)}
          <mark style={{ backgroundColor: "var(--mist)", color: "var(--navy)" }}>
            {evidence.excerpt}
          </mark>
          {state.text.slice(at + evidence.excerpt.length)}
        </>
      ) : (
        state.text
      )}
    </div>
  );
}

/** A full finding card. Critical and High only — Medium and Low collapse into a
 * compact table, because a report where every finding looks identical gives the
 * reader no triage signal and they stop reading.
 *
 * Voice is flat and factual, third person: the engine "states", it does not
 * "falsely claim" or "hallucinate". Severity carries the alarm; the prose does
 * not. Anthropomorphising a named vendor's model is both imprecise and legally
 * careless. */
function FindingCard({ group, runId }: { group: FindingGroupRow; runId?: string }) {
  const isPrint = useIsPrint();
  const [open, setOpen] = React.useState(isPrint);
  const lead = group.evidence[0];

  return (
    <div className="report-card rounded-lg border border-[var(--rule)] bg-white p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={group.severity} />
        <span className="font-medium">{group.title}</span>
        {group.lifecycle_status && group.lifecycle_status !== "new" ? (
          <span
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
            style={
              group.lifecycle_status === "regressed"
                ? { backgroundColor: "var(--navy)", color: "#fff" }
                : { backgroundColor: "var(--rule-soft)", color: "var(--harbour)" }
            }
          >
            {group.lifecycle_status === "regressed"
              ? "Regressed"
              : group.lifecycle_status === "resolved"
                ? "Resolved"
                : `Open ${group.cycles_open ?? 1} cycle${(group.cycles_open ?? 1) === 1 ? "" : "s"}`}
          </span>
        ) : null}
        <span className="ml-auto text-xs text-harbour">{group.theme_label}</span>
      </div>

      {lead && (
        <p className="mb-2 text-[13px] text-harbour">
          {engineLabel(lead.engine_name)}
          {lead.model_id ? ` (${lead.model_id})` : ""} — checked{" "}
          {lead.observed_at.slice(0, 10) || "date not recorded"}, {group.occurrence.phrase} —
          states:
        </p>
      )}

      <blockquote
        className="mb-2 border-l-2 pl-3 text-[13px] italic"
        style={{ borderColor: "var(--mist)" }}
      >
        “{group.representative_claims[0]}”
      </blockquote>
      {group.reality && (
        <p className="mb-3 text-[13px]">
          <span className="section-label">From your fact sheet</span>
          <br />
          {group.reality}
        </p>
      )}

      <p className="mb-1 text-[13px]">
        <span className="font-medium">Fix:</span> {group.action}
      </p>
      <p className="text-xs text-harbour">
        Owner: {group.owner} · Effort: {group.effort} · Appears on{" "}
        {group.engines.map(engineLabel).join(", ") || "no recorded surface"} ·{" "}
        {group.instance_count} observation{group.instance_count === 1 ? "" : "s"}
      </p>

      {group.evidence.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="no-print mt-3 text-xs underline"
            style={{ color: "var(--blue)" }}
          >
            {open ? "Hide evidence" : `Show evidence (${group.evidence.length})`}
          </button>
          {/* Always rendered for print: print never scrolls, and a collapsed
              details element would silently drop the evidence trail from the PDF
              while the live page looks complete. */}
          <div className={open ? "mt-3 space-y-3" : "mt-3 hidden space-y-3 print:block"}>
            {group.evidence_total > group.evidence.length && (
              <p className="text-xs text-harbour">
                Showing {group.evidence.length} of {group.evidence_total} observations, one per
                surface. The full set is in the answers export.
              </p>
            )}
            {group.evidence.map((e, i) => (
              <div
                key={i}
                className="rounded border p-2 text-xs"
                style={{ borderColor: "var(--rule)" }}
              >
                <p className="mb-1 text-harbour">
                  <span className="section-label">Prompt</span> “{e.prompt}”
                </p>
                <p className="mb-1 text-harbour">
                  {engineLabel(e.engine_name)}
                  {e.model_id ? ` · ${e.model_id}` : " · model not recorded"} ·{" "}
                  {e.observed_at || "no timestamp"}
                </p>
                <p className="italic">“{e.excerpt}”</p>
                {runId && e.query_id && <AnswerPanel runId={runId} evidence={e} />}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function FindingsSection({ ctx }: { ctx: SectionContext }) {
  const { report, engineFilter, intentFilter, setEngineFilter, setIntentFilter } = ctx;
  const groups = report.finding_groups ?? [];
  const matches = React.useCallback(
    (engines: string[], intents: string[]) =>
      (engineFilter === "all" || engines.includes(engineFilter)) &&
      (intentFilter === "all" || intents.includes(intentFilter)),
    [engineFilter, intentFilter],
  );
  const visible = React.useMemo(
    () => groups.filter((g) => matches(g.engines, g.intents)),
    [groups, matches],
  );
  // The severity bar counts what is VISIBLE, so the bar and the cards below it
  // can never disagree — a summary that ignores the filter is a summary of a
  // different report.
  const bySeverity = React.useMemo(() => {
    const counts: Record<string, number> = { critical: 0, high: 0, med: 0, low: 0 };
    for (const g of visible) counts[g.severity] = (counts[g.severity] ?? 0) + 1;
    return counts;
  }, [visible]);
  const intentOptions = React.useMemo(
    () => [...new Set(groups.flatMap((g) => g.intents))].sort(),
    [groups],
  );
  const isFiltered = engineFilter !== "all" || intentFilter !== "all";
  const criticalAndHigh = visible.filter(
    (g) => g.severity === "critical" || g.severity === "high",
  );
  const mediumAndLow = visible.filter((g) => g.severity === "med" || g.severity === "low");

  if (!report.scorecard.accuracy_assessed) {
    return (
      <SectionShell title="Accuracy findings">
        <ThinData>
          {report.detection === "judge"
            ? "Accuracy was not assessed this cycle — without a fact sheet there is no ground truth to check the models' claims against."
            : "Accuracy was not assessed — the LLM judge did not run over this cycle's answers."}
        </ThinData>
      </SectionShell>
    );
  }

  return (
    <section id="findings" className="report-section scroll-mt-6 space-y-4">
      <CardLabel note={`${groups.length} themes`}>Accuracy findings</CardLabel>

      <div className="no-print flex flex-wrap items-center gap-2">
        <span className="section-label">Filter</span>
        <select
          className="rounded border px-2 py-1 text-[13px]"
          style={{ borderColor: "var(--rule)" }}
          value={engineFilter}
          onChange={(e) => setEngineFilter(e.target.value)}
        >
          <option value="all">All surfaces</option>
          {report.engines.map((e) => (
            <option key={e} value={e}>
              {engineLabel(e)}
            </option>
          ))}
        </select>
        <select
          className="rounded border px-2 py-1 text-[13px]"
          style={{ borderColor: "var(--rule)" }}
          value={intentFilter}
          onChange={(e) => setIntentFilter(e.target.value)}
        >
          <option value="all">All intents</option>
          {intentOptions.map((i) => (
            <option key={i} value={i}>
              {i.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        {isFiltered && (
          <>
            <button
              type="button"
              className="text-[13px] underline"
              style={{ color: "var(--blue)" }}
              onClick={() => {
                setEngineFilter("all");
                setIntentFilter("all");
              }}
            >
              Clear
            </button>
            <span className="text-xs text-harbour">
              Showing {visible.length} of {groups.length} findings
            </span>
          </>
        )}
      </div>

      {/* Count bar FIRST, before any individual finding: most readers stop
          there, and that is the design intent rather than a failure. */}
      <SeveritySummaryBar counts={bySeverity} />

      {visible.length === 0 ? (
        <ThinData>
          {isFiltered
            ? "No findings match this filter."
            : `No findings are open — every claim the models made about ${report.client_name} that your fact sheet covers checked out.`}
        </ThinData>
      ) : (
        <>
          {criticalAndHigh.length > 0 && (
            <div className="space-y-3">
              {criticalAndHigh.map((g) => (
                <FindingCard key={g.theme} group={g} runId={ctx.runId} />
              ))}
            </div>
          )}
          {mediumAndLow.length > 0 && (
            <Panel className="p-6">
              <p className="section-label mb-3">Medium and low findings ({mediumAndLow.length})</p>
              <div className="overflow-x-auto">
                <table className="w-full text-[12.5px]">
                  <thead>
                    <tr className="text-left text-harbour">
                      <th className="py-1.5 font-normal">Finding</th>
                      <th className="py-1.5 font-normal">Severity</th>
                      <th className="py-1.5 font-normal">Surfaces</th>
                      <th className="py-1.5 font-normal">Observed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mediumAndLow.map((g) => (
                      <tr key={g.theme} className="border-t border-[var(--rule-inner)]">
                        <td className="py-2">
                          <span className="font-medium">{g.title}</span>
                          <br />
                          <span className="text-xs text-harbour">{g.theme_label}</span>
                        </td>
                        <td className="py-2">
                          <SeverityBadge severity={g.severity} />
                        </td>
                        <td className="py-2">{g.engines.map(engineLabel).join(", ") || "—"}</td>
                        <td className="py-2 tabular-nums">
                          {g.occurrence.observed} of {g.occurrence.total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
    </section>
  );
}

/* ------------------------------------- §10 representative answers --- */

export function RepresentativeSection({ ctx }: { ctx: SectionContext }) {
  const section = ctx.report.representative_answers;
  if (!section?.slots.length) return null;
  return (
    <SectionShell title="Representative answers" note="Selected by published rule">
      <div className="space-y-3">
        {section.slots.map((slot) => (
          <Panel key={slot.slot} className="p-4">
            <div className="mb-2 flex flex-wrap items-baseline gap-2">
              <span className="font-medium">{slot.slot_label}</span>
              <span className="ml-auto text-[11px] text-harbour">{slot.rule}</span>
            </div>
            {!slot.available ? (
              <ThinData>{slot.note}</ThinData>
            ) : (
              <>
                <p className="mb-1.5 text-[12.5px] text-harbour">
                  {slot.engine_label}
                  {slot.model_id ? ` · ${slot.model_id}` : ""} ·{" "}
                  {slot.observed_at.slice(0, 10) || "date not recorded"}
                </p>
                <p className="mb-2 text-[13px]">
                  <span className="section-label">Question</span> “{slot.prompt}”
                </p>
                {/* An excerpt, not the answer. Printing answers inline is what
                    turned the deliverable into 90 pages; the full text is in
                    the export. */}
                <blockquote
                  className="border-l-2 pl-3 text-[13px] italic"
                  style={{ borderColor: "var(--mist)" }}
                >
                  “{slot.excerpt}”
                </blockquote>
                {slot.note ? (
                  <p className="mt-2 text-[12px] text-harbour">{slot.note}</p>
                ) : null}
              </>
            )}
          </Panel>
        ))}
      </div>
    </SectionShell>
  );
}

/* ------------------------------------------------- §11 methodology --- */

export function MethodologySection({ ctx }: { ctx: SectionContext }) {
  const m = ctx.report.methodology;
  if (!m) return null;
  return (
    <SectionShell title="Methodology">
      <Panel className="space-y-5 p-6 text-[13px]">
        <div>
          <p className="section-label mb-1.5">How we measured</p>
          <p className="text-harbour">
            We asked {m.surfaces.length} AI surface{m.surfaces.length === 1 ? "" : "s"} the{" "}
            {m.query_set_version} question set — {m.n_queries} question
            {m.n_queries === 1 ? "" : "s"}, {m.runs_per_query} independent time
            {m.runs_per_query === 1 ? "" : "s"} each — between {m.window_start || "—"} and{" "}
            {m.window_end || "—"}, and graded every answer against your fact sheet. Every rate in
            this report is shown as a count with its denominator.
          </p>
          <ul className="mt-2 space-y-0.5 text-harbour">
            {m.surfaces.map(([label, model]) => (
              <li key={label}>
                {label} — {model}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-harbour">
            {m.geography}. {m.account_config}
          </p>
        </div>

        <div>
          <p className="section-label mb-1.5">What the numbers mean</p>
          <dl className="space-y-1.5">
            {m.definitions.map(([term, definition]) => (
              <div key={term}>
                <dt className="inline font-medium">{term}. </dt>
                <dd className="inline text-harbour">{definition}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div>
          <p className="section-label mb-1.5">How the examples were chosen</p>
          <ul className="space-y-0.5 text-harbour">
            {m.selection_rules.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
        </div>

        <div>
          <p className="section-label mb-1.5">What changed in the measurement</p>
          <ul className="space-y-0.5 text-harbour">
            {m.changes_since_last.map((change) => (
              <li key={change}>{change}</li>
            ))}
          </ul>
        </div>

        {/* VERBATIM, exactly once. A client WILL re-run a prompt, get a different
            answer, and doubt the report; this pre-empts it. Do not paraphrase —
            it is worded to be honest without self-undermining. */}
        <div>
          <p className="section-label mb-1.5">On reproducing these results</p>
          <p className="text-harbour">{m.non_reproducibility}</p>
        </div>

        <div>
          <p className="section-label mb-1.5">Limitations</p>
          <ul className="space-y-0.5 text-harbour">
            {m.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>

        {m.judge_agreement && (
          <div>
            <p className="section-label mb-1.5">How the grading was checked</p>
            <p className="text-harbour">{m.judge_agreement}</p>
          </div>
        )}

        <p className="text-[11.5px] text-harbour">{m.independence}</p>
        {ctx.brand.poweredBy && (
          <p className="text-[11.5px] text-harbour">Measurement by {ctx.brand.name}.</p>
        )}
      </Panel>
    </SectionShell>
  );
}

/* --------------------------------------------- back matter A1–A6 --- */

export function BackMatterSection({ ctx }: { ctx: SectionContext }) {
  const back = ctx.report.back_matter;
  if (!back?.appendices.length) return null;
  return (
    <section className="report-section space-y-4">
      <CardLabel note={`${back.appendices.length} tables`}>Appendices</CardLabel>
      <p className="text-[13px] text-harbour">{back.note}</p>
      {/* The back matter's own mini-TOC. It is 12–20 pages of dense tables and a
          reader needs to be able to jump. */}
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[12.5px]">
        {back.appendices.map((a) => (
          <li key={a.id}>
            <span className="font-medium">{a.id}</span>{" "}
            <span className="text-harbour">{a.title}</span>
          </li>
        ))}
      </ul>
      {back.appendices.map((appendix) => (
        <div key={appendix.id} className="report-section space-y-2">
          <p className="text-[14px] font-medium">
            {appendix.id} · {appendix.title}
          </p>
          {appendix.note ? <p className="text-[12px] text-harbour">{appendix.note}</p> : null}
          {appendix.rows.length === 0 ? (
            <ThinData>Nothing to list for this cycle.</ThinData>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11.5px]">
                <thead>
                  <tr className="text-left text-harbour">
                    {appendix.columns.map((c) => (
                      <th key={c} className="py-1 pr-3 font-normal">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {appendix.rows.map((row, i) => (
                    <tr key={i} className="border-t border-[var(--rule-inner)] align-top">
                      {row.map((cell, j) => (
                        <td key={j} className="py-1 pr-3">
                          {cell || "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

/* ------------------------------------------- supporting detail --- */

/** Verdict stability and the losing-query ledger — the two tables that are not
 * in the contract's eleven sections but that an analyst checking our arithmetic
 * reaches for. Registered like everything else so they can be tiered or dropped
 * without touching a component. */
export function SupportingDetailSection({ ctx }: { ctx: SectionContext }) {
  const { report, engineFilter, intentFilter } = ctx;
  const stability = report.stability ?? [];
  const losing = report.losing_queries.filter(
    (l) =>
      (engineFilter === "all" || l.engine_name === engineFilter) &&
      (intentFilter === "all" || l.intent === intentFilter),
  );
  if (!stability.length && !losing.length) return null;
  return (
    <SectionShell title="Supporting detail">
      <div className="grid gap-4 lg:grid-cols-2">
        {stability.length > 0 && (
          <Panel className="p-6">
            <p className="section-label mb-3">Did the same answer come back twice?</p>
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-left text-harbour">
                  <th className="py-1.5 font-normal">Surface</th>
                  <th className="py-1.5 font-normal">Repeated</th>
                  <th className="py-1.5 font-normal">Split</th>
                  <th className="py-1.5 font-normal">Agreement</th>
                </tr>
              </thead>
              <tbody>
                {stability.map((row) => (
                  <tr key={row.engine_name} className="border-t border-[var(--rule-inner)]">
                    <td className="py-1.5 font-medium">{engineLabel(row.engine_name)}</td>
                    <td className="py-1.5 tabular-nums">{row.repeated_cells}</td>
                    <td className="py-1.5 tabular-nums">{row.split_cells}</td>
                    <td className="py-1.5 tabular-nums">{pct(row.mean_agreement)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[11.5px] text-harbour">
              A split cell read one way in some runs and the other way in the rest — its verdict
              could flip on a re-run. Surfaces missing from this table were not repeated enough
              times to say, which is unmeasured rather than stable.
            </p>
          </Panel>
        )}
        {losing.length > 0 && (
          <Panel className="p-6">
            <p className="section-label mb-3">Questions a competitor won ({losing.length})</p>
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="text-left text-harbour">
                    <th className="py-1.5 font-normal">Question</th>
                    <th className="py-1.5 font-normal">Surface</th>
                    <th className="py-1.5 font-normal">Named instead</th>
                  </tr>
                </thead>
                <tbody>
                  {/* The VERBATIM question, never `l.query_id`. `cmp-05` is the
                      most actionable data in the report made unreadable. */}
                  {losing.map((l, i) => (
                    <tr key={i} className="border-t border-[var(--rule-inner)] align-top">
                      <td className="py-1.5">
                        {l.prompt ? `“${l.prompt}”` : "(question text not recorded)"}
                        {l.intent && (
                          <div className="mt-1">
                            <IntentBadge intent={l.intent} />
                          </div>
                        )}
                      </td>
                      <td className="py-1.5">{engineLabel(l.engine_name)}</td>
                      <td className="py-1.5">{l.competitor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </div>
    </SectionShell>
  );
}
