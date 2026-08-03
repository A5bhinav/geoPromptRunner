/**
 * The Sable mark — three plumes on a shared baseline.
 *
 * Geometry is the guide's, exactly: width 1u, heights 1.7 / 2.3 / 2.9 u, gap
 * 0.3 u, corner `60% 60% 60% 0`. The box is therefore 3.6u × 2.9u.
 *
 * WHY SVG PATHS AND NOT THREE DIVS: the guide draws the plumes with CSS
 * border-radius, which the browser CLAMPS — 60%+60% on one axis exceeds 100%,
 * so every radius is scaled by 1/1.2 and the real shape is an ellipse of
 * rx=w/2, ry=h/2 with the bottom-left quadrant squared off. The paths below are
 * that shape stated directly, which means they survive `transform: scale()`,
 * print at any DPI, and drop into a favicon.
 *
 * DON'Ts encoded here rather than left to review: no rotation, no non-uniform
 * scale (the viewBox does the scaling), no colour outside the palette (`tone`
 * is a closed union), and the sub-20px degradations the guide requires.
 */
import * as React from "react";

type Tone = "paper" | "navy" | "mono";

const TONES: Record<Tone, [string, string, string]> = {
  // On a paper/white ground: Mist · Harbour · Navy.
  paper: ["#B2B7BC", "#697585", "#0E2340"],
  // On navy: white 36% · white 74% · Sky. This is the ONLY place Sky appears.
  navy: ["rgba(255,255,255,0.36)", "rgba(255,255,255,0.74)", "#7FA6D9"],
  // The guide's approved one-colour lockup, for favicons and stamps.
  mono: ["currentColor", "currentColor", "currentColor"],
};

/** One plume: an ellipse with the lower-left quadrant squared off. */
function path(x: number, w: number, h: number, base: number): string {
  const rx = w / 2;
  const ry = h / 2;
  const mid = base - ry;
  return [
    `M${x} ${base}`,
    `L${x} ${mid}`,
    `A${rx} ${ry} 0 0 1 ${x + rx} ${base - h}`,
    `A${rx} ${ry} 0 0 1 ${x + w} ${mid}`,
    `A${rx} ${ry} 0 0 1 ${x + rx} ${base}`,
    "Z",
  ].join(" ");
}

export interface PlumeProps {
  /** Rendered HEIGHT in px. The guide sizes the mark by height, never width.
   * 20 is the guide's three-plume minimum — go below it only deliberately. */
  size?: number;
  tone?: Tone;
  className?: string;
}

export function Plume({ size = 20, tone = "paper", className }: PlumeProps) {
  const fills = TONES[tone];
  // The guide's degradation ladder — below 20px drop the faintest plume and run
  // two-up; below 16px use the tallest alone. Encoded, not remembered.
  const count = size < 16 ? 1 : size < 20 ? 2 : 3;
  const u = 10;
  const heights = [1.7, 2.3, 2.9].slice(3 - count).map((k) => k * u);
  const gap = 0.3 * u;
  const width = count * u + (count - 1) * gap;
  const base = 2.9 * u;
  const tallest = heights[heights.length - 1];
  const shown = fills.slice(3 - count);

  return (
    <svg
      // Height drives; width follows the aspect ratio. Never set both.
      height={size}
      viewBox={`0 ${base - tallest} ${width} ${tallest}`}
      width={(size * width) / tallest}
      className={className}
      role="img"
      aria-label="Sable"
    >
      {heights.map((h, i) => (
        <path key={i} d={path(i * (u + gap), u, h, base)} fill={shown[i]} />
      ))}
    </svg>
  );
}

/** The full lockup: mark + Garamond wordmark + tracked descriptor. */
export function Wordmark({
  size = 20,
  tone = "paper",
  descriptor,
}: {
  size?: number;
  tone?: Tone;
  descriptor?: string;
}) {
  const onNavy = tone === "navy";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: size * 0.55 }}>
      <Plume size={size} tone={tone} />
      <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {/* The wordmark ALWAYS stays Garamond, and never sets below 14px. */}
        <span
          className="display"
          style={{
            fontSize: Math.max(14, size * 1.05),
            lineHeight: 1,
            fontWeight: 400,
            letterSpacing: "0.04em",
            color: onNavy ? "#FFFFFF" : "var(--navy)",
          }}
        >
          Sable
        </span>
        {descriptor ? (
          <span
            className="label"
            style={{ fontSize: 7.5, color: onNavy ? "rgba(255,255,255,0.6)" : undefined }}
          >
            {descriptor}
          </span>
        ) : null}
      </span>
    </span>
  );
}
