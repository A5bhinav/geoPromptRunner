"use client";

import * as React from "react";
import { Check, CircleAlert, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { Panel } from "@/components/page";
import { TierMeter } from "@/components/marks";
import { cn } from "@/lib/utils";
import type { IntakeReview } from "@/lib/api";

/**
 * The approve gate — the last human check before a sheet becomes the reference
 * every accuracy finding is measured against.
 *
 * THE RULE THIS SCREEN EXISTS TO ENFORCE. `verification_tier` is a MINIMUM, so
 * ONE unconfirmed claim caps the entire sheet at low/medium and hides every
 * serious finding. At approval each claim is either client-confirmed or it is
 * dropped; there is no third option. When something is unconfirmed the meter
 * says so in plain words, names the count, offers the way out — and Approve is
 * disabled WITH THE REASON STATED. A disabled button with no explanation is the
 * failure mode this screen is built to avoid.
 */

const SECTION_TITLES: Record<string, string> = {
  identity: "A · Identity",
  contact: "B · Contact",
  hours: "C · Hours",
  service_area: "D · Service area",
  licensing: "E · Licensing",
  services_pricing: "F · Services & pricing",
  presence: "G · Presence",
  features: "H · Features",
  positioning: "I · Positioning",
  watchlist: "J · Known bad answers",
};

/** Client-facing surface names. Never a raw engine key. */
const ENGINE_LABELS: Record<string, string> = {
  openai: "ChatGPT",
  openai_search: "ChatGPT (web search)",
  anthropic: "Claude",
  anthropic_search: "Claude (web search)",
  gemini: "Gemini",
  gemini_grounded: "Gemini (grounded)",
  perplexity: "Perplexity",
  google_ai_overviews: "Google AI Overviews",
  google_ai_mode: "Google AI Mode",
  mock: "Mock",
};

const INTENT_TONE: Record<string, string> = {
  problem_aware: "#B2B7BC",
  category: "#697585",
  comparison: "#12325C",
  brand: "#0E2340",
  local_intent: "#0E2340",
  hybrid: "#12325C",
  informational: "#697585",
  adjacent_authority: "#B2B7BC",
};

function prettyIntent(intent: string): string {
  return intent.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function downloadCsv(csv: string, domain: string): void {
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${domain.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-questions.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReviewStage({
  review,
  domain,
  approving,
  error,
  onApprove,
  onBackToConversation,
  onFixUnconfirmed,
}: {
  review: IntakeReview;
  domain: string;
  approving: boolean;
  error: string | null;
  onApprove: () => void;
  onBackToConversation: () => void;
  onFixUnconfirmed: () => void;
}) {
  const [showAllClaims, setShowAllClaims] = React.useState(false);
  const [showAllQueries, setShowAllQueries] = React.useState(false);

  const grouped = React.useMemo(() => {
    const out = new Map<string, IntakeReview["claims"]>();
    for (const c of review.claims) {
      const list = out.get(c.section) ?? [];
      list.push(c);
      out.set(c.section, list);
    }
    return [...out.entries()];
  }, [review.claims]);

  const shownClaims = showAllClaims ? review.claims.length : 7;
  const queries = showAllQueries ? review.query_set : review.query_set.slice(0, 5);
  const shape = review.run_shape;
  const blocks = review.lint.filter((i) => i.level === "block");
  const warns = review.lint.filter((i) => i.level === "warn");
  const confirmed = review.unconfirmed.length === 0 && review.claims.length > 0;

  let rendered = 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-auto px-8 pb-8">
        <div className="grid grid-cols-1 items-start gap-[18px] lg:grid-cols-2">
          {/* ------------------------------------------------------ the sheet */}
          <Panel className="overflow-hidden">
            <div className="flex items-baseline justify-between px-[18px] py-4">
              <span className="section-label">The sheet</span>
              <span className="text-[12px] text-harbour">
                {review.claims.length} claim{review.claims.length === 1 ? "" : "s"} · all from you
              </span>
            </div>

            {review.claims.length === 0 ? (
              <p className="border-t border-[var(--rule-inner)] px-[18px] py-6 text-[13px] text-harbour">
                Nothing has been confirmed yet. Go back to the conversation and answer at least one
                question — an empty sheet cannot flag anything.
              </p>
            ) : null}

            {grouped.map(([section, claims]) => {
              if (rendered >= shownClaims) return null;
              return (
                <div key={section}>
                  <div className="flex items-center gap-3 border-t border-[var(--rule-inner)] bg-[color:var(--band)] px-[18px] py-3">
                    <span className="section-label">
                      {SECTION_TITLES[section] ?? section}
                    </span>
                    <span className="ml-auto text-[11.5px] tabular-nums text-harbour">
                      {claims.length}
                    </span>
                  </div>
                  {claims.map((claim) => {
                    if (rendered >= shownClaims) return null;
                    rendered += 1;
                    return (
                      <div
                        key={claim.claim_id}
                        className="border-t border-[var(--rule-inner)] px-[18px] py-3.5"
                      >
                        {/* The assertion, exactly as the judge will read it. */}
                        <p className="text-[14px] font-medium leading-snug">{claim.value}</p>
                        {/* The owner's own words. Not the same string as the
                            assertion — the quote is the evidence FOR it, and
                            collapsing the two makes the provenance decorative. */}
                        <p className="mt-2 border-l-2 border-[var(--rule)] pl-3 text-[12px] italic leading-relaxed text-harbour">
                          “{claim.quote}”
                        </p>
                        <p className="mt-2 text-[11px] text-harbour">
                          {claim.claim_id} · you confirmed this · {claim.as_of}
                        </p>
                      </div>
                    );
                  })}
                </div>
              );
            })}

            {review.claims.length > shownClaims ? (
              <div className="flex items-center border-t border-[var(--rule)] bg-[color:var(--band-soft)] px-[18px] py-3 text-[12px] text-harbour">
                <span>
                  {shownClaims} of {review.claims.length} shown
                </span>
                <button
                  type="button"
                  onClick={() => setShowAllClaims(true)}
                  className="ml-auto text-blue hover:underline"
                >
                  See all
                </button>
              </div>
            ) : null}
          </Panel>

          {/* -------------------------------------------------- the questions */}
          <div className="flex flex-col gap-[18px]">
            <Panel className="overflow-hidden">
              <div className="px-[18px] pb-3.5 pt-4">
                <div className="flex items-baseline justify-between">
                  <span className="section-label">The questions</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadCsv(review.csv, domain)}
                    disabled={!review.csv}
                  >
                    Download CSV
                  </Button>
                </div>
                {/* The run shape in one plain sentence, before the table.
                    EVERY NUMBER COMES FROM THE GENERATED CSV. This line used to
                    read "4 assistants · 3 runs each" as literal text, which was
                    already wrong — the assembler emits five surfaces — and would
                    have gone on being wrong for every run whose config differed.
                    The cost is priced per engine, because a search surface can
                    cost 27x a parametric one. */}
                <p className="mt-2.5 text-[13px] tabular-nums">
                  {shape.questions} question{shape.questions === 1 ? "" : "s"} ·{" "}
                  {shape.surfaces} assistant{shape.surfaces === 1 ? "" : "s"} ·{" "}
                  {shape.runs_per_query} run{shape.runs_per_query === 1 ? "" : "s"} each ·{" "}
                  {shape.calls} calls · about ${shape.estimated_usd.toFixed(2)}
                </p>
                {shape.engines.length > 0 ? (
                  <p className="mt-1 text-[11px] text-harbour">
                    {shape.engines.map((e) => ENGINE_LABELS[e] ?? e).join(", ")}
                  </p>
                ) : null}
              </div>

              <table className="w-full">
                <tbody>
                  {queries.length === 0 ? (
                    <tr className="border-t border-[var(--rule-inner)]">
                      <td className="px-[18px] py-4 text-[13px] text-harbour">
                        No questions were generated. The checks below say why.
                      </td>
                    </tr>
                  ) : (
                    queries.map((q) => (
                      <tr key={q.query_id} className="border-t border-[var(--rule-inner)]">
                        <td className="w-[132px] py-2.5 pl-[18px] pr-3 align-top">
                          <span className="inline-flex items-center gap-[7px] text-[11.5px] text-harbour">
                            <span
                              aria-hidden
                              className="h-[7px] w-[7px] rounded-sm"
                              style={{ background: INTENT_TONE[q.intent] ?? "#B2B7BC" }}
                            />
                            {prettyIntent(q.intent)}
                          </span>
                        </td>
                        <td className="w-[68px] py-2.5 pr-3 align-top text-[11.5px] tabular-nums text-harbour">
                          {q.query_id}
                        </td>
                        {/* The widest column, at 14px: the question is the
                            content and the id is a join key. */}
                        <td className="py-2.5 pr-[18px] align-top text-[14px] leading-snug">
                          {q.text}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              {review.query_set.length > queries.length ? (
                <div className="flex items-center border-t border-[var(--rule)] bg-[color:var(--band-soft)] px-[18px] py-3 text-[12px] text-harbour">
                  <span>
                    {queries.length} of {review.query_set.length}
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowAllQueries(true)}
                    className="ml-auto text-blue hover:underline"
                  >
                    See all
                  </button>
                </div>
              ) : null}
            </Panel>

            <Panel className="flex flex-col gap-2.5 px-[18px] py-4">
              <span className="section-label">Checks</span>
              {blocks.length === 0 && warns.length === 0 ? (
                <span className="flex items-start gap-2.5 text-[13px] text-harbour">
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  Every check passed.
                </span>
              ) : null}
              {warns.map((item) => (
                <span
                  key={item.code + item.message}
                  className="flex items-start gap-2.5 text-[13px] text-harbour"
                >
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  {item.message}
                </span>
              ))}
              {/* A block names the FIX, never just the rule. */}
              {blocks.map((item) => (
                <span
                  key={item.code + item.message}
                  className="flex items-start gap-2.5 border-l-[3px] border-navy py-1.5 pl-3 text-[13px]"
                >
                  <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                  {item.message}
                </span>
              ))}
            </Panel>

            {error ? <Notice tone="problem">{error}</Notice> : null}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------- approve bar */}
      <div className="flex flex-wrap items-center gap-6 border-t border-[var(--rule)] px-8 pb-[22px] pt-4">
        <span className="flex items-center gap-3">
          <TierMeter confirmed={confirmed} size="lg" />
          <span className="max-w-[520px] text-[13.5px] font-medium">
            {confirmed ? (
              <>
                All {review.claims.length} facts confirmed by you — this sheet can flag anything, at
                any severity.
              </>
            ) : (
              <>
                {review.unconfirmed.length} fact
                {review.unconfirmed.length === 1 ? "" : "s"} nobody has confirmed. Until they&rsquo;re
                handled, this sheet can only flag low and medium issues — the serious ones stay
                hidden.
              </>
            )}
          </span>
        </span>

        <span className="ml-auto flex items-center gap-[18px]">
          {!confirmed ? (
            <Button variant="outline" onClick={onFixUnconfirmed}>
              Review the {review.unconfirmed.length}
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onBackToConversation}>
            Back to the conversation
          </Button>
          <span className="max-w-[340px] text-[12px] leading-snug text-[color:var(--ink-secondary)]">
            {/* Stated before the button, not after. Approving re-keys every
                cached verdict for this client — free to re-warm, but not
                invisible. */}
            This replaces the current sheet. Past reports keep the version they were run against;
            your next run uses this one.
          </span>
          <Button
            variant="hero"
            size="lg"
            onClick={onApprove}
            disabled={!review.can_approve || approving}
            // The reason lives on the button itself, so a disabled control is
            // never a dead end.
            title={
              review.can_approve
                ? undefined
                : !confirmed
                  ? `${review.unconfirmed.length} claim(s) are not confirmed yet`
                  : "the question set has not passed its checks"
            }
          >
            {approving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
            Approve &amp; activate
          </Button>
        </span>

        {!review.can_approve ? (
          <p className={cn("w-full text-[12px] text-[color:var(--ink-secondary)]")}>
            {!confirmed
              ? `Approve is off until every claim is confirmed or dropped: ${review.unconfirmed
                  .slice(0, 6)
                  .join(", ")}${review.unconfirmed.length > 6 ? "…" : ""}`
              : "Approve is off until the question set passes the blocked checks above."}
          </p>
        ) : null}
      </div>
    </div>
  );
}
