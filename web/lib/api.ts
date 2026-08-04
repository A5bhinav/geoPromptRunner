// Typed client for the GEO Audit API. Mirrors the payloads in src/api/.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Fail fast on a misconfigured origin rather than silently POSTing uploads
// (which carry client facts/competitor data) to a bad host.
{
  let ok = false;
  try {
    const u = new URL(API_BASE);
    ok = u.protocol === "http:" || u.protocol === "https:";
  } catch {
    ok = false;
  }
  if (!ok) throw new Error(`Invalid NEXT_PUBLIC_API_URL: ${API_BASE}`);
}

// Shared API key sent on every request. Note: NEXT_PUBLIC_* ships to the browser,
// so this gates anonymous access (and pairs with the backend GEO_API_KEY); it is
// not a per-user secret. Keep the frontend itself access-controlled for real
// isolation, or proxy the API through a server route to keep the key server-side.
const API_KEY = process.env.NEXT_PUBLIC_GEO_API_KEY || "";

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return { ...(API_KEY ? { "X-API-Key": API_KEY } : {}), ...(extra ?? {}) };
}

async function saveBlob(res: Response, filename: string): Promise<void> {
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// --- Parse / preview types (src/prompts/csv_loader.py) ---

export interface ValidationIssue {
  message: string;
  file: string | null;
  block: string | null;
  key: string | null;
}

export interface ConfigItem {
  key: string;
  value: string;
  source_file: string;
}

export interface FactItem {
  key: string;
  value: string;
  source_file: string;
}

export interface QueryItem {
  query_id: string;
  text: string;
  intent: string;
  persona: string | null;
  source_file: string;
  valid_intent: boolean;
}

export interface FileProvenance {
  filename: string;
  n_config: number;
  n_fact: number;
  n_query: number;
  summary: string;
}

export interface ResolvedConfig {
  client_name: string;
  category: string;
  competitors: string[];
  engines: string[];
  runs_per_query: number;
  client_domains: string[];
  judge: boolean;
  fact_sheet_present: boolean;
}

export interface ParsePreview {
  ok: boolean;
  errors: ValidationIssue[];
  config: ConfigItem[];
  facts: FactItem[];
  queries: QueryItem[];
  provenance: FileProvenance[];
  config_resolved: ResolvedConfig | null;
}

// --- Run status (src/api/runner.py) ---

export interface EngineStatus {
  name: string;
  state: "running" | "done" | "failed";
  completed: number;
  total: number;
  detail: string | null;
}

export interface RunStatus {
  run_id: string;
  client_name: string;
  state: "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
  completed: number;
  total: number;
  per_engine: EngineStatus[];
  error: string | null;
}

export interface RunSummary {
  run_id: string;
  client_name: string;
  state: string;
  created_at: string;
  n_queries: number;
  engines: string[];
}

// --- Report (src/api/reports.py) ---

// THERE IS NO GradePayload. The A–F grade and the prominence-weighted composite
// behind it are gone from the backend entirely (spec TR-T0) — not unrendered,
// not optional, gone. Re-adding a type here is the first step of putting a `B−`
// back on page 1.

/** One brand's row of the competitive leaderboard, **sorted by mention rate**.
 *
 * The `visibility` column is gone with the composite that fed it: the table used
 * to print it as a decimal AND sort the client's competitive ranking by it.
 * Prominence now travels as an ordinal label plus the distribution behind it. */
export interface LeaderRow {
  brand: string;
  is_client: boolean;
  mention_rate: number;
  /** The count behind the rate. Optional so pre-TR-T0 stored runs still parse;
   * when absent the row renders its rate alone. */
  present_cells?: number;
  cells?: number;
  share_of_model: number;
  /** Median position when present, raw level + client-facing wording. Null/"—"
   * means "no typical position" (the brand appears nowhere), never "absent". */
  prominence?: string | null;
  prominence_label?: string;
  /** Cells at each of the five levels, best first. Empty on the regex path,
   * which detects presence only and cannot see position. */
  prominence_distribution?: Record<string, number>;
}

export interface BucketRow {
  bucket: string;
  mention_rate: number;
  citation_rate: number | null;
  /** Cells that returned an answer, out of cells attempted. 0 answered ⇒ render
   * "—", not "0%" — the rates above are meaningless without a denominator. */
  answered_cells?: number;
  total_cells?: number;
}

/** How reproducibly one engine returned the same client verdict across repeat runs.
 * Per engine, because the engines no longer share a sampling regime — `openai` is
 * pinned to a model that rejects `temperature` and samples at its default. Rows only
 * appear for engines whose cells actually ran twice; an absent engine means
 * "not repeated", never "perfectly stable". */
export interface StabilityRow {
  engine_name: string;
  is_measured: boolean;
  repeated_cells: number;
  /** Cells whose runs disagreed — their verdict could flip on a re-run. */
  split_cells: number;
  mean_agreement: number;
}

/** One raw flag. The appendix and the CSV export — NOT what the report renders.
 * `finding_groups` is what a client reads. */
export interface FlagRow {
  type: string;
  /** The four-level scale: critical | high | med | low. `critical` is derived in
   * Python (src/pipeline/severity.py), never emitted by the judge. */
  severity: string;
  claim: string;
  reality: string;
  query_id?: string;
  engine_name?: string;
  intent?: string;
  run_index?: number;
  observed_at?: string;
  cluster_id?: string;
  theme?: string;
}

/** A rate WITH its denominator and interval. The only shape a rate ships in.
 *
 * Render `label` ("7 of 12 runs (58%)"), not `rate`. A bare percentage off a
 * sample this size is the single most misleading thing this report could print,
 * which is why the backend pre-formats the string rather than trusting each
 * surface to remember. `n === 0` means insufficient data — never 0%. */
export interface RatePayload {
  successes: number;
  n: number;
  n_eff: number;
  rate: number;
  ci_low: number;
  ci_high: number;
  label: string;
}

/** How reproducibly a finding appeared. Both numbers or neither. */
export interface OccurrenceRow {
  observed: number;
  total: number;
  first_seen_date: string;
  last_seen_date: string;
  /** "observed in 4 of 5 runs across 06-11 → 06-13" — pre-formatted so the
   * wording cannot drift between the web report, the digest and the PDF. */
  phrase: string;
}

/** What makes a finding checkable rather than assertable. */
export interface EvidenceRow {
  /** The VERBATIM question. Never the query id. */
  prompt: string;
  /** Join keys for the drill-down fetch. NEVER rendered — `cmp-05` is the most
   * actionable data in the report made unreadable. */
  query_id?: string;
  run_index?: number;
  engine_name: string;
  /** The pinned model that answered; "" on runs stored before it was recorded. */
  model_id: string;
  intent: string;
  observed_at: string;
  /** The model's own words. Quote it; never paraphrase. */
  excerpt: string;
  /** The fact-sheet line it contradicts, verbatim. */
  reality: string;
}

/** One root cause, one card, one action. The unit the report is built from. */
export interface FindingGroupRow {
  /** The group's stable id IS the theme. Cards are themes, not claim clusters:
   * "confused with Fitbit" and "not a recognized brand" share no words and are
   * one root cause with one fix. */
  theme: string;
  theme_label: string;
  title: string;
  severity: string;
  /** Individual observations. SECONDARY — headline counts are themes. */
  instance_count: number;
  engines: string[];
  intents: string[];
  occurrence: OccurrenceRow;
  representative_claims: string[];
  /** Every distinct claim-cluster folded in — the lifecycle engine's unit. */
  member_cluster_ids: string[];
  reality: string;
  evidence: EvidenceRow[];
  /** How many observations this finding has. `evidence` is capped — a card that
   * shows 4 of 94 must say so. */
  evidence_total: number;
  fix_channel: string;
  owner: string;
  effort: string; // S | M | L
  action: string;
  verification: string;
  priority: number;
  flag_types: string[];
  /** new | persisting | resolved | regressed. "new" on a first cycle, which is
   * honest — nothing has been compared against. */
  lifecycle_status?: string;
  cycles_open?: number;
  first_seen_date?: string;
}

/** One surface's week-over-week change, already gated. */
export interface MovementRow {
  key: string;
  before_successes: number;
  before_n: number;
  after_successes: number;
  after_n: number;
  delta_pp: number;
  direction: "up" | "down" | "flat" | "unknown";
  /** "ChatGPT: held steady at 8 of 12 runs" — pre-formatted, render as-is. */
  phrase: string;
  /** Why it is flat, when it is. Render it: a reader who asks "why isn't this
   * news" should get an answer, not a shrug. */
  flat_reason: string;
}

/** Lead with what changed, not with a static score.
 *
 * `accountability` is the sentence that determines renewal. Its arithmetic
 * closes exactly (opening = resolved + still_open, closing = still_open + new +
 * regressed) — never recompute it in the client, or the two can disagree. */
export interface WhatChangedPayload {
  available: boolean;
  accountability: string;
  opening: number;
  resolved: number;
  still_open: number;
  new: number;
  regressed: number;
  closing: number;
  resolved_all_time: number;
  cycles_considered: number;
  movements: MovementRow[];
  prior_run_date: string;
}

/** One brand's presence on one engine, as a count with its denominator. */
export interface EngineCellRow {
  brand: string;
  engine_name: string;
  present: number;
  /** Cells that returned an answer. 0 means NOT MEASURED, not 0% presence. */
  cells: number;
  rate: number;
}

export interface OpenFindingsPayload {
  /** The client-facing count. Themes, not instances. */
  themes: number;
  critical: number;
  instances: number;
  by_severity: Record<string, number>;
}

export interface SourceRow {
  domain: string;
  count: number;
}

export interface LosingRow {
  /** The verbatim question — this is what renders. Optional so runs stored
   * before P1-T3 still parse; falls back to nothing rather than to the id. */
  prompt?: string;
  /** A JOIN KEY. Never render it: `cmp-05` is the most actionable data in the
   * report made unreadable. */
  query_id: string;
  intent: string;
  engine_name: string;
  competitor: string;
  /** Judge prominence of the competitor in this cell; null on the regex path. */
  prominence?: string | null;
}

/** Measured tiles. No letter grade, no composite score — at all.
 *
 * `visibility_grade` is GONE from the payload, not merely unrendered. It
 * survived one round as "back-compat", which is exactly how a dead computation
 * stays alive long enough for the next person to re-render it. See
 * src/api/reports.py ScorecardPayload. */
export interface ScorecardPayload {
  /** Tile 1. Optional so pre-P1-T6 stored runs parse. */
  ai_visibility?: RatePayload;
  /** Tile 3, counted in themes. */
  open_findings?: OpenFindingsPayload;
  /** Tile 4 — replaces the grade. Null until the lifecycle engine lands (P2-T2);
   * the tile renders "—" rather than guessing an age. */
  oldest_open?: FindingGroupRow | null;
  share_of_model_client: number;
  top_competitor: string | null;
  top_competitor_share: number | null;
  mention_rate_client: number;
  mention_rate_top_competitor: number | null;
  citation_rate_client: number | null;
  accuracy_assessed: boolean;
  accuracy_flag_count: number | null;
}

export interface SiteCheckRow {
  check_key: string;
  category: number;
  page_url: string;
  status: string; // pass | partial | fail | ungradeable
  detail: string;
}

export interface SiteFindingRow {
  finding_type: string;
  title: string;
  url: string | null;
  confidence: string; // high | medium | low
}

export interface RoadmapRow {
  category: string;
  check_name: string;
  status: string; // partial | fail
  impact_label: string; // High | Medium | Low
  effort: string; // low | medium | high
  phase: number; // 1..4
}

export interface SiteAuditPayload {
  present: boolean;
  domain: string;
  pages_crawled: number;
  checks: SiteCheckRow[];
  summary: Record<string, number>;
  errors: number;
  offsite: SiteFindingRow[];
  roadmap: RoadmapRow[];
}

export interface ReportPayload {
  client_name: string;
  run_date: string;
  query_set_version: string;
  runs_per_query: number;
  /** Engines that returned at least one answer — built from answer existence, not
   * row existence, so a 404'd surface is not credited with measuring anything. */
  engines: string[];
  /** Engines that ran and returned nothing. Optional so older stored runs parse. */
  dead_engines?: string[];
  competitors: string[];
  client_domains: string[];
  detection: "judge" | "regex";
  scorecard: ScorecardPayload;
  leaderboard: LeaderRow[];
  by_bucket: BucketRow[];
  /** Per-engine reproducibility of the client's verdict across repeat runs. Optional
   * so runs stored before it existed still parse; empty on a single-run cycle. */
  stability?: StabilityRow[];
  /** Brand × engine presence, every cell carrying its own denominator. Empty on
   * the regex path. `cells === 0` is NOT MEASURED, which is a different fact
   * from 0% presence — render "—", never a zero. */
  engine_matrix?: EngineCellRow[];
  /** One bold sentence a CMO can act on. Generated DETERMINISTICALLY from
   * structured fields — no LLM. A hallucinating summary in a
   * hallucination-detection product is the worst failure mode available. */
  exec_summary?: string;
  /** What changed since last cycle. Optional so pre-P2 stored runs parse. */
  what_changed?: WhatChangedPayload;
  /** The theme rules that produced these groupings. Both cycles are always
   * classified with the current rules, so a rule change cannot manufacture a
   * resolve; this exists so an edition-diff can say "we regrouped these". */
  theme_rules_version?: string;
  /** ≤15 themed findings, Critical → High → Medium → Low then by priority.
   * THIS renders; `accuracy_flags` is the appendix. Optional so runs stored
   * before P1-T1 still parse and fall back to the flat flag list. */
  finding_groups?: FindingGroupRow[];
  /** The 3–7 highest-priority actions — a pre-sliced subset of `finding_groups`
   * in the same order, so every surface shows the same shortlist. */
  priority_actions?: FindingGroupRow[];
  /** Classifier health: rule / type-default / unclassified shares. Reported so a
   * rising type_default share is visible, never averaged away. */
  theme_coverage?: Record<string, number>;
  /** Why no week-over-week comparison is shown: "no_prior_run" |
   * "query_set_changed" | "". Render the honest explanation, never a comparison
   * across a changed query set. */
  comparison_blocked_reason?: string;
  /** The non-reproducibility disclosure. Render VERBATIM, once per report. Do
   * not paraphrase it — it is worded to be honest without self-undermining. */
  methodology_disclosure?: string;
  /** Vendor-independence disclaimer. Verbatim, once per report. */
  independence_disclaimer?: string;
  /** How often the judge agreed with a human reviewer. Render it even when it
   * says "not yet measured" — every Critical finding rests on the judge, and an
   * omission reads as "not applicable" rather than "not measured". */
  judge_agreement?: string;
  accuracy_flags: FlagRow[];
  sources: SourceRow[];
  losing_queries: LosingRow[];
  site_audit: SiteAuditPayload | null;
  // --- the report contract's sections (Phase T) ---------------------------
  // All optional: a run stored before Phase T has none of them, and every
  // section's registry entry has a thin-data fallback that says so rather than
  // rendering an empty box.
  /** §1 — six measured tiles and one NEUTRAL sentence. */
  exec_snapshot?: ExecSnapshotPayload;
  /** §3 — the N-cycle series, gated on comparability and coverage. */
  trend?: TrendPayload;
  /** §4 — per intent bucket, family-aware (consumer vs local-service). */
  question_types?: QuestionTypePayload;
  /** §5 — per engine, including attempted vs returned. */
  surfaces?: SurfacePayload;
  /** §6 — the leaderboard, with gated movement. */
  competitive?: CompetitivePayload;
  /** §7 — client citations, top domains, source types, the Pareto curve. */
  citations?: CitationsPayload;
  /** §10 — five slots filled by published, deterministic rules. */
  representative_answers?: RepresentativePayload;
  /** §11 — everything needed to re-run, check or challenge the measurement. */
  methodology?: MethodologyPayload;
  /** A1–A6 — the dense tables behind the analysis. */
  back_matter?: BackMatterPayload;
}

// --- Report contract sections (src/api/sections.py) ---

/** One measured tile. `direction` is only ever "up"/"down" when the significance
 * gate passed — an arrow is a claim that something happened, and at 3–5 runs
 * most week-over-week wobble is the sampling, not the market. */
export interface TilePayload {
  key: string;
  label: string;
  value: string;
  secondary: string;
  delta: string;
  direction: "up" | "down" | "flat" | "unknown";
  gated: boolean;
}

export interface ExecSnapshotPayload {
  tiles: TilePayload[];
  /** DESCRIPTIVE. The action clause opens section 8, never this one. */
  summary: string;
}

export interface TrendPoint {
  run_date: string;
  run_id: string;
  mention: RatePayload;
  citation: RatePayload | null;
  share_of_model: number;
  prominence: string | null;
  prominence_label: string;
  is_current: boolean;
}

export interface TrendPayload {
  points: TrendPoint[];
  cycles: number;
  /** False under four cycles — points only. A line through two points asserts a
   * direction the data cannot support, and a reader reads the slope. */
  draw_line: boolean;
  statement: string;
  excluded_cycles: number;
}

export interface QuestionTypeRow {
  bucket: string;
  label: string;
  mention: RatePayload;
  citation_rate: number | null;
  delta: string;
  /** Interval wider than ±15 pp ⇒ render the count and interval, not the point. */
  suppress_point: boolean;
}

export interface QuestionTypePayload {
  family: "consumer" | "local" | "mixed";
  rows: QuestionTypeRow[];
  best: string;
  weakest: string;
  note: string;
}

export interface SurfaceRow {
  engine_name: string;
  label: string;
  model_id: string;
  mention: RatePayload;
  prominence_distribution: Record<string, number>;
  attempted_cells: number;
  answered_cells: number;
  coverage_ratio: number;
  coverage_ok: boolean;
  delta: string;
  direction: "up" | "down" | "flat" | "unknown";
}

export interface SurfacePayload {
  rows: SurfaceRow[];
  degraded: string[];
  dead: string[];
  note: string;
}

export interface CompetitiveRow {
  brand: string;
  is_client: boolean;
  mention: RatePayload;
  share_of_model: number;
  prominence: string | null;
  prominence_label: string;
  prominence_distribution: Record<string, number>;
  delta: string;
  direction: "up" | "down" | "flat" | "unknown";
}

export interface CompetitivePayload {
  rows: CompetitiveRow[];
  gained: string[];
  lost: string[];
  note: string;
}

export interface CitationDomainRow {
  domain: string;
  count: number;
  share: number;
  /** Running share, domains ordered by count — the Pareto read. */
  cumulative_share: number;
  source_type: string;
  is_client: boolean;
  delta: string;
}

export interface CitationsPayload {
  client_citations: number;
  client_rate: RatePayload | null;
  domains: CitationDomainRow[];
  by_source_type: Record<string, number>;
  total_citations: number;
  concentration: string;
  note: string;
}

export interface RepresentativeAnswer {
  slot: string;
  slot_label: string;
  /** The published rule that chose this one. "Why this example" must have an
   * answer that is not "we liked it". */
  rule: string;
  available: boolean;
  prompt: string;
  query_id: string;
  run_index: number;
  engine_name: string;
  engine_label: string;
  model_id: string;
  observed_at: string;
  excerpt: string;
  note: string;
}

export interface RepresentativePayload {
  slots: RepresentativeAnswer[];
  selection_rules: string[];
}

export interface MethodologyPayload {
  window_start: string;
  window_end: string;
  query_set_version: string;
  n_queries: number;
  runs_per_query: number;
  surfaces: [string, string][];
  geography: string;
  account_config: string;
  definitions: [string, string][];
  changes_since_last: string[];
  limitations: string[];
  selection_rules: string[];
  non_reproducibility: string;
  independence: string;
  judge_agreement: string;
}

export interface AppendixTable {
  id: string;
  title: string;
  columns: string[];
  rows: string[][];
  note: string;
  total_rows: number;
}

export interface BackMatterPayload {
  appendices: AppendixTable[];
  note: string;
}

// --- Teaser types (teaser/ pipeline draft + the persisted review row) ---

export interface TeaserHeadlineNumber {
  companyAppears: number;
  competitorAppears: number;
  competitorName: string;
  n: number;
}

export interface TeaserDraft {
  prospectUrl: string;
  companyName: string;
  category: string;
  runDate: string;
  heroEngine: string;
  headlineNumber: TeaserHeadlineNumber;
  lead: { verbatimQuery: string };
  table: unknown[];
  // Persisted so a regenerated teaser matches the client/competitors by their
  // aliases, not just their names (kept in sync with teaser/src/types/domain.ts).
  clientAliases?: string[];
  competitorAliases?: Record<string, string[]>;
}

// Reviewer overrides for the printable copy. All optional — only edited fields
// are sent/stored. Mirrors the columns the review UI exposes.
export interface TeaserEditedFields {
  headline?: string;
  leadSentence?: string;
  cta?: string;
  stakesLine?: string;
}

export type TeaserStatus = "draft" | "approved" | "rejected" | "exported";

// A persisted teaser row (src/storage/db.py teasers table). Snake_case columns
// straight from Supabase; nested draft/edited_fields stay as their JSON shapes.
export interface TeaserRecord {
  id: string;
  prospect_url: string | null;
  company_name: string | null;
  category: string | null;
  run_date: string | null;
  hero_engine: string | null;
  headline_number: TeaserHeadlineNumber | Record<string, never>;
  lead: { verbatimQuery?: string } | Record<string, never>;
  table_findings: unknown[];
  draft: TeaserDraft;
  html: string | null;
  status: TeaserStatus;
  edited_fields: TeaserEditedFields;
  reject_reason: string | null;
  reviewed_by: string | null;
  created_at: string;
  updated_at: string;
}

// Lightweight shape for the saved-teasers list (a subset of TeaserRecord).
export interface TeaserSummary {
  id: string;
  company_name: string | null;
  status: TeaserStatus;
  created_at: string;
}

// --- Projects (src/api/projects.py): a domain-keyed roll-up of audits + teasers ---

export interface ProjectAudit {
  run_id: string;
  client_name: string;
  state: string;
  created_at: string;
  n_queries: number;
  engines: string[];
}

export interface ProjectTeaser {
  id: string;
  company_name: string | null;
  status: string;
  created_at: string;
}

export interface ProjectSummary {
  key: string;
  label: string;
  domain: string | null;
  audit_count: number;
  teaser_count: number;
  last_activity: string;
  last_state: string | null;
  engines: string[];
}

export interface ProjectDetail {
  key: string;
  label: string;
  domain: string | null;
  audits: ProjectAudit[];
  teasers: ProjectTeaser[];
}

/** One completed cycle, reduced to the numbers the project page plots.
 *
 * `query_set_version` is not decoration: a run is comparable only to a run that
 * asked the same questions, so the client connects a line only across points
 * that share it and says so when it cannot. */
export interface ProjectHistoryPoint {
  run_id: string;
  run_date: string;
  query_set_version: string;
  /** Both numbers, always. A mention rate without its denominator is the single
   * most misleading thing this product could print. */
  mention_successes: number;
  mention_n: number;
  share_of_model: number;
  open_findings: number;
  critical: number;
}

// --- Calls ---

function filesToForm(files: File[]): FormData {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  return form;
}

export async function previewAudit(files: File[]): Promise<ParsePreview> {
  const res = await fetch(`${API_BASE}/audits/preview`, {
    method: "POST",
    body: filesToForm(files),
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`preview failed (${res.status})`);
  return res.json();
}

export async function createAudit(
  files: File[],
  factSheetId?: string | null,
): Promise<{ run_id: string } | { errors: ParsePreview } | { refused: string }> {
  const form = filesToForm(files);
  // Attaches an APPROVED sheet from /fact-sheets as this run's ground truth.
  // Without it the endpoint accepts the run and judges against whatever `fact`
  // rows the CSV carried — which is how approving a sheet came to change one
  // column and nothing downstream.
  if (factSheetId) form.append("fact_sheet_id", factSheetId);
  const res = await fetch(`${API_BASE}/audits`, {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  if (res.status === 422) {
    const body = await res.json();
    // Two different 422s share this status: a CSV that would not parse (a
    // structured preview) and a fact sheet that cannot serve as ground truth (a
    // sentence). Showing the second as a parse error would send someone hunting
    // through their CSV for a problem that is not in it.
    if (typeof body.detail === "string") return { refused: body.detail };
    return { errors: body.detail as ParsePreview };
  }
  if (!res.ok) throw new Error(`create failed (${res.status})`);
  return res.json();
}

export async function listAudits(): Promise<RunSummary[]> {
  const res = await fetch(`${API_BASE}/audits`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw new Error(`list failed (${res.status})`);
  return res.json();
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${API_BASE}/projects`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw new Error(`list projects failed (${res.status})`);
  return res.json();
}

export async function getProject(key: string): Promise<ProjectDetail> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(key)}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`get project failed (${res.status})`);
  return res.json();
}

export async function getProjectHistory(key: string): Promise<ProjectHistoryPoint[]> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(key)}/history`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`project history failed (${res.status})`);
  return res.json();
}

export interface DeleteProjectResult {
  key: string;
  label: string;
  audits_deleted: number;
  teasers_deleted: number;
}

// Permanently deletes the project's audits (children cascade) and teasers.
export async function deleteProject(key: string): Promise<DeleteProjectResult> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(key)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    // Surface the API's own message (FastAPI `detail`) rather than a bare status.
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail || `delete project failed (${res.status})`);
  }
  return res.json();
}

export async function getStatus(runId: string): Promise<RunStatus> {
  const res = await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/status`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`status failed (${res.status})`);
  return res.json();
}

export async function getReport(runId: string): Promise<ReportPayload> {
  const res = await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/report`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`report failed (${res.status})`);
  return res.json();
}

