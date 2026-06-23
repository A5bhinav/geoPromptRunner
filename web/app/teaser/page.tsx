"use client";

import * as React from "react";
import {
  Sparkles,
  Loader2,
  Download,
  AlertTriangle,
  Check,
  X,
  Pencil,
  RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  saveTeaser,
  listTeasers,
  getTeaser,
  approveTeaser,
  editTeaser,
  rejectTeaser,
  type TeaserDraft,
  type TeaserEditedFields,
  type TeaserRecord,
  type TeaserSummary,
  type TeaserStatus,
} from "@/lib/api";

// Engines the platform knows (src/prompts/csv_loader.py KNOWN_ENGINES). "mock" is
// keyless — it runs the real pipeline with a fabricating engine, handy when no
// provider keys are configured.
const ENGINE_OPTIONS = [
  { id: "perplexity", label: "Perplexity" },
  { id: "openai", label: "ChatGPT" },
  { id: "google_ai_overviews", label: "AI Overviews" },
  { id: "anthropic", label: "Claude" },
  { id: "mock", label: "Mock (no keys)" },
];
const DEFAULT_ENGINES = ["perplexity", "openai", "google_ai_overviews"];

// TeaserDraft / TeaserRecord etc. now live in lib/api.ts (shared with the API
// client) rather than being redeclared here.
type TeaserResult =
  | { ok: true; draft: TeaserDraft; html: string }
  | { ok: false; stage: string; reason: string };

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
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "teaser";
}

// The status badge variants line up with the lifecycle in schema_teasers.sql.
const STATUS_VARIANT: Record<TeaserStatus, "secondary" | "success" | "destructive" | "default"> = {
  draft: "secondary",
  approved: "success",
  rejected: "destructive",
  exported: "default",
};

