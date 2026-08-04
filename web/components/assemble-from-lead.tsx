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
import { Loader2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import {
  assembleAudit,
  getFactSheet,
  listFactSheets,
  listTrades,
  type AssembleResult,
  type FactSheetSummary,
} from "@/lib/api";

interface Props {
  onAssembled: (file: File) => void;
  /**
   * Fires when a sheet is picked here, so the run-time fact-sheet picker can
   * pre-select the same one. The two selections are genuinely different acts —
   * this one supplies CONFIG, that one supplies the GROUND TRUTH the judge scores
   * against — but choosing the same sheet twice is friction, not information.
   */
  onSheetChosen: (id: string | null) => void;
  /**
   * Controlled mode. The Run screen's Sources card puts the TRIGGER in the card
   * header (next to "Template") and needs the FORM in the card body — a
   * self-contained disclosure cannot span those two places. When `open` is
   * supplied the component renders the form only, and the caller owns the
   * trigger; when it is omitted the component is self-contained, which is how
   * every other caller uses it.
   */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function AssembleFromLead({
  onAssembled,
  onSheetChosen,
  open: openProp,
  onOpenChange,
}: Props) {
  const [selfOpen, setSelfOpen] = React.useState(false);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : selfOpen;
  const setOpen = onOpenChange ?? setSelfOpen;
  const [trades, setTrades] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<AssembleResult | null>(null);

  const [sheets, setSheets] = React.useState<FactSheetSummary[]>([]);
  const [sheetId, setSheetId] = React.useState("");
  const [prefilled, setPrefilled] = React.useState(false);
  const [business, setBusiness] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [trade, setTrade] = React.useState("");
  const [city, setCity] = React.useState("");
  const [region, setRegion] = React.useState("");

  React.useEffect(() => {
    listFactSheets("active")
      .then(setSheets)
      .catch(() => setSheets([]));
  }, []);

  // Picking a sheet fills in what it already knows. It was extracted from the
  // business's own website, so asking for the name, domain and city again is
  // copying data we hold. Fields it cannot derive stay blank for you to type —
  // a blank means ask, not guess.
  const useSheet = async (id: string) => {
    setSheetId(id);
    setPrefilled(false);
    // Carry it to the run-time picker immediately, on SELECT rather than on
    // build: a run assembled from a sheet should be judged against that sheet,
    // and making someone re-pick it is an invitation to forget.
    onSheetChosen(id || null);
    if (!id) return;
    try {
      const sheet = await getFactSheet(id);
      const s = sheet.suggested;
      if (!s) return;
      if (s.business) setBusiness(s.business);
      if (s.website) setWebsite(s.website);
      if (s.city) setCity(s.city);
      if (s.region) setRegion(s.region);
      setPrefilled(true);
    } catch {
      setError("Could not read that fact sheet.");
    }
  };

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
    // Controlled: the caller draws the trigger, so drawing a second one here
    // would put two "Start from a lead" links on the same card.
    return controlled ? null : (
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
        <p className="mt-1 text-[11px] text-harbour">
          Builds the whole audit CSV: the trade&apos;s local questions, the config, and
          competitors from Google&apos;s local pack. Attach the fact sheet after, below.
        </p>
      </div>

      {sheets.length > 0 && (
        <label className="block space-y-1">
          <span className="text-[11px] text-harbour">
            Start from an approved fact sheet
          </span>
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={sheetId}
            onChange={(e) => void useSheet(e.target.value)}
          >
            <option value="">Enter the details by hand</option>
            {sheets.map((s) => (
              <option key={s.id} value={s.id}>
                {s.business_name || s.domain} — {s.domain}
              </option>
            ))}
          </select>
          {prefilled && (
            <span className="block text-[11px] text-muted-foreground">
              Filled from the sheet, and attached to the run below. Check anything
              it left blank.
            </span>
          )}
        </label>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="text-[11px] text-harbour">Business name</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={business}
            onChange={(e) => setBusiness(e.target.value)}
            placeholder="Albert Nahman Plumbing"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-harbour">Website</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="albertnahmanplumbing.com"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-harbour">Trade</span>
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
          <span className="text-[11px] text-harbour">City</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="Berkeley"
          />
        </label>
        <label className="space-y-1 sm:col-span-2">
          <span className="text-[11px] text-harbour">
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
          className="text-[13px] text-harbour hover:underline"
        >
          Cancel
        </button>
      </div>

      {error && <Notice tone="problem">{error}</Notice>}

      {result && (
        <div className="space-y-2 text-sm">
          <p>
            Added <code>{result.competitors.length}</code> competitor
            {result.competitors.length === 1 ? "" : "s"} from{" "}
            <span className="text-harbour">{result.competitor_source}</span>:{" "}
            {result.competitors.join(", ") || "none"}
          </p>
          {result.warning && (
            <Notice tone="info">{result.warning}</Notice>
          )}
          {result.excluded.length > 0 && (
            /* Shown, not hidden: a list that silently dropped the obvious local name
               looks complete and is not. */
            <details className="text-[11px] text-harbour">
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
