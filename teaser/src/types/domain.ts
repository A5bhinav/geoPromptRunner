/** teaserAuto's own domain types (the data it owns; see BUILD_PLAN.md §3). */

import type { AnswerRecord, IntentBucket, Prominence, ReportPayload } from "./platform.ts";

export interface Competitor {
  name: string;
  aliases: string[];
  /** Whether a human confirmed this competitor at the input gate. */
  confirmed: boolean;
}

/**
 * Which ICP a resolved site belongs to — the SINGLE selector for every
 * consumer/local divergence in the SMB pivot (docs/smb-pivot-build-plan.md §0.6).
 *
 * - `product`: a nationally-marketed consumer product. Competitors are direct
 *   substitutes anywhere; queries carry no geography.
 * - `local_service`: a service-area business (HVAC, plumbing, barbershop). Rivals
 *   are other shops in the same trade AND metro; queries are geo-anchored.
 *
 * The pivot ADDS the local ICP — it does not replace the consumer one. Every
 * divergence keys off this value; shared constants are forked by it, never edited
 * in place. `tests/consumerPathRegression.test.ts` guards that rule.
 */
export type BusinessKind = "product" | "local_service";

/**
 * Where a service-area business actually serves customers (W1.1).
 *
 * Absent for nationally-marketed products — a spurious location would geo-anchor
 * their queries and invalidate the measurement. Present only when the resolver read
 * a real NAP block (name/address/phone, contact page, or schema.org LocalBusiness)
 * off the site; it is never inferred from the brand name or a guess.
 */
export interface BusinessLocation {
  city: string;
  /** State / province, spelled as the site spells it ("California", not "CA"). */
  region: string;
  /**
   * Country as SearchApi's location database spells it — the full NAME
   * ("United States"), NOT an ISO code. Verified live 2026-07-27: `location=
   * "Berkeley,California,US"` is rejected with "Location was not found", while
   * "Berkeley,California,United States" resolves. Stored in the form the one
   * consumer needs, rather than storing ISO and mapping at every call site.
   */
  country: string;
  /** Additional named towns/neighborhoods the business explicitly serves. */
  serviceArea?: string[];
}

/**
 * The canonical location string SearchApi's Google engine accepts — "City,Region,US".
 * Verified LIVE against SearchApi 2026-07-27, not just against its docs: the country
 * must be the full name ("United States"); an ISO code is rejected outright with
 * "Location was not found". SearchApi builds the `uule` encoding itself, and
 * `location`/`uule` are mutually exclusive. Kept here so the teaser and the Python
 * engine agree on one serialization; `serviceArea` is deliberately NOT included — it
 * widens the query, it does not move the search origin.
 */
export function canonicalLocation(loc: BusinessLocation): string {
  return [loc.city, loc.region, loc.country]
    .map((p) => p.trim())
    .filter(Boolean)
    .join(",");
}

/**
 * One row of the platform's `fact` block (`fact,<key>,<value>,,`) — the flat pair
 * `src/prompts/csv_loader.py` renders as a `"{key}: {value}"` fact-sheet line.
 *
 * Flat by construction, which is WHY the key carries the section (`hours_sunday`,
 * `service_area_excluded`): `_build_fact_sheet` joins the rows into one block, so
 * the markdown sheet's headings do not survive and the key is the only structure
 * the judge ever sees (docs/factsheet-autogen-plan.md §2). The key is never empty
 * — a keyless row falls back to the bare value and silently degrades the sheet
 * (§2.1) — but enforcing that belongs to the generator, not to this carrier.
 *
 * The teaser never produces these. Extraction lives platform-side (§9.1); two
 * extraction prompts is the drift the fact-sheet plan exists to avoid.
 */
export interface FactClaimRow {
  key: string;
  value: string;
}

/** Resolver output: URL → company profile. */
export interface CompanyProfile {
  url: string;
  name: string;
  /**
   * Known name variants for the CLIENT itself (e.g. "YNAB" for "You Need A
   * Budget", a shortened brand form). Threaded into every client matcher so an
   * engine that names the client only by a variant still counts as present —
   * otherwise a real appearance prints as a reproduced loss and understates the
   * headline. Optional: mock/legacy/stored profiles that have no alias source
   * fall back to []. Competitors carry their own aliases on `Competitor`.
   */
  aliases?: string[];
  /**
   * Which ICP this site belongs to (W0.1). Optional by design so every existing
   * consumer call site compiles untouched; absent means `product`. Read it through
   * `businessKindOf()` rather than defaulting inline, so the fallback lives in one
   * place. Becomes the router in W2.4.
   */
  businessKind?: BusinessKind;
  /**
   * Service-area business location (W1.1). Optional by design so every existing
   * consumer call site compiles untouched — and absent is MEANINGFUL, not a
   * placeholder: a nationally-marketed product genuinely has no service area.
   */
  location?: BusinessLocation;
  category: string;
  competitors: Competitor[];
  clientDomains: string[];
  /** Optional claims that could seed a fact sheet (wrong-claim branch; manual). */
  productClaims: { claim: string; sourceUrl: string }[];
  /**
   * The fact sheet this audit measures answers against, as `fact` rows (F2).
   *
   * Optional by design so every existing call site compiles untouched — productClaims
   * above is required despite its comment, and a second required field would break
   * every profile literal and seven test files (plan §9.2.3) — and absent is
   * MEANINGFUL, not a placeholder: a dimension the sheet is blank on is one the judge
   * does not check and therefore cannot mis-flag. Coverage is not the metric here;
   * a false accusation in a document we send a stranger is the failure to avoid (§4.2).
   *
   * NOT derived from productClaims: those carry no key and no verbatim quote, so they
   * cannot pass the §4.1 gate that turns "the model said so" into "the page says so".
   */
  factClaims?: FactClaimRow[];
  resolvedAt: string;
  resolverModel: string;
}

