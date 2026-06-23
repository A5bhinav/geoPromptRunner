/**
 * The seam between teaserAuto and the geoPromptRunner measurement platform.
 *
 * teaserAuto only ever talks to the platform through this interface. The real
 * implementation (HttpPlatformClient) calls the FastAPI endpoints; MockPlatformClient
 * returns fixtures so the whole flow runs with no platform deployed and no keys.
 *
 * Endpoints the real client wraps (src/api/app.py):
 *   POST /audits                     (multipart CSV) -> { run_id }
 *   GET  /audits/{run_id}/status     -> RunStatus
 *   GET  /audits/{run_id}/report     -> ReportPayload
 *   GET  /audits/{run_id}/answers.md -> verbatim answers (parsed to AnswerRecord[])
 */

import type { AnswerRecord, ReportPayload, RunStatus } from "../types/platform.ts";

/** The audit input we submit: the CSV plus the metadata needed to mock a result. */
export interface AuditInput {
  /** Exact CSV body (block,key,value,intent,persona) sent to POST /audits. */
  csv: string;
  /** Parsed essentials (the real client ignores these; the mock uses them). */
  clientName: string;
  clientDomains: string[];
  competitors: string[];
  category: string;
  engines: string[];
  queries: { query_id: string; text: string; intent: string }[];
}

export interface PlatformClient {
  submitAudit(input: AuditInput): Promise<{ runId: string }>;
  getStatus(runId: string): Promise<RunStatus>;
  getReport(runId: string): Promise<ReportPayload>;
  getAnswers(runId: string): Promise<AnswerRecord[]>;
}
