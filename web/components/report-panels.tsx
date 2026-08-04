"use client";

import * as React from "react";
import { PanelCell, PanelGrid } from "@/components/page";
import { HeatCell, MeterRow, RAMP, TrendChart, type TrendPoint } from "@/components/marks";
import { SEVERITY_LABELS, SEVERITY_ORDER } from "@/components/badges";
import { cn, pct } from "@/lib/utils";
import type {
  BucketRow,
  EngineCellRow,
  FindingGroupRow,
  LeaderRow,
  RatePayload,
  SourceRow,
} from "@/lib/api";

/**
 * The report's overview: four panels, charts first.
 *
 * These REPLACE the recharts sections they cover (leaderboard, stacked share,
 * heatmap, bucket bars, sources bars). That is a deliberate deletion, not a
 * duplication: the packaging rules say don't add a charting dependency and
 * hand-roll the SVG, the old sources chart was still painting indigo / emerald /
 * amber from a categorical palette the brand does not have, and the old bucket
 * chart was spending a second hue on the citation series. Every mark below is a
 * div or a polyline in the four-step navy ramp.
 *
 * Panels are GRIDS SPLIT BY HAIRLINES, never a grid of separate cards. A
 * deliverable page wants one object with four readings.
 */

/** Client-facing surface names. Six surfaces, not four — Google AI Overviews and
 * Google AI Mode are different surfaces with different behaviour, and collapsing
 * them would average two things into a number describing neither. Never render a
 * raw engine key or a bare model id to a client. */
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
export const engineLabel = (name: string) => ENGINE_LABELS[name] ?? name;

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

/** Darkest is most severe. The ramp mirrors the mark's own logic — the plumes
 * step tone with height so the eye lands on the tallest, darkest form. */
const SEVERITY_TONE: Record<string, string> = {
  critical: RAMP[0],
  high: RAMP[1],
  med: RAMP[2],
  low: RAMP[3],
};

/** Distinct SHAPES, not just distinct fills. Load-bearing on a single-hue ramp:
 * colour genuinely cannot carry the distinction, and this is also what makes the
 * report legible in grayscale and to a colourblind reader. */
function SeverityGlyph({ severity, size = 9 }: { severity: string; size?: number }) {
  const p = { width: size, height: size, viewBox: "0 0 10 10", "aria-hidden": true } as const;
  if (severity === "critical")
    return (
      <svg {...p}>
        <polygon points="5,0 10,10 0,10" fill="currentColor" />
      </svg>
    );
  if (severity === "high")
    return (
      <svg {...p}>
        <circle cx="5" cy="5" r="5" fill="currentColor" />
      </svg>
    );
  if (severity === "med")
    return (
      <svg {...p}>
        <rect width="10" height="10" fill="currentColor" />
      </svg>
    );
  return (
    <svg {...p}>
      <circle cx="5" cy="5" r="2.5" fill="currentColor" />
    </svg>
  );
}

function SeverityPill({ severity }: { severity: string }) {
  const tone = SEVERITY_TONE[severity] ?? RAMP[3];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-medium"
      style={{ background: tone, color: severity === "low" ? RAMP[0] : "#fff" }}
    >
      <SeverityGlyph severity={severity} />
      {SEVERITY_LABELS[severity] ?? severity}
    </span>
  );
}

/* ------------------------------------------------------------- 1 headline --- */

/**
 * The headline panel IS the scorecard: one measured hero and three counted
 * tiles. No letter grade and no composite score — every number here is either
 * counted (findings, cycles open) or measured (sampled rate, share of model).
 *
 * ON THE HERO PERCENTAGE. The rule is "no rate without its denominator", and the
 * design puts the percentage at 76px with the count beneath it. Those pull
 * against each other, and the resolution is that the count sits in the SAME
 * block at 15px/500 in navy — not quieted to 13px Harbour — and the Wilson
 * interval sits under it. A reader cannot take away "66%" without also taking
 * away "119 of 180" and "95% CI 58–73%", which is what the rule is protecting
 * against: a precision illusion at n = 180.
 */
