import * as React from "react";
import { AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The app has no alert hue — Sable's palette is entirely cool and "no colours
 * outside the palette" is an explicit brand Don't. So a notice is distinguished
 * by a 3px navy-family LEFT RULE, an ICON, and a plain sentence. The icon and
 * the rule weight are load-bearing, not decoration: with a single-hue system,
 * colour genuinely cannot carry the distinction. Same reasoning as the report's
 * severity ramp (see components/badges.tsx).
 */
const TONE = {
  problem: { rule: "border-l-navy", Icon: AlertTriangle, ink: "text-navy" },
  info: { rule: "border-l-harbour", Icon: Info, ink: "text-navy" },
  done: { rule: "border-l-blue", Icon: CheckCircle2, ink: "text-navy" },
} as const;

export function Notice({
  tone = "problem",
  title,
  children,
  className,
}: {
  tone?: keyof typeof TONE;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const { rule, Icon, ink } = TONE[tone];
  return (
    <div
      role={tone === "problem" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-md border border-[var(--rule)] border-l-[3px] bg-white p-3.5 text-[13px]",
        rule,
        ink,
        className,
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="space-y-1">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className="text-harbour">{children}</div> : null}
      </div>
    </div>
  );
}
