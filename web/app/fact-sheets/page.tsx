"use client";

/**
 * The fact-sheet review queue (plan F4) — the reachable human gate.
 *
 * A generated sheet is always written DRAFT, and only an ACTIVE sheet is the
 * reference a run's accuracy judging is measured against. This screen is the only
 * path between those two states, which is deliberate: the generator is cheap,
 * unreviewed and occasionally confidently wrong, and a wrong line here does not
 * produce a missing finding — it produces a false accusation in a document we send
 * a stranger.
 *
 * So the design rule is that a reviewer must be able to CHECK a claim, not just
 * read it. Every claim shows its verbatim quote and a link to the page it came
 * from, side by side with the assertion it produced.
 */

import * as React from "react";
import { Check, X, Loader2, ExternalLink, AlertTriangle, HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  listFactSheets,
  getFactSheet,
  approveFactSheet,
  rejectFactSheet,
  type FactSheetSummary,
  type FactSheetDetail,
  type FactSheetState,
  type FactSheetVerification,
} from "@/lib/api";

// Anything short of client_confirmed says UNCONFIRMED in as many words. Two public
// sources can be stale together, and "cross-confirmed" reads like an endorsement to
// someone skimming a queue (plan §8).
const VERIFICATION_LABEL: Record<FactSheetVerification, string> = {
  public_source_only: "UNCONFIRMED · one public source",
  cross_confirmed: "UNCONFIRMED · two public sources agree",
  client_confirmed: "client-confirmed",
};

const STATE_TABS: { value: FactSheetState; label: string }[] = [
  { value: "draft", label: "Needs review" },
  { value: "active", label: "Active" },
  { value: "rejected", label: "Rejected" },
  { value: "superseded", label: "Superseded" },
];

function stateTone(state: FactSheetState): string {
  if (state === "active") return "border-[hsl(var(--success))] text-[hsl(var(--success))]";
  if (state === "rejected") return "border-destructive text-destructive";
  return "";
}

export default function FactSheetQueuePage() {
  const [tab, setTab] = React.useState<FactSheetState>("draft");
  const [rows, setRows] = React.useState<FactSheetSummary[]>([]);
  const [selected, setSelected] = React.useState<FactSheetDetail | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [rejectReason, setRejectReason] = React.useState("");

  const refresh = React.useCallback(() => {
    setLoading(true);
    setError(null);
    listFactSheets(tab)
      .then(setRows)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tab]);
  React.useEffect(refresh, [refresh]);

  const open = (id: string) => {
    setError(null);
    setRejectReason("");
    getFactSheet(id)
      .then(setSelected)
      .catch((e: Error) => setError(e.message));
  };

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setSelected(null);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Fact sheets</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Generated sheets are drafts. Approving one makes it the reference every accuracy
          finding for that domain is measured against — check the quotes before you do.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATE_TABS.map((t) => (
          <Button
            key={t.value}
            variant={tab === t.value ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setTab(t.value);
              setSelected(null);
            }}
          >
            {t.label}
          </Button>
        ))}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      )}

      {!loading && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nothing here. Sheets arrive from the worker (<code>geo factsheet-worker</code>) or the
          CLI (<code>geo factsheet</code>).
        </p>
      )}

      <div className="grid gap-3">
        {rows.map((row) => (
          <Card key={row.id} className="cursor-pointer" onClick={() => open(row.id)}>
            <CardHeader className="flex flex-row items-start justify-between gap-4 pb-2">
              <div>
                <CardTitle className="text-base">
                  {row.business_name || row.domain}{" "}
                  <span className="font-normal text-muted-foreground">v{row.version}</span>
                </CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  {row.domain} · generated {row.generated_at?.slice(0, 10)}
                  {row.lead_ref ? " · from a lead" : ""}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge variant="outline" className={stateTone(row.state)}>
                  {row.state}
                </Badge>
                <span className="text-[11px] text-muted-foreground">
                  {VERIFICATION_LABEL[row.verification_tier]}
                </span>
              </div>
            </CardHeader>
            {row.questions && row.questions.length > 0 && (
              <CardContent className="pt-0">
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <HelpCircle className="h-3.5 w-3.5" />
                  {row.questions.length} open question
                  {row.questions.length === 1 ? "" : "s"} to resolve
                </p>
              </CardContent>
            )}
            {row.reject_reason && (
              <CardContent className="pt-0">
                <p className="text-xs text-muted-foreground">Rejected: {row.reject_reason}</p>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      {selected && (
        <Card className="border-2">
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <CardTitle>
                  {selected.business_name} — v{selected.version}
                </CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  {selected.domain} · {selected.claims.length} claim
                  {selected.claims.length === 1 ? "" : "s"} ·{" "}
                  {VERIFICATION_LABEL[selected.verification_tier]}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-6">
            {selected.questions.length > 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                <p className="text-sm font-medium">Open questions — ask before approving</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Sources disagreed, or the answer is not derivable from a closed enumeration.
                  Nothing below is a fact yet.
                </p>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
                  {selected.questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ol>
              </div>
            )}

            <div className="space-y-3">
              {selected.claims.map((c) => (
                <div key={c.claim_id} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-sm">
                      <span className="font-medium">{c.key}:</span> {c.value}
                    </p>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {c.claim_id} · {c.polarity}
                    </span>
                  </div>
                  {/* The evidence, not a paraphrase. A reviewer who cannot check a
                      claim cannot approve it. */}
                  <blockquote className="mt-2 border-l-2 pl-3 text-xs text-muted-foreground">
                    “{c.verbatim_quote}”
                  </blockquote>
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 underline"
                    >
                      {c.source_url} <ExternalLink className="h-3 w-3" />
                    </a>
                    <span>· {c.source_kind}</span>
                    <span>· as of {c.as_of}</span>
                    <span>· {VERIFICATION_LABEL[c.verification]}</span>
                  </p>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t pt-4">
              <Button
                onClick={() => act(() => approveFactSheet(selected.id))}
                disabled={busy}
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Approve — make this the reference
              </Button>
              <input
                className="min-w-48 flex-1 rounded-md border px-3 py-2 text-sm"
                placeholder="Why is it wrong? (optional, but it tunes the extractor)"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
              <Button
                variant="outline"
                onClick={() => act(() => rejectFactSheet(selected.id, rejectReason))}
                disabled={busy}
              >
                <X className="h-4 w-4" /> Reject
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
