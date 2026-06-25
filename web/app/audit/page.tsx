"use client";

import * as React from "react";
import { FileText, Loader2, Download, Printer, AlertTriangle, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  listAudits,
  generateAudit,
  listAuditDeliverables,
  getAuditDeliverable,
  approveAuditDeliverable,
  rejectAuditDeliverable,
  type RunSummary,
  type AuditDraft,
  type AuditRecord,
  type AuditSummary,
  type AuditStatus,
  type GenerateAuditResult,
} from "@/lib/api";

function download(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "audit";
}

function printHtml(html: string) {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(html);
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 400);
}

const STATUS_VARIANT: Record<AuditStatus, "secondary" | "success" | "destructive" | "default"> = {
  draft: "secondary",
  approved: "success",
  rejected: "destructive",
  exported: "default",
};

function StatusBadge({ status }: { status: AuditStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

export default function AuditPage() {
  const [runs, setRuns] = React.useState<RunSummary[]>([]);
  const [runId, setRunId] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // The current preview: generated draft + html, plus the persisted row backing it.
  const [draft, setDraft] = React.useState<AuditDraft | null>(null);
  const [html, setHtml] = React.useState<string | null>(null);
  const [record, setRecord] = React.useState<AuditRecord | null>(null);
  const [deliverableId, setDeliverableId] = React.useState<string | null>(null);

  const [saved, setSaved] = React.useState<AuditSummary[]>([]);
  const [savedError, setSavedError] = React.useState<string | null>(null);

  const refreshRuns = React.useCallback(async () => {
    try {
      const all = await listAudits();
      setRuns(all.filter((r) => r.state === "done"));
    } catch {
      setError("Could not load completed runs (is the platform running?).");
    }
  }, []);

  const refreshSaved = React.useCallback(async () => {
    try {
      setSaved(await listAuditDeliverables());
      setSavedError(null);
    } catch {
      setSavedError("Saved audits are unavailable (is Supabase configured? run data/schema_audits.sql).");
    }
  }, []);

  React.useEffect(() => {
    void refreshRuns();
    void refreshSaved();
  }, [refreshRuns, refreshSaved]);

  const status: AuditStatus = record?.status ?? "draft";
  const clientName = draft?.clientName ?? record?.client_name ?? "audit";

  const generate = async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    setDraft(null);
    setHtml(null);
    setRecord(null);
    setDeliverableId(null);
    try {
      const res: GenerateAuditResult = await generateAudit(runId, category || undefined);
      if (!res.ok) {
        setError(`Generation failed at ${res.stage}: ${res.reason}`);
        return;
      }
      setDraft(res.draft);
      setHtml(res.html);
      setDeliverableId(res.deliverableId);
      if (res.deliverableId) {
        try {
          setRecord(await getAuditDeliverable(res.deliverableId));
        } catch {
          /* best-effort: preview/download still work */
        }
      }
      void refreshSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to generate audit");
    } finally {
      setLoading(false);
    }
  };

  const reopen = async (id: string) => {
    setError(null);
    try {
      const rec = await getAuditDeliverable(id);
      setRecord(rec);
      setDraft(rec.draft);
      setHtml(rec.html);
      setDeliverableId(rec.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to open audit");
    }
  };

  const doApprove = async () => {
    if (!deliverableId) return;
    setRecord(await approveAuditDeliverable(deliverableId));
    void refreshSaved();
  };

  const doReject = async () => {
    if (!deliverableId) return;
    const reason = window.prompt("Reason for rejecting (optional):") ?? undefined;
    setRecord(await rejectAuditDeliverable(deliverableId, reason));
    void refreshSaved();
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">AI Visibility Audit</h1>
      </div>
      <p className="text-muted-foreground">
        Turn a completed audit run into a client-ready AI Visibility Audit — review, approve, and download the PDF leave-behind.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Generate from a completed run</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-1">
              <span className="text-sm font-medium">Completed run</span>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
              >
                <option value="">Select a run…</option>
                {runs.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.client_name} · {r.n_queries} queries · {new Date(r.created_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Category (for the §1 headline)</span>
              <input
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder='e.g. "budgeting app"'
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              />
            </label>
          </div>
          <Button onClick={generate} disabled={!runId || loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}
            {loading ? "Generating…" : "Generate audit"}
          </Button>
          {error && (
            <p className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" /> {error}
            </p>
          )}
        </CardContent>
      </Card>

      {html && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-3">
              {clientName} — audit <StatusBadge status={status} />
            </CardTitle>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => printHtml(html)}>
                <Printer className="mr-2 h-4 w-4" /> Print / PDF
              </Button>
              <Button variant="outline" size="sm" onClick={() => download(`${slugify(clientName)}-audit.html`, html, "text/html")}>
                <Download className="mr-2 h-4 w-4" /> HTML
              </Button>
              <Button size="sm" onClick={doApprove} disabled={!deliverableId || status === "approved"}>
                <Check className="mr-2 h-4 w-4" /> Approve
              </Button>
              <Button variant="destructive" size="sm" onClick={doReject} disabled={!deliverableId || status === "rejected"}>
                <X className="mr-2 h-4 w-4" /> Reject
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {!deliverableId && (
              <p className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
                <AlertTriangle className="h-4 w-4" /> Not saved to Supabase — preview &amp; downloads work, but approve/reject need the
                <code className="mx-1">audit_deliverables</code> table (run <code>data/schema_audits.sql</code>).
              </p>
            )}
            <iframe title="audit preview" srcDoc={html} className="h-[80vh] w-full rounded-md border bg-white" />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Saved audits</CardTitle>
        </CardHeader>
        <CardContent>
          {savedError ? (
            <p className="text-sm text-muted-foreground">{savedError}</p>
          ) : saved.length === 0 ? (
            <p className="text-sm text-muted-foreground">No saved audits yet.</p>
          ) : (
            <ul className="divide-y">
              {saved.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-2">
                  <button className="text-left text-sm hover:underline" onClick={() => reopen(a.id)}>
                    {a.client_name ?? "—"} · {a.category ?? "—"} · grade {a.grade_letter ?? "—"}
                  </button>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={a.status} />
                    <span className="text-xs text-muted-foreground">{new Date(a.created_at).toLocaleDateString()}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
