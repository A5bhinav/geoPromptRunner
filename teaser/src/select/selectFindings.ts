/**
 * Lead-finding selection — ranks the platform's losing_queries to pick the hero
 * finding + 2 pattern-table rows, and computes the headline number.
 *
 * Lead rule: the most persuasive DEMAND-SIDE loss. A buyer asking for the
 * client's category ("best <category>") or describing its problem — and getting
 * a competitor — is a cleaner, harder-to-dismiss hook than a head-to-head
 * between two rivals the buyer named themselves (where a third brand not
 * appearing is a much higher bar). So the LEAD ranks by `leadScore`
 * (category/problem_aware weighted above comparison), engine credibility breaking
 * ties. The PATTERN TABLE still favors high-commercial-intent comparison rows
 * (`scoreRow`), so the head-to-heads corroborate the lead instead of fronting it.
 * The hero engine follows the lead (its engine), keeping the proof card + headline
 * on one engine; the table is the next 2 DISTINCT queries (not cherry-picked).
 *
 * Deterministic and pure — no clocks, no randomness. This is teaserAuto's IP.
 */

import type {
  CompanyProfile,
  Finding,
  HeadlineNumber,
} from "../types/domain.ts";
import type {
  AnswerRecord,
  IntentBucket,
  LosingRow,
  ReportPayload,
  SiteAuditPayload,
} from "../types/platform.ts";
import { buildMatcher } from "./entity.ts";
import { answerSnippet } from "../render/proofCard.ts";

/**
 * Commercial-intent priority — used to rank the PATTERN TABLE rows (comparison
 * is bottom-funnel and the strongest corroboration).
 */
const INTENT_PRIORITY: Record<IntentBucket, number> = {
  comparison: 5,
  category: 4,
  problem_aware: 3,
  adjacent_authority: 2,
  brand: 1,
  // Local: "best plumber in Berkeley" is the local equivalent of a comparison — it
  // returns a ranked set of named rivals, which is what corroborates the pattern.
  local_intent: 5,
  hybrid: 4,
  informational: 3,
};

/**
 * LEAD priority — favors demand-side queries where the buyer is open and the
 * client's absence is unambiguous (category > problem_aware), over comparison
 * queries that name rivals (a weaker hook for the hero slot). Comparisons still
 * dominate the table via INTENT_PRIORITY.
 */
const LEAD_INTENT_PRIORITY: Record<IntentBucket, number> = {
  category: 5,
  problem_aware: 4,
  comparison: 3,
  adjacent_authority: 2,
  brand: 1,
  // For the HERO slot local_intent still leads: unlike the consumer case there is no
  // "names a rival in the question" weakness to discount — "best plumber in Berkeley"
  // is a neutral, open question whose answer simply omits the client.
  local_intent: 5,
  hybrid: 4,
  informational: 2,
};

/** Engine credibility for hero selection + scoring (BUILD_PLAN.md §4d). */
const ENGINE_CREDIBILITY: Record<string, number> = {
  perplexity: 5,
  ai_overviews: 5,
  google_ai_overviews: 5,
  // Google's conversational answer surface. Rated with AI Overviews — it is the same
  // "what Google's AI tells your customer" claim — and unlike AI Overviews it actually
  // answers local-intent queries, so it is the Google surface most likely to supply the
  // hero finding for a local prospect.
  google_ai_mode: 5,
  openai: 3,
  openai_search: 4,
  gemini: 2,
  gemini_grounded: 3,
  anthropic: 2,
  anthropic_search: 3,
};

/** How the loss held up across the runs captured for one (query, engine) cell. */
export interface Reproduction {
  /** Runs that returned an answer for this cell. */
  observed: number;
  /** Of those, how many showed the loss: client absent AND competitor present. */
  confirming: number;
}

/**
 * Count how many of a cell's runs reproduce the loss, by re-checking the
 * verbatim answers (the same word-boundary matching computeHeadline uses). This
 * is text-based presence, not a re-judge — it verifies the printed claim's
 * backbone (client absent, competitor present) holds run-to-run rather than
 * resting on run 0 alone.
 */
