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
  status: "draft" | "approved" | "rejected" | "exported";
}
