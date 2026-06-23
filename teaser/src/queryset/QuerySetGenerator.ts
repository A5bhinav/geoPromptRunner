/**
 * QuerySetGenerator: CompanyProfile -> GeneratedQuerySet.
 *
 * Encodes the platform's query methodology (docs/query-generation-plan.md): the
 * 5 funnel buckets, weighting toward category/comparison (where teasers land),
 * and the hard rules (>=2 comparison queries leave the client unnamed; competitors
 * named; verbatim buyer language). MockQuerySetGenerator fills templates so the
 * flow runs with no LLM; the real generator (later) uses Claude with these rules
 * as the spec. See BUILD_PLAN.md §4b.
 */

import type { CompanyProfile, GeneratedQuerySet } from "../types/domain.ts";

export interface QuerySetGenerator {
  generate(profile: CompanyProfile): Promise<GeneratedQuerySet>;
}
