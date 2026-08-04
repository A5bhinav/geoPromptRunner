"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ChevronRight, Loader2, Sparkles, Trash2, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { Page, PageHeader, Panel, CardLabel } from "@/components/page";
import { TrendChart } from "@/components/marks";
import { StateBadge } from "@/components/badges";
import { INPUT_CLS } from "@/lib/ui";
import { cn, pct } from "@/lib/utils";
import {
  deleteProject,
  getProject,
  getProjectHistory,
  type ProjectDetail,
  type ProjectHistoryPoint,
} from "@/lib/api";

// Monochrome: weight carries state, the label carries the meaning. Sable has
// no alert hue, so `rejected` is not red — it is an outline chip.
const TEASER_STATUS_VARIANT: Record<string, "quiet" | "muted" | "outline" | "solid"> = {
  draft: "quiet",
  approved: "solid",
  rejected: "outline",
  exported: "muted",
};

function longDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export default function ProjectDetailPage() {
  const params = useParams<{ key: string }>();
  const key = decodeURIComponent(params.key);
  const router = useRouter();
  const [project, setProject] = React.useState<ProjectDetail | null>(null);
  const [history, setHistory] = React.useState<ProjectHistoryPoint[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Delete-confirmation state.
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [confirmText, setConfirmText] = React.useState("");
  const [deleting, setDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  React.useEffect(() => {
    getProject(key)
      .then(setProject)
      .catch(() => setError("Project not found, or the API is unreachable."));
    // The trend costs one report assembly per completed run, so it loads on its
    // own and the page does not wait for it. A missing trend is a quieter
    // failure than a blank page.
    getProjectHistory(key)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [key]);

  const byRun = React.useMemo(
    () => new Map((history ?? []).map((h) => [h.run_id, h])),
    [history],
  );

  /**
   * Only compare like instruments.
   *
   * A run is comparable only to a run with the same `query_set_version`, so the
   * line is drawn across the TRAILING RUN of cycles that share the newest
   * version and stops there. Older cycles asked different questions; joining
   * them with a line would assert a change in visibility that is really a change
   * in the measuring stick.
   */
  const { points, droppedForVersionChange } = React.useMemo(() => {
    const rows = history ?? [];
    if (rows.length === 0) return { points: [], droppedForVersionChange: 0 };
    const current = rows[rows.length - 1].query_set_version;
    let start = rows.length;
    while (start > 0 && rows[start - 1].query_set_version === current) start -= 1;
    const comparable = rows.slice(start).filter((r) => r.mention_n > 0);
    return {
      points: comparable.map((r) => ({
        label: shortDate(r.run_date),
        value: Math.round((r.mention_successes / r.mention_n) * 100),
      })),
      droppedForVersionChange: start,
    };
  }, [history]);

  // Cancel always closes (even with an error showing); only a delete in flight blocks it.
  const closeConfirm = () => {
    if (deleting) return;
    setConfirmOpen(false);
    setConfirmText("");
    setDeleteError(null);
  };

  // Backdrop click is a softer dismiss — don't let it discard a delete error the
  // user may want to read/retry; they must click Cancel explicitly.
  const onBackdrop = () => {
    if (deleting || deleteError) return;
    closeConfirm();
  };

  const onDelete = async () => {
    if (!project || confirmText.trim() !== project.label) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteProject(key);
      router.push("/projects");
      router.refresh();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed.");
      setDeleting(false);
    }
  };

  if (error) {
    return (
      <Page>
        <Notice tone="problem">{error}</Notice>
      </Page>
    );
  }
  if (project === null) {
    return (
      <Page>
        <p className="text-[13px] text-[color:var(--ink-secondary)]">Loading…</p>
      </Page>
    );
  }

  return (
    <Page className="gap-[22px]">
      <PageHeader
        eyebrow="Project"
        title={project.label}
        href={project.domain ? `https://${project.domain}` : undefined}
        hrefLabel={project.domain ?? undefined}
        actions={
          // `outline`, not a red button: the typed-confirmation dialog below is
          // the real guard, and Sable has no alert hue.
          <Button variant="outline" onClick={() => setConfirmOpen(true)}>
            <Trash2 className="h-4 w-4" aria-hidden /> Delete project
          </Button>
        }
      />

      <Panel className="p-5">
        <CardLabel className="mb-3.5">Mention rate over time</CardLabel>
        {history === null ? (
          <p className="py-8 text-[13px] text-harbour">Assembling the cycle history…</p>
        ) : points.length < 2 ? (
          <p className="py-8 text-[13px] text-harbour">
            {points.length === 1
              ? "One comparable cycle so far. A trend needs two — the next run draws the line."
              : "No completed cycle has a measured mention rate yet."}
          </p>
        ) : (
          <TrendChart
            points={points}
            yTicks={[25, 50, 75, 100]}
            ariaLabel={`Mention rate by cycle for ${project.label}`}
            caption={
              droppedForVersionChange > 0
                ? `All assistants combined. Each point is one cycle. ${droppedForVersionChange} earlier cycle${
                    droppedForVersionChange === 1 ? "" : "s"
                  } asked a different question set and are not comparable, so they are not plotted.`
                : "All assistants combined. Each point is one cycle."
            }
          />
        )}
      </Panel>

      <div>
        <p className="mb-3 text-[19px] font-semibold leading-tight tracking-[-0.01em]">
          Run history
        </p>
        {project.audits.length === 0 ? (
          <Panel className="px-5 py-8 text-[13px] text-harbour">
            No audits for this project yet.
          </Panel>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr>
                <th className="col-label w-[200px] pb-2 text-left">Date</th>
                <th className="col-label pb-2 text-left">Mention rate</th>
                <th className="col-label w-[150px] pb-2 text-right">Share of model</th>
                <th className="col-label w-[140px] pb-2 text-right">Open findings</th>
                <th className="col-label w-[100px] pb-2 text-right">Critical</th>
              </tr>
            </thead>
            <tbody>
              {project.audits.map((a) => {
                const h = byRun.get(a.run_id);
                const rate = h && h.mention_n > 0 ? h.mention_successes / h.mention_n : null;
                return (
                  <tr key={a.run_id} className="border-t border-[var(--rule-inner)]">
                    <td className="py-3">
                      <Link href={`/audits/${a.run_id}`} className="text-blue hover:underline">
                        {longDate(a.created_at)}
                      </Link>
                    </td>
                    <td className="py-3">
                      {rate === null ? (
                        // Not "0%". A run that never finished has no rate, and a
                        // zero would be a measurement we did not make.
                        <span className="inline-flex items-center gap-2 text-harbour">
                          <StateBadge state={a.state} />
                          {a.state === "done" ? "not measured" : ""}
                        </span>
                      ) : (
                        <span className="relative inline-flex w-[260px] items-center">
                          <span
                            aria-hidden
                            className="absolute left-0 top-1/2 h-5 -translate-y-1/2 rounded bg-navy/[0.12]"
                            style={{ width: `${rate * 100}%` }}
                          />
                          {/* The count is not optional garnish — the bar encodes
                              the rate and the text carries the denominator. */}
                          <span className="relative pl-2.5 tabular-nums">
                            {pct(rate)} · {h!.mention_successes} of {h!.mention_n}
                          </span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 text-right tabular-nums">
                      {h ? pct(h.share_of_model) : "—"}
                    </td>
                    <td className="py-3 text-right tabular-nums">{h ? h.open_findings : "—"}</td>
                    <td className="py-3 text-right tabular-nums">{h ? h.critical : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {project.teasers.length > 0 && (
        <div>
          <p className="mb-3 flex items-center gap-2 text-[19px] font-semibold leading-tight tracking-[-0.01em]">
            <Sparkles className="h-4 w-4 text-harbour" aria-hidden /> Teasers
            <span className="text-[13px] font-normal tabular-nums text-harbour">
              ({project.teasers.length})
            </span>
          </p>
          <Panel>
            <ul className="divide-y divide-[var(--rule-inner)]">
              {project.teasers.map((t) => (
                <li key={t.id}>
                  <Link
                    href={`/teaser?teaser=${encodeURIComponent(t.id)}`}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-navy/[0.03]"
                  >
                    <span className="text-[13px] font-medium">
                      {t.company_name || "Untitled teaser"}
                    </span>
                    <Badge
                      variant={TEASER_STATUS_VARIANT[t.status] ?? "quiet"}
                      className="capitalize"
                    >
                      {t.status}
                    </Badge>
                    <span className="ml-auto text-[11px] tabular-nums text-harbour">
                      {longDate(t.created_at)}
                    </span>
                    <ChevronRight className="h-4 w-4 text-harbour" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}

      {confirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={onBackdrop}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-project-title"
            className="w-full max-w-md rounded-lg border border-[var(--rule)] bg-white p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 text-navy">
              <TriangleAlert className="h-5 w-5" aria-hidden />
              <h2 id="delete-project-title" className="text-lg font-medium">
                Delete this project?
              </h2>
            </div>
            <p className="mt-3 text-[13px] text-harbour">
              This permanently deletes{" "}
              <span className="font-medium text-navy">
                {project.audits.length} audit{project.audits.length === 1 ? "" : "s"}
              </span>{" "}
              and{" "}
              <span className="font-medium text-navy">
                {project.teasers.length} teaser{project.teasers.length === 1 ? "" : "s"}
              </span>{" "}
              for <span className="font-medium text-navy">{project.label}</span>, including every
              answer, citation, judgment, and site-audit result. This cannot be undone.
            </p>
            <label className="mt-4 block text-[13px]">
              <span className="text-harbour">
                Type <span className="font-mono font-medium text-navy">{project.label}</span> to
                confirm:
              </span>
              <input
                autoFocus
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                className={cn(INPUT_CLS, "mt-1 h-10")}
                placeholder={project.label}
              />
            </label>
            {deleteError && (
              <Notice tone="problem" className="mt-2">
                {deleteError}
              </Notice>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={closeConfirm} disabled={deleting}>
                Cancel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={onDelete}
                disabled={deleting || confirmText.trim() !== project.label}
              >
                {deleting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Deleting…
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4" aria-hidden /> Delete permanently
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Page>
  );
}