export function countReproduction(
  answers: AnswerRecord[],
  queryId: string,
  engineName: string,
  clientMatch: (text: string) => boolean,
  competitorMatch: (text: string) => boolean,
): Reproduction {
  let observed = 0;
  let confirming = 0;
  for (const a of answers) {
    if (a.query_id !== queryId || a.engine_name !== engineName || !a.response) continue;
    observed++;
    if (!clientMatch(a.response) && competitorMatch(a.response)) confirming++;
  }
  return { observed, confirming };
}

/**
 * True when the loss is safe to call REPEATABLE in copy: it held on every run
 * that returned an answer, and there was more than one such run. A single-run
 * audit (observed ≤ 1) is never "repeatable" — there's nothing to repeat.
 */
export function reproduces(r: Reproduction): boolean {
  return r.observed >= 2 && r.confirming === r.observed;
}

function engineScore(engine: string): number {
  return ENGINE_CREDIBILITY[engine] ?? 1;
}

function scoreRow(row: LosingRow): number {
  // `?? 0` guards against an intent the platform adds that we don't yet weight:
  // without it the lookup is undefined and the whole score becomes NaN, which
  // silently corrupts the sort. Unknown intent ranks last, like unknown engines.
  return (INTENT_PRIORITY[row.intent] ?? 0) * 10 + engineScore(row.engine_name);
}

/**
 * Whether the copy may print "recommends" (and whether selection may boost the
 * row into the hero slot). ONLY an explicit `recommended_first` qualifies — a
 * null/undefined prominence is UNKNOWN, and cold outreach must not print its
 * strongest verb on a claim the judge didn't measure. Defaulting unknown to the
 * weaker claim under-claims at worst, which is the safe direction (the whole
 * teaser philosophy: only claim what the judge measured). This intentionally
 * reverses the old "legacy null == recommends" default (audit finding S7).
 */
export function isRecommendedFirst(prominence: LosingRow["prominence"]): boolean {
  return prominence === "recommended_first";
}

/**
 * A query is UN-WINNABLE for the client when its TEXT pits two or more tracked
 * rivals against each other (an A-vs-B head-to-head) and never names the client.
 * The client was structurally never a candidate, so its absence there is not a
 * loss — printing it produces the "Whoop vs Fitbit, <client> nowhere"
 * embarrassment and inflates the "appears in 0 of N" denominator. Judged on the
 * QUESTION text, not the answer: a category query names 0 rivals; "alternatives
 * to X" names 1 (still winnable — the client should surface); "X vs Y" names 2.
 */
export function isUnwinnableQuery(
  text: string,
  clientMatch: (t: string) => boolean,
  competitorMatchers: ((t: string) => boolean)[],
): boolean {
  if (!text.trim()) return false;
  if (clientMatch(text)) return false; // the client is named → it IS a candidate
  let named = 0;
  for (const m of competitorMatchers) {
    if (m(text)) named++;
    if (named >= 2) return true;
  }
  return false;
}

/** Lead ranking — demand-side intent dominates (×10), engine credibility breaks ties. */
function leadScore(row: LosingRow): number {
  // A recommended-first loss outranks any merely-present loss regardless of
  // intent: the hero slot's copy says "recommends", so the lead must be a row
  // that supports that verb whenever one exists.
  const firstBoost = isRecommendedFirst(row.prominence) ? 100 : 0;
  return firstBoost + (LEAD_INTENT_PRIORITY[row.intent] ?? 0) * 10 + engineScore(row.engine_name);
}

export type SelectionResult =
  | { ok: true; lead: Finding; table: Finding[]; headline: HeadlineNumber; heroEngine: string }
  | { ok: false; reason: string };

