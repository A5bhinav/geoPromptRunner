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
import { Check, X, Loader2, ExternalLink, HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Notice } from "@/components/notice";
import { INPUT_CLS } from "@/lib/ui";
import { cn } from "@/lib/utils";
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

// Weight, not hue: active is the heaviest chip, rejected an outline, the rest
// quiet. Sable has no alert hue and the label already carries the meaning.
const STATE_VARIANT: Record<FactSheetState, "quiet" | "muted" | "outline" | "solid"> = {
  active: "solid",
  rejected: "outline",
  draft: "muted",
  superseded: "quiet",
};

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
    // Was a <main> nested inside the layout's <main> — an a11y bug as well as a
    // duplicated container.
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="label">Fact sheets</p>
        <h1 className="display text-[34px] leading-tight">Ground truth for the judge</h1>
        <p className="max-w-xl text-[13px] leading-relaxed text-[color:var(--ink-secondary)]">
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

      {error && <Notice tone="problem">{error}</Notice>}

      {loading && (
        <p className="flex items-center gap-2 text-[13px] text-[color:var(--ink-secondary)]">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      )}

      {!loading && rows.length === 0 && (
        <p className="text-[13px] text-[color:var(--ink-secondary)]">
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
                  <span className="font-normal text-harbour">v{row.version}</span>
                </CardTitle>
                <p className="mt-1 text-[11px] text-harbour">
                  {row.domain} · generated {row.generated_at?.slice(0, 10)}
                  {row.lead_ref ? " · from a lead" : ""}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge variant={STATE_VARIANT[row.state] ?? "quiet"} className="capitalize">
                  {row.state}
                </Badge>
                <span className="text-[11px] text-harbour">
                  {VERIFICATION_LABEL[row.verification_tier]}
                </span>
              </div>
            </CardHeader>
            {row.questions && row.questions.length > 0 && (
              <CardContent className="pt-0">
                <p className="flex items-center gap-1.5 text-[11px] text-harbour">
                  <HelpCircle className="h-3.5 w-3.5" />
                  {row.questions.length} open question
                  {row.questions.length === 1 ? "" : "s"} to resolve
                </p>
              </CardContent>
            )}
            {row.reject_reason && (
              <CardContent className="pt-0">
                <p className="text-[11px] text-harbour">Rejected: {row.reject_reason}</p>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      {selected && (
        <Card className="border-navy/40">
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <CardTitle>
                  {selected.business_name} — v{selected.version}
                </CardTitle>
                <p className="mt-1 text-[11px] text-harbour">
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
              <Notice tone="info" title="Open questions — ask before approving">
                <p>
                  Sources disagreed, or the answer is not derivable from a closed enumeration.
                  Nothing below is a fact yet.
                </p>
                <ol className="mt-2 list-decimal space-y-1 pl-5">
                  {selected.questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ol>
              </Notice>
            )}

            <div className="space-y-3">
              {selected.claims.map((c) => (
                <div key={c.claim_id} className="rounded-md border border-[var(--rule)] p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-[13px]">
                      <span className="font-medium">{c.key}:</span> {c.value}
                    </p>
                    <span className="shrink-0 text-[11px] text-harbour">
                      {c.claim_id} · {c.polarity}
                    </span>
                  </div>
                  {/* The evidence, not a paraphrase. A reviewer who cannot check a
                      claim cannot approve it. */}
                  <blockquote className="mt-2 border-l-2 border-[var(--rule)] pl-3 text-[11px] text-harbour">
                    “{c.verbatim_quote}”
                  </blockquote>
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-harbour">
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-blue underline"
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
                className={cn(INPUT_CLS, "min-w-48 flex-1")}
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
    </div>
  );
}