/** One cell's full stored answer (P3-T1).
 *
 * The card quotes an EXCERPT; this is the whole thing. A client who wants to see
 * the sentence in context should not have to download the entire answers export
 * to do it — a finding they cannot check is one they have to take on trust. */
export async function getAnswerCell(
  runId: string,
  queryId: string,
  engine: string,
  runIndex: number,
): Promise<{ prompt: string; response: string | null; timestamp: string }> {
  const path =
    `${API_BASE}/audits/${encodeURIComponent(runId)}/answers/` +
    `${encodeURIComponent(queryId)}/${encodeURIComponent(engine)}/${runIndex}`;
  const res = await fetch(path, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw new Error(`answer failed (${res.status})`);
  return res.json();
}

/** Read-only report behind a signed link. Deliberately sends NO API key — the
 * token is the auth, and a login wall is what kills forwardability. */
export async function getSharedReport(
  token: string,
  password = "",
): Promise<ReportPayload> {
  const query = password ? `?password=${encodeURIComponent(password)}` : "";
  const res = await fetch(
    `${API_BASE}/shared/${encodeURIComponent(token)}/report${query}`,
    { cache: "no-store" },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "this link is not valid" }));
    throw new Error(detail.detail ?? `shared report failed (${res.status})`);
  }
  return res.json();
}