export function findAnswer(
  answers: AnswerRecord[],
  queryId: string,
  engineName: string,
  prefer?: (response: string) => boolean,
): AnswerRecord | undefined {
  const cell = answers.filter(
    (a) => a.query_id === queryId && a.engine_name === engineName && a.response,
  );
  // D3: when we can, show a run that actually REPRODUCES the printed loss (client
  // absent, competitor foregrounded) rather than run_index 0 blindly — engine
  // text drifts run-to-run, and the proof quote must back the claim. Pick the
  // lowest run_index among the confirming runs (deterministic). Fall back to
  // run_index 0, then any run.
  if (prefer) {
    const confirming = cell
      .filter((a) => prefer(a.response as string))
      .sort((x, y) => x.run_index - y.run_index);
    if (confirming.length) return confirming[0];
  }
  return cell.find((a) => a.run_index === 0) ?? cell[0];
}

function toFinding(
  row: LosingRow,
  role: "lead" | "table",
  answers: AnswerRecord[],
  repro: Reproduction,
  prefer?: (response: string) => boolean,
): Finding | null {
  const answer = findAnswer(answers, row.query_id, row.engine_name, prefer);
  if (!answer || !answer.response) return null;
  return {
    role,
    source: "losing_query",
    queryId: row.query_id,
    intent: row.intent,
    engineName: row.engine_name,
    competitor: row.competitor,
    prominence: row.prominence ?? null,
    verbatimQuery: answer.prompt,
    verbatimAnswer: answer.response,
    citations: answer.citations,
    rankScore: scoreRow(row),
    runsObserved: repro.observed,
    runsConfirming: repro.confirming,
  };
}

function computeHeadline(
  profile: CompanyProfile,
  answers: AnswerRecord[],
  competitorName: string,
  excludedQueryIds: ReadonlySet<string>,
): HeadlineNumber {
  // Match the client on its name AND any known client aliases, so an answer that
  // names it only by a variant still counts as present — otherwise a real
  // appearance would print as a reproduced loss and understate the headline.
  const clientMatch = buildMatcher(profile.name, profile.aliases ?? []);
  // Feed the competitor's known aliases so an answer that names it only by an
  // alias (e.g. "YNAB" for "You Need A Budget") still counts toward competitorAppears —
  // otherwise the headline understates the gap the teaser exists to show.
  const competitorAliases =
    profile.competitors.find((c) => c.name === competitorName)?.aliases ?? [];
  const competitorMatch = buildMatcher(competitorName, competitorAliases);

  const byQuery = new Map<string, { client: boolean; competitor: boolean }>();
  for (const a of answers) {
    if (!a.response) continue;
    // Denominator is the WINNABLE demand-side set only: brand queries name the
    // client (trivially present) and A-vs-B head-to-heads never had the client as
    // a candidate — counting either inflates "0 of N" and the stakes line (S2/S3).
    if (excludedQueryIds.has(a.query_id)) continue;
    const entry = byQuery.get(a.query_id) ?? { client: false, competitor: false };
    if (clientMatch(a.response)) entry.client = true;
    if (competitorMatch(a.response)) entry.competitor = true;
    byQuery.set(a.query_id, entry);
  }

  let companyAppears = 0;
  let competitorAppears = 0;
  for (const v of byQuery.values()) {
    if (v.client) companyAppears++;
    if (v.competitor) competitorAppears++;
  }
  return {
    companyAppears,
    competitorAppears,
    competitorName,
    n: byQuery.size,
  };
}

