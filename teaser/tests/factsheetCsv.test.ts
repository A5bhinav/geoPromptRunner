/**
 * F2 — the `fact` block in the audit CSV, and the sheet's survival across
 * regeneration (docs/factsheet-autogen-plan.md §10, C7/C8).
 *
 * Two properties this file exists to hold:
 *
 * 1. **A run with no sheet is byte-identical to the pre-F2 CSV.** The consumer ICP
 *    is still live and the platform parses both shapes; `factClaims` is additive or
 *    it is a regression. The expected string below is pinned, not derived.
 * 2. **A regenerated teaser keeps its sheet.** The stored ReportPayload carries the
 *    accuracy flags a sheet produced but not the sheet itself, so without
 *    persistence the reference those flags were graded against disappears on the
 *    regenerate path — the same silent drop already patched for aliases (T3).
 *
 * Pure — no network, no LLM, no platform.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { buildAuditCsv, type AuditCsvOptions } from "../src/platform/csv.ts";
import { profileFromStored, regenerateFromDraft } from "../src/pipeline.ts";
import type {
  CompanyProfile,
  FactClaimRow,
  Finding,
  GeneratedQuerySet,
  TeaserDraft,
} from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload } from "../src/types/platform.ts";

function profile(over: Partial<CompanyProfile> = {}): CompanyProfile {
  return {
    url: "https://acmering.io",
    name: "Acme Ring",
    aliases: [],
    category: "sleep-tracking smart ring",
    competitors: [
      { name: "Oura", aliases: [], confirmed: true },
      { name: "Whoop", aliases: [], confirmed: true },
    ],
    clientDomains: ["acmering.io"],
    productClaims: [],
    resolvedAt: "2026-06-22T00:00:00.000Z",
    resolverModel: "mock",
    ...over,
  };
}

const QUERY_SET: GeneratedQuerySet = {
  version: "v1",
  queries: [
    { query_id: "q1", text: "best smart ring", intent: "category", weight: 1, persona: null },
  ],
};

const CSV_OPTIONS: AuditCsvOptions = { engines: ["openai"], runsPerQuery: 3, judge: true };

/**
 * The sheet-less consumer CSV, pinned character for character. Captured from the
 * PRE-F2 emitter (`git show HEAD:teaser/src/platform/csv.ts`) and typed out here
 * rather than derived from the current one — a pin computed from the code it
 * guards proves nothing. Every row carries the two trailing empty columns; the
 * schema is five-wide whether or not intent/persona apply.
 */
const PRE_F2_CSV = [
  "block,key,value,intent,persona",
  "config,client_name,Acme Ring,,",
  "config,category,sleep-tracking smart ring,,",
  "config,client_domains,acmering.io,,",
  "config,competitors,Oura;Whoop,,",
  "config,engines,openai,,",
  "config,runs_per_query,3,,",
  "config,judge,true,,",
  "query,q1,best smart ring,category,",
  "",
].join("\n");

function csvFor(factClaims?: FactClaimRow[]): string {
  return buildAuditCsv(
    factClaims === undefined ? profile() : profile({ factClaims }),
    QUERY_SET,
    CSV_OPTIONS,
  );
}

// --- 1. additive or nothing --------------------------------------------------------

test("a profile with no fact sheet emits exactly the pre-F2 CSV", () => {
  assert.equal(csvFor(), PRE_F2_CSV);
});

test("an EMPTY fact sheet is also byte-identical — no header, no blank row", () => {
  // An extraction pass that grounded nothing must cost the CSV nothing: blank is the
  // safe default (§4.2), and a stray row would change what the platform parses.
  assert.equal(csvFor([]), PRE_F2_CSV);
});

// --- 2. the fact block --------------------------------------------------------------

const SHEET: FactClaimRow[] = [
  // A comma in the value: "," stays the CSV column delimiter, so the cell is quoted.
  { key: "pricing", value: "$299 one-time, no subscription" },
  { key: "battery_life", value: "Up to 7 days on a charge" },
  // A quote in the value: doubled, and the whole cell quoted.
  { key: "warranty", value: 'The site says "1-year limited warranty"' },
];

test("fact rows are emitted as fact,<key>,<value>,, with correct quoting", () => {
  const lines = csvFor(SHEET).split("\n");

  assert.ok(lines.includes('fact,pricing,"$299 one-time, no subscription",,'));
  assert.ok(lines.includes("fact,battery_life,Up to 7 days on a charge,,"));
  assert.ok(lines.includes('fact,warranty,"The site says ""1-year limited warranty""",,'));
});

test("fact rows sit after the config block and before the query block", () => {
  const lines = csvFor(SHEET).split("\n");
  const lastConfig = lines.findLastIndex((l) => l.startsWith("config,"));
  const firstFact = lines.findIndex((l) => l.startsWith("fact,"));
  const lastFact = lines.findLastIndex((l) => l.startsWith("fact,"));
  const firstQuery = lines.findIndex((l) => l.startsWith("query,"));

  assert.ok(lastConfig < firstFact, "config must come first");
  assert.ok(lastFact < firstQuery, "queries must come last");
  // Sheet order is preserved: the platform joins the rows in file order into one
  // fact-sheet block, so a reordering emitter would reorder the judge's reference.
  assert.deepEqual(
    lines.filter((l) => l.startsWith("fact,")).map((l) => l.split(",")[1]),
    ["pricing", "battery_life", "warranty"],
  );
});

