"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import {
  Printer,
  Download,
  FileText,
  FileSpreadsheet,
  Gavel,
  Loader2,
  Trophy,
  Target,
  Quote,
  ShieldCheck,
  PieChart as PieIcon,
  BarChart3,
  Globe,
  TrendingDown,
  Repeat2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { IntentBadge, SeverityBadge, SeveritySummaryBar } from "@/components/badges";
import { SiteAuditSection } from "@/components/site-audit-section";
import { DEFAULT_BRAND, type BrandConfig } from "@/lib/brand";
import { useIsPrint } from "@/lib/render-mode";
// Charts pull in recharts (the heaviest dependency). Load them lazily on the
// client so recharts ships in a report-only chunk, not the shared bundle.
const chartFallback = <div className="h-40 animate-pulse rounded-lg bg-secondary/40" />;
// `ssr: false` + a loading fallback is right for the screen — recharts is the
// heaviest dependency in the bundle and belongs in a report-only chunk. It is
// WRONG for print, where the chunk may still be resolving when the capture runs.
// The readiness gate in RenderModeProvider covers the race (it requires two
// quiet frames after the last chart registers), which is why the dynamic import
// can stay: nothing captures until every chart has actually laid out.
const LeaderboardChart = dynamic(
  () => import("@/components/charts").then((m) => m.LeaderboardChart),
  { ssr: false, loading: () => chartFallback },
);
const ShareStackedBar = dynamic(
  () => import("@/components/charts").then((m) => m.ShareStackedBar),
  { ssr: false, loading: () => chartFallback },
);
const EngineHeatmap = dynamic(() => import("@/components/charts").then((m) => m.EngineHeatmap), {
  ssr: false,
  loading: () => chartFallback,
});
const BucketChart = dynamic(() => import("@/components/charts").then((m) => m.BucketChart), {
  ssr: false,
  loading: () => chartFallback,
});
const SourcesChart = dynamic(() => import("@/components/charts").then((m) => m.SourcesChart), {
  ssr: false,
  loading: () => chartFallback,
});
import { pct } from "@/lib/utils";
import {
  downloadAudit,
  fetchJudgeStatus,
  judgeAudit,
  type FindingGroupRow,
  type JudgeStatus,
  type MovementRow,
  type ReportPayload,
} from "@/lib/api";