function StatusBadge({ status }: { status: TeaserStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

export default function TeaserPage() {
  const [url, setUrl] = React.useState("");
  const [engines, setEngines] = React.useState<string[]>(DEFAULT_ENGINES);
  const [maxQueries, setMaxQueries] = React.useState(5);
  const [runs, setRuns] = React.useState(1);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<TeaserResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // The persisted row backing the current preview (after a generate or a reopen).
  const [record, setRecord] = React.useState<TeaserRecord | null>(null);
  // Saved-teasers list (the "Saved teasers" panel).
  const [saved, setSaved] = React.useState<TeaserSummary[]>([]);
  const [savedError, setSavedError] = React.useState<string | null>(null);

  const refreshSaved = React.useCallback(async () => {
    try {
      setSaved(await listTeasers());
      setSavedError(null);
    } catch {
      // Persistence is best-effort here — the generate→preview→download flow
      // still works without Supabase configured.
      setSavedError("Saved teasers are unavailable (is the platform / Supabase configured?).");
    }
  }, []);

  React.useEffect(() => {
    void refreshSaved();
  }, [refreshSaved]);

  const toggleEngine = (id: string) =>
    setEngines((prev) => (prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]));

  const generate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setRecord(null);
    try {
      const res = await fetch("/api/teaser", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, engines, maxQueries, runs }),
      });
      const data = (await res.json()) as TeaserResult;
      setResult(data);
      // Persist the draft so it can be reviewed (approve / edit / reject). Best
      // effort: a storage failure must not break the preview/download flow.
      if (data.ok) {
        try {
          const { teaser_id } = await saveTeaser(data.draft, data.html);
          setRecord(await getTeaser(teaser_id));
          void refreshSaved();
        } catch {
          setSavedError(
            "Generated — preview and downloads work, but it could not be saved, so " +
              "approve / edit / reject are unavailable (is the platform / Supabase configured?).",
          );
        }
      }
    } catch {
      setError("Could not reach the teaser service. Is the web server running?");
    } finally {
      setLoading(false);
    }
  };

  // Reopen a saved teaser into the preview + review surface.
  const reopen = async (id: string) => {
    setError(null);
    try {
      const rec = await getTeaser(id);
      setRecord(rec);
      setResult({ ok: true, draft: rec.draft, html: rec.html ?? "" });
    } catch {
      setError("Could not load that saved teaser.");
    }
  };

  const inputCls =
    "h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Teaser generator</h1>
        <p className="mt-1 text-muted-foreground">
          Turn a prospect URL into a one-page teaser showing where AI recommends a competitor and
          leaves them out. Runs a small, real audit through the platform.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Prospect</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="url">
              Website URL
            </label>
            <input
              id="url"
              className={inputCls}
              placeholder="https://www.acme-hq.io"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && url && !loading && generate()}
            />
          </div>

          <div className="space-y-1.5">
            <span className="text-sm font-medium">Engines</span>
            <div className="flex flex-wrap gap-2">
              {ENGINE_OPTIONS.map((opt) => {
                const on = engines.includes(opt.id);
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => toggleEngine(opt.id)}
                    className={
                      "rounded-full border px-3 py-1 text-sm transition-colors " +
                      (on
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-input bg-background text-muted-foreground hover:bg-accent")
                    }
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              Real engines need provider keys on the platform. No keys? Pick{" "}
              <span className="font-medium">Mock</span> to run the full flow keyless.
            </p>
          </div>

          <div className="flex flex-wrap gap-6">
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="maxq">
                Queries <span className="text-muted-foreground">(smaller = faster)</span>
              </label>
              <input
                id="maxq"
                type="number"
                min={1}
                max={7}
                className={inputCls + " w-28"}
                value={maxQueries}
                onChange={(e) => setMaxQueries(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="runs">
                Runs / query
              </label>
              <input
                id="runs"
                type="number"
                min={1}
                max={5}
                className={inputCls + " w-28"}
                value={runs}
                onChange={(e) => setRuns(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={generate} disabled={!url || engines.length === 0 || loading} size="lg">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate teaser
            </Button>
            {loading && (
              <span className="text-sm text-muted-foreground">
                Running the audit — a real run can take a few minutes…
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {result && !result.ok && (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Teaser not produced (stage: {result.stage})</p>
            <p className="mt-1 text-muted-foreground">{result.reason}</p>
            {result.stage === "select" && (
              <p className="mt-2 text-muted-foreground">
                A printable teaser needs judge-mode detection — make sure the platform has a judge
                key configured and that the prospect actually loses on a query.
              </p>
            )}
          </div>
        </div>
      )}

      {result && result.ok && (
        <TeaserResultView
          result={result}
          record={record}
          savedError={savedError}
          onRecordChange={(rec) => {
            setRecord(rec);
            void refreshSaved();
          }}
        />
      )}

      <SavedTeasers saved={saved} error={savedError} onReopen={reopen} onRefresh={refreshSaved} />
    </div>
  );
}

function TeaserResultView({
  result,
  record,
  savedError,
  onRecordChange,
}: {
  result: { ok: true; draft: TeaserDraft; html: string };
  record: TeaserRecord | null;
  savedError: string | null;
  onRecordChange: (rec: TeaserRecord) => void;
}) {
  const { draft, html } = result;
  const h = draft.headlineNumber;
  const slug = slugify(draft.companyName);

  const [editing, setEditing] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [busy, setBusy] = React.useState<null | "approve" | "reject" | "edit">(null);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const status: TeaserStatus | null = record?.status ?? null;
  const edited = record?.edited_fields ?? {};
  // The freshest printable HTML: a reviewer-edited re-render (record.html) wins
  // over the originally generated html, so preview + downloads reflect edits.
  const currentHtml = record?.html ?? html;

  // Re-render the one-pager with reviewer edits applied (teaser render endpoint).
  // Returns undefined on failure so the edit still persists as edited_fields.
  const rerenderHtml = async (fields: TeaserEditedFields): Promise<string | undefined> => {
    try {
      const res = await fetch("/api/teaser/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft, edited_fields: fields }),
      });
      if (!res.ok) return undefined;
      const data = (await res.json()) as { ok?: boolean; html?: string };
      return data.ok && typeof data.html === "string" ? data.html : undefined;
    } catch {
      return undefined;
    }
  };

  const run = async (
    kind: "approve" | "reject" | "edit",
    fn: () => Promise<TeaserRecord>,
  ) => {
    setBusy(kind);
    setActionError(null);
    try {
      onRecordChange(await fn());
    } catch {
      setActionError("Action failed — is the platform reachable?");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">{draft.companyName}</h2>
            {status && <StatusBadge status={status} />}
          </div>
          <p className="text-sm text-muted-foreground">
            {draft.companyName} {h.companyAppears}/{h.n} vs {h.competitorName} {h.competitorAppears}/
            {h.n} · hero: {draft.heroEngine} · lead: “{draft.lead.verbatimQuery}”
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => download(`${slug}.html`, currentHtml, "text/html")}>
            <Download className="h-4 w-4" /> HTML
          </Button>
          <Button
            variant="outline"
            onClick={() => download(`${slug}.json`, JSON.stringify(draft, null, 2), "application/json")}
          >
            <Download className="h-4 w-4" /> JSON
          </Button>
        </div>
      </div>

      {/* Review action bar — only once the draft has been persisted. */}
      {record ? (
        <Card>
          <CardContent className="space-y-3 pt-6">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                onClick={() => run("approve", () => approveTeaser(record.id))}
                disabled={busy !== null || status === "approved"}
              >
                {busy === "approve" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                Approve
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setEditing((v) => !v);
                  setRejecting(false);
                }}
                disabled={busy !== null}
              >
                <Pencil className="h-4 w-4" /> Edit copy
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  setRejecting((v) => !v);
                  setEditing(false);
                }}
                disabled={busy !== null}
              >
                <X className="h-4 w-4" /> Reject
              </Button>
            </div>

            {rejecting && (
              <div className="space-y-2">
                <textarea
                  className="min-h-[72px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Why is this teaser being rejected? (optional)"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() =>
                    run("reject", () => rejectTeaser(record.id, reason)).then(() =>
                      setRejecting(false),
                    )
                  }
                  disabled={busy !== null}
                >
                  {busy === "reject" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Confirm reject
                </Button>
              </div>
            )}

            {editing && (
              <EditCopy
                initial={edited}
                busy={busy === "edit"}
                onSave={(fields) =>
                  run("edit", async () => {
                    // Re-render with the edits applied so the persisted html (and
                    // thus the downloaded PDF/HTML) reflects them; fall back to a
                    // text-only edit if the renderer is unavailable.
                    const rendered = await rerenderHtml(fields);
                    return editTeaser(record.id, fields, rendered);
                  }).then(() => setEditing(false))
                }
              />
            )}

            {status === "rejected" && (
              <p className="text-sm text-muted-foreground">
                Reject reason: {record.reject_reason || "(none given)"}
              </p>
            )}
            {actionError && <p className="text-sm text-destructive">{actionError}</p>}
          </CardContent>
        </Card>
      ) : (
        savedError && <p className="text-sm text-muted-foreground">{savedError}</p>
      )}

      {/* Saved copy edits, surfaced above the preview. The printable HTML is
          re-rendered with these edits on save (see rerenderHtml), so the preview
          and downloads below already reflect them. */}
      {record && Object.values(edited).some((v) => v) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Reviewer edits</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {edited.headline && (
              <p>
                <span className="font-medium">Headline:</span> {edited.headline}
              </p>
            )}
            {edited.leadSentence && (
              <p>
                <span className="font-medium">Lead:</span> {edited.leadSentence}
              </p>
            )}
            {edited.stakesLine && (
              <p>
                <span className="font-medium">Stakes:</span> {edited.stakesLine}
              </p>
            )}
            {edited.cta && (
              <p>
                <span className="font-medium">CTA:</span> {edited.cta}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <iframe
        title="teaser preview"
        srcDoc={currentHtml}
        className="h-[1000px] w-full rounded-lg border bg-white"
      />
    </div>
  );
}

function EditCopy({
  initial,
  busy,
  onSave,
}: {
  initial: TeaserEditedFields;
  busy: boolean;
  onSave: (fields: TeaserEditedFields) => void;
}) {
  const [headline, setHeadline] = React.useState(initial.headline ?? "");
  const [leadSentence, setLeadSentence] = React.useState(initial.leadSentence ?? "");
  const [stakesLine, setStakesLine] = React.useState(initial.stakesLine ?? "");
  const [cta, setCta] = React.useState(initial.cta ?? "");

  const cls =
    "h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="space-y-3 rounded-md border border-input p-4">
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Headline</label>
        <input className={cls} value={headline} onChange={(e) => setHeadline(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Lead sentence</label>
        <input
          className={cls}
          value={leadSentence}
          onChange={(e) => setLeadSentence(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Stakes line</label>
        <input className={cls} value={stakesLine} onChange={(e) => setStakesLine(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label className="text-sm font-medium">Call to action</label>
        <input className={cls} value={cta} onChange={(e) => setCta(e.target.value)} />
      </div>
      <Button
        size="sm"
        disabled={busy}
        onClick={() =>
          onSave({
            ...(headline ? { headline } : {}),
            ...(leadSentence ? { leadSentence } : {}),
            ...(stakesLine ? { stakesLine } : {}),
            ...(cta ? { cta } : {}),
          })
        }
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
        Save edits
      </Button>
    </div>
  );
}

function SavedTeasers({
  saved,
  error,
  onReopen,
  onRefresh,
}: {
  saved: TeaserSummary[];
  error: string | null;
  onReopen: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Saved teasers</CardTitle>
        <Button variant="ghost" size="sm" onClick={onRefresh}>
          <RotateCcw className="h-4 w-4" /> Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {error && saved.length === 0 ? (
          <p className="text-sm text-muted-foreground">{error}</p>
        ) : saved.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No saved teasers yet — generate one above to review and approve it.
          </p>
        ) : (
          <ul className="divide-y">
            {saved.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {t.company_name || "(untitled)"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(t.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={t.status} />
                  <Button variant="outline" size="sm" onClick={() => onReopen(t.id)}>
                    Open
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
