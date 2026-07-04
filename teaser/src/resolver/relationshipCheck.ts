/**
 * Competitor relationship guard.
 *
 * The resolver (an LLM reading the prospect's site) can only know competitors as
 * of its training cutoff. A "competitor" that has since ACQUIRED, MERGED WITH,
 * or IS THE SAME COMPANY AS the client makes the whole teaser premise false —
 * observed live 2026-07-03: a Cal AI teaser led with "AI sends your buyers to
 * MyFitnessPal, not Cal AI" AFTER MyFitnessPal acquired Cal AI. Neither the
 * defunct-brand filter nor the honest-hero gate catches this — it needs CURRENT
 * web knowledge. So this module web-searches each competitor's relationship to
 * the client and drops any that are corporately entangled with it.
 *
 * The LLM/web call lives in `checkCompetitorRelationships`; everything else is
 * pure (`normalizeRelationships`, `pruneRelatedCompetitors`) and unit-tested.
 * `relationshipGuard` wires them together, logs drops, and is RECALL-SAFE: on
 * any failure it keeps all competitors and warns — the human confirm gate stays
 * the final backstop (never `--yes` a real send).
 */

import { researchJson } from "../llm/claude.ts";
import type { CompanyProfile, Competitor } from "../types/domain.ts";

export type RelationshipVerdict =
  | "independent" // separate companies, genuine rivals — keep
  | "competitor_acquired_client" // the competitor now owns the client — DROP
  | "client_acquired_competitor" // the client now owns the competitor — DROP
  | "same_company" // merger / rebrand / one entity — DROP
  | "unknown"; // no reliable evidence — keep (recall-safe)

export interface CompetitorRelationship {
  competitor: string;
  verdict: RelationshipVerdict;
  evidence: string;
}

export interface DroppedCompetitor {
  name: string;
  verdict: RelationshipVerdict;
  evidence: string;
}

const DROP_VERDICTS: ReadonlySet<RelationshipVerdict> = new Set<RelationshipVerdict>([
  "competitor_acquired_client",
  "client_acquired_competitor",
  "same_company",
]);

/** A competitor with this verdict cannot honestly appear in the teaser. */
export function isRelatedVerdict(v: RelationshipVerdict): boolean {
  return DROP_VERDICTS.has(v);
}

function describeVerdict(v: RelationshipVerdict): string {
  switch (v) {
    case "competitor_acquired_client":
      return "it ACQUIRED / now owns the client";
    case "client_acquired_competitor":
      return "the client acquired / now owns it";
    case "same_company":
      return "it is the same company (merger / rebrand)";
    default:
      return v;
  }
}

const SYSTEM_PROMPT = `You verify whether a company's listed "competitors" are genuinely independent rivals, or whether a corporate relationship makes a competitive comparison invalid. This gates a competitive-visibility teaser: naming a competitor that ACQUIRED, OWNS, MERGED WITH, or IS THE SAME COMPANY AS the client would be embarrassing and factually wrong.

Use web search to check CURRENT ownership (as of today). Acquisitions and mergers can be very recent — rely on what search returns, not on prior assumptions.

For each competitor, classify its relationship TO THE CLIENT:
- "independent": separate companies and genuine rivals (the normal case)
- "competitor_acquired_client": the competitor acquired or now owns the client
- "client_acquired_competitor": the client acquired or now owns the competitor
- "same_company": the same entity, a merger of the two, or one is a rebrand of the other
- "unknown": you could not find reliable evidence either way

Only use a verdict other than "independent" or "unknown" when search results CLEARLY support it. When unsure, use "unknown" — it will be kept. Put the source domain in "evidence".

Return ONLY a JSON array, one object per competitor:
[{"competitor": "<name exactly as given>", "verdict": "<one of the five>", "evidence": "<one line incl. source>"}]`;

function userPrompt(profile: CompanyProfile): string {
  const comps = profile.competitors.map((c) => c.name).join(", ");
  return [
    `Client company: ${profile.name} (${profile.url})`,
    `Category: ${profile.category}`,
    `Competitors to check: ${comps}`,
    "",
    `For EACH competitor above, determine its current corporate relationship to ${profile.name}. Return the JSON array only.`,
  ].join("\n");
}

function coerceVerdict(v: unknown): RelationshipVerdict {
  const s = typeof v === "string" ? v.trim().toLowerCase() : "";
  if (
    s === "independent" ||
    s === "competitor_acquired_client" ||
    s === "client_acquired_competitor" ||
    s === "same_company"
  ) {
    return s;
  }
  return "unknown";
}