export async function createShareLink(
  runId: string,
  ttlSeconds?: number,
  password?: string,
): Promise<{ token: string; path: string; expires_in: number }> {
  const res = await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/share`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ ttl_seconds: ttlSeconds, password: password ?? "" }),
  });
  if (!res.ok) throw new Error(`share failed (${res.status})`);
  return res.json();
}

export async function cancelAudit(runId: string): Promise<void> {
  await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    headers: authHeaders(),
  });
}

// Warm status of a run's notebooks — how many query answers and on-site content
// checks are already cached, so the UI can tell if Judge / the report is free.
export type NotebookStatus = { total: number; cached: number; warm: boolean };
export type JudgeStatus = { query: NotebookStatus; content: NotebookStatus };

export async function fetchJudgeStatus(runId: string): Promise<JudgeStatus> {
  const res = await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/judge-status`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`judge-status failed (${res.status})`);
  return res.json();
}

// Re-judge a completed run's stored answers and return the refreshed report.
// Free when the judge cache is warm (pre-filled via the /prejudge workflow in
// Claude Code); otherwise it runs the judge on the API.
export async function judgeAudit(runId: string): Promise<ReportPayload> {
  const res = await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/judge`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`judge failed (${res.status})`);
  return res.json();
}

// Downloads go through fetch (not an <a href>) so the X-API-Key header is sent;
// the response is saved as a blob.
export async function downloadAudit(
  runId: string,
  kind: "results.csv" | "answers.md",
): Promise<void> {
  const res = await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/${kind}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`download failed (${res.status})`);
  const ext = kind === "results.csv" ? "csv" : "md";
  await saveBlob(res, `geo-audit-${runId}-answers.${ext}`);
}

export async function listTrades(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/trades`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) return [];
  return res.json();
}

