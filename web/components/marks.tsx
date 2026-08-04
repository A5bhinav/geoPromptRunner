import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Every data mark in the app chrome, in one file.
 *
 * THE CONSTRAINT THAT SHAPES ALL OF IT: Sable has four inks and no alert hue.
 * There is no red, no amber, no green, and adding one is an explicit brand
 * Don't. So a categorical series cannot be coloured — it can only be RAMPED, and
 * a ramp is only honest when the axis is ordinal (funnel stage, severity, rank).
 * Where the axis is not ordinal, the distinction has to be carried by a glyph or
 * a label as well as a fill. That is why nothing here takes an arbitrary colour
 * prop: `tone` is a closed union, and the ramp is index-ordered.
 *
 * Charts are hand-authored SVG rather than a charting library on purpose. Every
 * one of these is a polyline or a rect with a fixed spec, they have to survive
 * the print path at a fixed size, and a library would bring its own colour
 * scale — the exact thing the paragraph above says cannot exist here.
 */

/** Darkest = first = most. Four steps and no fifth: a fifth would have to come
 * from outside the palette. A series longer than four collapses its tail into
 * "Others" (that is what the report's share-of-model panel does). */
export const RAMP = ["#0E2340", "#12325C", "#697585", "#B2B7BC"] as const;

/** Not-a-value. Diagonal hatch, not a fifth grey: a flat grey block reads as a
 * measured zero, and "we have no data for this" and "this measured zero" are
 * different claims — one of which we are not entitled to make. */
export const STRIPE =
  "repeating-linear-gradient(45deg, #dfe2e6, #dfe2e6 4px, #f2f1ec 4px, #f2f1ec 8px)";

export function rampAt(i: number): string {
  return RAMP[Math.min(i, RAMP.length - 1)];
}

/* ------------------------------------------------------------------ bars --- */

export interface Segment {
  label: string;
  value: number;
  /** Omit to take the ramp position. */
  tone?: string;
  /** Hatched: this band exists but was not measured. */
  striped?: boolean;
  /** White with a navy ring. For a band that is OFF the ordinal axis the ramp
   * encodes — `adjacent_authority` is not a funnel stage, it sits beside the
   * funnel — so giving it a rung would assert an ordering that isn't real.
   * Same reasoning as the hollow dot in components/badges.tsx. */
  hollow?: boolean;
}

function segmentStyle(s: Segment, i: number): React.CSSProperties {
  if (s.striped) return { background: STRIPE };
  if (s.hollow) return { background: "#fff", boxShadow: "inset 0 0 0 1px rgb(14 35 64 / 0.35)" };
  return { background: s.tone ?? rampAt(i) };
}

/**
 * The query set as one picture: a segmented bar plus a legend that carries the
 * counts. The legend is not decoration — with a monochrome ramp the bar alone
 * cannot tell you which band is which, so removing the legend removes the data.
 */