test("the config block is untouched by the presence of a sheet", () => {
  const configOf = (csv: string) =>
    csv.split("\n").filter((l) => l.startsWith("config,"));
  assert.deepEqual(configOf(csvFor(SHEET)), configOf(csvFor()));
});

// --- 3. the "location" substring collision ------------------------------------------

test('a fact value containing "location" adds no config,location row', () => {
  // consumerPathRegression.test.ts:252 asserts `!csv.includes("location")` over the
  // WHOLE CSV. What W1.4 actually guarantees is narrower — a consumer product emits
  // no `config,location` row — but the assertion is a substring check, so ANY fact
  // key or value containing that substring trips it even on the consumer path.
  //
  // That lock stays as it is: it guards a claim about the SEARCH ORIGIN, and
  // loosening it to inspect only config rows would let a real regression through.
  // The consequence is a constraint on fixtures, not on the emitter — a consumer
  // fixture in that file must carry no sheet (none does), and MockResolver's
  // placeholder sheet deliberately avoids the word. This test pins the property the
  // regression lock is really about, so the collision is documented rather than
  // discovered.
  const csv = csvFor([{ key: "service_area", value: "One location, in Berkeley" }]);

  assert.ok(csv.includes('fact,service_area,"One location, in Berkeley",,'));
  assert.ok(csv.includes("location"), "the substring is present — by way of a fact row");
  assert.ok(
    !csv.split("\n").some((l) => l.startsWith("config,location")),
    "no location row may appear for a product, whatever a fact row says",
  );
});

// --- 4. C8: regeneration keeps the sheet ---------------------------------------------

function baseReport(): ReportPayload {
  return {
    client_name: "Acme",
    run_date: "2026-06-20",
    query_set_version: "t",
    runs_per_query: 1,
    engines: ["perplexity", "openai"],
    competitors: ["YNAB"],
    client_domains: ["acme.io"],
    detection: "judge",
    scorecard: {
      visibility_grade: null,
      share_of_model_client: 0,
      top_competitor: "YNAB",
      top_competitor_share: 1,
      mention_rate_client: 0,
      mention_rate_top_competitor: 1,
      citation_rate_client: 0,
      accuracy_assessed: false,
      accuracy_flag_count: null,
    },
    leaderboard: [],
    by_bucket: [],
    accuracy_flags: [],
    sources: [],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "YNAB" },
    ],
  };
}

function answers(): AnswerRecord[] {
  return [
    {
      query_id: "q1",
      intent: "category",
      prompt: "best budgeting app?",
      engine_name: "openai",
      run_index: 0,
      response: "YNAB is the top pick.",
      citations: [],
      timestamp: "t",
    },
  ];
}

const staleLead: Finding = {
  role: "lead",
  source: "losing_query",
  queryId: "old",
  intent: "comparison",
  engineName: "perplexity",
  competitor: "Stale",
  prominence: null,
  verbatimQuery: "old query",
  verbatimAnswer: "old answer",
  citations: [],
  rankScore: 0,
  runsObserved: 1,
  runsConfirming: 1,
};

function savedDraft(over: Partial<TeaserDraft> = {}): TeaserDraft {
  return {
    prospectUrl: "https://acme.io",
    companyName: "Acme",
    category: "budgeting app",
    runDate: "2026-06-20",
    heroEngine: "perplexity",
    headline: "OLD HEADLINE",
    leadSentence: "old lead",
    headlineNumber: { companyAppears: 9, competitorAppears: 9, competitorName: "Stale", n: 9 },
    stakesLine: "old stakes",
    cta: "old cta",
    lead: staleLead,
    table: [],
    report: baseReport(),
    answers: answers(),
    status: "draft",
    ...over,
  };
}

test("a regenerated teaser keeps its fact sheet (C8)", () => {
  const r = regenerateFromDraft(savedDraft({ factClaims: SHEET }));
  assert.equal(r.ok, true);
  if (!r.ok) return;
  assert.deepEqual(r.draft.factClaims, SHEET);
});

test("regeneration is idempotent on the sheet — a second pass still carries it", () => {
  // The regenerate path feeds its own output back in when a teaser is re-rendered
  // more than once; a sheet that survived one hop but not two would be worse than
  // one that never persisted, because the loss would depend on render count.
  const first = regenerateFromDraft(savedDraft({ factClaims: SHEET }));
  assert.equal(first.ok, true);
  if (!first.ok) return;
  const second = regenerateFromDraft(first.draft);
  assert.equal(second.ok, true);
  if (!second.ok) return;
  assert.deepEqual(second.draft.factClaims, SHEET);
});

test("a draft with no sheet regenerates with no sheet — absent stays absent", () => {
  const r = regenerateFromDraft(savedDraft());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  assert.equal(r.draft.factClaims, undefined);
});

test("profileFromStored rehydrates the sheet, so a re-submitted CSV still carries it", () => {
  const p = profileFromStored(baseReport(), {
    url: "https://acme.io",
    category: "budgeting app",
    factClaims: SHEET,
  });
  assert.deepEqual(p.factClaims, SHEET);
  assert.ok(buildAuditCsv(p, QUERY_SET, CSV_OPTIONS).includes("fact,battery_life,"));

  // ...and omitting it leaves the rebuilt profile sheet-less rather than empty.
  const bare = profileFromStored(baseReport(), {
    url: "https://acme.io",
    category: "budgeting app",
  });
  assert.equal(bare.factClaims, undefined);
});
