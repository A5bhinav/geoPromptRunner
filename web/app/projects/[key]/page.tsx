"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronRight,
  FileText,
  Loader2,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { INPUT_CLS } from "@/lib/ui";
import { cn } from "@/lib/utils";
import { StateBadge } from "@/components/badges";
import { deleteProject, getProject, type ProjectDetail } from "@/lib/api";

// Monochrome: weight carries state, the label carries the meaning. Sable has
// no alert hue, so `rejected` is not red — it is an outline chip.
const TEASER_STATUS_VARIANT: Record<string, "quiet" | "muted" | "outline" | "solid"> = {
  draft: "quiet",
  approved: "solid",
  rejected: "outline",
  exported: "muted",
};

export default function ProjectDetailPage() {
  const params = useParams<{ key: string }>();
  const key = decodeURIComponent(params.key);
  const router = useRouter();
  const [project, setProject] = React.useState<ProjectDetail | null>(null);
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
  }, [key]);

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
      // Gone — back to the dashboard, and refresh so the card disappears.
      router.push("/projects");
      router.refresh();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed.");
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* --ink-secondary, not Harbour: on the PAPER ground Harbour is 4.14:1. */}
      <Link
        href="/projects"
        className="inline-flex items-center gap-1.5 text-[13px] text-[color:var(--ink-secondary)] transition-colors hover:text-navy"
      >
        <ArrowLeft className="h-4 w-4" /> All projects
      </Link>

      {error && <Notice tone="problem">{error}</Notice>}

      {project === null ? (
        !error && <p className="text-[13px] text-[color:var(--ink-secondary)]">Loading…</p>
      ) : (
        <>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="label">Project</p>
              <h1 className="display text-[34px] leading-tight">{project.label}</h1>
              {project.domain && (
                <a
                  href={`https://${project.domain}`}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-[13px] text-blue transition-colors hover:underline"
                >
                  {project.domain}
                </a>
              )}
            </div>
            {/* `outline`, not a red button: the typed-confirmation dialog below
                is the real guard, and Sable has no alert hue. */}
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              onClick={() => setConfirmOpen(true)}
            >
              <Trash2 className="h-4 w-4" /> Delete project
            </Button>
          </div>

          {/* Audits */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileText className="h-4 w-4 text-harbour" /> Audits
                <span className="text-[13px] font-normal tabular-nums text-harbour">
                  ({project.audits.length})
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {project.audits.length === 0 ? (
                <p className="text-[13px] text-harbour">No audits for this project yet.</p>
              ) : (
                <ul className="divide-y divide-[var(--rule)]">
                  {project.audits.map((a) => (
                    <li key={a.run_id}>
                      <Link
                        href={`/audits/${a.run_id}`}
                        className="-mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-navy/[0.03]"
                      >
                        <span className="text-[13px] font-medium text-navy">{a.client_name}</span>
                        <StateBadge state={a.state} />
                        <span className="text-[13px] text-harbour">
                          {a.n_queries} queries · {a.engines.join(", ") || "no engines"}
                        </span>
                        <span className="ml-auto text-[11px] tabular-nums text-harbour">
                          {new Date(a.created_at).toLocaleString()}
                        </span>
                        <ChevronRight className="h-4 w-4 text-harbour" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Teasers */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4 text-harbour" /> Teasers
                <span className="text-[13px] font-normal tabular-nums text-harbour">
                  ({project.teasers.length})
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {project.teasers.length === 0 ? (
                <p className="text-[13px] text-harbour">No teasers for this project yet.</p>
              ) : (
                <ul className="divide-y divide-[var(--rule)]">
                  {project.teasers.map((t) => (
                    <li key={t.id}>
                      <Link
                        href={`/teaser?teaser=${encodeURIComponent(t.id)}`}
                        className="-mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-navy/[0.03]"
                      >
                        <span className="text-[13px] font-medium text-navy">{t.company_name || "Untitled teaser"}</span>
                        <Badge
                          variant={TEASER_STATUS_VARIANT[t.status] ?? "quiet"}
                          className="capitalize"
                        >
                          {t.status}
                        </Badge>
                        <span className="ml-auto text-[11px] tabular-nums text-harbour">
                          {new Date(t.created_at).toLocaleString()}
                        </span>
                        <ChevronRight className="h-4 w-4 text-harbour" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Delete confirmation modal */}
          {confirmOpen && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
              onClick={onBackdrop}
            >
              <div
                className="w-full max-w-md rounded-lg border border-[var(--rule)] bg-white p-6 shadow-lg"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center gap-2 text-navy">
                  <TriangleAlert className="h-5 w-5" />
                  <h2 className="text-lg font-medium">Delete this project?</h2>
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
                  for <span className="font-medium text-navy">{project.label}</span>, including
                  every answer, citation, judgment, and site-audit result. This cannot be undone.
                </p>
                <label className="mt-4 block text-[13px]">
                  <span className="text-harbour">
                    Type{" "}
                    <span className="font-mono font-medium text-navy">{project.label}</span> to
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
                {deleteError && <Notice tone="problem" className="mt-2">{deleteError}</Notice>}
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
                        <Loader2 className="h-4 w-4 animate-spin" /> Deleting…
                      </>
                    ) : (
                      <>
                        <Trash2 className="h-4 w-4" /> Delete permanently
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
