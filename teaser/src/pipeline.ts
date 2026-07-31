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
import {
  attachLocalCompetitors,
  businessKindOf,
} from "./resolver/profileExtraction.ts";
import type { Resolver } from "./resolver/Resolver.ts";
import { selectFindings } from "./select/selectFindings.ts";
import {
  ctaLine,
  headline,
  leadSentence,
  stakesLine,
} from "./render/copy.ts";
import { canonicalLocation } from "./types/domain.ts";
import type {
  CompanyProfile,
  FactClaimRow,
  GeneratedQuerySet,
  TeaserDraft,
} from "./types/domain.ts";
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
  /**
   * Optional web-search guard run right after resolution: drops competitors that
   * are corporately entangled with the client (acquired it, were acquired by it,
   * or are the same company) BEFORE they seed queries or reach the confirm gate.
   * Returns the (possibly pruned) profile. Recall-safe — never throws.
   */
  relationshipCheck?: (profile: CompanyProfile) => Promise<CompanyProfile>;
}

export const DEFAULT_OPTIONS: PipelineOptions = {
  // Engine names must match the platform's KNOWN_ENGINES (src/prompts/csv_loader.py).
  //
  // Changed 2026-07-28, and kept BYTE-IDENTICAL to DEFAULT_ENGINES in
  // web/app/teaser/page.tsx — the two entry points previously disagreed
  // (openai_search+gemini_grounded here vs openai+google_ai_overviews there), so the
  // same prospect cost ~2x more through the CLI than through the UI and was measured on
  // different surfaces. Whichever door a teaser comes through, it must be the same
  // instrument.
  //
  // openai_search is out: OpenAI's 6,000 TPM search-class cap against ~17,200 tokens per
  // answer means it returns nothing (0 of 10 cells, measured twice). `openai` is the
  // parametric surface (gpt-5.6-luna) at ~100% coverage for ~$0.0015/call.
  engines: ["perplexity", "openai", "google_ai_mode"],
  // Repeat every query so a printed claim can be shown to REPRODUCE, not rest on
  // a single nondeterministic sample. Engine answers vary run-to-run; a prospect
  // who re-asks the query must see the same loss. Selection then prefers findings
  // that hold across all runs (see selectFindings reproducibility). 3 is the
  // smallest set that shows a stable majority; --runs overrides it.
  runsPerQuery: 3,
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

  // 1a. LOCAL ONLY: source competitors from Google's local pack, never from model
  //     recall. Claude does not reliably know the plumbers in a given city, so a
  //     resolver-extracted "competitor" for a local business is typically a national
  //     franchise or an invention — and a fabricated rival in a teaser emailed to a
  //     real shop owner is the one failure that survives human review. This is why
  //     attachLocalCompetitors throws rather than degrade when nothing was captured.
  if (businessKindOf(profile) === "local_service") {
    if (!profile.location) {
      return {
        ok: false,
        stage: "resolve",
        reason:
          `${url} is a local service-area business but no location was read from the ` +
          `site. Competitors must come from a location-pinned local pack; an unpinned ` +
          `capture names businesses in the wrong metro.`,
      };
    }
    const market = canonicalLocation(profile.location);
    const entities = await deps.platform.getLocalEntities(
      `best ${profile.category} in ${profile.location.city}`,
      market,
    );
    // [] means the query genuinely surfaced no pack — distinct from a capture
    // failure, which throws. Either way attachLocalCompetitors refuses to invent.
    profile = attachLocalCompetitors(profile, entities);
  }

  // 1b. Relationship guard: drop competitors corporately tied to the client
  //     (acquisitions/mergers the resolver LLM couldn't know) before they seed
  //     queries. Runs pre-confirm so the human reviews an already-clean list.
  if (opts.relationshipCheck) {
    profile = await opts.relationshipCheck(profile);
  }

  // 2. Generate the teaser-grade query set, capped to the leanest N (by weight)
  //    when maxQueries is set — a teaser needs only enough queries to surface a
  //    losing one, not a full audit's breadth.
  let querySet = await deps.querySetGenerator.generate(profile);
  // A teaser measures UNPROMPTED surfacing, so drop brand-intent queries. They
  // NAME the client (rule 1 in the generator), which makes the client trivially
  // "present" — inflating its headline count and category bar while never
  // yielding a losing-query finding (the client can't be absent from a query
  // that names it). Keep the neutral buyer queries. Guard the degenerate
  // all-brand set so we never submit an empty audit. (The full paid audit keeps
  // brand queries — brand visibility is a real signal there; this is teaser-only.)
  const nonBrandQueries = querySet.queries.filter((q) => q.intent !== "brand");
  if (nonBrandQueries.length > 0) {
    querySet = { ...querySet, queries: nonBrandQueries };
  }
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
  //    The CSV is the ONLY transport for the fact sheet — AuditInput's other fields
  //    are the parsed essentials the mock re-synthesizes from, and the real client
  //    ignores them. Since the rows ride on the profile, anything the confirm gate
  //    edits (or drops) reaches the platform exactly as the human left it.
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
    runsPerQuery: opts.runsPerQuery,
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
  opts: { status?: TeaserDraft["status"] } = {},
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
    // The headline names the LEAD's competitor (not the scorecard's top
    // competitor) so the headline, headline number, and proof card all tell
    // one story about one rival — and so its "sending your buyers to" claim
    // is graded by the same judge prominence that backs the lead.
    headline: headline(profile.name, selection.lead),
    leadSentence: leadSentence(profile.name, selection.lead),
    headlineNumber: selection.headline,
    stakesLine: stakesLine(profile.name, selection.headline),
    cta: ctaLine(profile.name),
    lead: selection.lead,
    table: selection.table,
    accuracyFindings: selection.accuracyFindings,
    report,
    answers,
    // Persist the resolved aliases so a regeneration from storage matches by
    // alias too (T3) — the stored report carries only names.
    clientAliases: profile.aliases ?? [],
    competitorAliases: Object.fromEntries(
      profile.competitors.map((c) => [c.name, c.aliases]),
    ),
    // Persist the sheet this run was measured against (C8). Spread rather than
    // `?? []` so "no sheet" stays distinguishable from "an empty sheet" — the two
    // produce the same CSV, but only the first means nobody has extracted one yet.
    ...(profile.factClaims ? { factClaims: profile.factClaims } : {}),
    // Fresh runs are drafts; regeneration preserves the saved status so a
    // re-render of an already-approved teaser stays clean (no draft banner).
    status: opts.status ?? "draft",
  };
  return { ok: true, draft };
}

