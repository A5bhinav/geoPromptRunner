/**
 * HttpPlatformClient — the real PlatformClient, talking to the geoPromptRunner
 * FastAPI (src/api/app.py) over HTTP. Drop-in interchangeable with
 * MockPlatformClient; config.ts selects it when GEO_PLATFORM_URL is set.
 *
 * Endpoint contract (all under the configured base URL):
 *   POST /audits                  (multipart: field "files" = the audit CSV) -> { run_id }
 *   GET  /audits/{run_id}/status  -> RunStatus  (extra per_engine field ignored)
 *   GET  /audits/{run_id}/report  -> ReportPayload
 *   GET  /audits/{run_id}/answers -> QueryResult[]  (consumed as AnswerRecord[])
 *
 * Uses Node 22 global fetch/FormData/Blob — no dependencies. Pure transport: it
 * passes the CSV through and returns the platform's payloads unchanged, so the
 * type definitions in ../types/platform.ts are the single source of truth.
 */

import type {
  AnswerRecord,
  ReportPayload,
  RunState,
  RunStatus,
} from "../types/platform.ts";
import type { AuditInput, PlatformClient } from "./PlatformClient.ts";

export interface HttpPlatformClientOptions {
  /** Base URL of the GEO Audit API, e.g. "http://localhost:8000". */
  baseUrl: string;
  /** Optional request timeout per call (ms). 0/undefined = no timeout. */
  timeoutMs?: number;
  /**
   * Optional shared secret sent as the X-API-Key header. Required when the
   * platform has GEO_API_KEY configured (it 401s data routes otherwise);
   * omit for an open local-dev API.
   */
  apiKey?: string;
}

/** The platform's POST /audits response. */
interface CreateAuditResponse {
  run_id: string;
}

export class HttpPlatformClient implements PlatformClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly apiKey: string | undefined;

  constructor(opts: HttpPlatformClientOptions) {
    // Normalize: drop a trailing slash so `${baseUrl}/audits` never doubles up.
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = opts.timeoutMs ?? 0;
    this.apiKey = opts.apiKey || undefined;
  }

  async submitAudit(input: AuditInput): Promise<{ runId: string }> {
    // The platform parses the CSV from an uploaded file under field name "files"
    // (Annotated[list[UploadFile], File()] in app.py). The other AuditInput
    // fields are derived from the CSV server-side, so we send only the CSV.
    const form = new FormData();
    form.append(
      "files",
      new Blob([input.csv], { type: "text/csv" }),
      "audit.csv",
    );
    const body = await this.request<CreateAuditResponse>("POST", "/audits", {
      body: form,
    });
    return { runId: body.run_id };
  }

  async getStatus(runId: string): Promise<RunStatus> {
    const raw = await this.request<Record<string, unknown>>(
      "GET",
      `/audits/${encodeURIComponent(runId)}/status`,
    );
    // Project onto our RunStatus; the platform also returns per_engine, which the
    // teaser doesn't model. state is one of the RunState string values.
    return {
      run_id: String(raw.run_id ?? runId),
      client_name: String(raw.client_name ?? ""),
      state: raw.state as RunState,
      completed: Number(raw.completed ?? 0),
      total: Number(raw.total ?? 0),
      error: raw.error == null ? null : String(raw.error),
    };
  }

  async getReport(runId: string): Promise<ReportPayload> {
    return this.request<ReportPayload>(
      "GET",
      `/audits/${encodeURIComponent(runId)}/report`,
    );
  }

  async getAnswers(runId: string): Promise<AnswerRecord[]> {
    // The endpoint returns rows in the storage QueryResult shape, which is
    // field-for-field AnswerRecord (see types/platform.ts).
    return this.request<AnswerRecord[]>(
      "GET",
      `/audits/${encodeURIComponent(runId)}/answers`,
    );
  }

  /** One JSON request with status-aware errors and an optional timeout. */
  private async request<T>(
    method: string,
    path: string,
    init: { body?: BodyInit } = {},
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const controller = this.timeoutMs > 0 ? new AbortController() : null;
    const timer =
      controller && this.timeoutMs > 0
        ? setTimeout(() => controller.abort(), this.timeoutMs)
        : null;
    // Only set X-API-Key; leave Content-Type unset so fetch derives the
    // multipart boundary for FormData uploads.
    const headers: Record<string, string> = {};
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    let res: Response;
    try {
      res = await fetch(url, {
        method,
        body: init.body,
        headers,
        signal: controller?.signal,
      });
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      throw new Error(`platform ${method} ${path} failed: ${reason}`);
    } finally {
      if (timer) clearTimeout(timer);
    }

    if (!res.ok) {
      // Surface the platform's error body (e.g. the 422 validation detail) so
      // the pipeline's failure reason is actionable.
      const detail = await res.text().catch(() => "");
      throw new Error(
        `platform ${method} ${path} -> ${res.status} ${res.statusText}` +
          (detail ? `: ${detail.slice(0, 2000)}` : ""),
      );
    }
    return (await res.json()) as T;
  }
}