export function selectFindings(
  profile: CompanyProfile,
  report: ReportPayload,
  answers: AnswerRecord[],
): SelectionResult {
  if (report.detection !== "judge") {
    return {
      ok: false,
      reason: `detection mode is "${report.detection}" — needs the judge for a printable finding`,
    };
  }
  if (report.losing_queries.length === 0) {
    return { ok: false, reason: "no losing queries — the client is not being left out" };
  }

  // Only rows that name a competitor are printable — the teaser names the rival
  // the client is losing to (BUILD_PLAN.md §7 #8: "with a named competitor").
  const namedRows = report.losing_queries.filter((r) => r.competitor.trim() !== "");
  if (namedRows.length === 0) {
    return { ok: false, reason: "no losing query names a competitor — nothing to print against" };
  }

  // Client is matched on its name AND any known client aliases; competitors feed
  // their own aliases so an alias-only mention still counts.
  const clientMatch = buildMatcher(profile.name, profile.aliases ?? []);
  const competitorMatcher = (name: string) =>
    buildMatcher(name, profile.competitors.find((c) => c.name === name)?.aliases ?? []);
  // One matcher per tracked competitor entity — used to detect A-vs-B queries.
  const competitorMatchers = profile.competitors.map((c) => buildMatcher(c.name, c.aliases));
  // The run to SHOW for a given competitor: one that reproduces the loss (client
  // absent, that competitor present) so the proof card foregrounds the claim.
  const preferFor = (name: string) => (resp: string) =>
    !clientMatch(resp) && competitorMatcher(name)(resp);

  // First question text seen per query — the un-winnable (A-vs-B) test reads the
  // QUESTION, not the answer.
  const promptOf = new Map<string, string>();
  for (const a of answers) {
    if (a.prompt && !promptOf.has(a.query_id)) promptOf.set(a.query_id, a.prompt);
  }

  // The WINNABLE demand-side set: exclude brand-intent queries (they name the
  // client → trivially present) and A-vs-B head-to-heads (the client was never a
  // candidate). Applied to the printable rows AND the headline denominator so
  // selection and the "X of N" number tell one honest story (S1/S2/S3). Brand is
  // already dropped pre-submit in the live pipeline; this also covers regenerate.
  const excludedQueryIds = new Set<string>();
  for (const a of answers) {
    if (
      a.intent === "brand" ||
      isUnwinnableQuery(a.prompt ?? "", clientMatch, competitorMatchers)
    ) {
      excludedQueryIds.add(a.query_id);
    }
  }
  const isExcludedRow = (row: LosingRow): boolean =>
    row.intent === "brand" ||
    excludedQueryIds.has(row.query_id) ||
    isUnwinnableQuery(promptOf.get(row.query_id) ?? "", clientMatch, competitorMatchers);

  const named = namedRows.filter((r) => !isExcludedRow(r));
  if (named.length === 0) {
    return {
      ok: false,
      reason:
        "every losing query is a brand query or an A-vs-B head-to-head where the client was never a candidate — no winnable demand-side loss to print",
    };
  }

  // Reproducibility of each candidate loss across its runs, from the verbatim answers.
  const reproOf = new Map<LosingRow, Reproduction>();
  for (const row of named) {
    reproOf.set(
      row,
      countReproduction(answers, row.query_id, row.engine_name, clientMatch, competitorMatcher(row.competitor)),
    );
  }
  const repro = (row: LosingRow): Reproduction => reproOf.get(row) ?? { observed: 0, confirming: 0 };

  // Honest-hero gate (#2). The headline prints "AI sends your buyers to
  // <competitor>" with an aggregate count beneath it — that story is only true
  // when the competitor is MORE visible than the client across the measured
  // queries. A row whose competitor appears no more often than the client
  // (e.g. client 4/5 vs competitor 3/5 — observed live with Copilot/Mint) would
  // print a headline its own number contradicts, so it cannot be the hero. Note
  // companyAppears is competitor-independent, so this only ever filters OUT rows
  // whose specific competitor the client already matches or beats. Cached per
  // competitor since computeHeadline rescans every answer.
  const headlineCache = new Map<string, HeadlineNumber>();
  const headlineFor = (competitor: string): HeadlineNumber => {
    const hit = headlineCache.get(competitor);
    if (hit) return hit;
    const h = computeHeadline(profile, answers, competitor, excludedQueryIds);
    headlineCache.set(competitor, h);
    return h;
  };
  const heroPool = named.filter((row) => {
    const h = headlineFor(row.competitor);
    return h.competitorAppears > h.companyAppears;
  });
  if (heroPool.length === 0) {
    return {
      ok: false,
      reason:
        "no honest hero: the client appears at least as often as every competitor it loses to — a headline here would contradict its own numbers",
    };
  }

  // Proof-foregrounding gate. The hero's proof card shows only the LEADING PROSE
  // of the answer (answerSnippet) and labels it "<competitor> recommended
  // instead" — so the lead competitor must actually appear in that shown snippet,
  // or the card contradicts itself. This bites when the engine's real top pick is
  // a brand we don't track: prominence is judged only against tracked competitors,
  // so after the relationship guard drops the true leader (e.g. an acquirer/parent
  // like MyFitnessPal for Cal AI), the judge labels the next brand
  // "recommended_first" even though the visible answer recommends the dropped one.
  // Requiring the competitor in the rendered snippet moves the hero to a query
  // where it is genuinely foregrounded. Match exactly what renderProofCard shows.
  const shownInProof = (row: LosingRow): boolean => {
    const a = findAnswer(answers, row.query_id, row.engine_name, preferFor(row.competitor));
    if (!a || !a.response) return false;
    return competitorMatcher(row.competitor)(answerSnippet(a.response));
  };
  const provablePool = heroPool.filter(shownInProof);
  if (provablePool.length === 0) {
    return {
      ok: false,
      reason:
        "no provable hero: in every losing query the shown answer's top recommendation is a brand not in the tracked competitor set (often a dropped acquirer/parent) — the proof card would recommend one brand while the headline names another",
    };
  }

  // Lead = the best cell that joins to a verbatim answer. In a MULTI-RUN audit,
  // reproduction is a GATE, not just a tiebreaker (S6): if any hero-eligible row
  // held on every run, the hero MUST be one of those — a single-run fluke can't
  // become the hero while the copy asserts it as a repeatable fact. Within the
  // eligible pool, leadScore puts a recommended-first, demand-side loss in the
  // hero slot; query_id/engine break ties DETERMINISTICALLY (D4) so equal-ranked
  // findings can't swap on incoming order. The hero engine follows the lead (NOT
  // the globally-most-credible engine), so proof card + headline stay on one engine.
  const multiRun = provablePool.some((r) => repro(r).observed >= 2);
  const reproducingPool = provablePool.filter((r) => reproduces(repro(r)));
  const leadPool = multiRun && reproducingPool.length > 0 ? reproducingPool : provablePool;
  const leadRanked = [...leadPool].sort((a, b) => {
    const ra = reproduces(repro(a)) ? 1 : 0;
    const rb = reproduces(repro(b)) ? 1 : 0;
    if (ra !== rb) return rb - ra;
    if (leadScore(b) !== leadScore(a)) return leadScore(b) - leadScore(a);
    return a.query_id.localeCompare(b.query_id) || a.engine_name.localeCompare(b.engine_name);
  });
  let leadRow: LosingRow | null = null;
  let lead: Finding | null = null;
  for (const row of leadRanked) {
    const f = toFinding(row, "lead", answers, repro(row), preferFor(row.competitor));
    if (f) {
      leadRow = row;
      lead = f;
      break;
    }
  }
  if (!leadRow || !lead) {
    return { ok: false, reason: "could not join any losing finding to a verbatim answer" };
  }
  const heroEngine = leadRow.engine_name;

  // Table: next 2 DISTINCT queries (not the lead's), drawn from the SAME gated
  // pool the hero passed (S8) — every table row has cleared the honest-hero,
  // proof-foregrounding, and winnable gates, so a row can't contradict the
  // headline. Ranked by COMMERCIAL intent (scoreRow), deterministic tiebreak (D4).
  const tableRanked = [...provablePool].sort(
    (a, b) =>
      scoreRow(b) - scoreRow(a) ||
      a.query_id.localeCompare(b.query_id) ||
      a.engine_name.localeCompare(b.engine_name),
  );
  const seen = new Set<string>([leadRow.query_id]);
  const table: Finding[] = [];
  for (const row of tableRanked) {
    if (table.length >= 2) break;
    if (seen.has(row.query_id)) continue;
    const f = toFinding(row, "table", answers, repro(row), preferFor(row.competitor));
    if (!f) continue;
    seen.add(row.query_id);
    table.push(f);
  }

  const headline = headlineFor(leadRow.competitor);

  return { ok: true, lead, table, headline, heroEngine };
}

