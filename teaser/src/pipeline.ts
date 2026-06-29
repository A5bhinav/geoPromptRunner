/**
 * The teaserAuto pipeline: URL -> reviewable TeaserDraft.
 *
 * Orchestrates the lifecycle in BUILD_PLAN.md §1.3:
 *   resolve -> generate query set -> (optional confirm) -> submit -> poll
 *   -> fetch report + answers -> select findings -> assemble draft.
 *
 * Every external service is injected (Deps) so this runs identically against
 * mocks or real adapters. Pure orchestration; no I/O of its own beyond the deps.
 */

import type { PlatformClient } from "./platform/PlatformClient.ts";
import { buildAuditCsv } from "./platform/csv.ts";
import type { QuerySetGenerator } from "./queryset/QuerySetGenerator.ts";
import type { Resolver } from "./resolver/Resolver.ts";
import { selectFindings } from "./select/selectFindings.ts";
import {
  ctaLine,
  headline,
  leadSentence,
  stakesLine,
} from "./render/copy.ts";
import type { CompanyProfile, GeneratedQuerySet, TeaserDraft } from "./types/domain.ts";
import type { AnswerRecord, ReportPayload, RunStatus } from "./types/platform.ts";

export interface PipelineDeps {
  resolver: Resolver;
  querySetGenerator: QuerySetGenerator;
  platform: PlatformClient;
}

export interface PipelineOptions {
  engines: string[];
  runsPerQuery: number;
  judge: boolean;
  /**
   * Cap the generated query set to the highest-weight N queries — a teaser audit
   * is deliberately smaller (and cheaper/faster) than a full platform audit.
   * 0/undefined = use the whole generated set.
   */
  maxQueries?: number;
  /** Max status polls before giving up. */
  maxPolls: number;
  /** ms between polls (0 in tests/mock). */
  pollIntervalMs: number;
  /**
   * Optional human confirm gate over the resolved profile + generated queries.
   * Return the (possibly edited) profile/querySet to proceed, or null to abort.
   */
  confirm?: (
    profile: CompanyProfile,
    querySet: GeneratedQuerySet,
  ) => Promise<{ profile: CompanyProfile; querySet: GeneratedQuerySet } | null>;
}

export const DEFAULT_OPTIONS: PipelineOptions = {
  // Engine names must match the platform's KNOWN_ENGINES (src/prompts/csv_loader.py).
  engines: ["perplexity", "google_ai_overviews", "openai"],
  runsPerQuery: 1,
  judge: true,
  maxPolls: 60,
  pollIntervalMs: 0,
};

export type PipelineResult =
  | { ok: true; draft: TeaserDraft }
  | { ok: false; stage: string; reason: string };

const delay = (ms: number) => (ms > 0 ? new Promise((r) => setTimeout(r, ms)) : Promise.resolve());

async function pollUntilDone(
  platform: PlatformClient,
  runId: string,
  opts: PipelineOptions,
): Promise<RunStatus> {
  let last: RunStatus | null = null;
  for (let i = 0; i < opts.maxPolls; i++) {
    last = await platform.getStatus(runId);
    if (last.state === "done" || last.state === "failed" || last.state === "cancelled") {
      return last;
    }
    await delay(opts.pollIntervalMs);
  }
  if (last) return last;
  throw new Error("no status returned");
}

