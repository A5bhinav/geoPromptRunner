import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Page furniture: the content well, the header block, and the panel.
 *
 * These exist because the redesign's screens agree on their skeleton — 28px/32px
 * of Paper, an eyebrow above a 34px title, one hero action right — and disagree
 * only in the middle. Before this, each page re-declared its own padding and its
 * own h1 size, and they had already drifted by 2px.
 */

/** The content well. 28px top / 32px sides is the spec on every screen.
 *
 * The 1200px cap is not arbitrary: the design is drawn at 1440 with a 240px
 * rail, so 1200 IS the drawn content width. Left-aligned rather than centred —
 * on a 2560px monitor a centred well leaves the rail floating alone at the far
 * left, which looks like a rendering bug. */
export function Page({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex max-w-[1200px] flex-col gap-5 px-8 pb-8 pt-7", className)}>
      {children}
    </div>
  );
}

/** Eyebrow · title · optional domain link and helper line, with the page's one
 * hero action pinned right. */
export function PageHeader({
  eyebrow,
  title,
  href,
  hrefLabel,
  helper,
  actions,
}: {
  eyebrow: string;
  title: React.ReactNode;
  href?: string;
  hrefLabel?: string;
  helper?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-8">
      <div className="min-w-0">
        <p className="label mb-1.5">{eyebrow}</p>
        <h1 className="page-title">{title}</h1>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-block text-[13px] text-blue hover:underline"
          >
            {hrefLabel ?? href}
          </a>
        ) : null}
        {helper ? (
          // --ink-secondary, not Harbour: this sits on the PAPER ground, where
          // Harbour measures 4.14:1 and fails AA. Harbour is safe on a card only.
          <p className="mt-2 max-w-[660px] text-[13px] leading-relaxed text-[color:var(--ink-secondary)]">
            {helper}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2.5">{actions}</div> : null}
    </div>
  );
}

/** A white card: 1px navy-at-12%, radius 14, NO shadow. The guide draws its
 * cards with a rule, and a shadow under a navy rule reads muddy. */
export function Panel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-[var(--rule)] bg-white", className)}
      {...props}
    >
      {children}
    </div>
  );
}

/**
 * A panel split into cells by internal hairlines.
 *
 * The report's four panels are grids divided by rules — NOT a grid of separate
 * cards. The distinction is the whole look: separate cards give you four objects
 * with four shadows of white space between them; one panel with hairlines gives
 * you one object with four readings, which is what a deliverable page wants.
 */
export function PanelGrid({
  cols,
  className,
  children,
}: {
  cols: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Panel className={cn("grid", className)} style={{ gridTemplateColumns: cols }}>
      {children}
    </Panel>
  );
}

/** One cell of a PanelGrid. The left rule is drawn by every cell but the first,
 * so cells can be added or dropped without re-deciding who owns the divider. */
export function PanelCell({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "min-w-0 border-l border-[var(--rule-inner)] px-6 py-[22px] first:border-l-0",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** The 10px tracked-uppercase label that opens a card, with an optional quiet
 * right-hand note ("25 questions", "14 total"). */
export function CardLabel({
  children,
  note,
  className,
}: {
  children: React.ReactNode;
  note?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4", className)}>
      <span className="section-label">{children}</span>
      {note ? <span className="text-[12px] text-harbour">{note}</span> : null}
    </div>
  );
}

/**
 * The three-or-four number strip under a page title: one white card, equal
 * cells, hairline splits.
 *
 * One card and not three: three cards would give three objects of equal weight
 * to a reading that is one sentence — "25 questions across 6 surfaces is 450
 * calls". The hairlines say the numbers belong to each other.
 */
export function StatStrip({
  stats,
  className,
}: {
  stats: { label: string; value: React.ReactNode; note?: string }[];
  className?: string;
}) {
  return (
    <Panel className={cn("flex py-[18px]", className)}>
      {stats.map((s) => (
        <div
          key={s.label}
          className="min-w-0 flex-1 border-r border-[var(--rule-inner)] px-6 last:border-r-0"
        >
          <p className="section-label mb-1">{s.label}</p>
          <p className="text-[40px] font-semibold leading-[0.95] tracking-[-0.02em] tabular-nums">
            {s.value}
          </p>
          {s.note ? <p className="mt-1.5 text-[11px] text-harbour">{s.note}</p> : null}
        </div>
      ))}
    </Panel>
  );
}

/** A pill chip. `tone="selected"` is the filled navy state (a chosen quick
 * reply, an applied filter); `tone="soft"` is the 6%-navy resting state the
 * settings rail uses for a surface that is switched on. */
export function Chip({
  tone = "outline",
  className,
  children,
  ...props
}: {
  tone?: "outline" | "soft" | "selected" | "dashed";
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const isButton = typeof props.onClick === "function";
  const cls = cn(
    "inline-flex items-center gap-[7px] rounded-full px-2.5 py-[3px] text-[11.5px] transition-colors",
    tone === "outline" && "border border-[var(--rule)] text-harbour",
    tone === "soft" && "bg-navy/[0.06] text-navy",
    tone === "selected" && "border border-navy bg-navy text-white",
    tone === "dashed" && "border border-dashed border-navy/25 text-harbour hover:text-navy",
    className,
  );
  return isButton ? (
    <button type="button" className={cls} {...props}>
      {children}
    </button>
  ) : (
    <span className={cls}>{children}</span>
  );
}
