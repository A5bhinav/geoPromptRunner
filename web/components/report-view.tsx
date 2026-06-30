"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import {
  Printer,
  Download,
  FileText,
  FileSpreadsheet,
  Gavel,
  Loader2,
  Trophy,
  Target,
  Quote,
  ShieldCheck,
  PieChart as PieIcon,
  BarChart3,
  Globe,
  TrendingDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { IntentBadge, SeverityBadge } from "@/components/badges";
import { SiteAuditSection } from "@/components/site-audit-section";
// Charts pull in recharts (the heaviest dependency). Load them lazily on the
// client so recharts ships in a report-only chunk, not the shared bundle.
const chartFallback = <div className="h-40 animate-pulse rounded-lg bg-secondary/40" />;
const LeaderboardChart = dynamic(
  () => import("@/components/charts").then((m) => m.LeaderboardChart),
  { ssr: false, loading: () => chartFallback },
);
const ShareDonut = dynamic(() => import("@/components/charts").then((m) => m.ShareDonut), {
  ssr: false,
  loading: () => chartFallback,
});
const BucketChart = dynamic(() => import("@/components/charts").then((m) => m.BucketChart), {
  ssr: false,
  loading: () => chartFallback,
});
const SourcesChart = dynamic(() => import("@/components/charts").then((m) => m.SourcesChart), {
  ssr: false,
  loading: () => chartFallback,
});
import { pct } from "@/lib/utils";
import { downloadAudit, judgeAudit, type ReportPayload } from "@/lib/api";

