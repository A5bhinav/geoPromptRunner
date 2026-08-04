"use client";

import * as React from "react";
import {
  Printer,
  Download,
  FileText,
  FileSpreadsheet,
  Gavel,
  Loader2,
  Target,
  ShieldCheck,
  Scale,
  BarChart3,
  Globe,
  TrendingDown,
  Repeat2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Notice } from "@/components/notice";
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
import { Page, PageHeader } from "@/components/page";
import { SidebarLabel, SidebarRow, SidebarSlot } from "@/components/app-shell";
import {
  CompetitivePanel,
  FindingsPanel,
  HeadlinePanel,
  PresencePanel,
  engineLabel,
} from "@/components/report-panels";
// RECHARTS IS GONE FROM THE REPORT. The five lazy-loaded chart components it
// backed (leaderboard, stacked share, heatmap, bucket bars, sources bars) are
// replaced by the four hand-rolled panels above. Three reasons, in order of
// weight: the packaging rules say don't add a charting dependency and hand-roll
// the SVG; the sources chart was still painting indigo / emerald / amber from a
// categorical palette this brand does not have, and the bucket chart spent a
// second hue on the citation series; and the dynamic-import-versus-print race
// (a chunk still resolving when the capture runs) stops existing when there is
// no chunk. components/charts.tsx has no remaining importer.
import { pct } from "@/lib/utils";
import {
  downloadAudit,
  fetchJudgeStatus,
  judgeAudit,
  type FindingGroupRow,
  getAnswerCell,
  type EvidenceRow,
  type JudgeStatus,
  type MovementRow,
  type ReportPayload,
} from "@/lib/api";

/** The rail's table of contents. The four ids are on the four panels; findings
 * is the full section further down, which is where "See all" lands. */
const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "competitive", label: "Competitive" },
  { id: "presence", label: "Where it shows up" },
  { id: "findings", label: "Findings" },
] as const;

/** "2026-06-14" → "14 Jun". Falls back to the raw string rather than to
 * "Invalid Date" — a run date we cannot parse is still a label. */
function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function SectionTitle({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <h2 className="label flex items-center gap-2">
      {icon}
      {children}
    </h2>
  );
}

// `engineLabel` now lives in components/report-panels.tsx and is imported above:
// the panels and the finding cards must agree on what a surface is called, and
// two copies of the same map is how "Google AI Mode" ends up rendered as
// `google_ai_mode` in exactly one place.

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

/** The full stored answer behind one observation, with the flagged sentence
 * highlighted (P3-T1).
 *
 * The card quotes an excerpt; a reader who doubts it needs the sentence IN
 * CONTEXT, and the alternative was downloading the whole answers export. Fetched
 * on expand and cached per cell — the answers are already stored, so this is
 * retrieval, never a re-measurement.
 *
 * Highlighting is a plain substring match on the excerpt. When it does not match
 * (the judge may quote across a line break) the answer still renders, unhighlighted
 * — showing the evidence beats refusing to show it because a marker missed. */
