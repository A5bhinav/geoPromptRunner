/**
 * MockQuerySetGenerator — builds a teaser-grade query set from templates, weighted
 * to category/comparison buckets. Deterministic, no LLM. The query texts use the
 * profile's category + top competitor so they read as real buyer questions.
 *
 * Hard-rule notes (from the methodology) honored even in the mock:
 *   - >=2 comparison queries that do NOT name the client (tests unprompted surfacing)
 *   - the client is named only in the brand-intent query
 *   - competitors are named in comparison queries
 *
 * Replace with ClaudeQuerySetGenerator (same interface) later. See BUILD_PLAN.md §4b.
 */

import type {
  CompanyProfile,
  GeneratedQuery,
  GeneratedQuerySet,
} from "../types/domain.ts";
import type { IntentBucket } from "../types/platform.ts";
import type { QuerySetGenerator } from "./QuerySetGenerator.ts";

interface Template {
  intent: IntentBucket;
  weight: number;
  /**
   * Build the query text. `competitor` is the top rival (the one answers tend to
   * recommend); `competitor2` is a second rival used to NAME a comparison query
   * without naming the one the answer recommends — so "asked about B, AI pivots to
   * A, you're absent" reads coherently.
   */
  build: (ctx: { category: string; client: string; competitor: string; competitor2: string }) => string;
}

const TEMPLATES: Template[] = [
  {
    intent: "category",
    weight: 1.4,
    build: ({ category }) => `What's the best ${category} for a growing startup?`,
  },
  {
    intent: "category",
    weight: 1.4,
    build: ({ category }) => `Which ${category} do teams recommend in 2026?`,
  },
  {
    intent: "comparison",
    weight: 1.8,
    build: ({ competitor2 }) => `What are the best alternatives to ${competitor2}?`,
  },
  {
    intent: "comparison",
    weight: 1.8,
    build: ({ category, competitor2 }) =>
      `${competitor2} vs other ${category} options — which should I pick?`,
  },
  {
    intent: "problem_aware",
    weight: 1.0,
    build: ({ category }) => `How do I choose a ${category} that scales with my team?`,
  },
  {
    intent: "adjacent_authority",
    weight: 1.0,
    build: ({ category }) => `What do experts say are the top ${category} tools right now?`,
  },
  {
    intent: "brand",
    weight: 2.0,
    build: ({ client }) => `Is ${client} any good — what do people think of it?`,
  },
];

export class MockQuerySetGenerator implements QuerySetGenerator {
  async generate(profile: CompanyProfile): Promise<GeneratedQuerySet> {
    const competitor = profile.competitors[0]?.name ?? "the market leader";
    const competitor2 = profile.competitors[1]?.name ?? competitor;
    const ctx = { category: profile.category, client: profile.name, competitor, competitor2 };

    const queries: GeneratedQuery[] = TEMPLATES.map((t, i): GeneratedQuery => ({
      query_id: `q${String(i + 1).padStart(2, "0")}`,
      text: t.build(ctx),
      intent: t.intent,
      weight: t.weight,
      persona: null,
    }));

    return { version: "teaser-mock-v1", queries };
  }
}