/** One "why AI skips you" gap — a fixable on/off-site cause behind the loss. */
export interface WhyGap {
  /** The check name (a positive statement of what good looks like). */
  label: string;
  status: string; // fail | partial
  impact: string; // High | Medium | Low
}

const IMPACT_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };
const STATUS_RANK: Record<string, number> = { fail: 2, partial: 1 };

/** A Category-1 check detail that means OUR probe was edge-blocked, not that the
 * site has a real problem: an HTTP 403/429, an anti-bot/consent challenge, or the
 * crawler admitting it couldn't even get a browser baseline. */
const PROBE_BLOCKED_DETAIL = /http\s*40[39]|http\s*429|anti-bot|challenge|did[n'’]?t return 200|can[' ’]?t assess/i;

/**
 * True when our own crawl probe was edge-blocked (403 / anti-bot challenge / no
 * browser baseline). Modern edge firewalls (Vercel, Cloudflare) reject our
 * httpx client's fingerprint while serving real verified crawlers and browsers —
 * proven on calai.app: `robots.txt: Allow /` + a sitemap, curl/GPTBot get 200,
 * yet our probe gets 403. When that happens the Category-1 technical-ACCESS
 * verdicts (robots.txt, sitemap, llms.txt, CDN/WAF, gating) describe OUR client
 * being blocked, not the prospect's crawler policy — so they must not be printed
 * as the prospect's own failings. (Fitbod's 403 is a genuine block, but the
 * crawler can't yet tell the two apart — that's task A; until then we suppress
 * conservatively rather than assert a checkable falsehood in cold outreach.)
 */
