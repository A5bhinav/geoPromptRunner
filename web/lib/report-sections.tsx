import * as React from "react";
import {
  BackMatterSection,
  CitationSection,
  CompetitiveSection,
  CoverSection,
  ExecSnapshotSection,
  FindingsSection,
  MethodologySection,
  PriorityActionsSection,
  QuestionTypeSection,
  RepresentativeSection,
  SupportingDetailSection,
  SurfaceSection,
  ThinData,
  TrendSection,
  WhatChangedSection,
  type SectionContext,
} from "@/components/report-contract";

/**
 * THE REPORT IS A LIST. This file is that list.
 *
 * The section order used to live in JSX, which meant changing what the report
 * contains — or moving a section behind a tier — was a component edit. That is
 * the thing the standing rule forbids: structure is code, content is data, and
 * if changing what a client sees requires touching `report-view.tsx` then the
 * abstraction is wrong (spec TR-T11).
 *
 * So: reordering sections is a reordering of this array. Dropping one is a
 * deletion from this array. Moving one behind a paid tier is changing one
 * string. None of those touches a component, and `tests/test_report_packaging.py`
 * asserts the rendered order matches this array.
 *
 * **Every entry must have a `thinDataFallback`.** A section with nothing to say
 * says so; it never renders an empty box. That is not politeness — an empty
 * section reads as a rendering bug, and a client who thinks the tool is broken
 * stops trusting the numbers that did render.
 */

/** `track` ships to everyone today. `track_pro` exists so moving sections 8 and
 * 9 (priority actions, accuracy findings) behind a paid tier later is a one-line
 * change here — and NO tier gating is built beyond reading this field, because
 * speculative gating is how a tier system becomes load-bearing before anyone has
 * bought the tier. */
export type SectionTier = "track" | "track_pro";

export interface ReportSection {
  /** Stable id. Used as the anchor, the React key, and the registry test's
   * subject — never renamed casually, because a client's bookmark points at it. */
  id: string;
  /** What the section is called in the table of contents. The heading itself is
   * the component's, so a section can carry a longer in-page title. */
  title: string;
  tier: SectionTier;
  /** Whether this section appears in the rail's table of contents. The cover and
   * the appendices do not — a TOC that lists its own cover is noise. */
  inToc: boolean;
  render: (ctx: SectionContext) => React.ReactNode;
  /** What renders when `render` has nothing to show. Required, non-null. */
  thinDataFallback: (ctx: SectionContext) => React.ReactNode;
  /** True when the payload has enough to render this section at all. Returning
   * false shows the fallback instead — it does NOT hide the section. */
  hasData: (ctx: SectionContext) => boolean;
}

const notMeasured = (what: string) => (): React.ReactNode => (
  <ThinData>{what}</ThinData>
);

/**
 * The contract, in delivery order. Front matter 0–11, then the appendices.
 *
 * Actions (8) precede findings (9) deliberately — answer-first. The findings are
 * the evidence behind the actions, not a preamble to them.
 */
