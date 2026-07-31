/**
 * Builds the platform's audit-input CSV (src/prompts/csv_loader.py format):
 *   block,key,value,intent,persona
 * where block ∈ { config, fact, query }.
 *
 * config rows carry client_name/category/competitors/client_domains/engines/
 * runs_per_query/judge. query rows carry the buyer query text + intent + persona.
 * fact rows (optional) build the fact sheet for the wrong-claim branch.
 */

import { canonicalLocation } from "../types/domain.ts";
import type { CompanyProfile, GeneratedQuerySet } from "../types/domain.ts";

function csvCell(value: string): string {
  // Quote if the value contains comma, quote, or newline; double internal quotes.
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function row(block: string, key: string, value: string, intent = "", persona = ""): string {
  return [block, key, value, intent, persona].map(csvCell).join(",");
}

export interface AuditCsvOptions {
  engines: string[];
  runsPerQuery: number;
  judge: boolean;
}

export function buildAuditCsv(
  profile: CompanyProfile,
  querySet: GeneratedQuerySet,
  opts: AuditCsvOptions,
): string {
  const lines: string[] = ["block,key,value,intent,persona"];

  // --- config block ---
  // Multi-value cells use ";" as the in-cell separator (the platform's
  // csv_loader _LIST_SEP); "," stays the CSV column delimiter.
  lines.push(row("config", "client_name", profile.name));
  lines.push(row("config", "category", profile.category));
  lines.push(row("config", "client_domains", profile.clientDomains.join(";")));
  lines.push(
    row("config", "competitors", profile.competitors.map((c) => c.name).join(";")),
  );
  lines.push(row("config", "engines", opts.engines.join(";")));
  lines.push(row("config", "runs_per_query", String(opts.runsPerQuery)));
  lines.push(row("config", "judge", opts.judge ? "true" : "false"));
  // Emitted ONLY for service-area businesses (W1.4). A consumer product has no
  // location, so its CSV is byte-identical to the pre-pivot one and the platform
  // parses it exactly as before.
  if (profile.location) {
    lines.push(row("config", "location", canonicalLocation(profile.location)));
  }

  // --- fact block ---
  // Emitted only when the profile actually carries a sheet, so a run without one is
  // byte-identical to the pre-F2 CSV — the consumer path (and its regression lock)
  // never sees a new row, and blank stays the safe default (plan §4.2).
  //
  // Between config and query because that is csv_loader's _BLOCKS order and how a
  // human reads an audit CSV; the parser itself routes on the block column, so
  // position is presentation, not contract.
  //
  // Keys go out verbatim. §2.1 forbids a keyless row (the platform would fall back
  // to the bare value and lose the section signal), but the guarantee belongs to the
  // generator that builds the sheet — dropping one here would hide that bug rather
  // than surface it.
  for (const fact of profile.factClaims ?? []) {
    lines.push(row("fact", fact.key, fact.value));
  }

  // --- query block ---
  for (const q of querySet.queries) {
    lines.push(row("query", q.query_id, q.text, q.intent, q.persona ?? ""));
  }

  return lines.join("\n") + "\n";
}