/**
 * The starter CSV. With a trade, a filled local query set (29 questions) instead
 * of the 4-query consumer starter — the trade templates existed behind the
 * endpoint and were unreachable because it never passed one through.
 */
export async function downloadTemplate(trade?: string | null): Promise<void> {
  const qs = trade ? `?trade=${encodeURIComponent(trade)}` : "";
  const res = await fetch(`${API_BASE}/template.csv${qs}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`template failed (${res.status})`);
  await saveBlob(res, trade ? `geo-audit-template-${trade}.csv` : "geo-audit-template.csv");
}

// --- Teaser persistence + review (src/api/app.py /teasers) ---

const jsonHeaders = () => authHeaders({ "Content-Type": "application/json" });

// Persist a freshly generated draft (from the /api/teaser child-process route).
// Returns the new row id so the UI can drive approve / edit / reject on it.
export async function saveTeaser(
  draft: TeaserDraft,
  html: string,
): Promise<{ teaser_id: string }> {
  const res = await fetch(`${API_BASE}/teasers`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ draft, html }),
  });
  if (!res.ok) throw new Error(`save teaser failed (${res.status})`);
  return res.json();
}

export async function listTeasers(): Promise<TeaserSummary[]> {
  const res = await fetch(`${API_BASE}/teasers`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw new Error(`list teasers failed (${res.status})`);
  return res.json();
}

export async function getTeaser(id: string): Promise<TeaserRecord> {
  const res = await fetch(`${API_BASE}/teasers/${encodeURIComponent(id)}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`get teaser failed (${res.status})`);
  return res.json();
}

