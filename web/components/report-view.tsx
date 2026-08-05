"use client";

import * as React from "react";
import { Printer, Download, FileText, FileSpreadsheet, Gavel, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Notice } from "@/components/notice";
import { SiteAuditSection } from "@/components/site-audit-section";
import { DEFAULT_BRAND, type BrandConfig } from "@/lib/brand";
import { useIsPrint } from "@/lib/render-mode";
import { Page, PageHeader } from "@/components/page";
import { SidebarLabel, SidebarRow, SidebarSlot } from "@/components/app-shell";
import { engineLabel } from "@/components/report-panels";
import { type SectionContext } from "@/components/report-contract";
import { REPORT_SECTIONS, sectionsForTier, type SectionTier } from "@/lib/report-sections";
import {
  downloadAudit,
  downloadReportPdf,
  fetchJudgeStatus,
  judgeAudit,
  type JudgeStatus,
  type ReportPayload,
} from "@/lib/api";

/**
 * The report shell.
 *
 * This component owns the CHROME — masthead, export buttons, the judge control,
 * the rail's table of contents, the filter state — and nothing else. Every piece
 * of report CONTENT renders from `web/lib/report-sections.tsx`, in the order that
 * registry declares.
 *
 * That split is the point of TR-T11. The section order used to live in this
 * file's JSX, which meant "move the citations section above the competitive one"
 * or "put priority actions behind a paid tier" was a component edit. Now both are
 * edits to a data structure, and a snapshot test asserts the rendered order
 * matches it. If you find yourself adding report content here, add a registry
 * entry instead.
 *
 * RECHARTS IS GONE FROM THE REPORT. Every mark is a div or a hand-rolled
 * polyline in the four-step navy ramp: the packaging rules say don't add a
 * charting dependency, the old sources chart painted indigo/emerald/amber from a
 * categorical palette this brand does not have, and the dynamic-import-versus-
 * print race stops existing when there is no chunk.
 */