function AnswerPanel({
  runId,
  evidence,
}: {
  runId: string;
  evidence: EvidenceRow;
}) {
  // Discrete members, not `{status: "idle" | "loading"}` — a combined member
  // cannot be narrowed away by the early returns below, so `state.text` stops
  // typechecking in the branch where it is provably present.
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
  if (state.status === "loading") return <span className="body text-xs">Loading…</span>;
  if (state.status === "error") return <span className="body text-xs">{state.message}</span>;

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
                {runId && e.query_id && <AnswerPanel runId={runId} evidence={e} />}
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

  // The visibility trend. Two points, not four: this run and the one it is
  // GATED against. `what_changed` is only populated when the two cycles are
  // comparable instruments (same query set), so a series built from it can never
  // silently compare across a changed question set — which is the one thing the
  // recurring contract forbids outright. Undefined ⇒ the headline panel draws
  // per-surface presence instead, because a one-point line is not a trend.
  const trend = React.useMemo(() => {
    if (!changed) return undefined;
    const before = changed.movements.reduce((a, m) => a + m.before_successes, 0);
    const beforeN = changed.movements.reduce((a, m) => a + m.before_n, 0);
    const after = changed.movements.reduce((a, m) => a + m.after_successes, 0);
    const afterN = changed.movements.reduce((a, m) => a + m.after_n, 0);
    if (!beforeN || !afterN) return undefined;
    return [
      { label: shortDate(changed.prior_run_date), value: Math.round((before / beforeN) * 100) },
      { label: shortDate(report.run_date), value: Math.round((after / afterN) * 100) },
    ];
  }, [changed, report.run_date]);

  // The client's own row of the brand × surface matrix, in the report's fixed
  // engine order. Feeds the headline panel's first-cycle fallback.
  const clientBySurface = React.useMemo(() => {
    const rows = report.engine_matrix ?? [];
    return report.engines.map((engine) => {
      const cell = rows.find(
        (r) => r.engine_name === engine && r.brand === report.client_name,
      );
      return { engine, present: cell?.present ?? 0, cells: cell?.cells ?? 0 };
    });
  }, [report.engine_matrix, report.engines, report.client_name]);

  const isPrint = useIsPrint();
  const [activeSection, setActiveSection] = React.useState<string>("overview");
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

  const scrollTo = (id: string) => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const headerActions = (
    <>
      {runId && (
        <Button
          variant="outline"
          onClick={runJudge}
          disabled={judging}
          title={
            report.detection === "judge"
              ? "Re-run the LLM judge over the stored answers (free if the judge cache is warm)"
              : "Run the LLM judge over the stored answers — free if you pre-judged this run on the subscription"
          }
        >
          {judging ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Gavel className="h-4 w-4" aria-hidden />
          )}
          {judging ? "Judging…" : report.detection === "judge" ? "Re-judge" : "Judge"}
          {!judging && allWarm ? " · free" : ""}
        </Button>
      )}
      <Button variant="outline" onClick={() => window.print()}>
        <Printer className="h-4 w-4" aria-hidden /> Export
      </Button>
    </>
  );

  return (
    <div className={brand.themeClass}>
      {/* The rail carries the report's own table of contents. Report-only: it is
          rendered through a portal into the shell, and the shell's rail is
          `no-print`, so none of this reaches the PDF. */}
      <SidebarSlot slot="sections">
        <SidebarLabel>Sections</SidebarLabel>
        <div className="flex flex-col gap-px">
          {SECTIONS.map((s) => (
            <SidebarRow
              key={s.id}
              active={activeSection === s.id}
              count={s.id === "findings" ? groups.length : undefined}
              onClick={() => scrollTo(s.id)}
            >
              {s.label}
            </SidebarRow>
          ))}
        </div>
      </SidebarSlot>
      <SidebarSlot slot="footer">
        <button
          type="button"
          onClick={() => window.print()}
          className="h-[34px] w-full rounded-full bg-white text-[12px] font-semibold text-navy transition-opacity hover:opacity-90"
        >
          Build PDF
        </button>
      </SidebarSlot>

      {/* TWO HEADERS, ON PURPOSE.
          The PDF and the workbench are different artifacts. The deliverable
          opens on a full-bleed navy masthead — the ONLY place Sky is legal in
          the whole report, and the thing that makes a printed page look like it
          came from somewhere. The screen opens on the app's own eyebrow/title
          block, because a navy band immediately under a navy rail is a wall.
          `useIsPrint()` picks; neither is a fallback for the other. */}
      {isPrint ? (
        <div className="on-navy report-section px-6 py-5">
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
      ) : null}

      <Page className="gap-[22px]">
        {isPrint ? null : (
          <PageHeader
            eyebrow={`Report · ${report.run_date}`}
            title={report.client_name}
            href={report.client_domains[0] ? `https://${report.client_domains[0]}` : undefined}
            hrefLabel={report.client_domains[0]}
            actions={headerActions}
          />
        )}

        {/* The instrument, in one line. Everything a reader needs to know a
            number in this report is comparable to a number in the last one:
            which question set, how many repeats, which surfaces. */}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[13px] text-[color:var(--ink-secondary)]">
          <span>
            Query set {report.query_set_version} · {report.runs_per_query} run
            {report.runs_per_query === 1 ? "" : "s"} per question ·{" "}
            {report.engines.map(engineLabel).join(", ") || "no surface returned an answer"}
          </span>
          <Badge variant={report.detection === "judge" ? "muted" : "quiet"}>
            {report.detection === "judge" ? "LLM judge" : "regex detection"}
          </Badge>
          {report.competitors.map((c) => (
            <Badge key={c} variant="outline">
              {c}
            </Badge>
          ))}
        </div>

        <div className="no-print flex flex-col items-end gap-1.5">
          <div className="flex gap-2">
          {/* Re-judge and Export moved to the page header — they are the two
              actions the screen exists for. What is left here is the raw-data
              trapdoor: the exports an analyst uses to check our arithmetic. */}
          {runId && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadAnswers("results.csv")}
                title="Every query and the full model response, one row per call"
              >
                <FileSpreadsheet className="h-4 w-4" aria-hidden /> Answers CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadAnswers("answers.md")}
                title="Readable answers doc with the judge's verdict inline"
              >
                <FileText className="h-4 w-4" aria-hidden /> Answers MD
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" onClick={downloadJson}>
            <Download className="h-4 w-4" aria-hidden /> JSON
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
                <span className="font-medium text-blue">warm, Judge is $0</span>
              ) : (
                <>
                  not fully warm; <code>/prejudge {runId.slice(0, 8)}</code> in Claude Code to make
                  it free.
                </>
              )}
            </p>
          )}
        </div>

      {judgeError && (
        <Notice tone="problem" className="no-print">
          {judgeError}
        </Notice>
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

      {/* §1 The overview — four panels, charts first.
          The headline panel IS the scorecard: one measured hero and three
          counted tiles (open findings, share of model, oldest still open). No
          letter grade and no composite score — see ScorecardPayload in
          src/api/reports.py for why that stays true. */}
      <section id="overview" className="report-section scroll-mt-6">
        <HeadlinePanel
          clientName={report.client_name}
          visibility={visibility}
          surfaces={report.engines.length}
          delta={overall ? <DeltaChip movement={overall} /> : undefined}
          themes={open?.themes ?? 0}
          critical={open?.critical ?? 0}
          accuracyAssessed={s.accuracy_assessed}
          shareOfModel={s.share_of_model_client}
          topCompetitor={topComp}
          topCompetitorShare={s.top_competitor_share}
          oldestOpen={s.oldest_open ?? null}
          trend={trend}
          perSurface={clientBySurface}
        />
      </section>

      <section id="competitive" className="report-section scroll-mt-6">
        <CompetitivePanel
          leaderboard={report.leaderboard}
          bySeverity={bySeverity}
          totalFindings={open?.themes ?? groups.length}
          buckets={report.by_bucket}
          accuracyAssessed={s.accuracy_assessed}
        />
      </section>

      <section id="presence" className="report-section scroll-mt-6">
        <PresencePanel
          matrix={report.engine_matrix ?? []}
          engines={report.engines}
          clientName={report.client_name}
          clientDomains={report.client_domains}
          sources={report.sources}
        />
      </section>

      <FindingsPanel
        groups={visibleGroups}
        engines={report.engines}
        criticalCount={visibleBySeverity.critical ?? 0}
        onSeeAll={() => scrollTo("findings")}
      />

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

      {/* §2 The leaderboard table.
          The CHARTS that used to open this section — stacked share, paired
          leaderboard bars, the brand × surface heatmap — are now the
          Competitive and Presence panels above. What survives here is the
          table: the exact figures behind those marks, for a reader who wants to
          check them rather than scan them. The paired "prior cycle" bar is not
          missed — the only series it ever carried was the client's, and that is
          the delta chip on the headline. */}
      <section className="space-y-3">
        <SectionTitle icon={<Scale className="h-3.5 w-3.5" />}>
          Competitive position, in figures
        </SectionTitle>
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
                        <Badge variant="solid" className="ml-2">
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

      {/* §3 Funnel stage + accuracy.
          The BARS are the Competitive panel's third cell; this is the table
          behind them, which also carries the citation rate — a second series
          the panel deliberately does not spend a hue on. */}
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
              <Table>
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
        <section id="findings" className="report-section scroll-mt-6 space-y-4">
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
                    <FindingCard key={g.theme} group={g} runId={runId} />
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
                          <span className="font-medium text-navy">{row.split_cells}</span>
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
              {/* The BARS are the Presence panel's second cell (top 7); this is
                  the full list. */}
              {report.sources.length > 0 && (
                <Table>
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
                <TrendingDown className="h-4 w-4 text-navy" />
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
      </Page>
    </div>
  );
}