/**
 * Reconstruct the minimal CompanyProfile that selection/assembly needs, from a
 * stored run's report (+ the draft's category/url). No crawl. Client/competitor
 * aliases and the fact sheet are rehydrated from the saved draft when present (T3,
 * C8) — the stored ReportPayload itself carries only names and the flags the sheet
 * produced, so a draft saved before those fields were persisted (or a run that had
 * neither) falls back to name-only matching and no sheet.
 */
export function profileFromStored(
  report: ReportPayload,
  opts: {
    url: string;
    category: string;
    clientAliases?: string[];
    competitorAliases?: Record<string, string[]>;
    factClaims?: FactClaimRow[];
  },
): CompanyProfile {
  const competitorAliases = opts.competitorAliases ?? {};
  return {
    url: opts.url,
    name: report.client_name,
    aliases: opts.clientAliases ?? [],
    category: opts.category,
    competitors: report.competitors.map((name) => ({
      name,
      aliases: competitorAliases[name] ?? [],
      confirmed: true,
    })),
    clientDomains: report.client_domains,
    productClaims: [],
    // productClaims stay empty (the report never carried them), but the fact sheet
    // rides back on so a regenerated teaser measures against the same reference the
    // stored flags were graded from.
    ...(opts.factClaims ? { factClaims: opts.factClaims } : {}),
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
    clientAliases: saved.clientAliases,
    competitorAliases: saved.competitorAliases,
    factClaims: saved.factClaims,
  });
  return assembleDraft(profile, saved.report, saved.answers, saved.prospectUrl, {
    status: saved.status,
  });
}
