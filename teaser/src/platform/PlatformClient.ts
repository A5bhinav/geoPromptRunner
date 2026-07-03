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

import type { AuditDraft } from "../types/audit.ts";
import type { TeaserDraft } from "../types/domain.ts";
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
  /** Runs per query (also encoded in the CSV; the real client uses the CSV, the
   *  mock reads this to synthesize that many run_index samples). */
  runsPerQuery: number;
  queries: { query_id: string; text: string; intent: string }[];
}

export interface PlatformClient {
  submitAudit(input: AuditInput): Promise<{ runId: string }>;
  getStatus(runId: string): Promise<RunStatus>;
  getReport(runId: string): Promise<ReportPayload>;
  getAnswers(runId: string): Promise<AnswerRecord[]>;
  /**
   * Persist a generated draft (+ rendered html) to the platform's teasers store
   * (POST /teasers). Returns the new teaser id, or null when persistence isn't
   * available (the mock, or a best-effort failure) — saving must never fail the
   * run. Every generated teaser is captured this way for review + training data.
   */
  saveTeaser(draft: TeaserDraft, html: string): Promise<string | null>;
  /**
   * Flip a persisted teaser to status="approved" (POST /teasers/{id}/approve) —
   * the human sign-off gate. Returns true on success, false when approval isn't
   * available (the mock, or a failed call). Approval is the transition that
   * clears the draft banner, so an approved teaser is the only sendable one.
   */
  approveTeaser(teaserId: string): Promise<boolean>;
  /**
   * Persist a generated AI Visibility Audit (+ rendered html) to the platform's
   * audit_deliverables store (POST /audit-deliverables). Returns the new
   * deliverable id, or null when persistence isn't available (the mock, or a
   * best-effort failure) — saving must never fail the generation. Every audit is
   * captured this way for review + a record of every deliverable (doc §11).
   */
  saveAuditDeliverable(draft: AuditDraft, html: string): Promise<string | null>;
}
