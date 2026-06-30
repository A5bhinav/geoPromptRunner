/**
 * FetchClaudeResolver — the dependency-free real Resolver: URL -> CompanyProfile
 * with NO Docker / crawl4ai server. It fetches the homepage (and best-effort one
 * pricing/comparison page) directly over HTTP, reduces the HTML to readable text,
 * and hands it to Claude under the shared PROFILE_SCHEMA. Same interface as the
 * other resolvers, so config.ts swaps it in behind the Claude-key gate.
 *
 * Trade-off vs Crawl4aiClaudeResolver: no JS execution, so heavy SPAs that render
 * client-side may yield little text. For those, crawl4ai is still the better
 * adapter; this one wins on zero-setup (just ANTHROPIC_API_KEY).
 *
 * Fetching arbitrary user-supplied URLs is an SSRF vector, so every hop is
 * guarded: scheme allow-list, DNS resolution with a private/reserved-IP block,
 * and a capped manual redirect chain (each Location re-validated).
 */

import { promises as dns } from "node:dns";
import { isIP } from "node:net";
import { extractJson, claudeModel } from "../llm/claude.ts";
import type { CompanyProfile } from "../types/domain.ts";
import type { Resolver } from "./Resolver.ts";
import {
  PROFILE_SCHEMA,
  PROFILE_SYSTEM_PROMPT,
  buildProfile,
  type ExtractedProfile,
} from "./profileExtraction.ts";

const FETCH_TIMEOUT_MS = 15_000;
const MAX_REDIRECTS = 5;
const MAX_BYTES = 2_000_000; // 2 MB of HTML is plenty; guards against huge pages.
const MAX_TEXT_CHARS = 40_000; // cap per page handed to Claude.
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 (geo-teaser-resolver)";

/** Internal-link match for a pricing/comparison/about page worth a second fetch. */
const SECONDARY_LIKE = /pricing|plans|compare|comparison|alternativ|\/vs\b|about/i;

/** A labeled text block (one per fetched page) for handing to Claude. */
export interface LabeledText {
  url: string;
  text: string;
}

/**
 * True when an IP literal is in a private/reserved/loopback/link-local range and
 * must never be fetched (SSRF). Pure — exported for tests. Covers IPv4 ranges and
 * the common IPv6 cases (loopback, ULA, link-local, and v4-mapped addresses).
 */
export function isBlockedIp(ip: string): boolean {
  const v = isIP(ip);
  if (v === 4) return isBlockedV4(ip);
  if (v === 6) return isBlockedV6(ip);
  return true; // not a parseable IP -> refuse, fail closed.
}