/** One generated buyer query (platform Query shape + our metadata). */
export interface GeneratedQuery {
  query_id: string;
  text: string;
  intent: IntentBucket;
  weight: number;
  persona: string | null;
}

/** The teaser-grade query set we generate and submit to the platform. */
export interface GeneratedQuerySet {
  version: string;
  queries: GeneratedQuery[];
}

/** A selected finding (lead or pattern-table row), joined to verbatim text. */
export interface Finding {
  role: "lead" | "table";
  source: "losing_query" | "accuracy_flag";
  queryId: string;
  intent: IntentBucket;
  engineName: string;
  competitor: string;
  /**
   * How prominently the judge saw the competitor in this cell — drives the
   * copy verb ("recommends" needs recommended_first). null = unknown (drafts
   * stored before the platform sent prominence; those all came through
   * losing_cells, which only emitted recommended_first cells).
   */
  prominence: Prominence | null;
  verbatimQuery: string;
  verbatimAnswer: string;
  citations: string[];
  rankScore: number;
  /**
   * Reproducibility of the loss across the runs the platform captured for this
   * (query, engine): how many runs returned an answer (`runsObserved`) and how
   * many of those showed the loss — client absent, competitor present
   * (`runsConfirming`). A single-run audit yields 1/1. Copy only claims a loss
   * is repeatable when it held on every observed run and there were ≥2 of them.
   */
  runsObserved: number;
  runsConfirming: number;
  /**
   * The accuracy flag behind this finding. Present iff `source ===
   * "accuracy_flag"`, null otherwise.
   *
   * A losing-query finding says "a competitor got recommended instead"; an
   * accuracy finding says "the model stated something your own site
   * contradicts", and needs the contradicted pair to be printable at all.
   * `competitor` is "" and `prominence` null on these — there is no rival, the
   * subject is the client's own facts.
   */
  flag?: FindingFlag | null;
}

/** The judged contradiction behind an `accuracy_flag` finding. */
export interface FindingFlag {
  type: string; // AccuracyFlagType value
  severity: string; // Severity value
  /** What the answer stated. */
  claim: string;
  /** The verbatim fact-sheet line it contradicts. */
  reality: string;
}

/** The "appears in X of N / competitor in Y of N" headline metric. */
export interface HeadlineNumber {
  companyAppears: number;
  competitorAppears: number;
  competitorName: string;
  n: number;
}

/** A fully-assembled draft teaser, ready for review/render. */
export interface TeaserDraft {
  prospectUrl: string;
  companyName: string;
  category: string;
  runDate: string;
  heroEngine: string;
  headline: string;
  leadSentence: string;
  headlineNumber: HeadlineNumber;
  stakesLine: string;
  cta: string;
  lead: Finding;
  table: Finding[];
  /**
   * Accuracy findings this run's fact sheet was ENTITLED to send (F3), already
   * filtered by `selectAccuracyFindings` against the sheet's verification tier.
   * Optional: legacy drafts predate it, and a run with no approved sheet has none.
   *
   * These carry `runsObserved: 0` on purpose — the judge scored one cell, so the
   * copy must NOT print an occurrence line for them the way a losing-query finding
   * does. "1 of 1" would read as "we tried once and it held".
   */
  accuracyFindings?: Finding[];
  /** Cached report + answers so the teaser is reproducible as engines drift. */
  report: ReportPayload;
  answers: AnswerRecord[];
  /**
   * Aliases captured at generation time so a teaser REGENERATED from storage
   * isn't alias-blind (T3). The stored ReportPayload carries only competitor/
   * client NAMES, so without these `profileFromStored` would reset aliases to []
   * and an alias-only client mention would re-count as a loss (re-opening S4).
   * Optional: legacy drafts saved before this field fall back to name-only.
   */
  clientAliases?: string[];
  /** competitor name → aliases, persisted for the same reason (T3). */
  competitorAliases?: Record<string, string[]>;
  /**
   * Business kind + location captured at generation time, for the SAME reason as
   * clientAliases (T3): a teaser REGENERATED from storage rebuilds its profile from
   * the stored ReportPayload, which carries neither. Without these, regenerating a
   * LOCAL teaser would silently produce a consumer-shaped one — the losing-cell
   * geography, the copy, and the source checklist would all revert. Optional:
   * legacy drafts saved before this field fall back to product/no-location.
   */
  businessKind?: BusinessKind;
  location?: BusinessLocation;
  /**
   * The fact sheet the run was submitted with, captured at generation time for the
   * SAME reason as clientAliases (T3, and C8 in the fact-sheet plan §13.3): a teaser
   * REGENERATED from storage rebuilds its profile from the stored ReportPayload,
   * which carries the accuracy flags but not the sheet those flags were graded
   * against. Without this the sheet is silently dropped and the regenerated teaser
   * cites a reference nothing still holds. Optional: legacy drafts, and runs that had
   * no sheet, fall back to absent — which stays distinct from an empty sheet.
   */
  factClaims?: FactClaimRow[];
  status: "draft" | "approved" | "rejected" | "exported";
}
