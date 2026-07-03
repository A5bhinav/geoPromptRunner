/**
 * Teaser freshness — a teaser's claims are a snapshot of what AI engines said on
 * the audit date, and engine answers drift. A teaser sent months later can quote
 * a loss that no longer holds, which is both wrong and a credibility risk. So a
 * teaser has a shelf life measured from its audit's run_date (BUILD_PLAN §5:
 * expiry + re-run cadence).
 *
 * Split so the pure, clock-free parts (validThrough, daysBetween) can render in
 * the template and be unit-tested, while staleness (which needs "now") is
 * computed by callers that have a clock (the CLIs) and passed into the renderer.
 */

/** How long a teaser is considered current, in days, from its audit run_date. */
export const SHELF_LIFE_DAYS = 30;

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** Parse a "YYYY-MM-DD" (or ISO) date to UTC midnight; null if unparseable. */
function parseDate(dateStr: string): Date | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Whole days from `from` to `to` (negative if `to` precedes `from`). */
export function daysBetween(from: string, to: Date): number {
  const start = parseDate(from);
  if (!start) return 0;
  return Math.floor((to.getTime() - start.getTime()) / MS_PER_DAY);
}

/**
 * The date a teaser built on `runDate` stops being current ("YYYY-MM-DD").
 * Pure — no clock — so the printed one-pager can always show "valid through".
 * Returns "" when runDate is unparseable (the caller then omits the line).
 */
export function validThrough(runDate: string): string {
  const start = parseDate(runDate);
  if (!start) return "";
  const end = new Date(start.getTime() + SHELF_LIFE_DAYS * MS_PER_DAY);
  return end.toISOString().slice(0, 10);
}

/** True when a teaser built on `runDate` is past its shelf life as of `now`. */
export function isStale(runDate: string, now: Date): boolean {
  const start = parseDate(runDate);
  if (!start) return false; // unknown age → don't block; the missing date is visible
  return daysBetween(runDate, now) > SHELF_LIFE_DAYS;
}
