/** teaserAuto's own domain types (the data it owns; see BUILD_PLAN.md §3). */

import type { AnswerRecord, IntentBucket, Prominence, ReportPayload } from "./platform.ts";

export interface Competitor {
  name: string;
  aliases: string[];
  /** Whether a human confirmed this competitor at the input gate. */
  confirmed: boolean;
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
  status: "draft" | "approved" | "rejected" | "exported";
}