export async function runTeaserPipeline(
  url: string,
  deps: PipelineDeps,
  options: Partial<PipelineOptions> = {},
): Promise<PipelineResult> {
  const opts: PipelineOptions = { ...DEFAULT_OPTIONS, ...options };

  // 1. Resolve URL -> company profile.
  let profile = await deps.resolver.resolve(url);

  // 2. Generate the teaser-grade query set, capped to the leanest N (by weight)
  //    when maxQueries is set — a teaser needs only enough queries to surface a
  //    losing one, not a full audit's breadth.
  let querySet = await deps.querySetGenerator.generate(profile);
  if (opts.maxQueries && opts.maxQueries > 0 && querySet.queries.length > opts.maxQueries) {
    const leanest = [...querySet.queries]
      .sort((a, b) => b.weight - a.weight)
      .slice(0, opts.maxQueries);
    querySet = { ...querySet, queries: leanest };
  }

  // 2b. Optional human confirm gate (competitors are the risky output).
  if (opts.confirm) {
    const confirmed = await opts.confirm(profile, querySet);
    if (!confirmed) return { ok: false, stage: "confirm", reason: "aborted at confirm gate" };
    profile = confirmed.profile;
    querySet = confirmed.querySet;
  }

  // 3. Submit the audit to the platform.
  const csv = buildAuditCsv(profile, querySet, {
    engines: opts.engines,
    runsPerQuery: opts.runsPerQuery,
    judge: opts.judge,
  });
  const { runId } = await deps.platform.submitAudit({
    csv,
    clientName: profile.name,
    clientDomains: profile.clientDomains,
    competitors: profile.competitors.map((c) => c.name),
    category: profile.category,
    engines: opts.engines,
    queries: querySet.queries.map((q) => ({ query_id: q.query_id, text: q.text, intent: q.intent })),
  });

  // 4. Poll to completion.
  const status = await pollUntilDone(deps.platform, runId, opts);
  if (status.state !== "done") {
    return { ok: false, stage: "audit", reason: `audit ${status.state}: ${status.error ?? ""}` };
  }

  // 5. Fetch report + verbatim answers.
  const [report, answers] = await Promise.all([
    deps.platform.getReport(runId),
    deps.platform.getAnswers(runId),
  ]);

  // 6-7. Select findings + assemble the draft (shared with regeneration).
  return assembleDraft(profile, report, answers, url);
}

/**
 * Steps 6-7 — select findings and assemble the draft from a report + verbatim
 * answers. Pure (no I/O). Shared by the live pipeline and `regenerateFromDraft`,
 * so a regenerated teaser gets the exact same selection + copy as a fresh run.
 */
export function assembleDraft(
  profile: CompanyProfile,
  report: ReportPayload,
  answers: AnswerRecord[],
  prospectUrl: string,
): PipelineResult {
  const selection = selectFindings(profile, report, answers);
  if (!selection.ok) {
    return { ok: false, stage: "select", reason: selection.reason };
  }
  const draft: TeaserDraft = {
    prospectUrl,
    companyName: profile.name,
    category: profile.category,
    runDate: report.run_date,
    heroEngine: selection.heroEngine,
    headline: headline(profile.name, report.scorecard.top_competitor ?? selection.lead.competitor),
    leadSentence: leadSentence(profile.name, selection.lead),
    headlineNumber: selection.headline,
    stakesLine: stakesLine(profile.name, selection.headline),
    cta: ctaLine(profile.name),
    lead: selection.lead,
    table: selection.table,
    report,
    answers,
    status: "draft",
  };
  return { ok: true, draft };
}

/**
 * Reconstruct the minimal CompanyProfile that selection/assembly needs, from a
 * stored run's report (+ the draft's category/url). No crawl — competitor
 * aliases aren't stored, so they fall back to []; selection still matches on the
 * competitor names the report already carries (only alias-only mentions are
 * missed, a small precision cost vs. re-running the whole audit).
 */
export function profileFromStored(
  report: ReportPayload,
  opts: { url: string; category: string },
): CompanyProfile {
  return {
    url: opts.url,
    name: report.client_name,
    category: opts.category,
    competitors: report.competitors.map((name) => ({ name, aliases: [], confirmed: true })),
    clientDomains: report.client_domains,
    productClaims: [],
    resolvedAt: "",
    resolverModel: "regenerated-from-storage",
  };
}

/**
 * Regenerate a fresh draft from a previously-saved teaser, reusing its stored
 * report + verbatim answers — applies the CURRENT selection logic and copy with
 * ZERO engine calls (no resolve, no submit, no runner). This is how teaser
 * improvements reach already-run prospects without paying to re-run the audit.
 */
export function regenerateFromDraft(saved: TeaserDraft): PipelineResult {
  if (!saved.report || !Array.isArray(saved.answers)) {
    return {
      ok: false,
      stage: "select",
      reason: "saved teaser has no stored report/answers to regenerate from",
    };
  }
  const profile = profileFromStored(saved.report, {
    url: saved.prospectUrl,
    category: saved.category,
  });
  return assembleDraft(profile, saved.report, saved.answers, saved.prospectUrl);
}
