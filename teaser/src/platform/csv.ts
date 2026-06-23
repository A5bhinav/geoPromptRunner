/**
 * Builds the platform's audit-input CSV (src/prompts/csv_loader.py format):
 *   block,key,value,intent,persona
 * where block ∈ { config, fact, query }.
 *
 * config rows carry client_name/category/competitors/client_domains/engines/
 * runs_per_query/judge. query rows carry the buyer query text + intent + persona.
 * fact rows (optional) build the fact sheet for the wrong-claim branch.
 */

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

  // --- query block ---
  for (const q of querySet.queries) {
    lines.push(row("query", q.query_id, q.text, q.intent, q.persona ?? ""));
  }

  return lines.join("\n") + "\n";
}
