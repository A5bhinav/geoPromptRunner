"use client";

import * as React from "react";
import Link from "next/link";
import { Notice } from "@/components/notice";
import { Page, PageHeader, Panel } from "@/components/page";
import { StateBadge } from "@/components/badges";
import { listProjects, type ProjectSummary } from "@/lib/api";

/** "2026-06-14T…" → "14 June 2026". Falls back to the raw string: a timestamp we
 * cannot parse is still better than "Invalid Date". */
function longDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

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
    <Page className="gap-6">
      <PageHeader
        eyebrow="Projects"
        title="Every client, every run"
        helper="Every audit and teaser, grouped by client. One place to see all the work for a domain."
      />

      {error && <Notice tone="problem">{error}</Notice>}

      {projects === null ? (
        <p className="text-[13px] text-[color:var(--ink-secondary)]">Loading…</p>
      ) : projects.length === 0 ? (
        <Panel className="px-5 py-10 text-center text-[13px] text-harbour">
          No projects yet. Run an audit or generate a teaser and it&apos;ll show up here, grouped by
          its domain.
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-[18px] md:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => (
            <Link
              key={p.key}
              href={`/projects/${encodeURIComponent(p.key)}`}
              className="group rounded-lg"
            >
              <Panel className="flex h-full min-h-[172px] flex-col gap-2 p-5 transition-colors group-hover:border-navy/35">
                <div className="flex items-start justify-between gap-3">
                  <span className="text-[16px] font-semibold leading-tight">{p.label}</span>
                  {/* Fill weight + glyph, never hue: Sable has no alert colour,
                      so `interrupted` is a Mist chip with a triangle, not red. */}
                  {p.last_state ? <StateBadge state={p.last_state} /> : null}
                </div>

                {p.domain ? (
                  <span className="truncate text-[13px] text-blue">{p.domain}</span>
                ) : (
                  <span className="text-[13px] text-harbour">No domain on file</span>
                )}

                <p className="text-[13px] tabular-nums text-[color:var(--ink-secondary)]">
                  {p.audit_count} audit{p.audit_count === 1 ? "" : "s"}
                  {p.teaser_count > 0
                    ? ` · ${p.teaser_count} teaser${p.teaser_count === 1 ? "" : "s"}`
                    : ""}
                </p>

                {p.engines.length > 0 ? (
                  <p className="line-clamp-2 text-[11px] text-[color:var(--ink-secondary)]">
                    {p.engines.join(", ")}
                  </p>
                ) : null}

                {p.last_activity ? (
                  <p className="mt-auto pt-2 text-[11px] tabular-nums text-[color:var(--ink-secondary)]">
                    {longDate(p.last_activity)}
                  </p>
                ) : null}
              </Panel>
            </Link>
          ))}
        </div>
      )}
    </Page>
  );
}