export function accessProbeUnreliable(site: SiteAuditPayload): boolean {
  const cat1 = (site.checks ?? []).filter((c) => c.category === 1);
  const crawlerAccess = cat1.find((c) => c.check_key === "crawler_access");
  if (crawlerAccess?.status === "fail" && PROBE_BLOCKED_DETAIL.test(crawlerAccess.detail ?? "")) {
    return true;
  }
  // Or ≥2 Cat-1 checks failing specifically with a block/challenge signature.
  return (
    cat1.filter((c) => c.status === "fail" && PROBE_BLOCKED_DETAIL.test(c.detail ?? "")).length >= 2
  );
}

/**
 * Pick the top fixable gaps behind the visibility loss — the "why AI skips you"
 * block. The site-audit roadmap is already gaps-only (fail/partial); we order by
 * fix phase (technical accessibility first), then fail-before-partial, then
 * impact, and take the top `max`. Returns [] when no site audit ran.
 *
 * When our crawl probe was edge-blocked (`accessProbeUnreliable`), the phase-1
 * technical-accessibility gaps are dropped: they'd otherwise tell the prospect
 * "your site blocks AI crawlers / your content is gated" when in reality only our
 * probe was blocked and real crawlers get in. Content/off-site gaps (judged from
 * content we did obtain, or from the web) are kept.
 */
export function selectWhyGaps(
  site: SiteAuditPayload | null | undefined,
  max = 3,
): WhyGap[] {
  if (!site || !site.present || !Array.isArray(site.roadmap) || site.roadmap.length === 0) {
    return [];
  }
  const dropAccessGaps = accessProbeUnreliable(site);
  return [...site.roadmap]
    .filter((r) => !(dropAccessGaps && r.phase === 1))
    .sort(
      (a, b) =>
        a.phase - b.phase ||
        (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0) ||
        (IMPACT_RANK[(b.impact_label ?? "").toLowerCase()] ?? 0) -
          (IMPACT_RANK[(a.impact_label ?? "").toLowerCase()] ?? 0),
    )
    .slice(0, max)
    .map((r) => ({ label: r.check_name, status: r.status, impact: r.impact_label }));
}