export function HeadlinePanel({
  clientName,
  visibility,
  surfaces,
  delta,
  themes,
  critical,
  accuracyAssessed,
  shareOfModel,
  topCompetitor,
  topCompetitorShare,
  oldestOpen,
  trend,
  perSurface,
}: {
  clientName: string;
  visibility?: RatePayload;
  surfaces: number;
  delta?: React.ReactNode;
  themes: number;
  critical: number;
  accuracyAssessed: boolean;
  shareOfModel: number;
  topCompetitor: string | null;
  topCompetitorShare: number | null;
  oldestOpen: FindingGroupRow | null;
  /** Two or more comparable cycles, or undefined. Never a single point. */
  trend?: TrendPoint[];
  perSurface: { engine: string; present: number; cells: number }[];
}) {
  const measured = visibility && visibility.n > 0;
  return (
    <PanelGrid cols="340px 1fr">
      <PanelCell className="flex flex-col gap-2.5">
        <p className="section-label">AI visibility</p>
        {measured ? (
          <>
            <p className="mt-1.5 text-[76px] font-semibold leading-[0.85] tracking-[-0.035em] tabular-nums">
              {pct(visibility.rate)}
            </p>
            <p className="text-[15px] font-medium leading-snug tabular-nums">
              {visibility.successes} of {visibility.n} sampled answers name {clientName}
            </p>
            <p className="text-[12px] text-harbour tabular-nums">
              across {surfaces} surface{surfaces === 1 ? "" : "s"} · 95% CI{" "}
              {pct(visibility.ci_low)}–{pct(visibility.ci_high)}
            </p>
          </>
        ) : (
          <>
            <p className="mt-1.5 text-[34px] font-semibold leading-tight">Insufficient data</p>
            <p className="text-[13px] text-harbour">No surface returned an answer to measure.</p>
          </>
        )}
        {delta ? <span className="self-start">{delta}</span> : null}

        <div className="mt-auto flex gap-6 pt-4">
          <MiniStat
            label="Open findings"
            value={accuracyAssessed ? themes : "—"}
            note={accuracyAssessed ? `${critical} critical` : "not assessed"}
          />
          <MiniStat
            label="Share of model"
            value={pct(shareOfModel)}
            note={
              topCompetitor
                ? `vs ${topCompetitor} ${pct(topCompetitorShare)}`
                : "no competitors configured"
            }
          />
          {/* Replaces the grade, and does its job better: SLA-style aging is what
              creates pressure to act, and it is a count rather than an opinion. */}
          <MiniStat
            label="Oldest open"
            value={oldestOpen ? `${oldestOpen.cycles_open ?? 1}` : "—"}
            note={oldestOpen ? oldestOpen.title : "needs a prior cycle"}
          />
        </div>
      </PanelCell>

      <PanelCell>
        {trend && trend.length >= 2 ? (
          <>
            <div className="mb-2.5 flex items-baseline justify-between">
              <p className="section-label">Visibility by cycle</p>
              <span className="text-[12px] text-harbour">Answers naming the brand</span>
            </div>
            <TrendChart
              points={trend}
              yTicks={[20, 40, 60, 80]}
              height={230}
              ariaLabel={`Visibility by cycle for ${clientName}`}
            />
          </>
        ) : (
          <>
            <div className="mb-4 flex items-baseline justify-between">
              <p className="section-label">Visibility by surface</p>
              <span className="text-[12px] text-harbour">
                {/* A one-point line is not a trend, so it is not drawn. */}
                One cycle so far — no trend yet
              </span>
            </div>
            <div className="flex flex-col gap-3">
              {perSurface.length === 0 ? (
                <p className="text-[13px] text-harbour">
                  Per-surface presence needs the LLM judge — run it to populate this.
                </p>
              ) : (
                perSurface.map((r) => (
                  <MeterRow
                    key={r.engine}
                    label={engineLabel(r.engine)}
                    labelWidth={160}
                    valueWidth={64}
                    pct={r.cells ? (r.present / r.cells) * 100 : 0}
                    striped={r.cells === 0}
                    value={r.cells === 0 ? "—" : `${r.present}/${r.cells}`}
                  />
                ))
              )}
            </div>
          </>
        )}
      </PanelCell>
    </PanelGrid>
  );
}

function MiniStat({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <span className="flex min-w-0 flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-harbour">
        {label}
      </span>
      <span className="text-[20px] tabular-nums">{value}</span>
      {note ? <span className="truncate text-[11px] text-harbour">{note}</span> : null}
    </span>
  );
}

/* ---------------------------------------------------------- 2 competitive --- */

