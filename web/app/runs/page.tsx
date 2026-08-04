"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ChevronRight,
  ClipboardCheck,
  FileText,
  Gavel,
  Loader2,
  Play,
  ShieldCheck,
  Wand2,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { Page, PageHeader, Panel, CardLabel, Chip, StatStrip } from "@/components/page";
import { SegmentedBar, type Segment } from "@/components/marks";
import { INPUT_CLS } from "@/lib/ui";
import { cn } from "@/lib/utils";
import { UploadDropzone } from "@/components/upload-dropzone";
import { PreviewPanels } from "@/components/preview-panels";
import { RecentAudits } from "@/components/recent-audits";
import { INTENT_LABELS } from "@/components/badges";
import {
  createAudit,
  previewAudit,
  getSheetQuerySet,
  listFactSheets,
  type ParsePreview,
  type FactSheetSummary,
} from "@/lib/api";

/** Funnel order, cold → warm, then the off-funnel band, then the unset one.
 * This is the ONLY order this bar is ever drawn in: the ramp encodes the
 * ordinal axis, so re-sorting by count would make the tones meaningless. */
const FUNNEL_ORDER = [
  "problem_aware",
  "category",
  "comparison",
  "brand",
  "adjacent_authority",
] as const;

function RunWorkbench() {
  const router = useRouter();
  // The Start screen hands a sheet over by id. Reading it here is what makes
  // "approve, then run it" one gesture instead of a re-pick.
  const handedOver = useSearchParams().get("sheet");
  const [files, setFiles] = React.useState<File[]>([]);
  const [preview, setPreview] = React.useState<ParsePreview | null>(null);
  const [previewing, setPreviewing] = React.useState(false);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Approved sheets only. A draft is not ground truth — approval is the gate —
  // and the API refuses one anyway, so offering it here would only produce a 422.
  const [sheets, setSheets] = React.useState<FactSheetSummary[]>([]);
  const [factSheetId, setFactSheetId] = React.useState<string | null>(handedOver);
  const [pickingSheet, setPickingSheet] = React.useState(false);
  const [showParsed, setShowParsed] = React.useState(false);
  // The question set that came with the chosen sheet. Loaded, not uploaded: the
  // intake already generated and linted it, and making someone re-upload the
  // file it produced is asking them to carry it between two screens by hand.
  const [sheetCsv, setSheetCsv] = React.useState<string>("");
  const [sheetQueryCount, setSheetQueryCount] = React.useState(0);

  React.useEffect(() => {
    listFactSheets("active")
      .then(setSheets)
      .catch(() => setSheets([]));
  }, []);

  React.useEffect(() => {
    if (files.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewing(true);
    setError(null);
    previewAudit(files)
      .then((p) => !cancelled && setPreview(p))
      .catch(() => !cancelled && setError("Could not reach the API. Is the backend running?"))
      .finally(() => !cancelled && setPreviewing(false));
    return () => {
      cancelled = true;
    };
  }, [files]);

  // Picking an approved sheet loads ITS question set and makes it the run's
  // source. It enters as a normal File so it goes through the same preview,
  // validation and cost guard a hand-made CSV does — an assembled run and an
  // uploaded one should be the same thing by the time they reach validation.
  React.useEffect(() => {
    if (!factSheetId) {
      setSheetCsv("");
      setSheetQueryCount(0);
      return;
    }
    let cancelled = false;
    getSheetQuerySet(factSheetId)
      .then((set) => {
        if (cancelled || !set.csv) return;
        setSheetCsv(set.csv);
        setSheetQueryCount(set.queries.length);
        const name = `${set.fact_sheet_id.slice(0, 8)}-questions.csv`;
        setFiles([new File([set.csv], name, { type: "text/csv" })]);
      })
      .catch(() => {
        if (cancelled) return;
        // A sheet approved before the intake existed has no stored set. That is
        // not an error — it just means this run needs a CSV like it always did.
        setSheetCsv("");
        setSheetQueryCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [factSheetId]);

  const addFiles = (incoming: File[]) =>
    setFiles((prev) => {
      const byName = new Map(prev.map((f) => [f.name, f]));
      for (const f of incoming) byName.set(f.name, f);
      return Array.from(byName.values());
    });

  const removeFile = (name: string) =>
    setFiles((prev) => prev.filter((f) => f.name !== name));

  const runAudit = async () => {
    setCreating(true);
    setError(null);
    try {
      const res = await createAudit(files, factSheetId);
      if ("run_id" in res) {
        router.push(`/audits/${res.run_id}`);
      } else if ("refused" in res) {
        // The CSV parsed; the SHEET was rejected. Say so as a sentence rather
        // than rendering it as a parse error over the upload.
        setError(res.refused);
      } else {
        setPreview(res.errors);
      }
    } catch {
      setError("Could not start the audit. Is the backend running?");
    } finally {
      setCreating(false);
    }
  };

  const cfg = preview?.config_resolved ?? null;
  const chosenSheet = sheets.find((s) => s.id === factSheetId) ?? null;

  // --- the three numbers -----------------------------------------------------
  const nQuestions = preview?.queries.length ?? 0;
  const nSurfaces = cfg?.engines.length ?? 0;
  const runsPer = cfg?.runs_per_query ?? 0;
  // Calls is questions × surfaces × RUNS PER QUESTION, not questions × surfaces.
  // Repeats are what make a rate reproducible and they are the majority of the
  // spend on any run with runs_per_query > 1 — showing the smaller number here
  // and the real one on the Running screen is how a cost surprise happens.
  const nCalls = nQuestions * nSurfaces * runsPer;

  const funnel: Segment[] = React.useMemo(() => {
    const counts = new Map<string, number>();
    let unset = 0;
    for (const q of preview?.queries ?? []) {
      if (!q.valid_intent) unset += 1;
      else counts.set(q.intent, (counts.get(q.intent) ?? 0) + 1);
    }
    const segs: Segment[] = FUNNEL_ORDER.map((intent) => ({
      label: INTENT_LABELS[intent] ?? intent,
      value: counts.get(intent) ?? 0,
      // adjacent_authority is off the funnel, so it gets the hollow swatch
      // rather than a fifth rung the four-step ramp does not have.
      hollow: intent === "adjacent_authority",
    }));
    // "Unset" is a query whose intent the loader could not validate. It is not a
    // stage — it is a gap in the set — so it is hatched, and its count is inked.
    segs.push({ label: "Unset", value: unset, striped: true });
    return segs;
  }, [preview]);

  const canRun = Boolean(preview?.ok) && !creating;

  return (
    <Page>
      <PageHeader
        eyebrow="New run"
        title={cfg?.client_name || "New run"}
        actions={
          <Button variant="hero" size="lg" onClick={runAudit} disabled={!canRun}>
            {creating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <Play className="h-3.5 w-3.5" aria-hidden />
            )}
            Run audit
          </Button>
        }
      />

      <StatStrip
        stats={[
          { label: "Questions", value: nQuestions || "—" },
          {
            label: "Surfaces",
            value: nSurfaces || "—",
            note: cfg && nSurfaces === 0 ? "every configured engine" : undefined,
          },
          {
            label: "Calls",
            value: nCalls || "—",
            note: nCalls ? `${nQuestions} × ${nSurfaces} surfaces × ${runsPer} runs` : undefined,
          },
        ]}
      />

      {error && <Notice tone="problem">{error}</Notice>}

      {/* Parse errors are the one thing on this screen that must not be a
          disclosure: they are the reason Run audit is disabled. */}
      {preview && preview.errors.length > 0 && (
        <Notice
          tone="problem"
          title={`${preview.errors.length} issue${
            preview.errors.length === 1 ? "" : "s"
          } to fix before running`}
        >
          <ul className="space-y-1">
            {preview.errors.map((e, i) => (
              <li key={i}>
                • {e.file ? <span className="font-medium text-navy">{e.file}: </span> : null}
                {e.message}
              </li>
            ))}
          </ul>
        </Notice>
      )}

      <div className="flex gap-5">
        {/* ------------------------------------------------------ main column */}
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <Panel className="px-5 py-[18px]">
            <CardLabel
              className="mb-3.5"
              note={nQuestions ? `${nQuestions} questions` : undefined}
            >
              Coverage by funnel stage
            </CardLabel>
            {nQuestions === 0 ? (
              <p className="text-[13px] text-harbour">
                Add a CSV and the shape of the question set shows up here.
              </p>
            ) : (
              <SegmentedBar
                segments={funnel}
                ariaLabel={`Question coverage by funnel stage across ${nQuestions} questions`}
              />
            )}
          </Panel>

          <Panel>
            <div className="flex items-center justify-between px-5 pb-3 pt-[18px]">
              <span className="section-label">Sources</span>
              {/* The Start screen, not the queue: a conversation BEGINS there,
                  and the queue only lists what conversations have produced. */}
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 text-[13px] font-medium text-blue hover:underline"
              >
                <Wand2 className="h-4 w-4" aria-hidden /> Build one from a conversation
              </Link>
            </div>
            <div className="flex flex-col gap-2.5 px-5 pb-5">
              {/* "Start from a lead" is GONE. Its five fields — business name,
                  website, trade, city, state — are the intake conversation's
                  opening cards now. Two places to describe one business was one
                  too many: the form could not produce a claim and the chat could
                  not produce a query set, so a client went through both and said
                  the same things twice. */}
              <UploadDropzone
                files={files}
                provenance={preview?.provenance ?? []}
                onAdd={addFiles}
                onRemove={removeFile}
              />

              {/* The fact sheet is a SOURCE, and it belongs in the same list as
                  the CSVs — it is the thing every accuracy finding is measured
                  against, and burying it in a rail made it easy to start a run
                  without one. */}
              {chosenSheet ? (
                <div className="flex items-center gap-3 rounded-md border border-[var(--rule)] px-3.5 py-2.5 text-[13px]">
                  <ClipboardCheck className="h-4 w-4 shrink-0 text-harbour" aria-hidden />
                  <span className="font-medium">
                    Fact sheet v{chosenSheet.version}
                  </span>
                  <span className="truncate text-harbour">
                    {chosenSheet.business_name || chosenSheet.domain} · approved
                  </span>
                  <button
                    type="button"
                    onClick={() => setPickingSheet((v) => !v)}
                    className="ml-auto text-[12px] text-blue hover:underline"
                  >
                    Change
                  </button>
                </div>
              ) : null}

              {chosenSheet && sheetCsv ? (
                <div className="flex items-center gap-3 rounded-md border border-[var(--rule)] px-3.5 py-2.5 text-[13px]">
                  <FileText className="h-4 w-4 shrink-0 text-harbour" aria-hidden />
                  <span className="font-medium">Question set</span>
                  <span className="truncate text-harbour">
                    generated with the sheet · {sheetQueryCount} question
                    {sheetQueryCount === 1 ? "" : "s"}
                  </span>
                </div>
              ) : null}

              {(!chosenSheet || pickingSheet) && sheets.length > 0 ? (
                <label className="block">
                  <span className="sr-only">Fact sheet</span>
                  <select
                    className={INPUT_CLS}
                    value={factSheetId ?? ""}
                    onChange={(e) => {
                      setFactSheetId(e.target.value || null);
                      setPickingSheet(false);
                    }}
                  >
                    <option value="">
                      No fact sheet — use the CSV&apos;s fact rows
                    </option>
                    {sheets.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.business_name || s.domain} — v{s.version} · {s.domain}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              {sheets.length === 0 ? (
                <p className="text-[11px] text-harbour">
                  No approved fact sheet yet.{" "}
                  <Link href="/fact-sheets" className="text-blue hover:underline">
                    Build one
                  </Link>{" "}
                  and accuracy findings can flag at any severity.
                </p>
              ) : null}
            </div>
          </Panel>

          {previewing && !preview && (
            <div className="flex items-center gap-2 text-[13px] text-[color:var(--ink-secondary)]">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Parsing…
            </div>
          )}

          {/* The design deliberately has no questions table on this screen — the
              funnel bar IS the question set. The parsed detail stays reachable
              because it is how a bad CSV gets diagnosed, but it opens on
              request rather than pushing the run controls off the fold. */}
          {preview && (
            <div>
              <button
                type="button"
                onClick={() => setShowParsed((v) => !v)}
                aria-expanded={showParsed}
                className="inline-flex items-center gap-1.5 text-[13px] font-medium text-blue hover:underline"
              >
                <ChevronRight
                  className={cn("h-4 w-4 transition-transform", showParsed && "rotate-90")}
                  aria-hidden
                />
                {showParsed ? "Hide the parsed set" : "Review the parsed set"}
              </button>
              {showParsed ? (
                <div className="mt-3">
                  <PreviewPanels preview={preview} />
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* -------------------------------------------------------- right rail */}
        <div className="flex w-[300px] shrink-0 flex-col gap-4">
          <Panel className="flex flex-col gap-3.5 px-5 py-[18px]">
            <span className="text-[14px] font-medium">Settings</span>

            <div>
              <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.24em] text-harbour">
                Surfaces
              </p>
              {cfg && cfg.engines.length > 0 ? (
                <div className="grid grid-cols-2 gap-1.5">
                  {cfg.engines.map((e) => (
                    <span
                      key={e}
                      className="inline-flex items-center gap-[7px] rounded-md bg-navy/[0.06] px-2.5 py-1.5 text-[12.5px]"
                    >
                      <span aria-hidden className="h-[7px] w-[7px] rounded-full bg-navy" />
                      <span className="truncate">{e}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-[12.5px] text-harbour">
                  {cfg ? "Every configured engine." : "Set by the CSV’s config block."}
                </p>
              )}
            </div>

            <div>
              <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.24em] text-harbour">
                Competitors
              </p>
              {cfg && cfg.competitors.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {cfg.competitors.map((c) => (
                    <Chip key={c}>{c}</Chip>
                  ))}
                </div>
              ) : (
                // No "+ add" chip: competitors come from the CSV config block and
                // there is nothing here that could write one back. A control that
                // does nothing is worse than the absence of a control.
                <p className="text-[12.5px] text-harbour">
                  Set by the CSV’s <code className="text-[11.5px]">competitors</code> row.
                </p>
              )}
            </div>
          </Panel>

          <Panel className="flex flex-col gap-3 px-5 py-[18px]">
            <span className="text-[14px] font-medium">Pre-flight</span>
            <PreflightRow
              Icon={ShieldCheck}
              on={Boolean(factSheetId)}
              text={
                factSheetId
                  ? "Fact sheet attached"
                  : "No fact sheet — accuracy stays unassessed"
              }
            />
            <PreflightRow
              Icon={Gavel}
              on={cfg?.judge ?? false}
              text={cfg?.judge ? "Judge on" : "Judge off — answers only"}
            />
            <PreflightRow
              Icon={Workflow}
              on={Boolean(cfg && cfg.client_domains.length > 0)}
              text={
                cfg && cfg.client_domains.length > 0
                  ? "Site crawl queued"
                  : "No client domain — site audit skipped"
              }
            />
          </Panel>
        </div>
      </div>

      <RecentAudits />
    </Page>
  );
}

/** A pre-flight line. Harbour + a Harbour glyph is "not going to happen"; navy
 * is "will happen". No tick/cross pair — the sentence carries the state, and a
 * cross in a palette with no alert hue reads as an error rather than an
 * absence. */
function PreflightRow({
  Icon,
  on,
  text,
}: {
  Icon: typeof ShieldCheck;
  on: boolean;
  text: string;
}) {
  return (
    <div className={cn("flex items-center gap-2.5 text-[13px]", !on && "text-harbour")}>
      <Icon className="h-[15px] w-[15px] shrink-0" aria-hidden />
      <span>{text}</span>
    </div>
  );
}

/**
 * `useSearchParams` opts a route out of static prerendering unless it sits
 * inside a Suspense boundary. The boundary is cheap and the fallback is the
 * page's own empty state, so a cold load looks like a loading page rather than
 * a blank one.
 */
export default function RunPage() {
  return (
    <React.Suspense
      fallback={
        <Page>
          <p className="text-[13px] text-[color:var(--ink-secondary)]">Loading…</p>
        </Page>
      }
    >
      <RunWorkbench />
    </React.Suspense>
  );
}
