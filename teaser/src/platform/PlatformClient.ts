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
  /**
   * An APPROVED fact sheet to judge this run's accuracy against.
   *
   * Mutually exclusive with `fact` rows in the CSV — the platform refuses a run
   * carrying both, because two sources of ground truth for one measurement is the
   * ambiguity §4.3 says becomes a question rather than a silent winner.
   *
   * The pointer rather than embedded rows, deliberately: only the id populates
   * `fact_sheet_verification` on the report, and without that tier every accuracy
   * finding is suppressed by the send gate. Embedding the rows gives the judge
   * ground truth and then throws away the permission to say anything about it.
   */
  factSheetId?: string | null;
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

/** One business from Google's local pack, as the platform's /local-entities returns it. */
export interface LocalEntity {
  name: string;
  address: string;
  /** Google's own category string ("Plumber", "Barber shop"). */
  category: string;
  rating: number | null;
  reviews: number | null;
  ludocid: string | null;
  position: number | null;
}

export interface PlatformClient {
  submitAudit(input: AuditInput): Promise<{ runId: string }>;
  /**
   * Businesses in Google's local pack for a query at a canonical location (W1.6).
   *
   * The ONLY sanctioned source of local competitor candidates. Claude does not
   * reliably know the plumbers in a given city, and a fabricated rival printed in a
   * teaser emailed to a real shop owner is the unrecoverable failure for this
   * product — so local rivals come from captured entities or the resolver fails.
   *
   * Goes through the platform rather than SearchApi directly because
   * SEARCHAPI_API_KEY lives in the platform's settings and nowhere else.
   *
   * Throws when the capture is unavailable; returns [] when the query genuinely
   * surfaced no local pack. Those are different situations and the caller must be
   * able to tell them apart — an empty list must never be read as "no competitors".
   */
  /**
   * The APPROVED fact sheet for a domain, or null when none has been approved.
   *
   * Null is the normal state, not an error: most prospects have no reviewed sheet,
   * and a teaser without one simply carries no accuracy findings. Returning null
   * rather than throwing is what keeps the teaser generating for every other
   * prospect while sheets are still being reviewed.
   */
  getActiveFactSheetId(domain: string): Promise<string | null>;
  getLocalEntities(query: string, location: string): Promise<LocalEntity[]>;
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
