"use client";

import * as React from "react";
import Link from "next/link";
import { FolderOpen, FileText, Sparkles, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StateBadge } from "@/components/badges";
import { listProjects, type ProjectSummary } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = React.useState<ProjectSummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => {
        setError("Could not load projects. Is the API running on :8000?");
        setProjects([]);
      });
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <p className="mt-1 text-muted-foreground">
          Every audit and teaser, grouped by prospect. One place to see all the work for a domain.
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {projects === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No projects yet. Run an audit or generate a teaser and it&apos;ll show up here grouped by
            its domain.
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => (
            <Link key={p.key} href={`/projects/${encodeURIComponent(p.key)}`} className="group">
              <Card className="h-full transition-colors group-hover:border-primary/50">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <FolderOpen className="h-4 w-4 text-muted-foreground" />
                    <span className="truncate">{p.label}</span>
                    {p.last_state && <StateBadge state={p.last_state} />}
                    <ChevronRight className="ml-auto h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5" /> {p.audit_count} audit
                      {p.audit_count === 1 ? "" : "s"}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5" /> {p.teaser_count} teaser
                      {p.teaser_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  {p.engines.length > 0 && (
                    <p className="truncate text-xs text-muted-foreground">
                      Engines: {p.engines.join(", ")}
                    </p>
                  )}
                  {p.last_activity && (
                    <p className="text-xs text-muted-foreground">
                      Last activity {new Date(p.last_activity).toLocaleString()}
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
