/**
 * Assembles the teaser's text (headline, lead sentence, stakes, CTA) from the
 * selected findings. Deterministic templating — no LLM — so copy is reviewable
 * and consistent. Voice matches the "Ledger" editorial design.
 */

import { isRecommendedFirst } from "../select/selectFindings.ts";
import type { Finding, HeadlineNumber } from "../types/domain.ts";

/**
 * Humanize an unknown engine id so a raw snake_case token
 * ("bing_copilot") never leaks into a client deliverable: "bing_copilot" →
 * "Bing Copilot". A safe fallback for any platform engine not in the label map.
 */
function humanizeEngine(engine: string): string {
  return engine
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ") || engine;
}

/** Pretty engine label for captions/headlines. */
export function engineLabel(engine: string): string {
  const map: Record<string, string> = {
    perplexity: "Perplexity",
    ai_overviews: "AI Overviews",
    google_ai_overviews: "AI Overviews",
    openai: "ChatGPT",
    openai_search: "ChatGPT",
    gemini: "Gemini",
    gemini_grounded: "Gemini",
    anthropic: "Claude",
    anthropic_search: "Claude",
    // Bing Copilot family — the platform may emit any of these ids.
    copilot: "Copilot",
    bing_copilot: "Copilot",
    bing: "Bing",
  };
  // Humanize (not raw id) on miss so a new engine never prints as snake_case.
  return map[engine] ?? humanizeEngine(engine);
}

/** Brand color for the proof-card engine avatar. */
export function engineColor(engine: string): string {
  const map: Record<string, string> = {
    openai: "#10A37F",
    openai_search: "#10A37F",
    perplexity: "#20808D",
    ai_overviews: "#4285F4",
    google_ai_overviews: "#4285F4",
    gemini: "#8E75F0",
    gemini_grounded: "#8E75F0",
    anthropic: "#CC785C",
    anthropic_search: "#CC785C",
    copilot: "#0F6CBD",
    bing_copilot: "#0F6CBD",
    bing: "#0F6CBD",
  };
  return map[engine] ?? "#1b1a17";
}

/**
 * The verb the copy may print for a competitor in a losing cell, graded by the
 * judge's prominence so the teaser never claims more than what was measured:
 * "recommends" is reserved for recommended_first (or legacy rows, which all
 * came through the platform's recommended-first filter); anything the judge
 * saw as merely present grades down to "features"/"mentions".
 */
export function competitorVerb(lead: Finding): { active: string; passive: string } {
  if (isRecommendedFirst(lead.prominence)) {
    return { active: "recommends", passive: "is recommended" };
  }
  if (lead.prominence === "mid_pack") {
    return { active: "features", passive: "is featured" };
  }
  return { active: "mentions", passive: "is mentioned" };
}

/**
 * The past-participle a proof card may print for the competitor, graded by the
 * same prominence rule as competitorVerb so the card never overclaims:
 * "recommended" is reserved for recommended_first; a weaker prominence grades
 * down to "featured"/"mentioned". (The card previously hardcoded "recommended".)
 */
export function competitorProminenceWord(lead: Finding): string {
  if (isRecommendedFirst(lead.prominence)) return "recommended";
  if (lead.prominence === "mid_pack") return "featured";
  return "mentioned";
}

export function headline(companyName: string, lead: Finding): string {
  // A direct, present-tense threat — built to stop a busy reader, not read like an
  // article. Names the rival AI is steering buyers toward, and who it leaves out.
  // "sending your buyers to" is only printable when the judge saw the rival
  // recommended first; a weaker prominence grades down to a presence claim.
  if (isRecommendedFirst(lead.prominence)) {
    return `AI is sending your buyers to ${lead.competitor} — not ${companyName}.`;
  }
  return `When your buyers ask AI, ${lead.competitor} is in the answer — ${companyName} isn't.`;
}

export function leadSentence(companyName: string, lead: Finding): string {
  return (
    `Ask ${engineLabel(lead.engineName)} “${lead.verbatimQuery}” and it ${competitorVerb(lead).active} ` +
    `${lead.competitor} — ${companyName} is nowhere in the answer.`
  );
}

export function headlineNumberSentence(companyName: string, h: HeadlineNumber): string {
  return (
    `${companyName} appears in ${h.companyAppears} of ${h.n} buyer queries; ` +
    `${h.competitorName} appears in ${h.competitorAppears} of ${h.n}.`
  );
}