function isBlockedV4(ip: string): boolean {
  const p = ip.split(".").map((n) => Number(n));
  if (p.length !== 4 || p.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return true;
  const a = p[0]!;
  const b = p[1]!;
  if (a === 0 || a === 10 || a === 127) return true; // this-net, private, loopback
  if (a === 169 && b === 254) return true; // link-local (incl. cloud metadata)
  if (a === 172 && b >= 16 && b <= 31) return true; // private
  if (a === 192 && b === 168) return true; // private
  if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
  if (a === 192 && b === 0) return true; // 192.0.0.0/24 + test ranges
  if (a === 198 && (b === 18 || b === 19)) return true; // benchmarking
  if (a >= 224) return true; // multicast + reserved
  return false;
}

function isBlockedV6(ip: string): boolean {
  const lower = ip.toLowerCase();
  if (lower === "::1" || lower === "::") return true; // loopback / unspecified
  if (lower.startsWith("fe80")) return true; // link-local
  if (lower.startsWith("fc") || lower.startsWith("fd")) return true; // ULA fc00::/7
  // v4-mapped (::ffff:a.b.c.d) -> check the embedded v4.
  const mapped = lower.match(/::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  if (mapped?.[1]) return isBlockedV4(mapped[1]);
  return false;
}

/** Resolve a hostname and refuse if ANY resolved address is blocked. */
async function assertHostAllowed(hostname: string): Promise<void> {
  // A bare IP host is checked directly; otherwise resolve A/AAAA and check all.
  if (isIP(hostname)) {
    if (isBlockedIp(hostname)) throw new Error(`refusing to fetch private/reserved host ${hostname}`);
    return;
  }
  if (/(^|\.)(localhost|local|internal)$/i.test(hostname)) {
    throw new Error(`refusing to fetch internal host ${hostname}`);
  }
  let addrs: { address: string }[];
  try {
    addrs = await dns.lookup(hostname, { all: true });
  } catch {
    throw new Error(`could not resolve ${hostname}`);
  }
  if (addrs.length === 0) throw new Error(`no DNS records for ${hostname}`);
  for (const a of addrs) {
    if (isBlockedIp(a.address)) {
      throw new Error(`refusing to fetch ${hostname} -> private/reserved ${a.address}`);
    }
  }
}

/** Validate scheme + SSRF-guard the host for a single URL. */
async function assertUrlAllowed(u: URL): Promise<void> {
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    throw new Error(`unsupported URL scheme: ${u.protocol}`);
  }
  await assertHostAllowed(u.hostname);
}

/**
 * Fetch one URL's HTML following redirects manually (each hop SSRF-checked),
 * bounded by a timeout and a byte cap. Returns the final HTML + resolved URL.
 */
export async function safeFetchHtml(
  rawUrl: string,
): Promise<{ url: string; html: string }> {
  const withScheme = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;
  let current = new URL(withScheme);

  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    await assertUrlAllowed(current);
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(current.toString(), {
        redirect: "manual",
        signal: ac.signal,
        headers: { "User-Agent": USER_AGENT, Accept: "text/html,application/xhtml+xml" },
      });

      // Manual redirect handling so every Location is re-validated against SSRF.
      if (res.status >= 300 && res.status < 400) {
        const loc = res.headers.get("location");
        if (!loc) throw new Error(`redirect with no Location from ${current}`);
        current = new URL(loc, current);
        continue;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${current}`);
      const html = await readCapped(res, MAX_BYTES);
      return { url: current.toString(), html };
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error(`too many redirects (> ${MAX_REDIRECTS}) starting at ${rawUrl}`);
}

/** Read a response body as text, stopping once MAX_BYTES is exceeded. */
async function readCapped(res: Response, maxBytes: number): Promise<string> {
  const body = res.body;
  if (!body) return await res.text();
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      total += value.length;
      if (total >= maxBytes) {
        await reader.cancel();
        break;
      }
    }
  }
  return new TextDecoder("utf-8").decode(concat(chunks));
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

/**
 * Reduce HTML to readable text: drop scripts/styles/nav noise, strip tags,
 * decode the handful of common entities, and collapse whitespace. Pure
 * (exported for tests). Not a full Markdown converter — Claude reads prose fine.
 */
export function htmlToText(html: string): string {
  let s = html;
  // Remove elements whose text is noise for profiling.
  s = s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ");
  s = s.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ");
  s = s.replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, " ");
  s = s.replace(/<svg\b[^>]*>[\s\S]*?<\/svg>/gi, " ");
  s = s.replace(/<!--[\s\S]*?-->/g, " ");
  // Keep the <title> as a leading line (often the brand + tagline).
  const title = s.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim();
  // Block elements -> newlines so sentences don't run together.
  s = s.replace(/<\/(p|div|section|li|h[1-6]|tr|br)\s*>/gi, "\n");
  s = s.replace(/<br\s*\/?>/gi, "\n");
  // Strip all remaining tags.
  s = s.replace(/<[^>]+>/g, " ");
  // Decode common entities.
  s = s
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'");
  // Collapse whitespace, keeping line breaks.
  s = s.replace(/[ \t\f\v]+/g, " ").replace(/\s*\n\s*/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  const out = title ? `${title}\n\n${s}` : s;
  return out.length > MAX_TEXT_CHARS ? out.slice(0, MAX_TEXT_CHARS) : out;
}

/**
 * Pick one same-origin pricing/comparison/about link from a page's HTML to fetch
 * as a second page (better competitor/claim signal). Pure (exported for tests).
 */
export function pickSecondaryUrl(html: string, baseUrl: string): string | null {
  const base = new URL(baseUrl);
  const hrefs = [...html.matchAll(/<a\b[^>]*\bhref=["']([^"']+)["']/gi)].map((m) => m[1]);
  for (const href of hrefs) {
    if (!href || !SECONDARY_LIKE.test(href)) continue;
    let abs: URL;
    try {
      abs = new URL(href, base);
    } catch {
      continue;
    }
    if (abs.hostname !== base.hostname) continue; // same-origin only
    if (abs.pathname === base.pathname) continue; // not the homepage again
    return abs.toString();
  }
  return null;
}

/** Build the labeled text Claude reads (mirrors crawl4ai's labeled markdown). */
export function buildExtractionInput(pages: LabeledText[]): string {
  return pages.map((p) => `## ${p.url}\n\n${p.text}`).join("\n\n---\n\n");
}

export class FetchClaudeResolver implements Resolver {
  async resolve(url: string): Promise<CompanyProfile> {
    const home = await safeFetchHtml(url);
    const pages: LabeledText[] = [{ url: home.url, text: htmlToText(home.html) }];

    // Best-effort second page — never let it fail the run.
    const secondary = pickSecondaryUrl(home.html, home.url);
    if (secondary) {
      try {
        const p = await safeFetchHtml(secondary);
        pages.push({ url: p.url, text: htmlToText(p.html) });
      } catch {
        /* ignore — the homepage alone is enough to profile */
      }
    }

    const usable = pages.filter((p) => p.text.trim().length > 0);
    if (usable.length === 0) {
      throw new Error(`no readable text extracted from ${url} (JS-only page? try crawl4ai)`);
    }

    const extracted = await extractJson<ExtractedProfile>(
      PROFILE_SYSTEM_PROMPT,
      buildExtractionInput(usable),
      PROFILE_SCHEMA as unknown as Record<string, unknown>,
    );

    return buildProfile(url, extracted, claudeModel());
  }
}