export async function approveTeaser(id: string): Promise<TeaserRecord> {
  const res = await fetch(`${API_BASE}/teasers/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`approve teaser failed (${res.status})`);
  return res.json();
}

export async function editTeaser(
  id: string,
  edited_fields: TeaserEditedFields,
  html?: string,
): Promise<TeaserRecord> {
  const res = await fetch(`${API_BASE}/teasers/${encodeURIComponent(id)}/edit`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ edited_fields, html: html ?? null }),
  });
  if (!res.ok) throw new Error(`edit teaser failed (${res.status})`);
  return res.json();
}

export async function rejectTeaser(id: string, reason?: string): Promise<TeaserRecord> {
  const res = await fetch(`${API_BASE}/teasers/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ reason: reason ?? null }),
  });
  if (!res.ok) throw new Error(`reject teaser failed (${res.status})`);
  return res.json();
}

// --- Audit deliverable types (the paid AI Visibility Audit) ---

export type AuditStatus = "draft" | "approved" | "rejected" | "exported";

// The full AuditDraft is large + nested (teaser/src/types/audit.ts); the review UI
// only reads a handful of cover fields, so model those and keep the rest opaque.
export interface AuditDraft {
  runId: string;
  clientName: string;
  category: string;
  runDate: string;
  grade: { letter: string; score: number; rationale: string } | null;
  achievableGrade: string | null;
  headline: string;
  verdictSentence: string;
  headlineNumber: { clientAppears: number; competitorAppears: number; competitorName: string; n: number };
  [key: string]: unknown;
}

