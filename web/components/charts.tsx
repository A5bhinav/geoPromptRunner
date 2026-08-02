"use client";

import * as React from "react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BucketRow, EngineCellRow, LeaderRow, SourceRow } from "@/lib/api";
import {
  PRINT_CONTENT_WIDTH_PX,
  useChartSettled,
  useIsPrint,
} from "@/lib/render-mode";

/** Swaps ResponsiveContainer for a fixed-size box when printing.
 *
 * `ResponsiveContainer` sizes itself through `ResizeObserver`, and print layout
 * never fires those events — so on the PDF path a chart renders at whatever the
 * last on-screen size happened to be, which is usually the wrong one and
 * occasionally zero. A fixed box matching the `@page` content width is the only
 * thing that reliably measures.
 */
function ChartFrame({
  height,
  children,
}: {
  height: number;
  children: React.ReactElement;
}) {
  if (useIsPrint()) {
    return (
      <div style={{ width: PRINT_CONTENT_WIDTH_PX, height }}>
        {React.cloneElement(children, { width: PRINT_CONTENT_WIDTH_PX, height } as never)}
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      {children}
    </ResponsiveContainer>
  );
}


const INTENT_LABELS: Record<string, string> = {
  problem_aware: "Problem-aware",
  category: "Category",
  comparison: "Comparison",
  brand: "Brand",
  adjacent_authority: "Adjacent",
  local_intent: "Local",
  hybrid: "Hybrid",
  informational: "Informational",
};

/** Client-facing surface names. Six surfaces, not four — Google AI Overviews and
 * Google AI Mode are DIFFERENT surfaces with different behaviour, and collapsing
 * them into one "Google" would average two things into a number describing
 * neither. Never render a raw engine key or a bare model id to a client. */
const ENGINE_LABELS: Record<string, string> = {
  openai: "ChatGPT",
  openai_search: "ChatGPT (web search)",
  anthropic: "Claude",
  anthropic_search: "Claude (web search)",
  gemini: "Gemini",
  gemini_grounded: "Gemini (grounded)",
  perplexity: "Perplexity",
  google_ai_overviews: "Google AI Overviews",
  google_ai_mode: "Google AI Mode",
  mock: "Mock",
};

// A categorical palette for sources. The brand charts use the Sable navy ramp
// (see ShareStackedBar / EngineHeatmap); this stays only where a categorical
// encoding is genuinely needed and no brand comparison is implied.
const PALETTE = [
  "hsl(243 75% 59%)", // indigo (primary)
  "hsl(199 89% 48%)", // sky
  "hsl(160 84% 39%)", // emerald
  "hsl(38 92% 50%)", // amber
  "hsl(280 65% 60%)", // violet
  "hsl(340 75% 55%)", // rose
  "hsl(215 20% 65%)", // slate
];

const AXIS_TICK = { fontSize: 12, fill: "hsl(var(--muted-foreground))" };

const tooltipStyle = {
  contentStyle: {
    borderRadius: 8,
    border: "1px solid hsl(var(--border))",
    fontSize: 12,
    background: "hsl(var(--card))",
  },
};

/** Horizontal share-of-model bars (client highlighted). */
export const LeaderboardChart = React.memo(function LeaderboardChart({
  rows,
}: {
  rows: LeaderRow[];
}) {
  useChartSettled();
  const isPrint = useIsPrint();
  const data = React.useMemo(
    () =>
      rows.map((r) => ({
        brand: r.brand,
        share: Math.round(r.share_of_model * 100),
        isClient: r.is_client,
      })),
    [rows],
  );
  const height = Math.max(120, data.length * 46);

  return (
    <ChartFrame height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 8 }}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis
          type="category"
          dataKey="brand"
          width={120}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 13, fill: "hsl(var(--foreground))" }}
        />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v}%`, "Share of model"]} />
        <Bar dataKey="share" radius={[4, 4, 4, 4]} barSize={22} isAnimationActive={!isPrint}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.isClient ? "hsl(var(--primary))" : "hsl(215 20% 70%)"} />
          ))}
          <LabelList
            dataKey="share"
            position="right"
            formatter={(v: number) => `${v}%`}
            style={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
});

/** 100% stacked horizontal bar of share-of-model. Replaces the deleted donut.
 *
 * Arc-angle comparison across non-adjacent segments is a known perceptual weak
 * point — Semrush's own design system caps donuts at 5 segments and says never
 * use them to compare value sets, and this chart compares six brands. A single
 * stacked bar puts every segment on one shared baseline, so the client's share
 * against the leader's is a length comparison instead of an angle one.
 *
 * Hand-rolled SVG-free markup rather than recharts: it is a pure function of the
 * data, which means it renders in a Server Component and needs no hydration for
 * the PDF path. Numbers are printed, not just encoded. */
export const ShareStackedBar = React.memo(function ShareStackedBar({
  rows,
}: {
  rows: LeaderRow[];
}) {
  useChartSettled();
  const data = React.useMemo(
    () =>
      rows
        .map((r) => ({ name: r.brand, value: r.share_of_model, isClient: r.is_client }))
        .filter((d) => d.value > 0)
        .sort((a, b) => b.value - a.value),
    [rows],
  );

  if (data.length === 0) {
    return <p className="body py-8 text-center text-sm">No share to show — nothing was mentioned.</p>;
  }
  // The single-row state: one brand holds everything. Common on a pre-launch
  // client, and a stacked bar with one segment reads as a bug without the note.
  const soleBrand = data.length === 1 ? data[0] : null;

  return (
    <div className="space-y-3">
      <div className="flex h-7 w-full overflow-hidden rounded" style={{ gap: 2 }}>
        {data.map((d, i) => (
          <div
            key={d.name}
            title={`${d.name} — ${Math.round(d.value * 100)}%`}
            style={{
              flexGrow: d.value,
              // Monochrome ramp: the client is navy, competitors step lighter by
              // rank. No categorical palette — Sable has no second hue to spend.
              backgroundColor: d.isClient
                ? "var(--navy)"
                : i < 2
                  ? "var(--harbour)"
                  : "var(--mist)",
            }}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
        {data.map((d) => (
          <li key={d.name} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: d.isClient ? "var(--navy)" : "var(--harbour)" }}
            />
            <span className={d.isClient ? "font-medium" : ""}>{d.name}</span>
            <span className="tabular-nums">{Math.round(d.value * 100)}%</span>
          </li>
        ))}
      </ul>
      {soleBrand && (
        <p className="body text-xs">
          Only {soleBrand.name} was mentioned in any sampled answer, so it holds the whole bar.
        </p>
      )}
    </div>
  );
});

/** Brand × engine presence, one cell per pair, with the NUMBERS printed in it.
 *
 * The highest-value single chart in the report: engine divergence is the most
 * decision-relevant split in this data and nothing showed it before. Colour to
 * scan, digits to verify — colour alone fails accessibility and, on a
 * single-hue ramp, fails plain legibility too.
 *
 * Fixed column order and a pinned client row, both deliberate: a chart whose
 * layout moves between editions cannot be compared at a glance, which is the
 * whole job of a recurring report. */
export const EngineHeatmap = React.memo(function EngineHeatmap({
  rows,
  engines,
  clientName,
}: {
  rows: EngineCellRow[];
  engines: string[];
  clientName: string;
}) {
  useChartSettled();
  const byBrand = React.useMemo(() => {
    const map = new Map<string, Map<string, EngineCellRow>>();
    for (const r of rows) {
      if (!map.has(r.brand)) map.set(r.brand, new Map());
      map.get(r.brand)!.set(r.engine_name, r);
    }
    return map;
  }, [rows]);

  if (rows.length === 0 || engines.length === 0) {
    return (
      <p className="body py-8 text-center text-sm">
        Per-engine breakdown needs the LLM judge — run it to populate this grid.
      </p>
    );
  }

  // Client row first, then competitors by overall presence. Pinned, not sorted
  // into the pack: the reader is always looking for one row.
  const brands = [
    clientName,
    ...[...byBrand.keys()]
      .filter((b) => b !== clientName)
      .sort((a, b) => totalRate(byBrand.get(b)!) - totalRate(byBrand.get(a)!)),
  ].filter((b) => byBrand.has(b));

  return (
    <div className="space-y-2 overflow-x-auto">
      <table className="w-full min-w-[32rem] border-collapse text-sm">
        <thead>
          <tr>
            <th className="label px-2 py-1 text-left">Brand</th>
            {engines.map((e) => (
              <th key={e} className="label px-2 py-1 text-center">
                {ENGINE_LABELS[e] ?? e}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {brands.map((brand) => (
            <tr key={brand} className={brand === clientName ? "font-medium" : ""}>
              <td
                className="whitespace-nowrap px-2 py-1"
                style={
                  brand === clientName
                    ? { borderLeft: "3px solid var(--navy)", paddingLeft: "0.5rem" }
                    : undefined
                }
              >
                {brand}
              </td>
              {engines.map((engine) => {
                const cell = byBrand.get(brand)?.get(engine);
                // No answers is NOT zero presence. They are opposite facts and
                // rendering both as "0%" is the error this grid exists to avoid.
                if (!cell || cell.cells === 0) {
                  return (
                    <td
                      key={engine}
                      className="px-2 py-1 text-center tabular-nums"
                      style={{ color: "var(--mist)" }}
                      title="Not measured — this surface returned no answer"
                    >
                      —
                    </td>
                  );
                }
                return (
                  <td
                    key={engine}
                    className="px-2 py-1 text-center tabular-nums"
                    title={`${cell.present} of ${cell.cells} answers named ${brand}`}
                    style={{
                      // Sequential single-hue ramp: opacity over navy. One hue,
                      // magnitude by lightness — the only encoding the palette
                      // has room for.
                      backgroundColor: `rgba(14, 35, 64, ${(0.08 + cell.rate * 0.82).toFixed(3)})`,
                      color: cell.rate > 0.45 ? "#fff" : "var(--navy)",
                    }}
                  >
                    {cell.present}/{cell.cells}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="body text-xs">
        Each cell is how many sampled answers on that surface named the brand, out of how many
        answers that surface returned. Darker is more often. “—” means the surface returned no
        answer for that brand’s queries — not measured, which is different from not mentioned.
      </p>
    </div>
  );
});

function totalRate(cells: Map<string, EngineCellRow>): number {
  let present = 0;
  let total = 0;
  for (const c of cells.values()) {
    present += c.present;
    total += c.cells;
  }
  return total ? present / total : 0;
}

/** Grouped bars of mention (and citation, when present) per intent bucket. */
export const BucketChart = React.memo(function BucketChart({ rows }: { rows: BucketRow[] }) {
  useChartSettled();
  const isPrint = useIsPrint();
  const hasCitation = rows.some((r) => r.citation_rate !== null);
  const data = React.useMemo(
    () =>
      rows.map((r) => ({
        bucket: INTENT_LABELS[r.bucket] ?? r.bucket,
        mention: Math.round(r.mention_rate * 100),
        citation: r.citation_rate === null ? 0 : Math.round(r.citation_rate * 100),
      })),
    [rows],
  );

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No data.</p>;
  }

  return (
    <ChartFrame height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
        <XAxis dataKey="bucket" tickLine={false} axisLine={false} tick={AXIS_TICK} interval={0} />
        <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={AXIS_TICK} unit="%" />
        <Tooltip {...tooltipStyle} formatter={(v: number) => `${v}%`} cursor={{ fill: "hsl(var(--secondary))" }} />
        {hasCitation && <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />}
        <Bar dataKey="mention" name="Mention" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} barSize={hasCitation ? 16 : 28} isAnimationActive={!isPrint} />
        {hasCitation && (
          <Bar dataKey="citation" name="Citation" fill="hsl(199 89% 48%)" radius={[4, 4, 0, 0]} barSize={16} isAnimationActive={!isPrint} />
        )}
      </BarChart>
    </ChartFrame>
  );
});

/** Horizontal bars of the most-cited domains. */
export const SourcesChart = React.memo(function SourcesChart({ rows }: { rows: SourceRow[] }) {
  useChartSettled();
  const isPrint = useIsPrint();
  const data = React.useMemo(
    () => rows.slice(0, 8).map((r) => ({ domain: r.domain, count: r.count })),
    [rows],
  );
  if (data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No citations captured for this run.
      </p>
    );
  }
  const height = Math.max(120, data.length * 38);

  return (
    <ChartFrame height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 32, bottom: 4, left: 8 }}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="domain"
          width={140}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 12, fill: "hsl(var(--foreground))" }}
        />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [v, "cells"]} cursor={{ fill: "hsl(var(--secondary))" }} />
        <Bar dataKey="count" radius={[4, 4, 4, 4]} barSize={18} isAnimationActive={!isPrint}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            style={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
});