export function SegmentedBar({
  segments,
  height = 30,
  ariaLabel,
}: {
  segments: Segment[];
  height?: number;
  ariaLabel: string;
}) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  return (
    <div>
      <div
        role="img"
        aria-label={ariaLabel}
        className="flex overflow-hidden rounded"
        style={{ height, gap: 3 }}
      >
        {segments
          .filter((s) => s.value > 0)
          .map((s, i) => (
            <div key={s.label} style={{ flexGrow: s.value, ...segmentStyle(s, i) }} />
          ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[12.5px]">
        {segments.map((s, i) => (
          <span key={s.label} className="inline-flex items-center gap-[7px]">
            <span
              aria-hidden
              className="h-[9px] w-[9px] rounded-sm"
              style={segmentStyle(s, i)}
            />
            {s.label}{" "}
            <span
              className={cn(
                "tabular-nums",
                // The unmeasured band's count is the one a person needs to act
                // on, so it is inked rather than quieted.
                s.striped ? "font-medium text-navy" : "text-harbour",
              )}
            >
              {s.value}
            </span>
          </span>
        ))}
      </div>
      <span className="sr-only">{total} in total.</span>
    </div>
  );
}

/**
 * label · track · value. The workhorse: per-surface progress, visibility by
 * funnel stage, who-the-models-cite, all the same row.
 */
export function MeterRow({
  label,
  pct,
  value,
  tone = RAMP[0],
  labelWidth = 108,
  valueWidth = 40,
  striped,
  emphasis,
}: {
  label: string;
  /** 0–100. Ignored when `striped` — a hatched track has no fill. */
  pct: number;
  value?: React.ReactNode;
  tone?: string;
  labelWidth?: number;
  valueWidth?: number;
  striped?: boolean;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 text-[12.5px]">
      <span
        className={cn("shrink-0 truncate", emphasis ? "font-medium text-navy" : "text-harbour")}
        style={{ width: labelWidth }}
      >
        {label}
      </span>
      <span
        className="h-2.5 flex-1 overflow-hidden rounded-full"
        style={{ background: striped ? STRIPE : "rgb(14 35 64 / 0.08)" }}
      >
        {striped ? null : (
          <span
            className="block h-full rounded-full"
            style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: tone }}
          />
        )}
      </span>
      {value !== undefined ? (
        <span
          className={cn(
            "shrink-0 text-right tabular-nums",
            emphasis ? "font-medium text-navy" : "text-harbour",
          )}
          style={{ width: valueWidth }}
        >
          {value}
        </span>
      ) : null}
    </div>
  );
}

/** A heatmap cell. Navy at alpha; at 0.43 and above the fill is dark enough that
 * navy text drops below AA, so the ink flips to white. An em dash means no data
 * — never a zero, which would assert a measurement we did not make. */
export function HeatCell({ value, alpha }: { value: number | null; alpha: number }) {
  const dark = alpha >= 0.43;
  return (
    <span
      className={cn(
        "block rounded py-[9px] text-center tabular-nums",
        dark ? "text-white" : "text-navy",
      )}
      style={{ background: `rgba(14, 35, 64, ${value === null ? 0.04 : alpha})` }}
    >
      {value === null ? "—" : value}
    </span>
  );
}

/* ---------------------------------------------------------------- donut --- */

const DONUT_R = 60;
const DONUT_C = 2 * Math.PI * DONUT_R; // 377

/** Run progress. The number inside is the reading; the arc is the glance. */
export function Donut({
  pct,
  caption,
  size = 184,
}: {
  pct: number;
  caption: string;
  size?: number;
}) {
  const safe = Math.max(0, Math.min(100, pct));
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 150 150"
      role="img"
      aria-label={`${Math.round(safe)}% complete. ${caption}`}
      className="shrink-0"
    >
      <circle
        cx="75"
        cy="75"
        r={DONUT_R}
        fill="none"
        stroke="rgb(14 35 64 / 0.08)"
        strokeWidth="15"
      />
      <circle
        cx="75"
        cy="75"
        r={DONUT_R}
        fill="none"
        stroke={RAMP[0]}
        strokeWidth="15"
        strokeLinecap="round"
        strokeDasharray={`${(DONUT_C * safe) / 100} ${DONUT_C}`}
        transform="rotate(-90 75 75)"
      />
      <text
        x="75"
        y="72"
        textAnchor="middle"
        fontFamily="Libre Franklin, sans-serif"
        fontWeight="600"
        fontSize="34"
        letterSpacing="-1"
        fill={RAMP[0]}
      >
        {Math.round(safe)}%
      </text>
      <text
        x="75"
        y="94"
        textAnchor="middle"
        fontFamily="Libre Franklin, sans-serif"
        fontSize="10"
        fontWeight="500"
        letterSpacing="0.5"
        fill="#697585"
      >
        {caption}
      </text>
    </svg>
  );
}

/* --------------------------------------------------------------- trends --- */