// Reviewer overrides for the audit narrative. All optional. Mirrors AuditEdits.
export interface AuditEditedFields {
  headline?: string;
  verdictSentence?: string;
  achievableGrade?: string;
  projectedImpact?: string;
  nextSteps?: string;
}

// A persisted audit-deliverable row (src/storage/db.py audit_deliverables table).
export interface AuditRecord {
  id: string;
  run_id: string | null;
  client_name: string | null;
  category: string | null;
  run_date: string | null;
  grade_letter: string | null;
  grade_score: number | null;
  headline: { headline?: string; verdict?: string } | Record<string, never>;
  draft: AuditDraft;
  html: string | null;
  status: AuditStatus;
  edited_fields: AuditEditedFields;
  reject_reason: string | null;
  reviewed_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditSummary {
  id: string;
  client_name: string | null;
  category: string | null;
  grade_letter: string | null;
  status: AuditStatus;
  created_at: string;
}

// The /api/audit (Next child-process route) response.
export type GenerateAuditResult =
  | { ok: true; draft: AuditDraft; html: string; deliverableId: string | null }
  | { ok: false; stage: string; reason: string };

// --- Audit generation + persistence + review ---

// Generate an audit from a completed run_id (runs the generator via the Next
// child-process route, which also best-effort persists it to Supabase).
export async function generateAudit(
  runId: string,
  category?: string,
  perBucket?: number,
): Promise<GenerateAuditResult> {
  const res = await fetch(`/api/audit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ runId, category, perBucket }),
  });
  return res.json();
}

// Re-render the audit HTML from a draft + reviewer edits (Next child-process route).
export async function renderAudit(
  draft: AuditDraft,
  edited_fields: AuditEditedFields,
): Promise<{ ok: boolean; html?: string; reason?: string }> {
  const res = await fetch(`/api/audit/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft, edited_fields }),
  });
  return res.json();
}

export async function listAuditDeliverables(): Promise<AuditSummary[]> {
  const res = await fetch(`${API_BASE}/audit-deliverables`, { cache: "no-store", headers: authHeaders() });
  if (!res.ok) throw new Error(`list audits failed (${res.status})`);
  return res.json();
}

export async function getAuditDeliverable(id: string): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/audit-deliverables/${encodeURIComponent(id)}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`get audit failed (${res.status})`);
  return res.json();
}

export async function approveAuditDeliverable(id: string): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/audit-deliverables/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`approve audit failed (${res.status})`);
  return res.json();
}

export async function editAuditDeliverable(
  id: string,
  edited_fields: AuditEditedFields,
  html?: string,
): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/audit-deliverables/${encodeURIComponent(id)}/edit`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ edited_fields, html: html ?? null }),
  });
  if (!res.ok) throw new Error(`edit audit failed (${res.status})`);
  return res.json();
}

export async function rejectAuditDeliverable(id: string, reason?: string): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/audit-deliverables/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ reason: reason ?? null }),
  });
  if (!res.ok) throw new Error(`reject audit failed (${res.status})`);
  return res.json();
}

// --- Fact sheets: the F4 review queue (src/api/app.py /fact-sheets) ---
//
// A generated sheet is always DRAFT. Approving it is the only way it becomes the
// reference a run's accuracy judging is measured against, so this client exists to
// put that decision in front of a person.

export type FactSheetState = "draft" | "active" | "superseded" | "rejected";
export type FactSheetVerification =
  | "public_source_only"
  | "cross_confirmed"
  | "client_confirmed";

/** One row of the queue list — a projection, not the document. */
export interface FactSheetSummary {
  id: string;
  domain: string;
  business_name: string;
  business_kind: string;
  version: number;
  state: FactSheetState;
  verification_tier: FactSheetVerification;
  lead_ref: string | null;
  questions: string[] | null;
  reject_reason: string | null;
  generated_at: string;
  created_at: string;
}

/** One claim, WITH the evidence a reviewer needs to check it. */
export interface FactSheetClaim {
  claim_id: string;
  section: string;
  key: string;
  value: string;
  polarity: "positive" | "negative";
  /** The literal source line. Never a paraphrase — that is the §4.1 gate. */
  verbatim_quote: string;
  source_url: string;
  source_kind: string;
  as_of: string;
  verification: FactSheetVerification;
  confidence: "high" | "medium" | "low";
}

export interface FactSheetDetail {
  id: string;
  domain: string;
  business_name: string;
  business_kind: string;
  version: number;
  sheet_status: string;
  verification_tier: FactSheetVerification;
  generated_at: string;
  lead_ref: string | null;
  questions: string[];
  claims: FactSheetClaim[];
  markdown: string;
  /**
   * Run config derivable from this sheet, so a "start from a lead" form stops
   * asking for the name, domain and city the sheet was already extracted from.
   * Any field may be null — that means ASK, not guess. `region` in particular is
   * null when the sheet only carried a two-letter state, because nothing expands
   * an abbreviation.
   */
  suggested?: {
    business: string | null;
    website: string | null;
    city: string | null;
    region: string | null;
  };
}

/** Permanently delete a sheet and its claims.
 *
 * Safe for history: a finished run keeps its own copy of the sheet text and the
 * version it was judged against, so a past report cannot change underneath it. */
export async function deleteFactSheet(
  id: string,
): Promise<{ id: string; domain: string; deleted: number }> {
  const res = await fetch(`${API_BASE}/fact-sheets/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`delete fact sheet failed (${res.status})`);
  return res.json();
}

