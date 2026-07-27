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
import { businessKindOf } from "./profileExtraction.ts";
import type { CompanyProfile, Competitor } from "../types/domain.ts";

export type RelationshipVerdict =
  | "independent" // separate companies, genuine rivals — keep
  | "competitor_acquired_client" // the competitor now owns the client — DROP
  | "client_acquired_competitor" // the client now owns the competitor — DROP
  | "same_company" // merger / rebrand / one entity — DROP
  | "unknown"; // no reliable evidence — keep (recall-safe)

/**
 * Whether a "competitor" is a DIRECT SUBSTITUTE in the client's specific category
 * (audit C3). An off-category brand (a general fitness tracker seeded as a rival
 * for a strength-training wearable) makes the comparison invalid the same way an
 * acquirer does. Recall-safe: only "different_category" drops; unknown is kept.
 */
export type CategoryVerdict = "same_category" | "different_category" | "unknown";

/**
 * Whether a competitor serves the SAME market as a service-area client (W2.5).
 *
 * `CategoryVerdict` has no geography: a Phoenix plumber and a Boston plumber are both
 * `same_category` and both pass. For a local business that comparison is meaningless —
 * a customer in Berkeley will never choose between them.
 *
 * Recall-safe, matching the posture of every other verdict here: only a clear
 * `different_area` drops; `unknown` is kept and the human confirm gate catches the
 * rest. **Only ever computed for local_service clients** — a nationally-marketed
 * product has no service area, so running this on one would drop legitimate rivals on
 * a dimension that does not apply.
 */
export type ServiceAreaVerdict = "same_area" | "different_area" | "unknown";

export interface CompetitorRelationship {
  competitor: string;
  verdict: RelationshipVerdict;
  evidence: string;
  /** Same-specific-category judgment (audit C3). Optional/legacy → unknown (kept). */
  categoryMatch?: CategoryVerdict;
  /**
   * Same-service-area judgment (W2.5). Only populated for local_service clients;
   * absent/legacy → unknown (kept), so the consumer path is untouched.
   */
  serviceAreaMatch?: ServiceAreaVerdict;
}

