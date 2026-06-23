"use client";

import * as React from "react";
import { Sparkles, Loader2, Download, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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

interface HeadlineNumber {
  companyAppears: number;
  competitorAppears: number;
  competitorName: string;
  n: number;
}
interface TeaserDraft {
  prospectUrl: string;
  companyName: string;
  category: string;
  runDate: string;
  heroEngine: string;
  headlineNumber: HeadlineNumber;
  lead: { verbatimQuery: string };
  table: unknown[];
}
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

export default function TeaserPage() {
  const [url, setUrl] = React.useState("");
  const [engines, setEngines] = React.useState<string[]>(DEFAULT_ENGINES);
  const [maxQueries, setMaxQueries] = React.useState(5);
  const [runs, setRuns] = React.useState(1);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<TeaserResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const toggleEngine = (id: string) =>
    setEngines((prev) => (prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]));

  const generate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/teaser", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, engines, maxQueries, runs }),
      });
      const data = (await res.json()) as TeaserResult;
      setResult(data);
    } catch {
      setError("Could not reach the teaser service. Is the web server running?");
    } finally {
      setLoading(false);
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
        <TeaserResultView result={result} />
      )}
    </div>
  );
}

function TeaserResultView({ result }: { result: { ok: true; draft: TeaserDraft; html: string } }) {
  const { draft, html } = result;
  const h = draft.headlineNumber;
  const slug = slugify(draft.companyName);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{draft.companyName}</h2>
          <p className="text-sm text-muted-foreground">
            {draft.companyName} {h.companyAppears}/{h.n} vs {h.competitorName} {h.competitorAppears}/
            {h.n} · hero: {draft.heroEngine} · lead: “{draft.lead.verbatimQuery}”
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => download(`${slug}.html`, html, "text/html")}
          >
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
      <iframe
        title="teaser preview"
        srcDoc={html}
        className="h-[1000px] w-full rounded-lg border bg-white"
      />
    </div>
  );
}
