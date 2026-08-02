import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const INTENT_LABELS: Record<string, string> = {
  problem_aware: "Problem-aware",
  category: "Category",
  comparison: "Comparison",
  brand: "Brand",
  adjacent_authority: "Adjacent",
};

const INTENT_CLASSES: Record<string, string> = {
  problem_aware: "bg-sky-100 text-sky-700",
  category: "bg-indigo-100 text-indigo-700",
  comparison: "bg-violet-100 text-violet-700",
  brand: "bg-emerald-100 text-emerald-700",
  adjacent_authority: "bg-amber-100 text-amber-700",
};

export function IntentBadge({ intent }: { intent: string }) {
  const label = INTENT_LABELS[intent] ?? intent;
  const klass = INTENT_CLASSES[intent] ?? "bg-secondary text-secondary-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        klass,
      )}
    >
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

export function CheckStatusBadge({ status }: { status: string }) {
  const map: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
    pass: "success",
    partial: "warning",
    fail: "destructive",
    ungradeable: "secondary",
    unknown: "secondary",
  };
  return (
    <Badge variant={map[status] ?? "secondary"} className="capitalize">
      {status}
    </Badge>
  );
}

export function ImpactBadge({ impact }: { impact: string }) {
  const variant = impact === "High" ? "destructive" : impact === "Medium" ? "warning" : "secondary";
  return (
    <Badge variant={variant} className="capitalize">
      {impact}
    </Badge>
  );
}

export function StateBadge({ state }: { state: string }) {
  const map: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
    done: "success",
    running: "default",
    queued: "secondary",
    cancelled: "warning",
    interrupted: "warning",
    failed: "destructive",
  };
  return (
    <Badge variant={map[state] ?? "secondary"} className="capitalize">
      {state}
    </Badge>
  );
}
