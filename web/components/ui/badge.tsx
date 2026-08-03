import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium",
  {
    variants: {
      variant: {
        // Fill = navy family. Outline = categorical. Nothing else exists.
        // There is no success/warning/destructive: Sable has no alert hue, and
        // every state chip carries a glyph or a label as its second channel.
        solid: "bg-navy text-white",
        muted: "bg-navy/[0.06] text-navy",
        outline: "border border-navy/20 text-navy",
        quiet: "border border-[var(--rule)] text-harbour",
      },
    },
    defaultVariants: { variant: "muted" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
