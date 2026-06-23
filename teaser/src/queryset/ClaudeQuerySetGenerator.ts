/**
 * ClaudeQuerySetGenerator — the real QuerySetGenerator: CompanyProfile -> a
 * teaser-grade GeneratedQuerySet, using Claude with the methodology rules as the
 * spec (docs/query-generation-plan.md; MockQuerySetGenerator.ts for the teaser cut).
 *
 * Hard rules honored (and ENFORCED post-hoc — see validateAndRepair):
 *   - >=2 comparison queries that do NOT name the client (test unprompted surfacing)
 *   - the client is named ONLY in the brand-intent query
 *   - competitors are named in comparison queries
 *   - weighted toward category/comparison (where teasers land)
 *   - 5 intent buckets: problem_aware | category | comparison | brand | adjacent_authority
 *
 * The LLM output is validated against the GeneratedQuery shape and the hard
 * rules; if a rule is violated we repair deterministically (and, as a last
 * resort, fall back to the same template set the mock uses) so the pipeline
 * never receives an invalid set.
 */

import { extractJson } from "../llm/claude.ts";
import type {
  CompanyProfile,
  GeneratedQuery,
  GeneratedQuerySet,
} from "../types/domain.ts";
import type { IntentBucket } from "../types/platform.ts";
import type { QuerySetGenerator } from "./QuerySetGenerator.ts";

const VERSION = "teaser-claude-v1";

const INTENTS: IntentBucket[] = [
  "problem_aware",
  "category",
  "comparison",
  "brand",
  "adjacent_authority",
];

/** Per-bucket weights — heavier on category/comparison (matches the mock). */
const WEIGHTS: Record<IntentBucket, number> = {
  problem_aware: 1.0,
  category: 1.4,
  comparison: 1.8,
  brand: 2.0,
  adjacent_authority: 1.0,
};

/** Raw query shape Claude returns (no weight/query_id — we assign those). */
interface RawQuery {
  text: string;
  intent: IntentBucket;
}

const QUERY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    queries: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          text: { type: "string" },
          intent: {
            type: "string",
            enum: INTENTS,
          },
        },
        required: ["text", "intent"],
      },
    },
  },
  required: ["queries"],
} as const;

function systemPrompt(): string {
  return `You generate a small, teaser-grade set of real buyer questions for a competitive AI-visibility audit. The questions get asked verbatim to AI answer engines (ChatGPT, Perplexity, Google AI Overviews) to measure whether a company surfaces on its buyers' questions or whether competitors get recommended instead.

Tag each query with exactly one intent bucket:
- problem_aware: first-person buyer pain; NEVER name the category, the client, or any brand.
- category: "best <category> for X" style; may carry a real qualifier; do NOT name the client.
- comparison: head-to-heads and "alternatives to <competitor>"; name competitors. At least TWO comparison queries must NOT name the client (these test whether the client surfaces unprompted).
- brand: bottom-funnel about the CLIENT specifically (this is the ONLY bucket that may name the client).
- adjacent_authority: a topic the client could plausibly own as an expert; name no brand.

Hard rules:
1. The client is named ONLY in brand-intent queries — never in category/comparison/problem_aware/adjacent_authority.
2. At least 2 comparison queries leave the client unnamed.
3. Every comparison query names at least one competitor.
4. Weight the set toward category and comparison.
5. Write like a buyer talks to a chatbot — one question each, no compound asks, no leading queries that embed the answer.

Return 7-9 queries total.`;
}

function userPrompt(profile: CompanyProfile): string {
  const competitorNames = profile.competitors.map((c) => c.name);
  return [
    `Client (the company being audited): ${profile.name}`,
    `Category: ${profile.category}`,
    `Competitors: ${competitorNames.length ? competitorNames.join(", ") : "(none provided — use real category leaders)"}`,
    "",
    "Generate the query set following the rules. Remember: name the client ONLY in brand queries; name competitors in comparison queries; >=2 comparison queries leave the client unnamed.",
  ].join("\n");
}

/** Case-insensitive whole-ish-word presence of `name` in `text`. */
function mentions(text: string, name: string): boolean {
  if (!name.trim()) return false;
  return text.toLowerCase().includes(name.trim().toLowerCase());
}

/**
 * Validate the raw queries against the hard rules and repair deterministically.
 * Pure (no network) — the core of the tested logic.
 *
 * Repairs, in order:
 *   - drop empty/whitespace queries and any with an unknown intent
 *   - drop non-brand queries that name the client (rule 1 violation)
 *   - drop comparison queries that name no competitor (rule 3 violation)
 *   - if fewer than 2 client-free comparison queries survive, synthesize them
 *     from the template generator (rule 2)
 *   - if no brand query survives, synthesize one
 *   - if the whole set is unusable, fall back to the full template set
 * Then assign weights + sequential query_ids.
 */
