/**
 * Assembles the teaser's text (headline, lead sentence, stakes, CTA) from the
 * selected findings. Deterministic templating — no LLM — so copy is reviewable
 * and consistent. Voice matches the "Ledger" editorial design.
 */

import type { Finding, HeadlineNumber } from "../types/domain.ts";

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
  };
  return map[engine] ?? engine;
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
  };
  return map[engine] ?? "#1b1a17";
}

export function headline(companyName: string): string {
  return `What AI tells your buyers about ${companyName} — and what it quietly leaves out.`;
}

export function leadSentence(companyName: string, lead: Finding): string {
  return (
    `Ask ${engineLabel(lead.engineName)} “${lead.verbatimQuery}” and it recommends ` +
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
  const gap = h.n - h.companyAppears;
  return (
    `Every one of those ${gap} queries is a buyer being pointed to a competitor at the ` +
    `exact moment they're choosing — before ${companyName} ever enters the conversation.`
  );
}

export function ctaLine(companyName: string): string {
  return (
    `Want the full picture across every query your buyers actually ask — and the fixes ` +
    `that get ${companyName} cited? 15 minutes.`
  );
}

/** One-line read of what the proof shows. */
export function proofCaption(companyName: string, lead: Finding): string {
  return (
    `${engineLabel(lead.engineName)}, asked “${lead.verbatimQuery}”: ` +
    `${lead.competitor} is recommended; ${companyName} is absent.`
  );
}
