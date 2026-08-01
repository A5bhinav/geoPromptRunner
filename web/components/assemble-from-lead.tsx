"use client";

/**
 * Build a runnable audit CSV from a lead, instead of hand-editing a template.
 *
 * The output is added to the upload list as a normal file, so it flows through
 * the existing preview → pick fact sheet → Run audit path with no separate
 * machinery. That is deliberate: an assembled run and a hand-made one should be
 * the same thing by the time they reach validation, or the assembler becomes a
 * second, less-tested way in.
 */

import * as React from "react";
import { Loader2, Wand2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { assembleAudit, listTrades, type AssembleResult } from "@/lib/api";

interface Props {
  onAssembled: (file: File) => void;
}

export function AssembleFromLead({ onAssembled }: Props) {
  const [open, setOpen] = React.useState(false);
  const [trades, setTrades] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<AssembleResult | null>(null);

  const [business, setBusiness] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [trade, setTrade] = React.useState("");
  const [city, setCity] = React.useState("");
  const [region, setRegion] = React.useState("");

  React.useEffect(() => {
    listTrades()
      .then((t) => {
        setTrades(t);
        setTrade((cur) => cur || t[0] || "");
      })
      .catch(() => setTrades([]));
  }, []);

  const ready = business.trim() && website.trim() && trade && city.trim() && region.trim();

  const build = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await assembleAudit({ business, website, trade, city, region });
      setResult(res);
      const name = `${city.trim().toLowerCase().replace(/\s+/g, "-")}-${trade}.csv`;
      onAssembled(new File([res.csv], name, { type: "text/csv" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
      >
        <Wand2 className="h-4 w-4" /> Start from a lead
      </button>
    );
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div>
        <p className="text-sm font-medium">Start from a lead</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Builds the whole audit CSV: the trade&apos;s local questions, the config, and
          competitors from Google&apos;s local pack. Attach the fact sheet after, below.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Business name</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={business}
            onChange={(e) => setBusiness(e.target.value)}
            placeholder="Albert Nahman Plumbing"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Website</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="albertnahmanplumbing.com"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Trade</span>
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={trade}
            onChange={(e) => setTrade(e.target.value)}
          >
            {trades.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">City</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="Berkeley"
          />
        </label>
        <label className="space-y-1 sm:col-span-2">
          <span className="text-xs text-muted-foreground">
            State, spelled in full — &ldquo;California&rdquo;, not &ldquo;CA&rdquo;
          </span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="California"
          />
          <span className="block text-[11px] text-muted-foreground">
            An abbreviation is rejected rather than guessed: the search vendors return
            nothing for it, and an empty result reads as the business being absent.
          </span>
        </label>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={build} disabled={!ready || busy} size="sm">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
          Build audit CSV
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-sm text-muted-foreground hover:underline"
        >
          Cancel
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="space-y-2 text-sm">
          <p>
            Added <code>{result.competitors.length}</code> competitor
            {result.competitors.length === 1 ? "" : "s"} from{" "}
            <span className="text-muted-foreground">{result.competitor_source}</span>:{" "}
            {result.competitors.join(", ") || "none"}
          </p>
          {result.warning && (
            <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {result.warning}
            </p>
          )}
          {result.excluded.length > 0 && (
            /* Shown, not hidden: a list that silently dropped the obvious local name
               looks complete and is not. */
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">
                {result.excluded.length} listing{result.excluded.length === 1 ? "" : "s"} excluded
              </summary>
              <ul className="mt-1 space-y-0.5 pl-4">
                {result.excluded.map((x, i) => (
                  <li key={i}>
                    {x.name} — {x.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