function MetricCard({
  icon,
  label,
  value,
  sub,
  muted,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {icon}
          {label}
        </div>
        <div
          className={
            muted
              ? "text-lg font-medium text-muted-foreground"
              : "text-3xl font-semibold tabular-nums"
          }
        >
          {value}
        </div>
        {sub && <div className="mt-1 text-sm text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function gradeColor(letter: string): string {
  if (letter === "A" || letter === "B") return "text-[hsl(var(--success))]";
  if (letter === "C") return "text-[hsl(var(--warning))]";
  return "text-destructive";
}

function SectionTitle({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
      {icon}
      {children}
    </h2>
  );
}

export function ReportView({
  report,
  runId,
  onJudged,
}: {
  report: ReportPayload;
  runId?: string;
  // Lets the parent swap in the refreshed report after an on-demand judge pass.
  onJudged?: (report: ReportPayload) => void;
}) {
  const s = report.scorecard;
  const topComp = s.top_competitor;

  const [judging, setJudging] = React.useState(false);
  const [judgeError, setJudgeError] = React.useState<string | null>(null);

  // Run the LLM judge over the stored answers. Free when the judge cache was
  // pre-filled on the subscription (the /prejudge workflow); otherwise it judges
  // on the API. On success the parent re-renders with the judged report.
  const runJudge = async () => {
    if (!runId || judging) return;
    setJudging(true);
    setJudgeError(null);
    try {
      const updated = await judgeAudit(runId);
      onJudged?.(updated);
    } catch {
      setJudgeError("Judging failed — is the API reachable and a judge key set?");
    } finally {
      setJudging(false);
    }
  };

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `geo-audit-${report.client_name.replace(/\s+/g, "-").toLowerCase()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Raw per-call answers (query text + full model response). Fetched with the
  // API key and saved as a blob (an <a href> couldn't carry the auth header).
  const downloadAnswers = (ext: "results.csv" | "answers.md") => {
    if (!runId) return;
    void downloadAudit(runId, ext);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {report.client_name} — GEO Audit
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {report.run_date} · query set {report.query_set_version} · {report.runs_per_query}{" "}
            run(s)/query · engines: {report.engines.join(", ") || "none"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge variant={report.detection === "judge" ? "default" : "secondary"}>
              {report.detection === "judge" ? "LLM judge" : "regex detection"}
            </Badge>
            {report.competitors.map((c) => (
              <Badge key={c} variant="outline">
                {c}
              </Badge>
            ))}
          </div>
        </div>
        <div className="no-print flex flex-col items-end gap-1.5">
          <div className="flex gap-2">
          {runId && (
            <Button
              variant={report.detection === "judge" ? "outline" : "default"}
              size="sm"
              onClick={runJudge}
              disabled={judging}
              title={
                report.detection === "judge"
                  ? "Re-run the LLM judge over the stored answers (free if the judge cache is warm)"
                  : "Run the LLM judge over the stored answers — free if you pre-judged this run on the subscription"
              }
            >
              {judging ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Gavel className="h-4 w-4" />
              )}
              {judging
                ? "Judging…"
                : report.detection === "judge"
                  ? "Re-judge"
                  : "Judge"}
            </Button>
          )}
          {runId && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadAnswers("results.csv")}
                title="Every query and the full model response, one row per call"
              >
                <FileSpreadsheet className="h-4 w-4" /> Answers CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadAnswers("answers.md")}
                title="Readable answers doc with the judge's verdict inline"
              >
                <FileText className="h-4 w-4" /> Answers MD
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" onClick={downloadJson}>
            <Download className="h-4 w-4" /> JSON
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4" /> Export
          </Button>
          </div>
          {runId && report.detection !== "judge" && (
            <p className="max-w-xs text-right text-xs text-muted-foreground">
              Tip: pre-judge this run on the subscription first (<code>/prejudge {runId.slice(0, 8)}</code> in
              Claude Code) so Judge is $0.
            </p>
          )}
        </div>
      </div>

      {judgeError && (
        <div className="no-print rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {judgeError}
        </div>
      )}

      {/* §1 Scorecard */}
      <section className="space-y-3">
        <SectionTitle icon={<Trophy className="h-3.5 w-3.5" />}>Scorecard</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard
            icon={<Trophy className="h-3.5 w-3.5" />}
            label="AI Visibility Grade"
            muted={!s.visibility_grade}
            value={
              s.visibility_grade ? (
                <span className={gradeColor(s.visibility_grade.letter)}>
                  {s.visibility_grade.letter}
                </span>
              ) : (
                "Not assessed"
              )
            }
            sub={s.visibility_grade ? s.visibility_grade.rationale : "needs the LLM judge"}
          />
          <MetricCard
            icon={<PieIcon className="h-3.5 w-3.5" />}
            label="Share of model"
            value={pct(s.share_of_model_client)}
            sub={
              topComp ? `vs ${topComp} ${pct(s.top_competitor_share)}` : "no competitors configured"
            }
          />
          <MetricCard
            icon={<Target className="h-3.5 w-3.5" />}
            label="Mention rate"
            value={pct(s.mention_rate_client)}
            sub={topComp ? `vs ${topComp} ${pct(s.mention_rate_top_competitor)}` : undefined}
          />
          <MetricCard
            icon={<Quote className="h-3.5 w-3.5" />}
            label="Citation rate"
            muted={s.citation_rate_client === null}
            value={s.citation_rate_client === null ? "Not assessed" : pct(s.citation_rate_client)}
            sub={
              s.citation_rate_client === null ? "no client domain provided" : "of cells cite client"
            }
          />
          <MetricCard
            icon={<ShieldCheck className="h-3.5 w-3.5" />}
            label="Accuracy flags"
            muted={!s.accuracy_assessed}
            value={s.accuracy_assessed ? (s.accuracy_flag_count ?? 0) : "Not assessed"}
            sub={
              s.accuracy_assessed
                ? "claims the models got wrong"
                : report.detection === "judge"
                  ? "needs a fact sheet"
                  : "needs the LLM judge"
            }
          />
        </div>
      </section>

      {/* §2 Competitive position — donut + bars */}
      <section className="space-y-3">
        <SectionTitle icon={<PieIcon className="h-3.5 w-3.5" />}>Competitive position</SectionTitle>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Share of model</CardTitle>
            </CardHeader>
            <CardContent>
              <ShareDonut rows={report.leaderboard} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Visibility leaderboard</CardTitle>
            </CardHeader>
            <CardContent>
              <LeaderboardChart rows={report.leaderboard} />
            </CardContent>
          </Card>
        </div>
        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Brand</TableHead>
                  <TableHead>Share of model</TableHead>
                  <TableHead>Mention rate</TableHead>
                  <TableHead>Visibility</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.leaderboard.map((r) => (
                  <TableRow key={r.brand}>
                    <TableCell className="font-medium">
                      {r.brand}
                      {r.is_client && (
                        <Badge variant="default" className="ml-2">
                          client
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">{pct(r.share_of_model)}</TableCell>
                    <TableCell className="tabular-nums">{pct(r.mention_rate)}</TableCell>
                    <TableCell className="tabular-nums">
                      {r.visibility === null ? "—" : r.visibility.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </section>

      {/* §3 Funnel stage + accuracy */}
      <section className="space-y-3">
        <SectionTitle icon={<BarChart3 className="h-3.5 w-3.5" />}>
          Visibility by funnel stage
        </SectionTitle>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mention &amp; citation by intent</CardTitle>
            </CardHeader>
            <CardContent>
              <BucketChart rows={report.by_bucket} />
              <Table className="mt-4">
                <TableHeader>
                  <TableRow>
                    <TableHead>Bucket</TableHead>
                    <TableHead>Mention</TableHead>
                    <TableHead>Citation</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.by_bucket.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-muted-foreground">
                        No data.
                      </TableCell>
                    </TableRow>
                  ) : (
                    report.by_bucket.map((b) => (
                      <TableRow key={b.bucket}>
                        <TableCell>
                          <IntentBadge intent={b.bucket} />
                        </TableCell>
                        <TableCell className="tabular-nums">{pct(b.mention_rate)}</TableCell>
                        <TableCell className="tabular-nums">
                          {b.citation_rate === null ? "—" : pct(b.citation_rate)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Accuracy flags ({report.accuracy_flags.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {report.accuracy_flags.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {s.accuracy_assessed
                    ? "None flagged — the models described the client accurately."
                    : report.detection === "judge"
                      ? "Not assessed — add a fact sheet (fact rows in the CSV) so the judge can check claims."
                      : "Not assessed — enable the LLM judge (config,judge,true)."}
                </p>
              ) : (
                <ul className="space-y-3">
                  {report.accuracy_flags.map((f, i) => (
                    <li key={i} className="rounded-lg border p-3">
                      <div className="mb-1 flex items-center gap-2">
                        <SeverityBadge severity={f.severity} />
                        <span className="text-sm font-medium capitalize">
                          {f.type.replace(/_/g, " ")}
                        </span>
                      </div>
                      <p className="text-sm">
                        <span className="text-destructive">{f.claim}</span>
                        <span className="text-muted-foreground"> → </span>
                        <span>{f.reality}</span>
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* §4 Sources + losing queries */}
      <section className="space-y-3">
        <SectionTitle icon={<Globe className="h-3.5 w-3.5" />}>Sources &amp; gaps</SectionTitle>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sources behind the category</CardTitle>
            </CardHeader>
            <CardContent>
              <SourcesChart rows={report.sources} />
              {report.sources.length > 0 && (
                <Table className="mt-4">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Domain</TableHead>
                      <TableHead>Cited in cells</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {report.sources.map((src) => (
                      <TableRow key={src.domain}>
                        <TableCell className="font-medium">{src.domain}</TableCell>
                        <TableCell className="tabular-nums">{src.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingDown className="h-4 w-4 text-destructive" />
                Losing queries ({report.losing_queries.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {report.losing_queries.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  None — the client appears wherever a competitor does.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Query</TableHead>
                      <TableHead>Engine</TableHead>
                      <TableHead>Competitor</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {report.losing_queries.map((l, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-medium">{l.query_id}</TableCell>
                        <TableCell>{l.engine_name}</TableCell>
                        <TableCell>{l.competitor}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* §5 On-site & off-site audit (technique checklist Cat 1–6) */}
      {report.site_audit?.present && <SiteAuditSection siteAudit={report.site_audit} />}
    </div>
  );
}