export function stakesLine(companyName: string, h: HeadlineNumber): string {
  // Only claims what computeHeadline measured: gap = queries where the client
  // never appeared. (The old copy said every gap query pointed buyers to a
  // competitor — untrue for queries where nobody we track appeared.)
  const gap = h.n - h.companyAppears;
  const queries = gap === 1 ? "query" : "queries";
  return (
    `That leaves ${gap} of ${h.n} buyer ${queries} answered without ${companyName} — ` +
    `buyers choosing at the exact moment ${companyName} isn't in the conversation.`
  );
}

export function ctaLine(companyName: string): string {
  return (
    `Want the full picture across every query your buyers actually ask — and the fixes ` +
    `that get ${companyName} cited? 15 minutes.`
  );
}

/**
 * An honest "we ran it more than once" line — printed only when the loss held on
 * every run the audit captured (≥2). Empty string otherwise, so a single-sample
 * audit makes no repeatability claim it can't back up.
 */
export function reproNote(lead: Finding): string {
  if (lead.runsObserved >= 2 && lead.runsConfirming === lead.runsObserved) {
    return `Asked ${lead.runsObserved} separate times — ${lead.competitor} came up every time. This isn't a one-off.`;
  }
  return "";
}

/** One-line read of what the proof shows. */
export function proofCaption(companyName: string, lead: Finding): string {
  return (
    `${engineLabel(lead.engineName)}, asked “${lead.verbatimQuery}”: ` +
    `${lead.competitor} ${competitorVerb(lead).passive}; ${companyName} is absent.`
  );
}

// --- W2.6: local-service copy -----------------------------------------------------
// FORKED from the consumer strings, not a rewrite (pivot §0.6). The local variants
// INHERIT every claim-fidelity rule above unchanged: they call competitorVerb /
// competitorProminenceWord rather than hardcoding a verb, so the teaser still never
// claims more than the judge measured.
//
// Two deliberate differences from the consumer copy, per the strategy doc — "owners
// respond to named competitors and phone-call economics, not dashboards":
//   1. "buyers" becomes "customers" / "homeowners".
//   2. No aggregate appearance ratio. The denominator is a query set WE chose, so
//      "appears in 3 of 12" reads as a visibility rate and is not one. Local copy
//      makes the reproducible per-query claim instead.

/** The sources AI actually cites for local businesses, in rough citation order. */
export const LOCAL_SOURCE_CHECKLIST: readonly string[] = [
  "Google Business Profile",
  "Yelp",
  "BBB",
  "Angi",
  "Thumbtack",
  "Facebook",
  "Bing Places",
  "Reddit",
];

export function localHeadline(companyName: string, lead: Finding): string {
  // Same prominence grading as the consumer headline: "sending your customers to"
  // is only printable when the judge saw the rival recommended first.
  if (isRecommendedFirst(lead.prominence)) {
    return `AI is sending your customers to ${lead.competitor} — not ${companyName}.`;
  }
  return `When customers ask AI, ${lead.competitor} is in the answer — ${companyName} isn't.`;
}

export function localLeadSentence(companyName: string, lead: Finding): string {
  return (
    `Ask ${engineLabel(lead.engineName)} “${lead.verbatimQuery}” and it ${competitorVerb(lead).active} ` +
    `${lead.competitor} — ${companyName} is nowhere in the answer.`
  );
}

/**
 * The local stakes line. Deliberately makes NO aggregate-ratio claim (see above) and
 * no dollar claim: we have not measured this shop's job value, and inventing one
 * would be the same class of error as an unmeasured prominence verb.
 */
export function localStakesLine(companyName: string, lead: Finding): string {
  return (
    `That's a customer with a problem right now, being handed ${lead.competitor}'s name ` +
    `instead of ${companyName}'s.`
  );
}

export function localCtaLine(companyName: string): string {
  return (
    `Want to see every question your customers ask AI — and what it takes to get ` +
    `${companyName} named? 15 minutes.`
  );
}

/** Kind-selected copy, so callers thread business kind rather than branching. */
export function copyFor(businessKind: string): {
  headline: (companyName: string, lead: Finding) => string;
  leadSentence: (companyName: string, lead: Finding) => string;
  ctaLine: (companyName: string) => string;
} {
  return businessKind === "local_service"
    ? { headline: localHeadline, leadSentence: localLeadSentence, ctaLine: localCtaLine }
    : { headline, leadSentence, ctaLine };
}