export interface TrendPoint {
  /** Rendered under the point as "Mar 41%" — the label carries its own value so
   * the chart is readable without hovering, and prints. */
  label: string;
  value: number;
}

/**
 * The cycle-over-cycle line. Four points, not forty: this is a monthly cadence,
 * and a dense line would imply a resolution the measurement does not have.
 *
 * The LAST dot is drawn a point larger. That is the only "you are here" marker —
 * no annotation, no callout box.
 */
export function TrendChart({
  points,
  yTicks = [25, 50, 75, 100],
  height = 240,
  ariaLabel,
  caption,
}: {
  points: TrendPoint[];
  yTicks?: number[];
  height?: number;
  ariaLabel: string;
  caption?: string;
}) {
  const W = 1180;
  const H = 240;
  const PAD_L = 46;
  const TOP = 20;
  const BASE = 200;
  const max = Math.max(...yTicks);
  const y = (v: number) => BASE - (v / max) * (BASE - TOP);
  // Points are inset from both ends so the first and last labels do not clip.
  const span = W - PAD_L - 70;
  const x = (i: number) =>
    points.length === 1 ? PAD_L + span / 2 : PAD_L + 24 + (i * (span - 24)) / (points.length - 1);

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={height}
        role="img"
        aria-label={ariaLabel}
        // `report-chart` is what scripts/check-print-layout.mjs measures for
        // collapsed geometry. It replaced the `.recharts-wrapper` selector when
        // recharts left the report — an unmarked chart is an unchecked chart.
        className="report-chart"
      >
        {yTicks.map((t) => (
          <line
            key={t}
            x1={PAD_L}
            y1={y(t)}
            x2={W}
            y2={y(t)}
            stroke="rgb(14 35 64 / 0.07)"
          />
        ))}
        {/* The zero line is drawn darker — it is an axis, not a gridline. */}
        <line x1={PAD_L} y1={BASE} x2={W} y2={BASE} stroke="rgb(14 35 64 / 0.12)" />
        {[0, ...yTicks].map((t) => (
          <text
            key={t}
            x={PAD_L - 8}
            y={y(t) + 4}
            textAnchor="end"
            fontFamily="Libre Franklin, sans-serif"
            fontSize="11"
            fill="#697585"
          >
            {t}%
          </text>
        ))}
        {points.length > 1 ? (
          <polyline
            points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")}
            fill="none"
            stroke={RAMP[0]}
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}
        {points.map((p, i) => (
          <circle
            key={p.label}
            cx={x(i)}
            cy={y(p.value)}
            r={i === points.length - 1 ? 5.5 : 4.5}
            fill={RAMP[0]}
          />
        ))}
        {points.map((p, i) => (
          <text
            key={p.label}
            x={x(i)}
            y={BASE + 24}
            textAnchor="middle"
            fontFamily="Libre Franklin, sans-serif"
            fontSize="11"
            fill="#697585"
          >
            {p.label} {p.value}%
          </text>
        ))}
      </svg>
      {caption ? (
        <p className="mt-2.5 text-[11px] text-[color:var(--ink-secondary)]">{caption}</p>
      ) : null}
    </div>
  );
}

/**
 * The live cumulative curve on the Running screen. Deliberately axis-less: it
 * answers "is this still moving" and nothing else, and the exact number sits
 * above it at 38px where it can actually be read.
 */
