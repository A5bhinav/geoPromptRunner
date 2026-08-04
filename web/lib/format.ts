/**
 * The one formatter that owns "how much did this move" — the TS mirror of
 * `src/pipeline/fmt.py`. Keep the two in step: the same delta must read the
 * same in the PDF, the digest and the screen.
 *
 * **Percentage points, never percent change.** A change in a *rate* is stated
 * in percentage points: 42% → 48% is `+6.0 pp`, not `+14%`. Percent change is
 * reserved for changes in a *count*: 120 → 150 citations is `+25%`.
 *
 * No component assembles a delta string by hand (spec TR-T2). `pct()` in
 * ./utils formats a LEVEL; it must never be used on a difference of two rates.
 */

/** What a delta is measured in. Naming it is the point — the wrong unit is the
 * failure this module exists to prevent. */
export type DeltaUnit = "rate" | "count";

/** A first cycle. Not "0.0 pp": nothing was measured before, which is a
 * different statement from "it did not move". */
export const NO_PRIOR = "Baseline — no prior cycle";

/** A move that rounds to zero at this precision. "Flat" is a claim in words,
 * not a signed zero the reader has to interpret. */
export const NO_CHANGE = "no change";

const PP_EPSILON = 0.05;

/** Render an already-computed percentage-point delta (e.g. `MovementRow.delta_pp`,
 * which the significance gate produced — recomputing it from rounded rates here
 * would let a tile and its section disagree in the last decimal). */
export function fmtPp(deltaPp: number | null | undefined): string {
  if (deltaPp === null || deltaPp === undefined) return NO_PRIOR;
  if (Math.abs(deltaPp) < PP_EPSILON) return NO_CHANGE;
  return `${deltaPp > 0 ? "+" : "−"}${Math.abs(deltaPp).toFixed(1)} pp`;
}

/** Two rates in [0, 1] → a percentage-point delta. */
export function fmtRateDelta(
  before: number | null | undefined,
  after: number | null | undefined,
): string {
  if (before === null || before === undefined) return NO_PRIOR;
  if (after === null || after === undefined) return NO_PRIOR;
  return fmtPp((after - before) * 100);
}

/** Two counts → a percent change. A zero base has no percent change, so it
 * renders "new" when something appeared and "no change" when nothing did. */
export function fmtCountDelta(
  before: number | null | undefined,
  after: number | null | undefined,
): string {
  if (before === null || before === undefined) return NO_PRIOR;
  if (after === null || after === undefined) return NO_PRIOR;
  if (before === 0) return after > 0 ? "new" : NO_CHANGE;
  const change = ((after - before) / before) * 100;
  if (Math.abs(change) < 0.5) return NO_CHANGE;
  return `${change > 0 ? "+" : "−"}${Math.abs(change).toFixed(0)}%`;
}

/** The single entry point. `"rate"` → pp; `"count"` → percent. */
export function fmtDelta(
  before: number | null | undefined,
  after: number | null | undefined,
  unit: DeltaUnit,
): string {
  return unit === "rate" ? fmtRateDelta(before, after) : fmtCountDelta(before, after);
}
