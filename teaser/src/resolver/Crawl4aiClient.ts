/**
 * Dependency-free HTTP client for a self-hosted crawl4ai REST server (image
 * series 0.8.x). Uses Node 22's global `fetch` — no SDK, no deps.
 *
 * We use two endpoints:
 *   - POST /md    single URL -> clean markdown STRING (top-level `markdown`)
 *   - POST /crawl multi-URL  -> items with NESTED markdown.{fit,raw} + links
 *
 * `/md` is the simple path (homepage / known slugs); `/crawl` is used only when
 * we want `links.internal` to discover a pricing/alternatives page. Prefer
 * `fit_markdown` (filtered, LLM-ready) over `raw_markdown` everywhere.
 *
 * Config: CRAWL4AI_BASE_URL (default http://localhost:11235), optional
 * CRAWL4AI_API_TOKEN (sent as `Authorization: Bearer` only when set). Each
 * request is bounded by a client-side AbortController timeout.
 */

export type FilterType = "fit" | "raw" | "bm25" | "llm";

/** Response shape of POST /md — `markdown` is the already-resolved string. */
export interface MarkdownResult {
  url: string;
  filter: FilterType;
  query: string | null;
  cache: string | null;
  markdown: string;
  success: boolean;
}

/** Per-result shape of POST /crawl — `markdown` is an OBJECT here, not a string. */
export interface CrawlResultItem {
  url: string;
  success: boolean;
  status_code: number | null;
  markdown: { raw_markdown: string; fit_markdown: string };
  links?: {
    internal?: { href: string; text: string }[];
    external?: { href: string; text: string }[];
  };
  metadata?: Record<string, unknown>;
  error_message?: string;
}

/** A labeled markdown block (one per crawled page) for handing to Claude. */
export interface LabeledPage {
  url: string;
  markdown: string;
}

const DEFAULT_BASE_URL = "http://localhost:11235";

/** Internal-link / common-slug match for pricing-style pages. */
const PRICING_LIKE = /pricing|plans|compare|comparison|alternativ|\/vs\b/i;

export class Crawl4aiClient {
  private readonly baseUrl: string;
  private readonly token?: string;

  constructor(opts?: { baseUrl?: string; token?: string }) {
    this.baseUrl = (
      opts?.baseUrl ??
      process.env.CRAWL4AI_BASE_URL ??
      DEFAULT_BASE_URL
    ).replace(/\/$/, "");
    this.token = opts?.token ?? process.env.CRAWL4AI_API_TOKEN ?? undefined;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    // Gate the bearer header on CRAWL4AI_API_TOKEN being set — the server binds
    // loopback-only and needs no auth when the token is unset.
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  private async post<T>(path: string, body: unknown, timeoutMs: number): Promise<T> {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: this.headers(),
        body: JSON.stringify(body),
        signal: ac.signal,
      });
      const text = await res.text();
      // Transport/auth/validation failures are non-2xx; crawl-level failures
      // come back 200 with success:false (checked by callers).
      if (!res.ok) {
        throw new Error(`crawl4ai ${path} HTTP ${res.status}: ${text.slice(0, 500)}`);
      }
      return JSON.parse(text) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Readiness check — GET /health returns 200 when the server is up. */
  async health(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/health`, { headers: this.headers() });
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Single URL -> clean markdown string. Default f="fit" (LLM-ready). */
  async getMarkdown(
    url: string,
    opts?: { f?: FilterType; q?: string; cacheBust?: boolean },
  ): Promise<string> {
    const body: Record<string, unknown> = {
      url,
      f: opts?.f ?? "fit",
      c: opts?.cacheBust ? String(Date.now()) : "0",
    };
    if (opts?.q) body["q"] = opts.q;
    const data = await this.post<MarkdownResult>("/md", body, 45_000);
    if (!data.success) throw new Error(`crawl4ai /md success=false for ${url}`);
    return data.markdown;
  }

  /**
   * Multi-URL crawl. Returns items with nested markdown.fit_markdown + links
   * for discovery. Uses PruningContentFilter (no query) by default.
   */
  async crawl(
    urls: string[],
    opts?: { pruneThreshold?: number; query?: string },
  ): Promise<CrawlResultItem[]> {
    const filter = opts?.query
      ? {
          type: "BM25ContentFilter",
          params: { query: opts.query, threshold: opts?.pruneThreshold ?? 0.5 },
        }
      : {
          type: "PruningContentFilter",
          params: { threshold: opts?.pruneThreshold ?? 0.48 },
        };
    const body = {
      urls,
      browser_config: { type: "BrowserConfig", params: { headless: true } },
      crawler_config: {
        type: "CrawlerRunConfig",
        params: {
          cache_mode: "bypass",
          stream: false,
          markdown_generator: {
            type: "DefaultMarkdownGenerator",
            params: { content_filter: filter },
          },
        },
      },
    };
    const data = await this.post<{ success: boolean; results: CrawlResultItem[] }>(
      "/crawl",
      body,
      60_000,
    );
    return data.results ?? [];
  }

  /**
   * Homepage + best-effort discovered pricing/alternatives pages -> labeled
   * markdown for Claude. Crawls the homepage (for `links.internal`), filters
   * pricing-like links, then fetches up to `maxInternal` of them via /md.
   * Prefers fit_markdown, falling back to raw_markdown when fit is empty.
   */
  async getCompanyMarkdown(
    homepageUrl: string,
    opts?: { maxInternal?: number },
  ): Promise<LabeledPage[]> {
    const maxInternal = opts?.maxInternal ?? 2;
    const out: LabeledPage[] = [];

    const results = await this.crawl([homepageUrl]);
    const home = results[0];
    if (home?.success) {
      const md = home.markdown.fit_markdown || home.markdown.raw_markdown;
      if (md) out.push({ url: home.url, markdown: md });
    }

    const targets = pickInternalTargets(home?.links?.internal ?? [], maxInternal);
    for (const u of targets) {
      try {
        out.push({ url: u, markdown: await this.getMarkdown(u, { f: "fit" }) });
      } catch {
        // Best-effort — a missing/blocked internal page shouldn't fail the run.
      }
    }
    return out;
  }
}

/**
 * Pick up to `limit` distinct pricing-style internal hrefs from a link list.
 * Pure (no network) so it can be unit-tested. Exported for tests.
 */
export function pickInternalTargets(
  internal: { href: string; text: string }[],
  limit: number,
): string[] {
  const seen = new Set<string>();
  const picked: string[] = [];
  for (const link of internal) {
    const href = link.href;
    if (!href) continue;
    if (!PRICING_LIKE.test(href) && !PRICING_LIKE.test(link.text ?? "")) continue;
    if (seen.has(href)) continue;
    seen.add(href);
    picked.push(href);
    if (picked.length >= limit) break;
  }
  return picked;
}
