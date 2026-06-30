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
import { StateBadge } from "@/components/badges";
import { deleteProject, getProject, type ProjectDetail } from "@/lib/api";

const TEASER_STATUS_VARIANT: Record<
  string,
  "secondary" | "success" | "destructive" | "default"
> = {
  draft: "secondary",
  approved: "success",
  rejected: "destructive",
  exported: "default",
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
      <Link
        href="/projects"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> All projects
      </Link>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {project === null ? (
        !error && <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{project.label}</h1>
              {project.domain && (
                <a
                  href={`https://${project.domain}`}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-muted-foreground transition-colors hover:text-foreground hover:underline"
                >
                  {project.domain}
                </a>
              )}
            </div>
            <Button
              variant="destructive"
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
                <FileText className="h-4 w-4 text-muted-foreground" /> Audits
                <span className="text-sm font-normal text-muted-foreground">
                  ({project.audits.length})
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {project.audits.length === 0 ? (
                <p className="text-sm text-muted-foreground">No audits for this project yet.</p>
              ) : (
                <ul className="divide-y">
                  {project.audits.map((a) => (
                    <li key={a.run_id}>
                      <Link
                        href={`/audits/${a.run_id}`}
                        className="flex items-center gap-3 py-2.5 hover:opacity-80"
                      >
                        <span className="font-medium">{a.client_name}</span>
                        <StateBadge state={a.state} />
                        <span className="text-sm text-muted-foreground">
                          {a.n_queries} queries · {a.engines.join(", ") || "no engines"}
                        </span>
                        <span className="ml-auto text-xs text-muted-foreground">
                          {new Date(a.created_at).toLocaleString()}
                        </span>
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
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
                <Sparkles className="h-4 w-4 text-muted-foreground" /> Teasers
                <span className="text-sm font-normal text-muted-foreground">
                  ({project.teasers.length})
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {project.teasers.length === 0 ? (
                <p className="text-sm text-muted-foreground">No teasers for this project yet.</p>
              ) : (
                <ul className="divide-y">
                  {project.teasers.map((t) => (
                    <li key={t.id}>
                      <Link
                        href={`/teaser?teaser=${encodeURIComponent(t.id)}`}
                        className="flex items-center gap-3 py-2.5 hover:opacity-80"
                      >
                        <span className="font-medium">{t.company_name || "Untitled teaser"}</span>
                        <Badge
                          variant={TEASER_STATUS_VARIANT[t.status] ?? "secondary"}
                          className="capitalize"
                        >
                          {t.status}
                        </Badge>
                        <span className="ml-auto text-xs text-muted-foreground">
                          {new Date(t.created_at).toLocaleString()}
                        </span>
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
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
                className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center gap-2 text-destructive">
                  <TriangleAlert className="h-5 w-5" />
                  <h2 className="text-lg font-semibold">Delete this project?</h2>
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  This permanently deletes{" "}
                  <span className="font-medium text-foreground">
                    {project.audits.length} audit{project.audits.length === 1 ? "" : "s"}
                  </span>{" "}
                  and{" "}
                  <span className="font-medium text-foreground">
                    {project.teasers.length} teaser{project.teasers.length === 1 ? "" : "s"}
                  </span>{" "}
                  for <span className="font-medium text-foreground">{project.label}</span>, including
                  every answer, citation, judgment, and site-audit result. This cannot be undone.
                </p>
                <label className="mt-4 block text-sm">
                  <span className="text-muted-foreground">
                    Type{" "}
                    <span className="font-mono font-medium text-foreground">{project.label}</span> to
                    confirm:
                  </span>
                  <input
                    autoFocus
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                    placeholder={project.label}
                  />
                </label>
                {deleteError && <p className="mt-2 text-sm text-destructive">{deleteError}</p>}
                <div className="mt-5 flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={closeConfirm} disabled={deleting}>
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
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
