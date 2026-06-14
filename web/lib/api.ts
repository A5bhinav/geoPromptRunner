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

export interface GradePayload {
  letter: string;
  score: number;
  raw_score: number;
  accuracy_penalty: number;
  n_flags: number;
  rationale: string;
}

export interface LeaderRow {
  brand: string;
  is_client: boolean;
  visibility: number | null;
  mention_rate: number;
  share_of_model: number;
}

export interface BucketRow {
  bucket: string;
  mention_rate: number;
  citation_rate: number | null;
}

export interface FlagRow {
  type: string;
  severity: string;
  claim: string;
  reality: string;
}

export interface SourceRow {
  domain: string;
  count: number;
}

export interface LosingRow {
  query_id: string;
  intent: string;
  engine_name: string;
  competitor: string;
}

export interface ScorecardPayload {
  visibility_grade: GradePayload | null;
  share_of_model_client: number;
  top_competitor: string | null;
  top_competitor_share: number | null;
  mention_rate_client: number;
  mention_rate_top_competitor: number | null;
  citation_rate_client: number | null;
  accuracy_assessed: boolean;
  accuracy_flag_count: number | null;
}

export interface ReportPayload {
  client_name: string;
  run_date: string;
  query_set_version: string;
  runs_per_query: number;
  engines: string[];
  competitors: string[];
  client_domains: string[];
  detection: "judge" | "regex";
  scorecard: ScorecardPayload;
  leaderboard: LeaderRow[];
  by_bucket: BucketRow[];
  accuracy_flags: FlagRow[];
  sources: SourceRow[];
  losing_queries: LosingRow[];
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
): Promise<{ run_id: string } | { errors: ParsePreview }> {
  const res = await fetch(`${API_BASE}/audits`, {
    method: "POST",
    body: filesToForm(files),
    headers: authHeaders(),
  });
  if (res.status === 422) {
    const body = await res.json();
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

export async function cancelAudit(runId: string): Promise<void> {
  await fetch(`${API_BASE}/audits/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    headers: authHeaders(),
  });
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

export async function downloadTemplate(): Promise<void> {
  const res = await fetch(`${API_BASE}/template.csv`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`template failed (${res.status})`);
  await saveBlob(res, "geo-audit-template.csv");
}