export const REPORT_SECTIONS: readonly ReportSection[] = [
  {
    id: "cover",
    title: "Cover",
    tier: "track",
    inToc: false,
    render: (ctx) => <CoverSection ctx={ctx} />,
    hasData: () => true,
    thinDataFallback: notMeasured("No run to report on."),
  },
  {
    id: "snapshot",
    title: "Executive snapshot",
    tier: "track",
    inToc: true,
    render: (ctx) => <ExecSnapshotSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.exec_snapshot),
    thinDataFallback: notMeasured(
      "This run was stored before the snapshot existed, so its six measured tiles cannot be rebuilt.",
    ),
  },
  {
    id: "what-changed",
    title: "What changed",
    tier: "track",
    inToc: true,
    render: (ctx) => <WhatChangedSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.what_changed?.available),
    thinDataFallback: (ctx) => (
      <ThinData>
        {ctx.report.comparison_blocked_reason === "query_set_changed"
          ? "The question set changed since the last cycle, so the two are not comparable instruments and no week-over-week figures are shown. Comparison resumes next cycle."
          : "This is the first cycle for this question set, so there is nothing to compare against yet."}
      </ThinData>
    ),
  },
  {
    id: "trend",
    title: "Visibility trend",
    tier: "track",
    inToc: true,
    render: (ctx) => <TrendSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.trend?.points.length),
    thinDataFallback: notMeasured("No comparable cycle has been measured yet."),
  },
  {
    id: "question-types",
    title: "By question type",
    tier: "track",
    inToc: true,
    render: (ctx) => <QuestionTypeSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.question_types?.rows.length),
    thinDataFallback: notMeasured("No question returned an answer this cycle."),
  },
  {
    id: "surfaces",
    title: "By surface",
    tier: "track",
    inToc: true,
    render: (ctx) => <SurfaceSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.surfaces?.rows.length),
    thinDataFallback: notMeasured("No surface returned an answer this cycle."),
  },
  {
    id: "competitive",
    title: "Competitive position",
    tier: "track",
    inToc: true,
    render: (ctx) => <CompetitiveSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.competitive?.rows.length),
    thinDataFallback: notMeasured(
      "No competitor was named for this run, so there is no standing to compare.",
    ),
  },
  {
    id: "citations",
    title: "Citations",
    tier: "track",
    inToc: true,
    render: (ctx) => <CitationSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.citations),
    thinDataFallback: notMeasured(
      "No surface returned a citation this cycle. Several answer from memory and cite nothing at all.",
    ),
  },
  {
    id: "actions",
    title: "Priority actions",
    tier: "track",
    inToc: true,
    render: (ctx) => <PriorityActionsSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.priority_actions?.length),
    thinDataFallback: notMeasured(
      "No finding is open, so there is no action to rank this cycle.",
    ),
  },
  {
    id: "findings",
    title: "Accuracy findings",
    tier: "track",
    inToc: true,
    render: (ctx) => <FindingsSection ctx={ctx} />,
    hasData: () => true, // it renders its own "not assessed" state
    thinDataFallback: notMeasured("Accuracy was not assessed this cycle."),
  },
  {
    id: "representative",
    title: "Representative answers",
    tier: "track",
    inToc: true,
    render: (ctx) => <RepresentativeSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.representative_answers?.slots.length),
    thinDataFallback: notMeasured("No answer was stored for this cycle."),
  },
  {
    id: "supporting",
    title: "Supporting detail",
    tier: "track",
    inToc: true,
    render: (ctx) => <SupportingDetailSection ctx={ctx} />,
    hasData: (ctx) =>
      Boolean(ctx.report.stability?.length) || ctx.report.losing_queries.length > 0,
    thinDataFallback: notMeasured(
      "No cell was repeated and no competitor won a question outright.",
    ),
  },
  {
    id: "methodology",
    title: "Methodology",
    tier: "track",
    inToc: true,
    render: (ctx) => <MethodologySection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.methodology),
    thinDataFallback: notMeasured(
      "This run predates the methodology block, so its measurement window cannot be reconstructed.",
    ),
  },
  {
    id: "appendices",
    title: "Appendices",
    tier: "track",
    inToc: false,
    render: (ctx) => <BackMatterSection ctx={ctx} />,
    hasData: (ctx) => Boolean(ctx.report.back_matter?.appendices.length),
    thinDataFallback: notMeasured("No raw output was stored for this cycle."),
  },
];

/** Sections a given tier may see, in registry order. Today every section is
 * `track`, so this filters nothing — it exists so that when a section moves to
 * `track_pro`, the move is complete rather than half-built. */
export function sectionsForTier(tier: SectionTier): readonly ReportSection[] {
  return tier === "track_pro"
    ? REPORT_SECTIONS
    : REPORT_SECTIONS.filter((s) => s.tier === "track");
}
