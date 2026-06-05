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

export function SeverityBadge({ severity }: { severity: string }) {
  const variant =
    severity === "high" ? "destructive" : severity === "med" ? "warning" : "secondary";
  return (
    <Badge variant={variant} className="uppercase">
      {severity}
    </Badge>
  );
}

export function StateBadge({ state }: { state: string }) {
  const map: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
    done: "success",
    running: "default",
    queued: "secondary",
    cancelled: "warning",
    failed: "destructive",
  };
  return (
    <Badge variant={map[state] ?? "secondary"} className="capitalize">
      {state}
    </Badge>
  );
}