export function AreaChart({
  values,
  height = 140,
  ariaLabel,
}: {
  values: number[];
  height?: number;
  ariaLabel: string;
}) {
  const W = 640;
  const H = 140;
  if (values.length < 2) {
    return <div style={{ height }} aria-hidden />;
  }
  const max = Math.max(...values, 1);
  const x = (i: number) => (i * W) / (values.length - 1);
  const y = (v: number) => H - 4 - (v / max) * (H - 24);
  const line = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
      className="report-chart"
    >
      {[35, 70, 105].map((gy) => (
        <line
          key={gy}
          x1="0"
          y1={gy}
          x2={W}
          y2={gy}
          stroke="rgb(14 35 64 / 0.07)"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      <path d={`M${line.replace(/ /g, " L")} L${W} ${H} L0 ${H} Z`} fill="rgb(14 35 64 / 0.07)" />
      {/* non-scaling-stroke because preserveAspectRatio="none" stretches x to the
          container width — without it the line thins and thickens with the
          window, which reads as a rendering fault. */}
      <polyline
        points={line}
        fill="none"
        stroke={RAMP[0]}
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/* ---------------------------------------------------------------- plumes --- */

export type MarkState = "done" | "current" | "skipped" | "todo";

/**
 * The progress rail: the Sable mark taken apart and used as a scale.
 *
 * A SKIPPED mark is Mist with a navy ring — visibly ADDRESSED, never "answered"
 * and never "pending". That distinction is the whole reason skipping is safe to
 * offer: the owner can see that leaving something blank was recorded as a
 * decision, not lost.
 *
 * Never render this as a row of three-up mini logos. It is one plume per
 * question; the mark's own proportions do not apply.
 */
export function PlumeRail({
  marks,
  ariaLabel,
}: {
  marks: MarkState[];
  ariaLabel: string;
}) {
  const done = marks.filter((m) => m === "done" || m === "skipped").length;
  return (
    <span
      role="progressbar"
      aria-valuenow={done}
      aria-valuemin={0}
      aria-valuemax={marks.length}
      aria-label={ariaLabel}
      className="flex items-end gap-1"
    >
      {marks.map((m, i) => (
        <span
          key={i}
          aria-hidden
          className={cn("h-[11px] w-1", m === "current" && "anim-plume-breathe")}
          style={{
            borderRadius: "999px 999px 1px 1px",
            background:
              m === "done" ? RAMP[0] : m === "current" ? "#697585" : "#B2B7BC",
            boxShadow: m === "skipped" ? "0 0 0 1px #0E2340" : undefined,
          }}
        />
      ))}
    </span>
  );
}

/**
 * The verification tier, as the mark.
 *
 * `verification_tier` is a MINIMUM across the sheet's claims, so the third plume
 * is the one that matters: it is Mist until every claim is client-confirmed, and
 * navy the moment they are. Two navy plumes and a Mist one is the picture of
 * "this sheet can only flag low and medium issues" — which is the sentence next
 * to it.
 */
export function TierMeter({
  confirmed,
  size = "sm",
}: {
  confirmed: boolean;
  size?: "sm" | "lg";
}) {
  const heights = size === "lg" ? [9, 13, 17] : [8, 11, 14];
  const w = size === "lg" ? 5 : 4;
  return (
    <span aria-hidden className="flex items-end gap-[3px]">
      {heights.map((h, i) => (
        <span
          key={h}
          style={{
            width: w,
            height: h,
            borderRadius: "999px 999px 1px 1px",
            background: i === 2 && !confirmed ? "#B2B7BC" : RAMP[0],
          }}
        />
      ))}
    </span>
  );
}

/** "Sable is thinking" — the mark, pulsing left to right. Not a spinner: a
 * spinner says "the system is busy", and this says "someone is composing a
 * reply", which is the truer description of what the intake is doing. */
export function ThinkingPlumes() {
  const spec: [number, string, number][] = [
    [8, "#B2B7BC", 0],
    [11, "#697585", 150],
    [14, "#0E2340", 300],
  ];
  return (
    <span className="inline-flex items-end gap-[3px]" role="status" aria-label="Thinking">
      {spec.map(([h, fill, delay]) => (
        <span
          key={h}
          aria-hidden
          className="anim-plume-pulse w-1"
          style={{
            height: h,
            background: fill,
            borderRadius: "999px 999px 1px 1px",
            animationDelay: `${delay}ms`,
          }}
        />
      ))}
    </span>
  );
}
