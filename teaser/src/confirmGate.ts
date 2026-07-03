/**
 * Interactive confirm gate over the resolved profile + generated query set —
 * the human check BUILD_PLAN.md §7 #7 requires before a teaser audit runs.
 *
 * The riskiest LLM output is the competitor list (a wrong competitor becomes a
 * false claim in a sent teaser), so the gate centers on it: show what the
 * resolver extracted, let the reviewer keep/drop competitors or abort, and mark
 * the kept ones `confirmed: true`. Dropping a competitor also drops the
 * already-generated queries that name it — the query set was built from the
 * unconfirmed profile, so a stale rival would otherwise still reach the engines.
 *
 * Split into a pure core (`applySelection`, `parseSelection` — tested) and a
 * thin readline wrapper (`interactiveConfirm` — wired by the CLI in TTY mode).
 */

import readline from "node:readline/promises";
import type { CompanyProfile, GeneratedQuerySet } from "./types/domain.ts";

export type ConfirmDecision =
  | { kind: "all" }
  | { kind: "abort" }
  | { kind: "keep"; indices: number[] } // 0-based into profile.competitors
  | { kind: "invalid"; reason: string };

/**
 * Parse one line of reviewer input against the competitor list.
 *   ""/"y"/"yes"  -> keep all;  "n"/"no" -> abort;
 *   "1,3"         -> keep competitors 1 and 3 (1-based, as displayed).
 */
export function parseSelection(input: string, competitorCount: number): ConfirmDecision {
  const s = input.trim().toLowerCase();
  if (s === "" || s === "y" || s === "yes") return { kind: "all" };
  if (s === "n" || s === "no") return { kind: "abort" };
  const parts = s.split(/[\s,]+/).filter(Boolean);
  const indices: number[] = [];
  for (const p of parts) {
    const n = Number(p);
    if (!Number.isInteger(n) || n < 1 || n > competitorCount) {
      return { kind: "invalid", reason: `"${p}" is not a competitor number (1-${competitorCount})` };
    }
    if (!indices.includes(n - 1)) indices.push(n - 1);
  }
  if (indices.length === 0) return { kind: "invalid", reason: "no competitors selected" };
  return { kind: "keep", indices };
}

/** Case-insensitive whole-word test for a competitor name/alias in query text. */
function mentions(text: string, needle: string): boolean {
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`, "i").test(text);
}

export interface AppliedSelection {
  profile: CompanyProfile;
  querySet: GeneratedQuerySet;
  /** Query texts removed because they named a dropped competitor. */
  droppedQueries: string[];
}

/**
 * Apply a keep-set to the profile (kept competitors become confirmed) and prune
 * queries that name a dropped competitor by name or alias.
 */
export function applySelection(
  profile: CompanyProfile,
  querySet: GeneratedQuerySet,
  keepIndices: number[],
): AppliedSelection {
  const keep = new Set(keepIndices);
  const kept = profile.competitors
    .filter((_, i) => keep.has(i))
    .map((c) => ({ ...c, confirmed: true }));
  const dropped = profile.competitors.filter((_, i) => !keep.has(i));

  const droppedNeedles = dropped.flatMap((c) => [c.name, ...c.aliases]).filter(Boolean);
  const droppedQueries: string[] = [];
  const queries = querySet.queries.filter((q) => {
    const hit = droppedNeedles.some((needle) => mentions(q.text, needle));
    if (hit) droppedQueries.push(q.text);
    return !hit;
  });

  return {
    profile: { ...profile, competitors: kept },
    querySet: { ...querySet, queries },
    droppedQueries,
  };
}

/** Everything confirmed as-is — all competitors marked reviewed. */
export function confirmAll(
  profile: CompanyProfile,
  querySet: GeneratedQuerySet,
): { profile: CompanyProfile; querySet: GeneratedQuerySet } {
  return {
    profile: {
      ...profile,
      competitors: profile.competitors.map((c) => ({ ...c, confirmed: true })),
    },
    querySet,
  };
}

function render(profile: CompanyProfile, querySet: GeneratedQuerySet): string {
  const lines: string[] = [];
  lines.push(`\nResolved profile — review before the audit spends engine calls:`);
  lines.push(`  company    : ${profile.name} (${profile.url})`);
  lines.push(`  category   : ${profile.category}`);
  lines.push(`  domains    : ${profile.clientDomains.join(", ") || "(none)"}`);
  lines.push(`  competitors:`);
  profile.competitors.forEach((c, i) => {
    const aliases = c.aliases.length ? ` (aka ${c.aliases.join(", ")})` : "";
    lines.push(`    ${i + 1}. ${c.name}${aliases}`);
  });
  lines.push(`  queries (${querySet.queries.length}):`);
  for (const q of querySet.queries) {
    lines.push(`    [${q.intent}] ${q.text}`);
  }
  return lines.join("\n");
}

/**
 * The pipeline `confirm` hook: print the profile + queries, prompt on the TTY,
 * and return the (possibly pruned) inputs — or null to abort the run.
 */
export async function interactiveConfirm(
  profile: CompanyProfile,
  querySet: GeneratedQuerySet,
): Promise<{ profile: CompanyProfile; querySet: GeneratedQuerySet } | null> {
  console.log(render(profile, querySet));
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  try {
    for (;;) {
      const answer = await rl.question(
        `\nProceed? [Y]es / [n]o / numbers of competitors to KEEP (e.g. 1,3): `,
      );
      const decision = parseSelection(answer, profile.competitors.length);
      if (decision.kind === "abort") return null;
      if (decision.kind === "all") return confirmAll(profile, querySet);
      if (decision.kind === "keep") {
        const applied = applySelection(profile, querySet, decision.indices);
        if (applied.droppedQueries.length) {
          console.log(
            `  dropped ${applied.droppedQueries.length} quer${applied.droppedQueries.length === 1 ? "y" : "ies"} naming removed competitor(s):`,
          );
          for (const q of applied.droppedQueries) console.log(`    - ${q}`);
        }
        if (applied.querySet.queries.length === 0) {
          console.log(`  ✗ that selection leaves no queries to run — pick again or abort.`);
          continue;
        }
        return { profile: applied.profile, querySet: applied.querySet };
      }
      console.log(`  ✗ ${decision.reason}`);
    }
  } finally {
    rl.close();
  }
}