export async function listFactSheets(state?: FactSheetState): Promise<FactSheetSummary[]> {
  const qs = state ? `?state=${encodeURIComponent(state)}` : "";
  const res = await fetch(`${API_BASE}/fact-sheets${qs}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`list fact sheets failed (${res.status})`);
  return res.json();
}

export async function getFactSheet(id: string): Promise<FactSheetDetail> {
  const res = await fetch(`${API_BASE}/fact-sheets/${encodeURIComponent(id)}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`get fact sheet failed (${res.status})`);
  return res.json();
}

export async function approveFactSheet(id: string): Promise<{ id: string; state: string }> {
  const res = await fetch(`${API_BASE}/fact-sheets/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`approve fact sheet failed (${res.status})`);
  return res.json();
}

export async function rejectFactSheet(
  id: string,
  reason: string,
): Promise<{ id: string; state: string }> {
  const res = await fetch(`${API_BASE}/fact-sheets/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ reason }),
  });
  // 409 = the sheet is ACTIVE; live runs are judged against it.
  if (res.status === 409) {
    throw new Error("This sheet is active — activate a replacement instead of rejecting it.");
  }
  if (!res.ok) throw new Error(`reject fact sheet failed (${res.status})`);
  return res.json();
}

// --- Assemble a runnable audit from a lead (src/api/app.py /audits/assemble) ---

export interface AssembleRequest {
  business: string;
  website: string;
  trade: string;
  city: string;
  /** The state's FULL name ("California"). "CA" is refused by the API, not guessed. */
  region: string;
  country?: string;
  category?: string | null;
  runs_per_query?: number;
  judge?: boolean;
  /** Supply your own to skip the local-pack lookup (which spends a Serper credit). */
  competitors?: string[] | null;
}

export interface AssembleResult {
  csv: string;
  competitors: string[];
  /** What the local pack returned and why each was dropped — shown, never hidden. */
  excluded: { name: string; reason: string }[];
  competitor_source: string;
  /** Set when no competitor survived: the run would measure against nobody. */
  warning: string | null;
}

