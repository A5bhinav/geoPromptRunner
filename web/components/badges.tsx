import {
  AlertTriangle,
  Circle,
  CheckCircle2,
  Loader2,
  MinusCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const INTENT_LABELS: Record<string, string> = {
  problem_aware: "Problem-aware",
  category: "Category",
  comparison: "Comparison",
  brand: "Brand",
  adjacent_authority: "Adjacent",
};

/** Funnel order, cold → warm. The tone ramp is legal here (and only here)
 * because this axis is ORDINAL: a prospect moves problem-aware → category →
 * comparison → brand. `adjacent_authority` sits off the funnel and gets a
 * hollow dot rather than a rung on the ramp.
 *
 * This replaced five hues (sky, indigo, violet, emerald, amber) — the single
 * largest brand violation in the tree. */
const INTENT_TONE: Record<string, string> = {
  problem_aware: "var(--mist)",
  category: "var(--harbour)",
  comparison: "var(--blue)",
  brand: "var(--navy)",
};

export function IntentBadge({ intent }: { intent: string }) {
  const label = INTENT_LABELS[intent] ?? intent;
  const tone = INTENT_TONE[intent];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--rule)] px-2.5 py-0.5 text-[11px] font-medium text-navy">
      <span
        aria-hidden
        className="h-1.5 w-1.5 rounded-full"
        style={
          tone
            ? { backgroundColor: tone }
            : { border: "1px solid var(--harbour)" } /* off-funnel: hollow */
        }
      />
      {label}
    </span>
  );
}

/** The four severity tiers, in the only legal display order.
 *
 * Colour is a MONOCHROME NAVY RAMP, darkest = most severe. Sable has no red and
 * no gold — the palette is entirely cool and has no alert hue at all, and "no
 * colours outside the palette" is an explicit brand Don't. The ramp mirrors the
 * mark's own logic: the plumes step tone with height so the eye lands on the
 * tallest, darkest form.
 *
 * The icon and the label are therefore LOAD-BEARING, not belt-and-braces: with a
 * single-hue ramp colour genuinely cannot carry the distinction, and this also
 * fixes colourblind rendering and grayscale printing. Never remove either.
 *
 * Sentence case. The only uppercase in the system is the tracked label. */
export const SEVERITY_ORDER = ["critical", "high", "med", "low"] as const;

export const SEVERITY_LABELS: Record<string, string> = {
  critical: "Critical",
  high: "High",
  med: "Medium",
  low: "Low",
};

/** Distinct SHAPES, not just distinct fills — the redundant channel. */
function SeverityIcon({ severity }: { severity: string }) {
  const common = { width: 10, height: 10, "aria-hidden": true } as const;
  if (severity === "critical") {
    return (
      <svg {...common} viewBox="0 0 10 10">
        <polygon points="5,0 10,10 0,10" fill="currentColor" />
      </svg>
    );
  }
  if (severity === "high") {
    return (
      <svg {...common} viewBox="0 0 10 10">
        <circle cx="5" cy="5" r="5" fill="currentColor" />
      </svg>
    );
  }
  if (severity === "med") {
    return (
      <svg {...common} viewBox="0 0 10 10">
        <rect width="10" height="10" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg {...common} viewBox="0 0 10 10">
      <circle cx="5" cy="5" r="2.5" fill="currentColor" />
    </svg>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  const label = SEVERITY_LABELS[severity] ?? severity;
  return (
    <span className="sev-chip" data-severity={severity}>
      <SeverityIcon severity={severity} />
      {label}
    </span>
  );
}

/** "3 Critical · 12 High · 40 Medium · 180 Low", rendered BEFORE any individual
 * finding. Most readers stop here; that is the design intent, not a failure.
 * Counts are THEMES — one counting unit per client-facing view. */
export function SeveritySummaryBar({ counts }: { counts: Record<string, number> }) {
  const present = SEVERITY_ORDER.filter((s) => (counts[s] ?? 0) > 0);
  const total = present.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
  if (total === 0) {
    return (
      <p className="body text-sm">
        No findings are open — the models described this brand accurately.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <div className="sev-bar" role="img" aria-label={`${total} findings by severity`}>
        {present.map((s) => (
          <div
            key={s}
            style={{
              flexGrow: counts[s],
              backgroundColor: `var(--sev-${s === "med" ? "medium" : s})`,
            }}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {present.map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5 text-sm">
            <SeverityBadge severity={s} />
            <span className="tabular-nums font-medium">{counts[s]}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Site-audit check status, mapped onto the report's monochrome ramp rather than
 * onto new tokens. Weight carries severity (solid = worst); the glyph carries
 * the distinction, because with a single-hue ramp colour cannot. */
const CHECK_STATUS: Record<
  string,
  { variant: "solid" | "muted" | "outline" | "quiet"; Icon?: LucideIcon; glyph?: string }
> = {
  pass: { variant: "quiet", Icon: CheckCircle2 },
  partial: { variant: "muted", Icon: MinusCircle },
  fail: { variant: "solid", Icon: XCircle },
  // Not assessable is not a failure — it gets the em-dash, never a severity fill.
  ungradeable: { variant: "quiet", glyph: "—" },
  unknown: { variant: "quiet", glyph: "—" },
};

export function CheckStatusBadge({ status }: { status: string }) {
  const spec = CHECK_STATUS[status] ?? CHECK_STATUS.unknown;
  const { variant, Icon, glyph } = spec;
  return (
    <Badge variant={variant} className="capitalize">
      {Icon ? <Icon className="h-3 w-3 shrink-0" aria-hidden /> : null}
      {glyph ? (
        <span aria-hidden className="leading-none">
          {glyph}
        </span>
      ) : null}
      {status}
    </Badge>
  );
}

export function ImpactBadge({ impact }: { impact: string }) {
  const variant = impact === "High" ? "solid" : impact === "Medium" ? "muted" : "quiet";
  return (
    <Badge variant={variant} className="capitalize">
      {impact}
    </Badge>
  );
}

/** Run states. Distinguished by FILL WEIGHT + GLYPH, never hue.
 *
 * `done` and `failed` sharing a fill is deliberate: both are *finished*, which
 * is the property a scanner is actually filtering on, and the glyph splits them
 * instantly. If that proves unreadable in a 40-row list, the fix is a column
 * (sort/group by state), not a colour. */
const STATE: Record<
  string,
  { variant: "solid" | "muted" | "outline" | "quiet"; Icon: LucideIcon; spin?: boolean }
> = {
  done: { variant: "solid", Icon: CheckCircle2 },
  failed: { variant: "solid", Icon: XCircle },
  running: { variant: "muted", Icon: Loader2, spin: true },
  queued: { variant: "quiet", Icon: Circle },
  cancelled: { variant: "quiet", Icon: MinusCircle },
  // The only chip carrying the warning glyph — and it is TERMINAL and
  // unrecoverable ("we found this row non-terminal at startup and could not
  // rebuild it"), not paused.
  interrupted: { variant: "muted", Icon: AlertTriangle },
};

export function StateBadge({ state }: { state: string }) {
  const spec = STATE[state];
  if (!spec) {
    return (
      <Badge variant="quiet" className="capitalize">
        {state}
      </Badge>
    );
  }
  const { variant, Icon, spin } = spec;
  return (
    <Badge
      variant={variant}
      className={cn("capitalize", state === "interrupted" && "bg-mist text-navy")}
    >
      <Icon className={cn("h-3 w-3 shrink-0", spin && "animate-spin")} aria-hidden />
      {state}
    </Badge>
  );
}