export function ReportView({
  report,
  runId,
  onJudged,
  brand = DEFAULT_BRAND,
  tier = "track",
}: {
  report: ReportPayload;
  runId?: string;
  /** Lets the parent swap in the refreshed report after an on-demand judge pass. */
  onJudged?: (report: ReportPayload) => void;
  /** The client-facing skin. One object, so an agency white-label replaces the
   * entire brand rather than an accent colour. */
  brand?: BrandConfig;
  /** Which sections this reader may see. Everything ships as `track` today. */
  tier?: SectionTier;
}) {
  const isPrint = useIsPrint();
  const [activeSection, setActiveSection] = React.useState<string>("snapshot");
  // P3-T2 filters. Client-side only, no new payload. `no-print` on the controls
  // so a filtered PDF cannot be mistaken for the whole report.
  const [engineFilter, setEngineFilter] = React.useState<string>("all");
  const [intentFilter, setIntentFilter] = React.useState<string>("all");

  const [judging, setJudging] = React.useState(false);
  const [judgeError, setJudgeError] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<JudgeStatus | null>(null);

  const scrollTo = React.useCallback((id: string) => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const ctx: SectionContext = React.useMemo(
    () => ({
      report,
      runId,
      clientName: report.client_name,
      brand,
      engineFilter,
      intentFilter,
      setEngineFilter,
      setIntentFilter,
      onSeeAllFindings: () => scrollTo("findings"),
    }),
    [report, runId, brand, engineFilter, intentFilter, scrollTo],
  );

  const sections = React.useMemo(() => sectionsForTier(tier), [tier]);

  // Warm status of the notebooks (query answers + on-site content checks): tells
  // the user whether Judge will be free (all pre-judged on the subscription) or
  // still hit the API.
  const refreshStatus = React.useCallback(() => {
    if (!runId) return;
    fetchJudgeStatus(runId)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [runId]);
  React.useEffect(refreshStatus, [refreshStatus]);

  const allWarm =
    !!status &&
    (status.query.total === 0 || status.query.warm) &&
    (status.content.total === 0 || status.content.warm);

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

  const downloadAnswers = (ext: "results.csv" | "answers.md") => {
    if (!runId) return;
    void downloadAudit(runId, ext);
  };

  // THE CLIENT PDF COMES FROM THE WORKER, NOT FROM `window.print()`.
  //
  // Both buttons used to call `window.print()`, which renders this route in
  // SCREEN mode — no `?mode=print`, so no navy cover (`CoverSection` returns
  // null off-print), the workbench header printed with the Judge and Export
  // buttons in it, and no running header, page numbers or per-page independence
  // footer, because those are the worker's Playwright templates. That is not the
  // deliverable; it is a screenshot of the workbench.
  //
  // It is a server round-trip through headless Chromium, so it takes tens of
  // seconds on a report with a long citation ledger — hence the pending state.
  const [pdfBusy, setPdfBusy] = React.useState(false);
  const [pdfNote, setPdfNote] = React.useState<string | null>(null);
  const buildPdf = async () => {
    if (!runId || pdfBusy) return;
    setPdfBusy(true);
    setPdfNote(null);
    try {
      const how = await downloadReportPdf(runId);
      if (how === "print-page") {
        setPdfNote(
          "Chromium isn't installed on the API host, so the print-ready report opened in a new " +
            "tab instead — print it from there with Cmd-P.",
        );
      }
    } catch (e) {
      setPdfNote(e instanceof Error ? e.message : "The PDF did not build.");
    } finally {
      setPdfBusy(false);
    }
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
      {runId && (
        <Button
          variant="outline"
          onClick={() => void buildPdf()}
          disabled={pdfBusy}
          title="Build the client PDF on the server — cover page, running header, page numbers"
        >
          {pdfBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Printer className="h-4 w-4" aria-hidden />
          )}
          {pdfBusy ? "Building…" : "Export PDF"}
        </Button>
      )}
    </>
  );

  return (
    <div className={brand.themeClass}>
      {/* The rail carries the report's own table of contents, built from the
          registry — so a reordered report reorders its own navigation. Rendered
          through a portal into the shell, which is `no-print`. */}
      <SidebarSlot slot="sections">
        <SidebarLabel>Sections</SidebarLabel>
        <div className="flex flex-col gap-px">
          {sections
            .filter((s) => s.inToc)
            .map((s) => (
              <SidebarRow
                key={s.id}
                active={activeSection === s.id}
                count={
                  s.id === "findings" ? (report.finding_groups?.length ?? 0) : undefined
                }
                onClick={() => scrollTo(s.id)}
              >
                {s.title}
              </SidebarRow>
            ))}
        </div>
      </SidebarSlot>
      {/* The rail's Build PDF and the header's Export PDF are ONE action, and
          both go through the worker. A shared viewer has no runId and so gets
          neither — by design: they get the report and nothing that spends
          server time, and the sender is the one who exports the deliverable. */}
      {runId && (
        <SidebarSlot slot="footer">
          <button
            type="button"
            onClick={() => void buildPdf()}
            disabled={pdfBusy}
            className="h-[34px] w-full rounded-full bg-white text-[12px] font-semibold text-navy transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {pdfBusy ? "Building…" : "Build PDF"}
          </button>
        </SidebarSlot>
      )}

      <Page className="gap-[22px]">
        {/* WORKBENCH CHROME, AND THE COVER IS THE FIRST PAGE.
            Belt and braces: `isPrint` already drops this at `?mode=print`, which
            is the only way the client PDF is built, but `no-print` also covers a
            Cmd-P on the live page. A deliverable whose first page is the app's
            own title block with a Judge button in it is a screenshot of the
            workbench, not a report. */}
        {isPrint ? null : (
          <div className="no-print">
            <PageHeader
              eyebrow={`Report · ${report.run_date}`}
              title={report.client_name}
              href={report.client_domains[0] ? `https://${report.client_domains[0]}` : undefined}
              hrefLabel={report.client_domains[0]}
              actions={headerActions}
            />
          </div>
        )}

        {/* The instrument, in one line — everything a reader needs to know a
            number here is comparable to a number in the last cycle.
            `no-print` because METHODOLOGY ALREADY SAYS ALL OF IT, at length and
            in sentences ("We asked 4 AI surfaces the csv-… question set — 10
            questions, 1 independent time each…"), and the competitor chips are
            restated by the competitive-position table. Printed here it was
            duplicate copy sitting ABOVE the navy cover, which is the one thing
            page 1 of the deliverable is supposed to open on. */}
        <div className="no-print flex flex-wrap items-center gap-x-2 gap-y-1.5 text-[13px] text-[color:var(--ink-secondary)]">
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
            {/* The raw-data trapdoor: the exports an analyst uses to check our
                arithmetic. Re-judge and Export live in the page header. */}
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
                <>
                  {" "}
                  · content {status.content.cached}/{status.content.total}
                </>
              ) : null}
              {" — "}
              {allWarm ? (
                <span className="font-medium text-blue">warm, Judge is $0</span>
              ) : (
                <>
                  not fully warm; <code>/prejudge {runId.slice(0, 8)}</code> in Claude Code to
                  make it free.
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

        {/* The PDF build is a server round-trip that can fail or degrade, and a
            button that goes quiet for forty seconds and then does nothing is
            indistinguishable from a broken one. */}
        {pdfNote && (
          <Notice tone="problem" className="no-print">
            {pdfNote}
          </Notice>
        )}

        {/* THE REPORT. Every section, in registry order, each falling back to a
            statement rather than an empty box when it has nothing to show. */}
        {sections.map((section) => (
          <div key={section.id} id={section.id} className="scroll-mt-6">
            {section.hasData(ctx) ? section.render(ctx) : section.thinDataFallback(ctx)}
          </div>
        ))}

        {/* On-site & off-site audit (technique checklist Cat 1–6). Not part of
            the answer report's contract — it is a different measurement of a
            different thing — so it hangs off the end rather than claiming a
            section number. */}
        {report.site_audit?.present && <SiteAuditSection siteAudit={report.site_audit} />}
      </Page>
    </div>
  );
}

/** Exported so the packaging test can assert the rendered order matches the
 * registry without booting a browser. */
export const RENDERED_SECTION_IDS = REPORT_SECTIONS.map((s) => s.id);