export async function assembleAudit(body: AssembleRequest): Promise<AssembleResult> {
  const res = await fetch(`${API_BASE}/audits/assemble`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (res.status === 422) {
    // A refusal with a reason (an abbreviated region, an unknown trade). Surfaced
    // verbatim — the API's message explains what to do, and paraphrasing it here
    // would lose that.
    const detail = (await res.json()).detail;
    throw new Error(typeof detail === "string" ? detail : "Could not assemble the audit.");
  }
  if (!res.ok) throw new Error(`assemble failed (${res.status})`);
  return res.json();
}

// --- Fact-sheet intake (src/api/intake.py) -----------------------------------
//
// The registry is the single source of truth for what the intake asks: these
// types mirror the Python dataclasses, and the UI renders whatever the plan
// contains rather than hardcoding a card. A question that exists in the
// frontend but not in the registry is a question whose answer has nowhere to go.

export type IntakeAnswerKind =
  | "choice"
  | "multi"
  | "confirm"
  | "batch_confirm"
  | "text"
  | "longtext"
  | "list"
  | "hours"
  | "money"
  | "tiers"
  | "links"
  | "watchlist";

export interface IntakeOption {
  value: string;
  label: string;
}

export interface IntakePrefillEntry {
  value: string;
  source_url: string;
  source_kind: string;
  confidence: string;
}

export interface IntakeQuestion {
  id: string;
  kind: IntakeAnswerKind;
  section: string | null;
  keys: string[];
  /** What each field of a multi-key card is called. From the registry, so a
   * label cannot drift from the key it names. */
  keyLabels: Record<string, string>;
  /** "config" cards open the conversation — the five things the run cannot
   * start without. "facts" is everything the sheet is made of. */
  stage: "config" | "facts";
  prompt: string;
  /** The one-line rationale, shown in the open-questions launcher. */
  why: string;
  helper: string;
  placeholder: string;
  options: IntakeOption[];
  skippable: boolean;
  /** "No" is the valuable answer. Never reword these into positives. */
  negativeFirst: boolean;
  producesClaims: boolean;
  showIf: { questionId: string; equals: string } | null;
  prefill: Record<string, IntakePrefillEntry>;
}

/** done | current | skipped | todo. `skipped` renders as visibly ADDRESSED —
 * never as answered, never as pending. That distinction is what makes skipping
 * safe to offer. */
export type IntakeMark = "done" | "current" | "skipped" | "todo";

export interface IntakeProgress {
  marks: IntakeMark[];
  total: number;
  answered: number;
  confirmed: number;
  done: boolean;
}

export interface IntakeStoredAnswer {
  value: unknown;
  raw: string;
  skipped: boolean;
  answered_at: string;
}

export interface IntakeSession {
  session_id: string;
  domain: string;
  /** What the prompts call the business. Resolved server-side — a prompt that
   * addresses someone as "blackpropeller.com" is not one they will answer. */
  business_name: string;
  business_kind: string;
  state: string;
  fact_sheet_id: string | null;
  approved_fact_sheet_id: string | null;
  plan: IntakeQuestion[];
  answers: Record<string, IntakeStoredAnswer>;
  prefill: Record<string, IntakePrefillEntry>;
  run_inputs: Record<string, unknown>;
  next: IntakeQuestion | null;
  progress: IntakeProgress;
}

/** The exact sentence the owner is put on the record as saying. */
export interface IntakeAssertion {
  key: string;
  value: string;
  polarity: "positive" | "negative";
}

export interface IntakeAnswerResult {
  next: IntakeQuestion | null;
  progress: IntakeProgress;
  assertions: IntakeAssertion[];
  /** Marketing words we noticed. A NUDGE, never a block. */
  nudge: string[];
}

export interface IntakeReviewClaim {
  claim_id: string;
  section: string;
  key: string;
  value: string;
  quote: string;
  polarity: string;
  as_of: string;
  verification: string;
}

export interface IntakeQueryRow {
  query_id: string;
  text: string;
  intent: string;
  persona: string;
  provenance: string;
}

export interface LintItem {
  level: "block" | "warn";
  message: string;
  code: string;
}

/** What this set would actually run, read off the generated CSV — never
 * assumed. It is the last number a person sees before spending money. */
export interface IntakeRunShape {
  questions: number;
  engines: string[];
  surfaces: number;
  runs_per_query: number;
  calls: number;
  estimated_usd: number;
}

export interface IntakeReview {
  session_id: string;
  state: string;
  claims: IntakeReviewClaim[];
  /** Keys nobody confirmed. Named, not counted — "3 facts nobody confirmed"
   * with no way to see which is a dead end. */
  unconfirmed: string[];
  query_set: IntakeQueryRow[];
  csv: string;
  lint: LintItem[];
  run_shape: IntakeRunShape;
  tier: string;
  can_approve: boolean;
  run_inputs: Record<string, unknown>;
}

async function intakeJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    }),
  });
  if (!res.ok) {
    // A 409 from approve means an unconfirmed claim survived the tier rule, or
    // the question set failed its checks. Both carry a sentence a person can
    // act on; surface it rather than "request failed (409)".
    let detail: unknown = null;
    try {
      detail = (await res.json())?.detail;
    } catch {
      detail = null;
    }
    if (typeof detail === "string") throw new Error(detail);
    if (detail && typeof detail === "object" && "message" in detail) {
      throw new Error(String((detail as { message: unknown }).message));
    }
    throw new Error(`${path} failed (${res.status})`);
  }
  return res.json();
}

export function startIntake(sheetId: string): Promise<IntakeSession> {
  return intakeJson(`/fact-sheets/${encodeURIComponent(sheetId)}/intake`, { method: "POST" });
}

/** One conversation still in flight. */
export interface OpenIntake {
  session_id: string;
  domain: string;
  business_name: string;
  state: string;
  answered: number;
  updated_at: string;
}

/** THE COLD-START ENTRY POINT. No fact sheet needed, no crawl required — a
 * domain the crawler has never seen is exactly the case where the owner's
 * answers are the only thing on the sheet, and that sheet is already better
 * than a crawled one because every line of it is client-confirmed. */
export function startIntakeForBrand(body: {
  business: string;
  website: string;
}): Promise<IntakeSession> {
  return intakeJson(`/intake/start`, { method: "POST", body: JSON.stringify(body) });
}

/** Discard a conversation. Frees the domain so a new one can be started.
 *
 * Distinct from abandonment: `abandoned` records that an OWNER stopped
 * answering, which is a signal worth keeping. This is an OPERATOR throwing away
 * a conversation they opened by mistake. */
export function deleteIntake(
  sessionId: string,
): Promise<{ session_id: string; domain: string; deleted: number }> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export function listOpenIntakes(): Promise<OpenIntake[]> {
  return intakeJson(`/intake`);
}

export function getIntake(sessionId: string): Promise<IntakeSession> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}`);
}

export function answerIntake(
  sessionId: string,
  body: { question_id: string; value: unknown; raw: string; skipped: boolean },
): Promise<IntakeAnswerResult> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/answer`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** The sentence a candidate answer WOULD produce, without storing it.
 *
 * A round trip rather than a client-side copy of the phrasing on purpose: the
 * registry and its sentences live in one place, and a second implementation
 * here would drift the first time someone reworded a card — showing the owner
 * one sentence and quoting them on another. */
export function previewIntake(
  sessionId: string,
  body: { question_id: string; value: unknown; raw: string },
): Promise<{ assertions: IntakeAssertion[]; nudge: string[] }> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function backIntake(sessionId: string): Promise<IntakeSession> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/back`, { method: "POST" });
}

export function completeIntake(sessionId: string): Promise<IntakeReview> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/complete`, { method: "POST" });
}

export function getIntakeReview(sessionId: string): Promise<IntakeReview> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/review`);
}

export function patchIntakeReview(
  sessionId: string,
  body: { run_inputs?: Record<string, unknown> },
): Promise<IntakeReview> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/review`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** The question set the intake generated alongside an approved sheet.
 *
 * Read off the session that approved it rather than stored twice — two
 * representations of the same set is how they drift. */
export function getSheetQuerySet(
  sheetId: string,
): Promise<{ fact_sheet_id: string; queries: IntakeQueryRow[]; csv: string }> {
  return intakeJson(`/fact-sheets/${encodeURIComponent(sheetId)}/query-set`);
}

export function approveIntake(
  sessionId: string,
): Promise<{ fact_sheet_id: string; version: number; claims: number }> {
  return intakeJson(`/intake/${encodeURIComponent(sessionId)}/approve`, { method: "POST" });
}