export function CompetitivePanel({
  leaderboard,
  bySeverity,
  totalFindings,
  buckets,
  accuracyAssessed,
}: {
  leaderboard: LeaderRow[];
  bySeverity: Record<string, number>;
  totalFindings: number;
  buckets: BucketRow[];
  accuracyAssessed: boolean;
}) {
  const shares = leaderboard
    .map((r) => ({ name: r.brand, value: r.share_of_model, isClient: r.is_client }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value);
  const sole = shares.length === 1 ? shares[0] : null;

  const maxSeverity = Math.max(1, ...SEVERITY_ORDER.map((s) => bySeverity[s] ?? 0));

  return (
    <PanelGrid cols="1fr 1fr 1fr">
      {/* -- share of model: a 100% stacked bar, never a donut. Arc-angle
             comparison across non-adjacent segments is a known perceptual weak
             point; a single bar puts every brand on one shared baseline. */}
      <PanelCell>
        <p className="section-label">Share of model</p>
        {shares.length === 0 ? (
          <p className="mt-4 text-[13px] text-harbour">
            No share to show — nothing was mentioned in any sampled answer.
          </p>
        ) : (
          <>
            <ul className="mt-4 flex flex-col gap-3 text-[12.5px]">
              {shares.slice(0, 4).map((d, i) => (
                <li key={d.name} className="flex items-center gap-2.5">
                  <span
                    aria-hidden
                    className="h-[9px] w-[9px] shrink-0 rounded-sm"
                    style={{ background: d.isClient ? RAMP[0] : RAMP[Math.min(i + 1, 3)] }}
                  />
                  <span className={cn("flex-1 truncate", d.isClient && "font-medium")}>
                    {d.name}
                  </span>
                  <span
                    className={cn(
                      "text-[14px] font-semibold tabular-nums",
                      !d.isClient && "text-harbour",
                    )}
                  >
                    {pct(d.value)}
                  </span>
                </li>
              ))}
            </ul>
            <div
              role="img"
              aria-label={shares
                .map((d) => `${d.name} ${pct(d.value)}`)
                .join(", ")}
              className="mt-4 flex h-2.5 overflow-hidden rounded-full"
              style={{ gap: 2 }}
            >
              {shares.map((d, i) => (
                <span
                  key={d.name}
                  style={{
                    flexGrow: d.value,
                    background: d.isClient ? RAMP[0] : RAMP[Math.min(i + 1, 3)],
                  }}
                />
              ))}
            </div>
            {sole ? (
              // The single-row state. Common on a pre-launch client, and a
              // stacked bar with one segment reads as a bug without the note.
              <p className="mt-3 text-[11px] text-harbour">
                Only {sole.name} was mentioned in any sampled answer, so it holds the whole bar.
              </p>
            ) : null}
          </>
        )}
      </PanelCell>

      {/* -- findings by severity. Critical → High → Medium → Low, always in that
             order: never chronological, never by count. */}
      <PanelCell className="flex flex-col">
        <div className="flex items-baseline justify-between">
          <p className="section-label">Findings by severity</p>
          <span className="text-[12px] text-harbour">
            {accuracyAssessed ? `${totalFindings} total` : "not assessed"}
          </span>
        </div>
        {accuracyAssessed ? (
          <div className="mt-4 flex h-[132px] items-end gap-2.5">
            {SEVERITY_ORDER.map((s) => {
              const n = bySeverity[s] ?? 0;
              const tone = SEVERITY_TONE[s];
              return (
                <div key={s} className="flex flex-1 flex-col items-center gap-2">
                  <span
                    className="flex w-full items-center justify-center rounded text-[24px] font-semibold leading-none tabular-nums"
                    style={{
                      // A zero bar still gets a visible stub, so the tier is
                      // present in the chart rather than silently missing.
                      height: Math.max(28, (n / maxSeverity) * 110),
                      background: tone,
                      color: s === "low" ? RAMP[0] : "#fff",
                    }}
                  >
                    {n}
                  </span>
                  <span
                    className="flex items-center gap-1.5 text-[11px] font-medium text-harbour"
                    style={{ color: tone }}
                  >
                    <SeverityGlyph severity={s} size={8} />
                    <span className="text-harbour">{SEVERITY_LABELS[s]}</span>
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="mt-4 text-[13px] text-harbour">
            Accuracy needs an approved fact sheet and the LLM judge. Nothing is being checked, which
            is different from nothing being wrong.
          </p>
        )}
      </PanelCell>

      {/* -- visibility by funnel stage. Counts, not bare percentages: the bar
             already encodes the rate, so the number carries the denominator. */}
      <PanelCell>
        <p className="section-label">Visibility by funnel stage</p>
        <div className="mt-4 flex flex-col gap-3">
          {buckets.length === 0 ? (
            <p className="text-[13px] text-harbour">No questions carried a usable intent.</p>
          ) : (
            buckets.map((b) => {
              const answered = b.answered_cells ?? 0;
              const successes = Math.round(b.mention_rate * answered);
              return (
                <MeterRow
                  key={b.bucket}
                  label={INTENT_LABELS[b.bucket] ?? b.bucket}
                  labelWidth={108}
                  valueWidth={52}
                  pct={b.mention_rate * 100}
                  value={answered ? `${successes}/${answered}` : "—"}
                />
              );
            })
          )}
        </div>
        <p className="mt-3 text-[11px] text-harbour">
          Answers naming the brand, out of the answers that surface returned for that stage.
        </p>
      </PanelCell>
    </PanelGrid>
  );
}

/* -------------------------------------------------------------- 3 presence --- */

export function PresencePanel({
  matrix,
  engines,
  clientName,
  clientDomains,
  sources,
}: {
  matrix: EngineCellRow[];
  engines: string[];
  clientName: string;
  clientDomains: string[];
  sources: SourceRow[];
}) {
  const byBrand = new Map<string, Map<string, EngineCellRow>>();
  for (const r of matrix) {
    if (!byBrand.has(r.brand)) byBrand.set(r.brand, new Map());
    byBrand.get(r.brand)!.set(r.engine_name, r);
  }
  const rate = (cells: Map<string, EngineCellRow>) => {
    let p = 0;
    let t = 0;
    for (const c of cells.values()) {
      p += c.present;
      t += c.cells;
    }
    return t ? p / t : 0;
  };
  // Client row pinned first, then competitors by overall presence. A chart whose
  // layout moves between editions cannot be compared at a glance, which is the
  // whole job of a recurring report.
  const brands = [
    clientName,
    ...[...byBrand.keys()]
      .filter((b) => b !== clientName)
      .sort((a, b) => rate(byBrand.get(b)!) - rate(byBrand.get(a)!)),
  ].filter((b) => byBrand.has(b));

  const topSources = sources.slice(0, 7);
  const maxCites = Math.max(1, ...topSources.map((s) => s.count));
  const isClientDomain = (d: string) =>
    clientDomains.some((c) => d === c || d.endsWith(`.${c}`) || c.endsWith(`.${d}`));
  // The client's own domain last and emphasised — the reading is "how far down
  // the list are we", and burying it in rank order hides exactly that.
  const orderedSources = [
    ...topSources.filter((s) => !isClientDomain(s.domain)),
    ...topSources.filter((s) => isClientDomain(s.domain)),
  ];

  return (
    <PanelGrid cols="1.35fr 1fr">
      <PanelCell>
        <div className="mb-4 flex items-baseline justify-between">
          <p className="section-label">Brand × surface</p>
          <span className="text-[12px] text-harbour">Answers naming each brand</span>
        </div>
        {brands.length === 0 || engines.length === 0 ? (
          <p className="text-[13px] text-harbour">
            Per-surface breakdown needs the LLM judge — run it to populate this grid.
          </p>
        ) : (
          <>
            <table className="w-full text-[12.5px]">
              <thead>
                <tr>
                  <th />
                  {engines.map((e) => (
                    <th
                      key={e}
                      className="px-1 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-harbour"
                    >
                      {engineLabel(e)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {brands.map((brand) => {
                  const isClient = brand === clientName;
                  return (
                    <tr key={brand}>
                      <td
                        className={cn(
                          "whitespace-nowrap py-[3px] pl-2 pr-2.5",
                          isClient ? "border-l-[3px] border-navy font-medium" : "text-harbour",
                        )}
                      >
                        {brand}
                      </td>
                      {engines.map((engine) => {
                        const cell = byBrand.get(brand)?.get(engine);
                        // No answers is NOT zero presence. They are opposite
                        // facts, and rendering both as 0 is the single error
                        // this grid exists to avoid.
                        const measured = cell && cell.cells > 0;
                        return (
                          <td key={engine} className="px-1 py-[3px]">
                            <span
                              title={
                                measured
                                  ? `${cell!.present} of ${cell!.cells} answers named ${brand}`
                                  : "Not measured — this surface returned no answer"
                              }
                            >
                              <HeatCell
                                value={measured ? cell!.present : null}
                                alpha={measured ? 0.08 + cell!.rate * 0.6 : 0.04}
                              />
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-3 text-[11px] text-harbour">
              Each cell is how many sampled answers on that surface named the brand. Darker is more
              often. “—” means the surface returned no answer for that brand’s questions — not
              measured, which is different from not mentioned.
            </p>
          </>
        )}
      </PanelCell>

      <PanelCell>
        <div className="mb-4 flex items-baseline justify-between">
          <p className="section-label">Who the models cite</p>
          <span className="text-[12px] text-harbour">
            {topSources.length} of {sources.length} domain{sources.length === 1 ? "" : "s"}
          </span>
        </div>
        {orderedSources.length === 0 ? (
          <p className="text-[13px] text-harbour">
            No citations were captured on this run. Two of the six surfaces do not return them at
            all, so an empty list is not evidence of an absent brand.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {orderedSources.map((s) => (
              <MeterRow
                key={s.domain}
                label={s.domain}
                labelWidth={112}
                valueWidth={28}
                pct={(s.count / maxCites) * 100}
                value={s.count}
                emphasis={isClientDomain(s.domain)}
                tone={isClientDomain(s.domain) ? RAMP[3] : RAMP[1]}
              />
            ))}
          </div>
        )}
      </PanelCell>
    </PanelGrid>
  );
}

/* -------------------------------------------------------------- 4 findings --- */

/** The findings summary. Five rows and a link to the full section — the count
 * bar and the triage read live here; the evidence lives in the cards below. */
export function FindingsPanel({
  groups,
  engines,
  criticalCount,
  onSeeAll,
  controls,
}: {
  groups: FindingGroupRow[];
  engines: string[];
  criticalCount: number;
  onSeeAll: () => void;
  controls?: React.ReactNode;
}) {
  const shown = groups.slice(0, 5);
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--rule)] bg-white">
      <div className="flex items-center gap-4 px-5 pb-3.5 pt-5">
        <p className="section-label">Findings</p>
        <span className="text-[12px] text-harbour">
          {groups.length} open · {criticalCount} critical
        </span>
        {controls ? <span className="ml-auto flex gap-2">{controls}</span> : null}
      </div>
      <table className="w-full text-[13px]">
        <caption className="sr-only">
          Open findings by severity, with the surfaces each appears on and how many sampled answers
          showed it.
        </caption>
        <tbody>
          {shown.length === 0 ? (
            <tr className="border-t border-[var(--rule-inner)]">
              <td className="px-5 py-4 text-[13px] text-harbour">
                No findings are open — the models described this brand accurately in every sampled
                answer.
              </td>
            </tr>
          ) : (
            shown.map((g) => (
              <tr key={g.theme} className="border-t border-[var(--rule-inner)]">
                <td className="w-[112px] px-5 py-3">
                  <SeverityPill severity={g.severity} />
                </td>
                {/* The verbatim title, never the theme key — an id is a join
                    key, not content. */}
                <td className="py-3 font-medium">{g.title}</td>
                <td className="w-[190px] px-3 py-3">
                  <span
                    className="flex gap-[3px]"
                    role="img"
                    aria-label={`Appears on ${
                      g.engines.map(engineLabel).join(", ") || "no recorded surface"
                    }`}
                  >
                    {engines.map((e) => (
                      <span
                        key={e}
                        className="h-1.5 w-6 rounded-full"
                        style={{
                          background: g.engines.includes(e)
                            ? (SEVERITY_TONE[g.severity] ?? RAMP[0])
                            : "rgb(14 35 64 / 0.1)",
                        }}
                      />
                    ))}
                  </span>
                </td>
                <td className="w-[110px] py-3 pr-5 text-right tabular-nums text-harbour">
                  {g.occurrence.observed}/{g.occurrence.total}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      {groups.length > shown.length ? (
        <div className="flex items-center border-t border-[var(--rule)] bg-[color:var(--band-soft)] px-5 py-3 text-[12px] text-harbour">
          <span>
            {shown.length} of {groups.length}
          </span>
          <button
            type="button"
            onClick={onSeeAll}
            className="ml-auto text-blue hover:underline no-print"
          >
            See all
          </button>
        </div>
      ) : null}
    </div>
  );
}