export function validateAndRepair(
  profile: CompanyProfile,
  raw: RawQuery[],
): GeneratedQuery[] {
  const client = profile.name;
  const competitorNames = profile.competitors.map((c) => c.name).filter(Boolean);
  const namesAnyCompetitor = (text: string): boolean =>
    competitorNames.some((c) => mentions(text, c));

  // Pass 1: keep only well-formed, rule-1/rule-3-compliant queries.
  const kept: RawQuery[] = [];
  for (const q of raw) {
    const text = (q.text ?? "").trim();
    if (!text) continue;
    if (!INTENTS.includes(q.intent)) continue;
    // Rule 1: only brand queries may name the client.
    if (q.intent !== "brand" && mentions(text, client)) continue;
    // Rule 3: comparison queries must name a competitor.
    if (q.intent === "comparison" && !namesAnyCompetitor(text)) continue;
    kept.push({ text, intent: q.intent });
  }

  // Rule 2: ensure >=2 comparison queries that do NOT name the client.
  const clientFreeComparisons = kept.filter(
    (q) => q.intent === "comparison" && !mentions(q.text, client),
  );
  const needed = 2 - clientFreeComparisons.length;
  if (needed > 0) {
    for (const synth of synthComparisons(profile, needed)) kept.push(synth);
  }

  // Ensure at least one brand query exists (the only client-named slot).
  if (!kept.some((q) => q.intent === "brand")) {
    kept.push({ intent: "brand", text: brandTemplate(client) });
  }

  // Last resort: if somehow nothing usable remains, use the full template set.
  const usable = kept.length >= 3 ? kept : templateQueries(profile);

  return usable.map(
    (q, i): GeneratedQuery => ({
      query_id: `q${String(i + 1).padStart(2, "0")}`,
      text: q.text,
      intent: q.intent,
      weight: WEIGHTS[q.intent],
      persona: null,
    }),
  );
}

/** Synthesize up to `n` client-free comparison queries from competitors. */
function synthComparisons(profile: CompanyProfile, n: number): RawQuery[] {
  const cat = profile.category;
  const c1 = profile.competitors[0]?.name ?? "the market leader";
  const c2 = profile.competitors[1]?.name ?? c1;
  const candidates: RawQuery[] = [
    { intent: "comparison", text: `What are the best alternatives to ${c2}?` },
    {
      intent: "comparison",
      text: `${c2} vs other ${cat} options — which should I pick?`,
    },
    { intent: "comparison", text: `Is ${c1} or ${c2} better for most people?` },
  ];
  return candidates.slice(0, Math.max(0, n));
}

function brandTemplate(client: string): string {
  return `Is ${client} any good — what do people think of it?`;
}

/**
 * The full deterministic template set (mirrors MockQuerySetGenerator's hard-rule
 * shape). Used only as a total fallback when the LLM output is unusable.
 */
function templateQueries(profile: CompanyProfile): RawQuery[] {
  const cat = profile.category;
  const client = profile.name;
  const c2 = profile.competitors[1]?.name ?? profile.competitors[0]?.name ?? "the market leader";
  return [
    { intent: "category", text: `What's the best ${cat} for a growing startup?` },
    { intent: "category", text: `Which ${cat} do people recommend in 2026?` },
    { intent: "comparison", text: `What are the best alternatives to ${c2}?` },
    {
      intent: "comparison",
      text: `${c2} vs other ${cat} options — which should I pick?`,
    },
    {
      intent: "problem_aware",
      text: `How do I choose something that scales with my needs?`,
    },
    {
      intent: "adjacent_authority",
      text: `What do experts say are the top ${cat} options right now?`,
    },
    { intent: "brand", text: brandTemplate(client) },
  ];
}

export class ClaudeQuerySetGenerator implements QuerySetGenerator {
  async generate(profile: CompanyProfile): Promise<GeneratedQuerySet> {
    let raw: RawQuery[] = [];
    try {
      const result = await extractJson<{ queries: RawQuery[] }>(
        systemPrompt(),
        userPrompt(profile),
        QUERY_SCHEMA as unknown as Record<string, unknown>,
      );
      raw = Array.isArray(result.queries) ? result.queries : [];
    } catch {
      // Leave raw empty -> validateAndRepair falls back to the template set.
      raw = [];
    }

    const queries = validateAndRepair(profile, raw);
    return { version: VERSION, queries };
  }
}