export interface DroppedCompetitor {
  name: string;
  verdict: RelationshipVerdict;
  evidence: string;
  /** True when the drop reason was an off-category rival, not a corporate tie. */
  categoryMismatch?: boolean;
  /** True when the drop reason was a different service area (W2.5, local only). */
  serviceAreaMismatch?: boolean;
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

const CONSUMER_SYSTEM_PROMPT = `You verify whether a company's listed "competitors" are genuinely independent rivals in the SAME product category, or whether a corporate relationship OR a category mismatch makes a competitive comparison invalid. This gates a competitive-visibility teaser: naming a competitor that ACQUIRED, OWNS, MERGED WITH, or IS THE SAME COMPANY AS the client — or that is really a DIFFERENT product category (not a direct substitute) — would be embarrassing and factually wrong.

Use web search to check CURRENT ownership (as of today). Acquisitions and mergers can be very recent — rely on what search returns, not on prior assumptions.

For each competitor, classify its relationship TO THE CLIENT:
- "independent": separate companies and genuine rivals (the normal case)
- "competitor_acquired_client": the competitor acquired or now owns the client
- "client_acquired_competitor": the client acquired or now owns the competitor
- "same_company": the same entity, a merger of the two, or one is a rebrand of the other
- "unknown": you could not find reliable evidence either way

ALSO classify whether it is in the client's SPECIFIC category (a direct substitute a buyer would cross-shop against the client), given the client's category below:
- "same_category": a direct substitute in the same specific category
- "different_category": clearly a different product category (e.g. a general fitness tracker vs a strength-training wearable) — not a real head-to-head
- "unknown": not sure

Only use a verdict other than "independent"/"unknown" (or a category other than "same_category"/"unknown") when search results CLEARLY support it. When unsure, use "unknown" — it will be KEPT. Put the source domain in "evidence".

Return ONLY a JSON array, one object per competitor:
[{"competitor": "<name exactly as given>", "verdict": "<one of the five>", "category": "<one of the three>", "evidence": "<one line incl. source>"}]`;

/**
 * The service-area question, APPENDED for local_service clients only (W2.5).
 *
 * Forked rather than folded into the consumer prompt (pivot §0.6): asking a national
 * product's rivals about "service area" would invite spurious different_area verdicts
 * and drop legitimate competitors on a dimension that does not apply to them.
 */
const LOCAL_SERVICE_AREA_BLOCK = `

ALSO classify whether it serves the SAME LOCAL MARKET as the client. Two businesses in the same trade but different metros are NOT rivals — a customer in the client's city would never choose between them:
- "same_area": it serves the client's city or an overlapping service area
- "different_area": it clearly operates in a different metro/region
- "unknown": not sure

Add a "service_area" key to each object with one of those three values.`;

function systemPrompt(businessKind: string): string {
  return businessKind === "local_service"
    ? CONSUMER_SYSTEM_PROMPT + LOCAL_SERVICE_AREA_BLOCK
    : CONSUMER_SYSTEM_PROMPT;
}

function userPrompt(profile: CompanyProfile): string {
  const comps = profile.competitors.map((c) => c.name).join(", ");
  const loc = profile.location;
  const areaLine = loc
    ? [
        `Client's SERVICE AREA: ${loc.city}, ${loc.region}, ${loc.country}` +
          (loc.serviceArea?.length ? ` (also serves: ${loc.serviceArea.join(", ")})` : ""),
      ]
    : [];
  return [
    `Client company: ${profile.name} (${profile.url})`,
    `Client's SPECIFIC category: ${profile.category}`,
    ...areaLine,
    `Competitors to check: ${comps}`,
    "",
    `For EACH competitor above, determine (a) its current corporate relationship to ${profile.name} and (b) whether it is a direct substitute in the "${profile.category}" category. Return the JSON array only.`,
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

function coerceCategory(v: unknown): CategoryVerdict {
  const s = typeof v === "string" ? v.trim().toLowerCase() : "";
  if (s === "same_category" || s === "different_category") return s;
  return "unknown";
}

function coerceServiceArea(v: unknown): ServiceAreaVerdict {
  const s = typeof v === "string" ? v.trim().toLowerCase() : "";
  if (s === "same_area" || s === "different_area") return s;
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
        categoryMatch: coerceCategory(r.category),
        serviceAreaMatch: coerceServiceArea(r.service_area),
        evidence: typeof r.evidence === "string" ? r.evidence.trim() : "",
      });
    }
  }

  for (const c of profile.competitors) {
    if (!seen.has(c.name)) {
      out.push({
        competitor: c.name,
        verdict: "unknown",
        categoryMatch: "unknown",
        serviceAreaMatch: "unknown",
        evidence: "no verdict returned",
      });
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
    } else if (r && r.categoryMatch === "different_category") {
      // Off-category "competitor" (audit C3) — a different product category, not
      // a direct substitute. Recall-safe: only "different_category" drops here;
      // same_category and unknown are kept.
      dropped.push({ name: c.name, verdict: r.verdict, evidence: r.evidence, categoryMismatch: true });
    } else if (r && r.serviceAreaMatch === "different_area") {
      // Same trade, different metro (W2.5). A Phoenix plumber is `same_category` for
      // a Berkeley plumber and would pass the check above, but a Berkeley customer
      // will never choose between them. Only ever set for local_service clients, so
      // a national product cannot lose a rival here. Recall-safe: only an explicit
      // "different_area" drops; unknown is kept.
      dropped.push({
        name: c.name,
        verdict: r.verdict,
        evidence: r.evidence,
        serviceAreaMismatch: true,
      });
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
  const raw = await researchJson<unknown>(
    systemPrompt(businessKindOf(profile)),
    userPrompt(profile),
    {
      model: opts.model,
      // A couple of searches per competitor, capped.
      maxSearches: Math.min(2 + profile.competitors.length, 8),
    },
  );
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
    const why = d.categoryMismatch
      ? "it is a different product category (not a direct substitute)"
      : d.serviceAreaMismatch
        ? "it serves a different area (a customer here would never choose between them)"
        : describeVerdict(d.verdict);
    log(
      `  ⚠️  dropped competitor "${d.name}" — ${why}${
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
