/**
 * MockPlatformClient — synthesizes a realistic, losing-heavy audit result so the
 * entire teaserAuto flow runs with no platform deployed and no API keys.
 *
 * It models the scenario teasers are built on: the client is absent on the
 * high-intent category/comparison queries while the top competitor is recommended
 * everywhere — producing a strong losing_queries list and headline number.
 *
 * Determinism: output is a pure function of the submitted AuditInput (no clocks,
 * no randomness), so runs are reproducible and tests are stable. Swap in
 * HttpPlatformClient (same interface) once the real platform is reachable.
 */

import type {
  AnswerRecord,
  IntentBucket,
  LeaderRow,
  LosingRow,
  ReportPayload,
  RunStatus,
} from "../types/platform.ts";
import type { AuditInput, PlatformClient } from "./PlatformClient.ts";

interface StoredRun {
  input: AuditInput;
  report: ReportPayload;
  answers: AnswerRecord[];
}

/** The client is "present" only on brand-intent queries; absent elsewhere. */
function clientPresent(intent: string): boolean {
  return intent === "brand";
}

function fakeAnswer(
  clientName: string,
  topCompetitor: string,
  otherCompetitors: string[],
  queryText: string,
  intent: string,
): string {
  const q = queryText.toLowerCase();
  // Don't list a rival the buyer already named in the query (e.g. "alternatives
  // to Vantage" shouldn't recommend Vantage) — keeps the synthetic answer coherent.
  const namedInQuery = (b: string) => q.includes(b.toLowerCase());
  const others = otherCompetitors.filter((c) => !namedInQuery(c));
  const rivals = [topCompetitor, ...others].slice(0, 3);
  if (clientPresent(intent)) {
    return (
      `${clientName} is a solid option here. For "${q}", ` +
      `${clientName} is frequently mentioned alongside ${rivals.join(", ")}, ` +
      `though ${topCompetitor} is often the headline recommendation.`
    );
  }
  // Losing answer: competitor recommended first, client absent entirely.
  const otherChoices = rivals.slice(1);
  const otherClause = otherChoices.length
    ? ` Other strong choices include ${otherChoices.join(" and ")}.`
    : "";
  return (
    `For "${q}", the most recommended option is ${topCompetitor}.${otherClause} ` +
    `${topCompetitor} stands out for its maturity and integrations.`
  );
}

const SAMPLE_DOMAINS = ["g2.com", "reddit.com", "capterra.com", "producthunt.com"];

export class MockPlatformClient implements PlatformClient {
  private runs = new Map<string, StoredRun>();
  private counter = 0;

  async submitAudit(input: AuditInput): Promise<{ runId: string }> {
    const runId = `mock-run-${++this.counter}`;
    const built = this.build(input);
    this.runs.set(runId, built);
    return { runId };
  }

  async getStatus(runId: string): Promise<RunStatus> {
    const run = this.mustGet(runId);
    const total = run.answers.length;
    return {
      run_id: runId,
      client_name: run.input.clientName,
      state: "done",
      completed: total,
      total,
      error: null,
    };
  }

  async getReport(runId: string): Promise<ReportPayload> {
    return this.mustGet(runId).report;
  }

  async getAnswers(runId: string): Promise<AnswerRecord[]> {
    return this.mustGet(runId).answers;
  }

  private mustGet(runId: string): StoredRun {
    const run = this.runs.get(runId);
    if (!run) throw new Error(`mock run ${runId} not found`);
    return run;
  }

  private build(input: AuditInput): StoredRun {
    const client = input.clientName;
    const topCompetitor = input.competitors[0] ?? "Competitor";
    const others = input.competitors.slice(1);
    const engines = input.engines.length > 0 ? input.engines : ["perplexity"];
    const runDate = "2026-06-20";

    // --- synthesize one answer per (query, engine) ---
    const answers: AnswerRecord[] = [];
    const losing: LosingRow[] = [];
    for (const q of input.queries) {
      for (const engine of engines) {
        const response = fakeAnswer(client, topCompetitor, others, q.text, q.intent);
        answers.push({
          query_id: q.query_id,
          intent: q.intent as IntentBucket,
          prompt: q.text,
          engine_name: engine,
          run_index: 0,
          response,
          citations: SAMPLE_DOMAINS.slice(0, 2).map((d) => `https://${d}/${q.query_id}`),
          timestamp: `${runDate}T12:00:00Z`,
        });
        if (!clientPresent(q.intent)) {
          losing.push({
            query_id: q.query_id,
            intent: q.intent as IntentBucket,
            engine_name: engine,
            competitor: topCompetitor,
          });
        }
      }
    }

    // --- per-query presence (collapsed across engines) for the headline number ---
    const queryIds = input.queries.map((q) => q.query_id);
    const n = queryIds.length;
    const clientAppearsQueries = input.queries.filter((q) => clientPresent(q.intent)).length;
    const competitorAppearsQueries = n; // mock: top competitor present on every query

    // --- leaderboard / mention rates ---
    const clientMention = n === 0 ? 0 : clientAppearsQueries / n;
    const brands = [client, ...input.competitors];
    const mentionByBrand: Record<string, number> = {};
    for (const b of brands) mentionByBrand[b] = b === client ? clientMention : b === topCompetitor ? 1 : 0.5;
    const total = Object.values(mentionByBrand).reduce((a, b) => a + b, 0) || 1;
    const leaderboard: LeaderRow[] = brands
      .map((brand): LeaderRow => ({
        brand,
        is_client: brand === client,
        visibility: brand === client ? clientMention : brand === topCompetitor ? 0.95 : 0.4,
        mention_rate: mentionByBrand[brand] ?? 0,
        share_of_model: (mentionByBrand[brand] ?? 0) / total,
      }))
      .sort((a, b) => b.mention_rate - a.mention_rate);

    const report: ReportPayload = {
      client_name: client,
      run_date: runDate,
      query_set_version: "teaser-mock",
      runs_per_query: 1,
      engines,
      competitors: input.competitors,
      client_domains: input.clientDomains,
      detection: "judge",
      scorecard: {
        visibility_grade: {
          letter: "F",
          score: clientMention,
          raw_score: clientMention,
          accuracy_penalty: 0,
          n_flags: 0,
          rationale: "Client is absent on the high-intent category and comparison queries.",
        },
        share_of_model_client: (mentionByBrand[client] ?? 0) / total,
        top_competitor: topCompetitor,
        top_competitor_share: (mentionByBrand[topCompetitor] ?? 0) / total,
        mention_rate_client: clientMention,
        mention_rate_top_competitor: 1,
        citation_rate_client: 0,
        accuracy_assessed: false,
        accuracy_flag_count: null,
      },
      leaderboard,
      by_bucket: dedupeBuckets(input.queries).map((bucket) => ({
        bucket,
        mention_rate: bucket === "brand" ? 1 : 0,
        citation_rate: 0,
      })),
      accuracy_flags: [],
      sources: SAMPLE_DOMAINS.map((domain, i) => ({ domain, count: 6 - i })),
      losing_queries: losing,
    };

    // Stash the headline counts on a closure-free path: recompute in selector.
    void competitorAppearsQueries;

    return { input, report, answers };
  }
}

function dedupeBuckets(queries: { intent: string }[]): string[] {
  return [...new Set(queries.map((q) => q.intent))].sort();
}
