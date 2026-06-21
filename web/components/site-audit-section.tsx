import { ClipboardCheck, ListChecks, Route, Globe2 } from "lucide-react";
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
import { CheckStatusBadge, ImpactBadge } from "@/components/badges";
import type { SiteAuditPayload, SiteCheckRow, RoadmapRow } from "@/lib/api";

const PHASE_LABELS: Record<number, string> = {
  1: "Accessibility",
  2: "Content",
  3: "Off-site authority",
  4: "Measurement",
};

const CATEGORY_LABELS: Record<string, string> = {
  technical_accessibility: "Technical accessibility",
  content_coverage: "Content coverage",
  content_structure: "Content structure",
  content_substance: "Content substance (E-E-A-T)",
  structured_data: "Structured data",
  offsite_authority: "Off-site authority",
  baseline_measurement: "Baseline measurement",
};

const CHECK_LABELS: Record<string, string> = {
  ssr_rendering: "Server-rendered (AI-crawler visible)",
  internal_linking: "Internal linking",
  schema_valid: "Schema.org markup",
};

// Roll the per-page check verdicts into one status per check: fail > partial >
// pass; a check that's only ever ungradeable is dropped (not assessable).
function rollupChecks(checks: SiteCheckRow[]): { key: string; status: string; pages: number }[] {
  const byKey = new Map<string, string[]>();
  for (const c of checks) {
    const arr = byKey.get(c.check_key) ?? [];
    arr.push(c.status);
    byKey.set(c.check_key, arr);
  }
  const out: { key: string; status: string; pages: number }[] = [];
  for (const [key, statuses] of byKey) {
    const status = statuses.includes("fail")
      ? "fail"
      : statuses.includes("partial")
        ? "partial"
        : statuses.includes("pass")
          ? "pass"
          : "ungradeable";
    out.push({ key, status, pages: statuses.length });
  }
  return out;
}

function RoadmapTables({ roadmap }: { roadmap: RoadmapRow[] }) {
  if (roadmap.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No gaps — every assessable on-site/off-site check passes.
      </p>
    );
  }
  const phases = [...new Set(roadmap.map((r) => r.phase))].sort((a, b) => a - b);
  return (
    <div className="space-y-4">
      {phases.map((phase) => (
        <div key={phase}>
          <h4 className="mb-2 text-sm font-medium">
            Phase {phase} — {PHASE_LABELS[phase] ?? "Other"}
          </h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Gap</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Impact</TableHead>
                <TableHead>Effort</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {roadmap
                .filter((r) => r.phase === phase)
                .map((r, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{r.check_name}</TableCell>
                    <TableCell>
                      <CheckStatusBadge status={r.status} />
                    </TableCell>
                    <TableCell>
                      <ImpactBadge impact={r.impact_label} />
                    </TableCell>
                    <TableCell className="capitalize text-muted-foreground">{r.effort}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  );
}

export function SiteAuditSection({ siteAudit }: { siteAudit: SiteAuditPayload }) {
  const checks = rollupChecks(siteAudit.checks);
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <ClipboardCheck className="h-3.5 w-3.5" />
        Site Audit
      </h2>
      <p className="text-sm text-muted-foreground">
        {siteAudit.domain || "client site"} · {siteAudit.pages_crawled} page(s) crawled
        {siteAudit.errors > 0 && ` · ${siteAudit.errors} fetch error(s)`}
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Prioritized roadmap (§5) */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Route className="h-4 w-4" />
              Prioritized roadmap ({siteAudit.roadmap.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <RoadmapTables roadmap={siteAudit.roadmap} />
          </CardContent>
        </Card>

        {/* On-site checks rollup */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ListChecks className="h-4 w-4" />
              On-site checks
            </CardTitle>
          </CardHeader>
          <CardContent>
            {checks.length === 0 ? (
              <p className="text-sm text-muted-foreground">No on-site checks ran.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Check</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Pages</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {checks.map((c) => (
                    <TableRow key={c.key}>
                      <TableCell className="font-medium">{CHECK_LABELS[c.key] ?? c.key}</TableCell>
                      <TableCell>
                        <CheckStatusBadge status={c.status} />
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{c.pages}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Off-site findings (Cat 6) */}
      {siteAudit.offsite.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Globe2 className="h-4 w-4" />
              Off-site findings ({siteAudit.offsite.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {siteAudit.offsite.map((f, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant="outline" className="capitalize">
                    {f.finding_type.replace(/_/g, " ")}
                  </Badge>
                  {f.url ? (
                    <a
                      href={f.url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium underline-offset-2 hover:underline"
                    >
                      {f.title}
                    </a>
                  ) : (
                    <span className="font-medium">{f.title}</span>
                  )}
                  <span className="text-xs text-muted-foreground">({f.confidence})</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
