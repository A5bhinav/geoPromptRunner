/**
 * Crawl4aiClaudeResolver — the real Resolver: URL -> CompanyProfile.
 *
 * Pipeline: crawl the homepage (and best-effort a pricing/alternatives page) via
 * crawl4ai -> clean markdown -> Claude extracts the company profile under a
 * json_schema. Competitors come back `confirmed:false` on purpose — the human
 * input-confirm gate is what flips them to true.
 *
 * Same interface as MockResolver, so config.ts swaps it in behind an env gate.
 * The CompanyProfile shape is EXACTLY types/domain.ts.
 */

import { extractJson, claudeModel } from "../llm/claude.ts";
import { Crawl4aiClient, type LabeledPage } from "./Crawl4aiClient.ts";
import type { CompanyProfile } from "../types/domain.ts";
import type { Resolver } from "./Resolver.ts";
import {
  PROFILE_SCHEMA,
  PROFILE_SYSTEM_PROMPT,
  buildProfile,
  type ExtractedProfile,
} from "./profileExtraction.ts";

// Re-export so existing importers (tests, callers) keep their import path.
export { buildProfile } from "./profileExtraction.ts";

/** Build the labeled user content Claude reads. Pure (exported for tests). */
export function buildExtractionInput(pages: LabeledPage[]): string {
  return pages.map((p) => `## ${p.url}\n\n${p.markdown}`).join("\n\n---\n\n");
}

export class Crawl4aiClaudeResolver implements Resolver {
  private readonly crawler: Crawl4aiClient;

  constructor(crawler?: Crawl4aiClient) {
    this.crawler = crawler ?? new Crawl4aiClient();
  }

  async resolve(url: string): Promise<CompanyProfile> {
    const pages = await this.crawler.getCompanyMarkdown(url);
    if (pages.length === 0) {
      throw new Error(`crawl4ai returned no usable markdown for ${url}`);
    }

    const input = buildExtractionInput(pages);
    const extracted = await extractJson<ExtractedProfile>(
      PROFILE_SYSTEM_PROMPT,
      input,
      PROFILE_SCHEMA as unknown as Record<string, unknown>,
    );

    return buildProfile(url, extracted, claudeModel());
  }
}