/**
 * Turn the model's raw JSON into one validated verdict per profile competitor.
 * Pure. Names are matched back to the profile case-insensitively (so an
 * unknown/hallucinated name is ignored), and any competitor the model omitted
 * defaults to "unknown" (kept) — the guard never drops on missing data.
 */
export function normalizeRelationships(
  raw: unknown,
  profile: CompanyProfile,
): CompetitorRelationship[] {
  const canonicalByLower = new Map(
    profile.competitors.map((c) => [c.name.toLowerCase(), c.name]),
  );
  const out: CompetitorRelationship[] = [];
  const seen = new Set<string>();

  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== "object") continue;
      const r = item as Record<string, unknown>;
      const nameRaw = typeof r.competitor === "string" ? r.competitor.trim() : "";
      const canonical = canonicalByLower.get(nameRaw.toLowerCase());
      if (!canonical || seen.has(canonical)) continue;
      seen.add(canonical);
      out.push({
        competitor: canonical,
        verdict: coerceVerdict(r.verdict),
        evidence: typeof r.evidence === "string" ? r.evidence.trim() : "",
      });
    }
  }

  for (const c of profile.competitors) {
    if (!seen.has(c.name)) {
      out.push({ competitor: c.name, verdict: "unknown", evidence: "no verdict returned" });
    }
  }
  return out;
}

/**
 * Remove competitors whose verdict is a corporate-entanglement one. Pure.
 * Returns the (possibly unchanged) profile plus what was dropped, so the caller
 * can surface it. Independent AND unknown verdicts are kept.
 */
export function pruneRelatedCompetitors(
  profile: CompanyProfile,
  relationships: readonly CompetitorRelationship[],
): { profile: CompanyProfile; dropped: DroppedCompetitor[] } {
  const byLower = new Map(relationships.map((r) => [r.competitor.toLowerCase(), r]));
  const kept: Competitor[] = [];
  const dropped: DroppedCompetitor[] = [];

  for (const c of profile.competitors) {
    const r = byLower.get(c.name.toLowerCase());
    if (r && isRelatedVerdict(r.verdict)) {
      dropped.push({ name: c.name, verdict: r.verdict, evidence: r.evidence });
    } else {
      kept.push(c);
    }
  }

  if (dropped.length === 0) return { profile, dropped };
  return { profile: { ...profile, competitors: kept }, dropped };
}

/** Web-search the relationship of every competitor to the client. */
export async function checkCompetitorRelationships(
  profile: CompanyProfile,
  opts: { model?: string } = {},
): Promise<CompetitorRelationship[]> {
  if (profile.competitors.length === 0) return [];
  const raw = await researchJson<unknown>(SYSTEM_PROMPT, userPrompt(profile), {
    model: opts.model,
    // A couple of searches per competitor, capped.
    maxSearches: Math.min(2 + profile.competitors.length, 8),
  });
  return normalizeRelationships(raw, profile);
}

/**
 * Check + prune + log, recall-safe. Returns the profile with entangled
 * competitors removed. On any error it returns the profile UNCHANGED and warns
 * loudly — a network blip must not silently strip the competitor set, and the
 * human confirm gate remains the backstop.
 */
export async function relationshipGuard(
  profile: CompanyProfile,
  log: (msg: string) => void,
  opts: { model?: string } = {},
): Promise<CompanyProfile> {
  if (profile.competitors.length === 0) return profile;

  let relationships: CompetitorRelationship[];
  try {
    relationships = await checkCompetitorRelationships(profile, opts);
  } catch (err) {
    log(
      `  ⚠️  competitor relationship check failed (${
        err instanceof Error ? err.message : String(err)
      }) — keeping all competitors; verify ownership manually before sending.`,
    );
    return profile;
  }

  const { profile: pruned, dropped } = pruneRelatedCompetitors(profile, relationships);
  for (const d of dropped) {
    log(
      `  ⚠️  dropped competitor "${d.name}" — ${describeVerdict(d.verdict)}${
        d.evidence ? ` (${d.evidence})` : ""
      }. Not a valid rival for this teaser.`,
    );
  }
  if (dropped.length > 0 && pruned.competitors.length === 0) {
    log(
      `  ⚠️  every competitor was dropped as corporately tied to ${profile.name} — there is no independent rival to build a teaser against.`,
    );
  }
  return pruned;
}