function MetricCard({
  icon,
  label,
  value,
  sub,
  delta,
  muted,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  /** On a recurring report the delta is the SECOND-LARGEST element on a tile,
   * after the value. Absent until the lifecycle engine lands (P2-T2) — an absent
   * chip is honest; a "—" chip pretending to be a comparison is not. */
  delta?: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <Card className="card">
      <CardContent className="pt-6">
        <div className="label mb-2 flex items-center gap-2">
          {icon}
          {label}
        </div>
        <div className={muted ? "body text-lg font-medium" : "display-value"}>{value}</div>
        {delta && <div className="mt-1.5 text-sm font-medium">{delta}</div>}
        {sub && <div className="body mt-1 text-sm">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function SectionTitle({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <h2 className="label flex items-center gap-2">
      {icon}
      {children}
    </h2>
  );
}

/** Client-facing surface names. Never a raw engine key or a bare model id. */
const ENGINE_LABELS: Record<string, string> = {
  openai: "ChatGPT",
  openai_search: "ChatGPT (web search)",
  anthropic: "Claude",
  anthropic_search: "Claude (web search)",
  gemini: "Gemini",
  gemini_grounded: "Gemini (grounded)",
  perplexity: "Perplexity",
  google_ai_overviews: "Google AI Overviews",
  google_ai_mode: "Google AI Mode",
  mock: "Mock",
};

const engineLabel = (name: string) => ENGINE_LABELS[name] ?? name;

/** The delta, as a chip.
 *
 * On a recurring report the delta is the SECOND-LARGEST element on a tile, after
 * the value — it is the thing a returning reader looks for first. Sentence case:
 * "Up from 1 of 6", never "UP FROM 1 OF 6". The only uppercase in the system is
 * the tracked label. */
function DeltaChip({ movement }: { movement: MovementRow }) {
  if (movement.direction === "unknown") {
    return <span className="body text-xs">not comparable</span>;
  }
  const flat = movement.direction === "flat";
  const glyph = flat ? "—" : movement.direction === "up" ? "▲" : "▼";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
      style={
        flat
          ? { backgroundColor: "var(--rule-soft)", color: "var(--harbour)" }
          : { backgroundColor: "var(--navy)", color: "#fff" }
      }
      // Shape AND text, never colour alone — the palette is a single navy ramp
      // and has no up/down hue to spend.
      title={movement.flat_reason || undefined}
    >
      <span aria-hidden="true">{glyph}</span>
      {flat
        ? "Held steady"
        : `${movement.direction === "up" ? "Up" : "Down"} from ${movement.before_successes} of ${movement.before_n}`}
    </span>
  );
}

/** Where a finding is in its life. Regressed is the one that must stand out —
 * a fix that did not hold is worse news than a fresh problem. */
function LifecycleBadge({ status, cycles }: { status?: string; cycles?: number }) {
  if (!status || status === "new") return null;
  const label =
    status === "regressed"
      ? "Regressed"
      : status === "resolved"
        ? "Resolved"
        : `Open ${cycles ?? 1} cycle${(cycles ?? 1) === 1 ? "" : "s"}`;
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
      style={
        status === "regressed"
          ? { backgroundColor: "var(--navy)", color: "#fff" }
          : { backgroundColor: "var(--rule-soft)", color: "var(--harbour)" }
      }
    >
      {label}
    </span>
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
function FindingCard({ group }: { group: FindingGroupRow }) {
  const isPrint = useIsPrint();
  // Expanded by default when printing. A collapsed disclosure is exactly the
  // "silently drops content" failure — the live page looks complete while the
  // PDF loses the evidence trail, which is the part that makes a finding
  // checkable rather than assertable.
  const [open, setOpen] = React.useState(isPrint);
  const lead = group.evidence[0];

  return (
    <div className="report-card card rounded-lg p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SeverityBadge severity={group.severity} />
        <span className="font-medium">{group.title}</span>
        <LifecycleBadge status={group.lifecycle_status} cycles={group.cycles_open} />
        <span className="body ml-auto text-xs">{group.theme_label}</span>
      </div>

      {lead && (
        <p className="body mb-2 text-sm">
          {engineLabel(lead.engine_name)}
          {lead.model_id ? ` (${lead.model_id})` : ""} — checked{" "}
          {lead.observed_at.slice(0, 10) || "date not recorded"}, {group.occurrence.phrase} —
          states:
        </p>
      )}

      <blockquote
        className="mb-2 border-l-2 pl-3 text-sm italic"
        style={{ borderColor: "var(--mist)" }}
      >
        “{group.representative_claims[0]}”
      </blockquote>
      {group.reality && (
        <p className="mb-3 text-sm">
          <span className="label">From your fact sheet</span>
          <br />
          {group.reality}
        </p>
      )}

      <p className="mb-1 text-sm">
        <span className="font-medium">Fix:</span> {group.action}
      </p>
      <p className="body text-xs">
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
          <div className={open ? "mt-3 space-y-3" : "hidden mt-3 space-y-3 print:block"}>
            {/* The card evidences a few observations, not all of them — say so
                rather than letting the reader infer this is everything. */}
            {group.evidence_total > group.evidence.length && (
              <p className="body text-xs">
                Showing {group.evidence.length} of {group.evidence_total} observations, one per
                surface. The full set is in the answers export.
              </p>
            )}
            {group.evidence.map((e, i) => (
              <div key={i} className="rounded border p-2 text-xs" style={{ borderColor: "var(--rule)" }}>
                <p className="body mb-1">
                  <span className="label">Prompt</span> “{e.prompt}”
                </p>
                <p className="body mb-1">
                  {engineLabel(e.engine_name)}
                  {e.model_id ? ` · ${e.model_id}` : " · model not recorded"} ·{" "}
                  {e.observed_at || "no timestamp"}
                </p>
                <p className="italic">“{e.excerpt}”</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function ReportView({
  report,
  runId,
  onJudged,
  brand = DEFAULT_BRAND,
}: {
  report: ReportPayload;
  runId?: string;
  // Lets the parent swap in the refreshed report after an on-demand judge pass.
  onJudged?: (report: ReportPayload) => void;
  /** The client-facing skin. One object, so an agency white-label replaces the
   * entire brand rather than an accent colour. */
  brand?: BrandConfig;
}) {
  const s = report.scorecard;
  const topComp = s.top_competitor;

  // Findings, grouped. Optional in the payload so runs stored before P1-T1 still
  // render — they fall back to no cards, and the appendix still lists the flags.
  const groups = report.finding_groups ?? [];
  const actions = report.priority_actions ?? [];
  const open = s.open_findings;
  const visibility = s.ai_visibility;
  const bySeverity = open?.by_severity ?? {};
  // Only rendered when a comparison is genuinely available. A first cycle shows
  // nothing here rather than an empty section implying something was compared.
  const changed = report.what_changed?.available ? report.what_changed : null;
  // The tile's delta is the run-wide roll-up of the SAME gated movements the
  // section lists — derived, never separately computed, so the tile and the
  // section can never disagree about whether something moved.
  const overall: MovementRow | null = React.useMemo(() => {
    const rows = changed?.movements.filter((m) => m.direction !== "unknown") ?? [];
    if (rows.length === 0) return null;
    const sum = (pick: (m: MovementRow) => number) => rows.reduce((a, m) => a + pick(m), 0);
    const moved = rows.filter((m) => m.direction !== "flat");
    return {
      key: "overall",
      before_successes: sum((m) => m.before_successes),
      before_n: sum((m) => m.before_n),
      after_successes: sum((m) => m.after_successes),
      after_n: sum((m) => m.after_n),
      delta_pp: 0,
      // Flat unless at least one surface earned a direction, and it takes the
      // majority direction of those that did. A tile that says "Up" while every
      // listed surface says "held steady" is the contradiction to avoid.
      direction:
        moved.length === 0
          ? "flat"
          : moved.filter((m) => m.direction === "up").length >= moved.length / 2
            ? "up"
            : "down",
      phrase: "",
      flat_reason:
        moved.length === 0 ? "no surface moved beyond this cycle's noise" : "",
    };
  }, [changed]);

  // Prior-cycle share per brand, for the paired bars. Only the client's series
  // is measured cycle-over-cycle today, so competitors show no prior bar rather
  // than a fabricated one.
  const priorShares = React.useMemo(() => {
    if (!changed) return undefined;
    const before = changed.movements.reduce((a, m) => a + m.before_successes, 0);
    const beforeN = changed.movements.reduce((a, m) => a + m.before_n, 0);
    if (!beforeN) return undefined;
    return { [report.client_name]: before / beforeN };
  }, [changed, report.client_name]);
  // P3-T2 filters. Client-side only, no new payload. `no-print` on the controls
  // so a filtered PDF cannot be mistaken for the whole report — a partial export
  // that looks complete is the same class of bug as a lazy-loaded section that
  // silently vanishes.
  const [engineFilter, setEngineFilter] = React.useState<string>("all");
  const [intentFilter, setIntentFilter] = React.useState<string>("all");

  const matches = React.useCallback(
    (engines: string[], intents: string[]) =>
      (engineFilter === "all" || engines.includes(engineFilter)) &&
      (intentFilter === "all" || intents.includes(intentFilter)),
    [engineFilter, intentFilter],
  );

  const visibleGroups = React.useMemo(
    () => groups.filter((g) => matches(g.engines, g.intents)),
    [groups, matches],
  );
  const visibleLosing = React.useMemo(
    () =>
      report.losing_queries.filter(
        (l) =>
          (engineFilter === "all" || l.engine_name === engineFilter) &&
          (intentFilter === "all" || l.intent === intentFilter),
      ),
    [report.losing_queries, engineFilter, intentFilter],
  );
  const isFiltered = engineFilter !== "all" || intentFilter !== "all";

  // The severity bar counts what is VISIBLE, so the bar and the cards below it
  // can never disagree — a summary that ignores the filter is a summary of a
  // different report.
  const visibleBySeverity = React.useMemo(() => {
    const counts: Record<string, number> = { critical: 0, high: 0, med: 0, low: 0 };
    for (const g of visibleGroups) counts[g.severity] = (counts[g.severity] ?? 0) + 1;
    return counts;
  }, [visibleGroups]);

  const intentOptions = React.useMemo(
    () => [...new Set(groups.flatMap((g) => g.intents))].sort(),
    [groups],
  );

  const criticalAndHigh = visibleGroups.filter(
    (g) => g.severity === "critical" || g.severity === "high",
  );
  const mediumAndLow = visibleGroups.filter(
    (g) => g.severity === "med" || g.severity === "low",
  );

  const [judging, setJudging] = React.useState(false);
  const [judgeError, setJudgeError] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<JudgeStatus | null>(null);

  // Warm status of the notebooks (query answers + on-site content checks): tells
  // the user whether Judge will be free (all pre-judged on the subscription) or
  // still hit the API. Refreshed on mount and after a judge run.
  const refreshStatus = React.useCallback(() => {
    if (!runId) return;
    fetchJudgeStatus(runId)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [runId]);
  React.useEffect(refreshStatus, [refreshStatus]);

  // Everything with an LLM cost is already cached → Judge / the report is $0.
  const allWarm =
    !!status &&
    (status.query.total === 0 || status.query.warm) &&
    (status.content.total === 0 || status.content.warm);

  // Run the LLM judge over the stored answers. Free when the judge cache was
  // pre-filled on the subscription (the /prejudge workflow); otherwise it judges
  // on the API. On success the parent re-renders with the judged report.
  const runJudge = async () => {
    if (!runId || judging) return;
    setJudging(true);
    setJudgeError(null);
    try {
      const updated = await judgeAudit(runId);
      onJudged?.(updated);
      refreshStatus();
    } catch {
      setJudgeError("Judging failed — is the API reachable and a judge key set?");
    } finally {
      setJudging(false);
    }
  };

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `geo-audit-${report.client_name.replace(/\s+/g, "-").toLowerCase()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Raw per-call answers (query text + full model response). Fetched with the
  // API key and saved as a blob (an <a href> couldn't carry the auth header).
  const downloadAnswers = (ext: "results.csv" | "answers.md") => {
    if (!runId) return;
    void downloadAudit(runId, ext);
  };

  return (
    <div className={`${brand.themeClass} space-y-8 p-4 sm:p-6`}>
      {/* Masthead — a full-bleed navy band, which is the ONLY place Sky is legal
          in the whole report. `--on-navy-accent` exists only inside `.on-navy`,
          so using it anywhere else is a missing-variable bug rather than a
          design-review argument. */}
      <div className="on-navy report-section -mx-4 -mt-4 px-4 py-5 sm:-mx-6 sm:-mt-6 sm:px-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="display-lg">{report.client_name}</h1>
            <p className="label mt-1" style={{ color: "var(--on-navy-accent)" }}>
              AI visibility report
            </p>
          </div>
          {brand.showMark && (
            <span className="wordmark text-lg" style={{ color: "var(--on-navy-accent)" }}>
              {brand.name}
            </span>
          )}
        </div>
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="body text-sm">
            {report.run_date} · query set {report.query_set_version} · {report.runs_per_query}{" "}
            run(s)/query · surfaces:{" "}
            {report.engines.map(engineLabel).join(", ") || "none"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge variant={report.detection === "judge" ? "default" : "secondary"}>
              {report.detection === "judge" ? "LLM judge" : "regex detection"}
            </Badge>
            {report.competitors.map((c) => (
              <Badge key={c} variant="outline">
                {c}
              </Badge>
            ))}
          </div>
        </div>
        <div className="no-print flex flex-col items-end gap-1.5">
          <div className="flex gap-2">
          {runId && (
            <Button
              variant={report.detection === "judge" ? "outline" : "default"}
              size="sm"
              onClick={runJudge}
              disabled={judging}
              title={
                report.detection === "judge"
                  ? "Re-run the LLM judge over the stored answers (free if the judge cache is warm)"
                  : "Run the LLM judge over the stored answers — free if you pre-judged this run on the subscription"
              }
            >
              {judging ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Gavel className="h-4 w-4" />
              )}
              {judging
                ? "Judging…"
                : report.detection === "judge"
                  ? "Re-judge"
                  : "Judge"}
              {!judging && allWarm ? " · free" : ""}
            </Button>
          )}
          {runId && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadAnswers("results.csv")}
                title="Every query and the full model response, one row per call"
              >
                <FileSpreadsheet className="h-4 w-4" /> Answers CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadAnswers("answers.md")}
                title="Readable answers doc with the judge's verdict inline"
              >
                <FileText className="h-4 w-4" /> Answers MD
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" onClick={downloadJson}>
            <Download className="h-4 w-4" /> JSON
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4" /> Export
          </Button>
          </div>
          {runId && status && (
            <p className="max-w-xs text-right text-xs text-muted-foreground">
              Notebook: query {status.query.cached}/{status.query.total}
              {status.content.total > 0 ? (
                <> · content {status.content.cached}/{status.content.total}</>
              ) : null}
              {" — "}
              {allWarm ? (
                <span className="text-[hsl(var(--success))]">warm, Judge is $0</span>
              ) : (
                <>
                  not fully warm; <code>/prejudge {runId.slice(0, 8)}</code> in Claude Code to make
                  it free.
                </>
              )}
            </p>
          )}
        </div>
      </div>

      {judgeError && (
        <div className="no-print rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {judgeError}
        </div>
      )}

      {/* §0 Executive summary — the one sentence a CMO acts on. Generated
          deterministically from structured fields; no model wrote it. */}
      {report.exec_summary && (
        <section className="report-section">
          <p className="display text-xl leading-snug">{report.exec_summary}</p>
          {report.comparison_blocked_reason === "query_set_changed" && (
            <p className="body mt-2 text-sm">
              The question set changed since the last cycle, so the two are not comparable
              instruments and no week-over-week figures are shown. Comparison resumes next cycle.
            </p>
          )}
        </section>
      )}

      {/* §0b What changed — immediately after the summary and before the
          scorecard, because "did your recommendations do anything" is the
          question that determines renewal. A recurring report with no
          comparison is a status update. */}
      {changed && (
        <section className="report-section space-y-3">
          <SectionTitle icon={<Repeat2 className="h-3.5 w-3.5" />}>
            What changed since {changed.prior_run_date || "the last cycle"}
          </SectionTitle>
          <Card className="card">
            <CardContent className="space-y-4 pt-6">
              <p className="text-base font-medium">{changed.accountability}</p>

              {changed.movements.length > 0 && (
                <div>
                  <p className="label mb-2">By surface</p>
                  <ul className="space-y-1.5">
                    {/* Flat cells are LISTED, not omitted. A weekly product that
                        manufactures news in flat weeks destroys itself faster
                        than one that reports nothing happened. */}
                    {changed.movements.map((m) => (
                      <li key={m.key} className="text-sm">
                        <span className="inline-flex items-center gap-2">
                          <DeltaChip movement={m} />
                          <span>{m.phrase.replace(/^[^:]+:\s*/, "")}</span>
                          <span className="body">{engineLabel(m.key)}</span>
                        </span>
                        {m.flat_reason && (
                          <span className="body block text-xs">{m.flat_reason}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      {/* §1 Scorecard — four tiles, every one COUNTED or MEASURED.
          No letter grade and no composite score. See ScorecardPayload in
          src/api/reports.py for why that stays true. */}
      <section className="space-y-3">
        <SectionTitle icon={<Trophy className="h-3.5 w-3.5" />}>Scorecard</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            icon={<Target className="h-3.5 w-3.5" />}
            label="AI visibility"
            delta={overall && <DeltaChip movement={overall} />}
            muted={!visibility || visibility.n === 0}
            value={
              visibility && visibility.n > 0
                ? `${visibility.successes} of ${visibility.n}`
                : "Insufficient data"
            }
            sub={
              visibility && visibility.n > 0
                ? `sampled answers across ${report.engines.length} surfaces · 95% CI ${pct(
                    visibility.ci_low,
                  )}–${pct(visibility.ci_high)}`
                : "no surface returned an answer"
            }
          />
          <MetricCard
            icon={<PieIcon className="h-3.5 w-3.5" />}
            label="Share of model"
            value={pct(s.share_of_model_client)}
            sub={
              topComp ? `vs ${topComp} ${pct(s.top_competitor_share)}` : "no competitors configured"
            }
          />
          <MetricCard
            icon={<ShieldCheck className="h-3.5 w-3.5" />}
            label="Open findings"
            muted={!s.accuracy_assessed}
            value={s.accuracy_assessed ? (open?.themes ?? 0) : "Not assessed"}
            sub={
              s.accuracy_assessed
                ? `${open?.critical ?? 0} critical · ${open?.instances ?? 0} observations`
                : report.detection === "judge"
                  ? "needs a fact sheet"
                  : "needs the LLM judge"
            }
          />
          {/* Replaces the grade, and does its job better: SLA-style aging is what
              creates pressure to act, and it is a count rather than an opinion.
              Renders "—" until the lifecycle engine lands (P2-T2) — an age we
              cannot compute is not one we may guess. */}
          <MetricCard
            icon={<Repeat2 className="h-3.5 w-3.5" />}
            label="Oldest still open"
            muted={!s.oldest_open}
            value={s.oldest_open ? s.oldest_open.title : "—"}
            sub={
              s.oldest_open
                ? s.oldest_open.occurrence.phrase
                : "needs a prior cycle to measure against"
            }
          />
        </div>
      </section>

      {/* §1b This cycle's priority actions — above the findings, because a
          reader who stops after one section should stop after the plan. 3–7
          rows: more than that is a backlog wearing a plan's clothes. */}
      {actions.length > 0 && (
        <section className="report-section space-y-3">
          <SectionTitle icon={<Target className="h-3.5 w-3.5" />}>
            This cycle&rsquo;s priority actions
          </SectionTitle>
          <Card className="card">
            <CardContent className="pt-6">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Action</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead>Effort</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {actions.map((a) => (
                    <TableRow key={a.theme}>
                      <TableCell>
                        <span className="font-medium">{a.title}</span>
                        <br />
                        <span className="body text-sm">{a.action}</span>
                      </TableCell>
                      <TableCell>
                        <SeverityBadge severity={a.severity} />
                      </TableCell>
                      <TableCell>{a.owner}</TableCell>
                      <TableCell className="tabular-nums">{a.effort}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>
      )}

      {/* §2 Competitive position — donut + bars */}
      <section className="space-y-3">
        <SectionTitle icon={<PieIcon className="h-3.5 w-3.5" />}>Competitive position</SectionTitle>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="card">
            <CardHeader>
              <CardTitle className="text-base">Share of model</CardTitle>
            </CardHeader>
            <CardContent>
              <ShareStackedBar rows={report.leaderboard} />
            </CardContent>
          </Card>
          <Card className="card">
            <CardHeader>
              <CardTitle className="text-base">Visibility leaderboard</CardTitle>
            </CardHeader>
            <CardContent>
              <LeaderboardChart rows={report.leaderboard} prior={priorShares} />
            </CardContent>
          </Card>
        </div>

        {/* Brand x surface. The most decision-relevant split in the data, and
            nothing showed it before. */}
        {(report.engine_matrix?.length ?? 0) > 0 && (
          <Card className="card">
            <CardHeader>
              <CardTitle className="text-base">Where each brand appears, by surface</CardTitle>
            </CardHeader>
            <CardContent>
              <EngineHeatmap
                rows={report.engine_matrix ?? []}
                engines={report.engines}
                clientName={report.client_name}
              />
            </CardContent>
          </Card>
        )}
        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Brand</TableHead>
                  <TableHead>Share of model</TableHead>
                  <TableHead>Mention rate</TableHead>
                  <TableHead>Visibility</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.leaderboard.map((r) => (
                  <TableRow key={r.brand}>
                    <TableCell className="font-medium">
                      {r.brand}
                      {r.is_client && (
                        <Badge variant="default" className="ml-2">
                          client
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">{pct(r.share_of_model)}</TableCell>
                    <TableCell className="tabular-nums">{pct(r.mention_rate)}</TableCell>
                    <TableCell className="tabular-nums">
                      {r.visibility === null ? "—" : r.visibility.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </section>

      {/* §3 Funnel stage + accuracy */}
      <section className="space-y-3">
        <SectionTitle icon={<BarChart3 className="h-3.5 w-3.5" />}>
          Visibility by funnel stage
        </SectionTitle>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mention &amp; citation by intent</CardTitle>
            </CardHeader>
            <CardContent>
              <BucketChart rows={report.by_bucket} />
              <Table className="mt-4">
                <TableHeader>
                  <TableRow>
                    <TableHead>Bucket</TableHead>
                    <TableHead>Mention</TableHead>
                    <TableHead>Citation</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.by_bucket.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-muted-foreground">
                        No data.
                      </TableCell>
                    </TableRow>
                  ) : (
                    report.by_bucket.map((b) => (
                      <TableRow key={b.bucket}>
                        <TableCell>
                          <IntentBadge intent={b.bucket} />
                        </TableCell>
                        <TableCell className="tabular-nums">{pct(b.mention_rate)}</TableCell>
                        <TableCell className="tabular-nums">
                          {b.citation_rate === null ? "—" : pct(b.citation_rate)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="card">
            <CardHeader>
              <CardTitle className="text-base">Accuracy at a glance</CardTitle>
            </CardHeader>
            <CardContent>
              {!s.accuracy_assessed ? (
                <p className="body text-sm">
                  {report.detection === "judge"
                    ? "Not assessed — add a fact sheet (fact rows in the CSV) so the judge can check claims against ground truth."
                    : "Not assessed — enable the LLM judge (config,judge,true)."}
                </p>
              ) : (
                <SeveritySummaryBar counts={bySeverity} />
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* §3c Findings — the deliverable.
          Count bar FIRST, before any individual finding: most readers stop
          there, and that is the design intent rather than a failure. Full cards
          for Critical and High only; Medium and Low collapse into a table. */}
      {s.accuracy_assessed && (
        <section className="report-section space-y-4">
          <SectionTitle icon={<ShieldCheck className="h-3.5 w-3.5" />}>
            What the models get wrong
          </SectionTitle>

          <div className="no-print flex flex-wrap items-center gap-2">
            <span className="label">Filter</span>
            <select
              className="rounded border px-2 py-1 text-sm"
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
              className="rounded border px-2 py-1 text-sm"
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
              <button
                type="button"
                className="text-sm underline"
                style={{ color: "var(--blue)" }}
                onClick={() => {
                  setEngineFilter("all");
                  setIntentFilter("all");
                }}
              >
                Clear
              </button>
            )}
            {isFiltered && (
              <span className="body text-xs">
                Showing {visibleGroups.length} of {groups.length} findings
              </span>
            )}
          </div>

          <SeveritySummaryBar counts={visibleBySeverity} />

          {visibleGroups.length === 0 ? (
            <p className="body text-sm">
              {isFiltered
                ? "No findings match this filter."
                : `No findings are open — every claim the models made about ${report.client_name} that your fact sheet covers checked out.`}
            </p>
          ) : (
            <>
              {criticalAndHigh.length > 0 && (
                <div className="space-y-3">
                  {criticalAndHigh.map((g) => (
                    <FindingCard key={g.theme} group={g} />
                  ))}
                </div>
              )}

              {mediumAndLow.length > 0 && (
                <Card className="card">
                  <CardHeader>
                    <CardTitle className="text-base">
                      Medium and low findings ({mediumAndLow.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Finding</TableHead>
                          <TableHead>Severity</TableHead>
                          <TableHead>Surfaces</TableHead>
                          <TableHead>Observed</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {mediumAndLow.map((g) => (
                          <TableRow key={g.theme}>
                            <TableCell>
                              <span className="font-medium">{g.title}</span>
                              <br />
                              <span className="body text-xs">{g.theme_label}</span>
                            </TableCell>
                            <TableCell>
                              <SeverityBadge severity={g.severity} />
                            </TableCell>
                            <TableCell className="text-sm">
                              {g.engines.map(engineLabel).join(", ") || "—"}
                            </TableCell>
                            <TableCell className="tabular-nums text-sm">
                              {g.occurrence.observed} of {g.occurrence.total}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </section>
      )}

      {/* §3b How reproducible the verdicts were across repeat runs */}
      {(report.stability?.length ?? 0) > 0 && (
        <section className="space-y-3">
          <SectionTitle icon={<Repeat2 className="h-3.5 w-3.5" />}>Verdict stability</SectionTitle>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Did the same answer come back twice?</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Engine</TableHead>
                    <TableHead>Repeated cells</TableHead>
                    <TableHead>Split</TableHead>
                    <TableHead>Agreement</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.stability?.map((row) => (
                    <TableRow key={row.engine_name}>
                      <TableCell className="font-medium">{row.engine_name}</TableCell>
                      <TableCell className="tabular-nums">{row.repeated_cells}</TableCell>
                      <TableCell className="tabular-nums">
                        {row.split_cells > 0 ? (
                          <span className="text-destructive">{row.split_cells}</span>
                        ) : (
                          row.split_cells
                        )}
                      </TableCell>
                      <TableCell className="tabular-nums">{pct(row.mean_agreement)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="mt-3 text-sm text-muted-foreground">
                A split cell read one way in some runs and the other way in the rest — its
                verdict could flip on a re-run, so findings resting on it are weaker than the
                headline rates suggest. Engines missing from this table were not repeated
                enough times to say (that is unmeasured, not stable).
              </p>
            </CardContent>
          </Card>
        </section>
      )}

      {/* §4 Sources + losing queries */}
      <section className="space-y-3">
        <SectionTitle icon={<Globe className="h-3.5 w-3.5" />}>Sources &amp; gaps</SectionTitle>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sources behind the category</CardTitle>
            </CardHeader>
            <CardContent>
              <SourcesChart rows={report.sources} />
              {report.sources.length > 0 && (
                <Table className="mt-4">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Domain</TableHead>
                      <TableHead>Cited in cells</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {report.sources.map((src) => (
                      <TableRow key={src.domain}>
                        <TableCell className="font-medium">{src.domain}</TableCell>
                        <TableCell className="tabular-nums">{src.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingDown className="h-4 w-4 text-destructive" />
                Losing queries ({visibleLosing.length}{isFiltered ? ` of ${report.losing_queries.length}` : ""})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {visibleLosing.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  None — the client appears wherever a competitor does.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Query</TableHead>
                      <TableHead>Engine</TableHead>
                      <TableHead>Competitor</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {/* The VERBATIM question, never `l.query_id`. `cmp-05` is
                        the most actionable data in the report made unreadable;
                        the id stays in the payload as a join key only. */}
                    {visibleLosing.map((l, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <span className="font-medium">
                            {l.prompt ? `“${l.prompt}”` : "(question text not recorded)"}
                          </span>
                          {l.intent && (
                            <div className="mt-1">
                              <IntentBadge intent={l.intent} />
                            </div>
                          )}
                        </TableCell>
                        <TableCell>{engineLabel(l.engine_name)}</TableCell>
                        <TableCell>{l.competitor}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* §5 On-site & off-site audit (technique checklist Cat 1–6) */}
      {report.site_audit?.present && <SiteAuditSection siteAudit={report.site_audit} />}

      {/* §6 Methodology — the disclosures, VERBATIM and exactly once.
          A client WILL re-run a prompt, get a different answer, and doubt the
          report. Pre-empt it here; never let them discover it. Do not paraphrase
          either string — both are worded to be honest without self-undermining,
          and both are supplied by the backend so every surface says the same
          thing. */}
      <section className="report-section space-y-3">
        <SectionTitle icon={<ShieldCheck className="h-3.5 w-3.5" />}>Methodology</SectionTitle>
        <Card className="card">
          <CardContent className="space-y-3 pt-6">
            <div>
              <p className="label mb-1">How we measured</p>
              <p className="body text-sm">
                We asked {report.engines.length} AI surfaces (
                {report.engines.map(engineLabel).join(", ") || "none"}) the{" "}
                {report.query_set_version} question set, {report.runs_per_query} independent times
                per question, and graded each answer against your fact sheet. Every rate in this
                report is shown as a count with its denominator; percentages are secondary because
                at this sample size a bare percentage is misleading.
              </p>
            </div>
            {report.methodology_disclosure && (
              <div>
                <p className="label mb-1">On reproducing these results</p>
                <p className="body text-sm">{report.methodology_disclosure}</p>
              </div>
            )}
            <div>
              <p className="label mb-1">Severity</p>
              <p className="body text-sm">
                <strong>Critical</strong> — a category or identity error, or a claim that materially
                changes a purchase decision. <strong>High</strong> — an invented or materially
                misstated capability, or a competitor&rsquo;s attributes applied to you.{" "}
                <strong>Medium</strong> — a real capability omitted or understated.{" "}
                <strong>Low</strong> — imprecise phrasing, unverifiable but not contradicted.
              </p>
            </div>
            {report.judge_agreement && (
              <div>
                <p className="label mb-1">How the grading was checked</p>
                <p className="body text-sm">{report.judge_agreement}</p>
              </div>
            )}
            {report.independence_disclaimer && (
              <p className="body text-xs">{report.independence_disclaimer}</p>
            )}
            {brand.poweredBy && (
              <p className="body text-xs">Measurement by {brand.name}.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
