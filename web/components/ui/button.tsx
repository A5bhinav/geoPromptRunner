import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // Pill, per the guide. Sentence case — the tracked-uppercase treatment the
  // guide shows on its Primary/Secondary chips is reserved for the ONE hero
  // action per page (`variant="hero"`); applying it to "Add file" and "Cancel"
  // makes a dense tool unreadable and is the one sanctioned deviation.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "bg-navy text-white hover:bg-blue",
        outline: "border border-navy/25 bg-transparent text-navy hover:bg-navy/[0.04]",
        ghost: "text-harbour hover:bg-navy/[0.04] hover:text-navy",
        // The one action a page exists for. Tracked uppercase, per the guide.
        hero: "bg-navy px-6 text-[11px] uppercase tracking-[0.14em] text-white hover:bg-blue",
        // No `destructive`. Sable has no alert hue. Destructive actions use
        // `outline` and are gated by a typed confirmation, which is the safety
        // mechanism that actually works.
      },
      size: {
        default: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };
