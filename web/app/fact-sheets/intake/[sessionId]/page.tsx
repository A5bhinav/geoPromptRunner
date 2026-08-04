"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Check, Loader2, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { SidebarLabel, SidebarSlot } from "@/components/app-shell";
import { PlumeRail, ThinkingPlumes, TierMeter } from "@/components/marks";
import { Constellation } from "@/components/intake/constellation";
import { ReviewStage } from "@/components/intake/review-stage";
import {
  StructuredAnswer,
  emptyValue,
  hasContent,
  isStructuredKind,
  summarize,
  toPayload,
  type StructuredValue,
} from "@/components/intake/structured-answer";
import { cn } from "@/lib/utils";
import { FIELD_HINT_CLS, FIELD_LABEL_CLS, INPUT_CLS } from "@/lib/ui";
import {
  answerIntake,
  approveIntake,
  completeIntake,
  getIntake,
  previewIntake,
  type IntakeAssertion,
  type IntakeQuestion,
  type IntakeReview,
  type IntakeSession,
} from "@/lib/api";

/**
 * Fact-sheet intake → review, as ONE flow.
 *
 * Not two routes. The conversation and the approve gate are one continuous act:
 * the owner answers questions, then looks at what they said and signs it. A
 * navigation between those two moments costs the context of everything they
 * just typed, and the second half stops feeling like a consequence of the
 * first. So the stage is state, the shell and the header persist across it, and
 * "Back to the conversation" genuinely goes back rather than re-entering.
 *
 * The session survives a refresh: it is stored server-side and every answer is
 * a POST, so reopening lands on the last unanswered card with the transcript
 * rebuilt from the stored answers.
 */

/** The reply lands, then the next question follows. Long enough to read as a
 * reply rather than a form submit; short enough that nine of them is not a
 * wait. Both are in `styles/motion.css`'s vocabulary — nothing informational
 * depends on either, so reduced motion just makes them instant. */
const REPLY_MS = 760;
const NEXT_QUESTION_MS = 480;

type Turn =
  | { id: string; role: "sable"; text: string }
  | { id: string; role: "user"; text: string }
  | { id: string; role: "pending" };

type Stage = "conversation" | "review";

/** Prompts carry a `{business}` slot. Substituted at every render site, not
 * just in the aria-label: the chat bubble is what a person actually reads, and
 * a literal "{business}" in it undoes the whole conversational conceit. */
function fill(prompt: string, business: string): string {
  return prompt.replace("{business}", business);
}

/** What the composer sends for one card, given what the owner typed and tapped.
 *
 * Kind-aware because the API stores a shape the assertion builder can read: a
 * list card sends an array, a choice sends the option value, everything else
 * sends the text. */
function buildValue(
  q: IntakeQuestion,
  typed: string,
  picked: string[],
  fields: Record<string, string>,
  structured: StructuredValue,
): unknown {
  // A composite card carries its whole answer in the structured control — the
  // registry describes its shape, and `toPayload` writes exactly what the
  // server's assertion builders read.
  if (isStructuredKind(q)) return toPayload(q, structured);
  switch (q.kind) {
    case "batch_confirm":
    case "links":
      // Only the fields that were actually filled. A key the owner left alone
      // is ABSENT, not empty: a fact nobody looked at is not a fact anybody
      // confirmed, and an empty string would become a claim asserting nothing.
      return Object.fromEntries(
        q.keys.map((k) => [k, (fields[k] ?? "").trim()]).filter(([, v]) => v),
      );
    case "choice":
    case "confirm":
      return picked[0] ?? typed.trim();
    case "multi":
    case "list":
      // Typed text becomes another entry, so "Sunday" and a typed "Wednesday"
      // both land as items rather than one replacing the other.
      return [...picked, ...typed.split(",").map((s) => s.trim()).filter(Boolean)];
    default:
      return typed.trim();
  }
}

/** The composer's own summary of a multi-field card, for the user bubble. */
function fieldsSummary(q: IntakeQuestion, fields: Record<string, string>): string {
  return q.keys
    .map((k) => [q.keyLabels[k] ?? k, (fields[k] ?? "").trim()] as const)
    .filter(([, v]) => v)
    .map(([label, v]) => `${label}: ${v}`)
    .join(" · ");
}

function rawOf(typed: string, picked: string[], labels: Map<string, string>): string {
  const chosen = picked.map((p) => labels.get(p) ?? p);
  if (chosen.length && typed.trim()) return `${chosen.join(", ")} — ${typed.trim()}`;
  return chosen.join(", ") || typed.trim();
}

export default function IntakePage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = decodeURIComponent(params.sessionId);
  const router = useRouter();

  const [session, setSession] = React.useState<IntakeSession | null>(null);
  const [review, setReview] = React.useState<IntakeReview | null>(null);
  const [stage, setStage] = React.useState<Stage>("conversation");
  const [view, setView] = React.useState<"overview" | "details">("overview");
  const [error, setError] = React.useState<string | null>(null);

  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [draft, setDraft] = React.useState("");
  const [picked, setPicked] = React.useState<string[]>([]);
  const [fields, setFields] = React.useState<Record<string, string>>({});
  const [structured, setStructured] = React.useState<StructuredValue>({});
  const [pending, setPending] = React.useState(false);
  const [launcherOpen, setLauncherOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [nudge, setNudge] = React.useState<string[]>([]);
  const [nudgeDismissed, setNudgeDismissed] = React.useState(false);
  const [confirmedFacts, setConfirmedFacts] = React.useState<IntakeAssertion[]>([]);

  const timers = React.useRef<ReturnType<typeof setTimeout>[]>([]);
  const cardRef = React.useRef<HTMLDivElement>(null);
  const later = (fn: () => void, ms: number) => {
    timers.current.push(setTimeout(fn, ms));
  };
  React.useEffect(() => () => timers.current.forEach(clearTimeout), []);

  // --- open or resume --------------------------------------------------------
  React.useEffect(() => {
    let cancelled = false;
    getIntake(sessionId)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        // Rebuild the transcript from stored answers so a refresh loses
        // nothing — the conversation is a view of the session, not the state.
        const answered: Turn[] = [];
        for (const q of s.plan) {
          const a = s.answers[q.id];
          if (!a) continue;
          answered.push({
            id: `q-${q.id}`,
            role: "sable",
            text: fill(q.prompt, s.business_name),
          });
          answered.push({
            id: `u-${q.id}`,
            role: "user",
            text: a.skipped ? "Skip this one" : a.raw || String(a.value ?? ""),
          });
        }
        // The opener only belongs on a session nobody has answered yet — the
        // test is on ANSWERED turns, not on the array that already has the next
        // question appended to it.
        const opening: Turn[] = answered.length
          ? answered
          : [
              {
                id: "intro",
                role: "sable",
                // Only claim a crawl when there was one, and "prefill exists" is
                // NOT that test — the Start screen seeds the name and website
                // into prefill too, so a cold start would otherwise open by
                // claiming credit for reading a site nobody read. A crawled
                // fact is one whose source is a page; a seeded one is marked
                // `client`.
                text:
                  (Object.values(s.prefill).some((p) => p.source_kind !== "client")
                    ? `I pulled what I could off ${s.domain}. `
                    : "") +
                  `${s.plan.length} questions and it's on the record. Skip anything ` +
                  "you're not sure about — a blank is never wrong, a guess can be.",
              },
            ];
        setTurns(
          s.next
            ? [
                ...opening,
                { id: `q-${s.next.id}`, role: "sable", text: fill(s.next.prompt, s.business_name) },
              ]
            : opening,
        );
        if (s.state === "awaiting_review") {
          void completeIntake(s.session_id).then(setReview).then(() => setStage("review"));
        }
      })
      .catch(
        (e) =>
          !cancelled &&
          setError(e instanceof Error ? e.message : "Could not open the intake."),
      );
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const current = session?.next ?? null;

  // Focus the CARD, not the input, on each new question — so a screen reader
  // hears the question before it lands in a text field.
  React.useEffect(() => {
    if (stage === "conversation" && current) cardRef.current?.focus();
    // Seed from prefill: a fact the crawl already found should be a
    // check-and-move-on, not a retype. A card with nothing found renders the
    // same fields empty, which is how the intake works for a domain the
    // crawler has never seen.
    setEditingKnown(false);
    setFields(
      current
        ? Object.fromEntries(
            current.keys.map((k) => [k, current.prefill[k]?.value ?? ""]),
          )
        : {},
    );
    // Composite cards seed the same way — a TEXT part whose key the crawl
    // already found renders filled, so the owner checks rather than retypes.
    setStructured(current ? emptyValue(current) : {});
  }, [current?.id, stage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keys we already have a value for versus the ones still genuinely open.
  const [editingKnown, setEditingKnown] = React.useState(false);
  const knownKeys = React.useMemo(
    () => (current ? current.keys.filter((k) => (fields[k] ?? "").trim()) : []),
    [current, fields],
  );
  const openKeys = React.useMemo(
    () => (current ? current.keys.filter((k) => !(fields[k] ?? "").trim()) : []),
    [current, fields],
  );

  const optionLabels = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const o of current?.options ?? []) map.set(o.value, o.label);
    return map;
  }, [current]);

  const prompt = React.useMemo(
    () => (current ? fill(current.prompt, session?.business_name ?? "") : ""),
    [current, session],
  );

  const send = async (skipped: boolean) => {
    if (!session || !current || pending) return;
    const typed = draft;
    const chosen = picked;
    const filled = fields;
    const composed = structured;
    const isForm = current.kind === "batch_confirm" || current.kind === "links";
    const summary = isStructuredKind(current)
      ? hasContent(current, composed)
        ? summarize(current, composed)
        : ""
      : isForm
        ? fieldsSummary(current, filled)
        : "";
    if (!skipped && !typed.trim() && chosen.length === 0 && !summary) return;

    const userText = skipped
      ? "Skip this one"
      : summary || rawOf(typed, chosen, optionLabels);
    setTurns((t) => [
      ...t,
      { id: `u-${Date.now()}`, role: "user", text: userText },
      { id: `p-${Date.now()}`, role: "pending" },
    ]);
    setDraft("");
    setPicked([]);
    setFields({});
    setStructured({});
    setPending(true);
    setLauncherOpen(false);
    setNudge([]);
    setNudgeDismissed(false);

    try {
      const result = await answerIntake(session.session_id, {
        question_id: current.id,
        value: skipped ? null : buildValue(current, typed, chosen, filled, composed),
        raw: skipped ? "" : userText,
        skipped,
      });
      const fresh = await getIntake(session.session_id);

      later(() => {
        setTurns((t) => t.filter((x) => x.role !== "pending"));
        setPending(false);
        if (result.assertions.length > 0) {
          setConfirmedFacts((f) => [...f, ...result.assertions]);
          setTurns((t) => [
            ...t,
            {
              id: `s-${Date.now()}`,
              role: "sable",
              text: `On the record: “${result.assertions[0].value}”`,
            },
          ]);
        } else {
          setTurns((t) => [
            ...t,
            {
              id: `s-${Date.now()}`,
              role: "sable",
              // Said out loud, because a blank producing nothing is the
              // guarantee that makes skipping safe — not a silent no-op.
              text: "Left blank — nothing gets checked on that one.",
            },
          ]);
        }
        setNudge(result.nudge);
        setSession(fresh);
        if (fresh.next) {
          later(
            () =>
              setTurns((t) => [
                ...t,
                {
                  id: `q-${fresh.next!.id}`,
                  role: "sable",
                  text: fill(fresh.next!.prompt, fresh.business_name),
                },
              ]),
            NEXT_QUESTION_MS,
          );
        } else {
          later(
            () =>
              setTurns((t) => [
                ...t,
                {
                  id: `done-${Date.now()}`,
                  role: "sable",
                  text:
                    "That's everything I need. Hit Review & create when you're ready, or keep " +
                    "adding context.",
                },
              ]),
            NEXT_QUESTION_MS,
          );
        }
      }, REPLY_MS);
    } catch (e) {
      setPending(false);
      setTurns((t) => t.filter((x) => x.role !== "pending"));
      // Never lose a typed answer to a failed request.
      setDraft(typed);
      setPicked(chosen);
      setFields(filled);
      setStructured(composed);
      setError(e instanceof Error ? e.message : "That answer did not save. Try again.");
    }
  };

  const toReview = async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      setReview(await completeIntake(session.session_id));
      setStage("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build the review.");
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const result = await approveIntake(session.session_id);
      router.push(`/fact-sheets?approved=${encodeURIComponent(result.fact_sheet_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed.");
      setBusy(false);
    }
  };

  // --- the live assertion preview -------------------------------------------
  //
  // THE POINT OF THE SCREEN. The owner sees the exact sentence they will be
  // quoted on before the card commits — "No after-hours or emergency service.",
  // not their tap ("No"). It comes from the SERVER, from the same builder that
  // will write the claim, because a client-side copy of the phrasing would drift
  // the first time a card was reworded and the preview would stop being true.
  //
  // Debounced 400ms: it is an aria-live region, and announcing on every
  // keystroke makes it unusable with a screen reader.
  const [previewText, setPreviewText] = React.useState("");
  React.useEffect(() => {
    if (!session || !current) {
      setPreviewText("");
      return;
    }
    const value = buildValue(current, draft, picked, fields, structured);
    const empty = isStructuredKind(current)
      ? !hasContent(current, structured)
      : Array.isArray(value)
        ? value.length === 0
        : !String(value ?? "").trim();
    if (empty) {
      setPreviewText("");
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      previewIntake(session.session_id, {
        question_id: current.id,
        value,
        raw: isStructuredKind(current)
          ? summarize(current, structured)
          : current.kind === "batch_confirm" || current.kind === "links"
            ? fieldsSummary(current, fields)
            : rawOf(draft, picked, optionLabels),
      })
        .then((r) => {
          if (cancelled) return;
          setPreviewText(r.assertions[0]?.value ?? "");
          setNudge(r.nudge);
        })
        // A failed preview shows nothing rather than a guess — the one thing
        // this element must never do is display a sentence we did not build.
        .catch(() => !cancelled && setPreviewText(""));
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [session, current, draft, picked, fields, structured, optionLabels]);

  const progress = session?.progress;
  // The COUNT is every question still open; the LIST is the next four. Showing
  // four and labelling it "4 questions left" when seventeen remain is a promise
  // the flow immediately breaks.
  const remaining = React.useMemo(() => {
    if (!session || !current) return [];
    const at = session.plan.findIndex((q) => q.id === current.id);
    return session.plan.slice(at + 1).filter((q) => !session.answers[q.id]);
  }, [session, current]);
  const upcoming = remaining.slice(0, 4);

  if (error && !session) {
    return (
      <div className="px-8 py-7">
        <Notice tone="problem">{error}</Notice>
      </div>
    );
  }
  if (!session) {
    return (
      <p className="flex items-center gap-2 px-8 py-7 text-[13px] text-[color:var(--ink-secondary)]">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Opening the intake…
      </p>
    );
  }

  const done = Boolean(progress?.done);

  return (
    <div className="flex h-screen flex-col">
      <SidebarSlot slot="sections">
        <SidebarLabel>Sheets</SidebarLabel>
        <div className="px-2.5 text-[12.5px] text-white/70">
          {session.business_name || session.domain}
        </div>
      </SidebarSlot>
      <SidebarSlot slot="footer">
        <p className="text-[12.5px]">
          {progress?.confirmed ?? 0} fact{(progress?.confirmed ?? 0) === 1 ? "" : "s"} confirmed
        </p>
        <p className="mt-1 text-[11.5px] text-white/60">
          {stage === "review" ? "ready to review" : "draft · in progress"}
        </p>
      </SidebarSlot>

      {/* ---------------------------------------------------------- header */}
      <div className="flex items-start justify-between gap-6 border-b border-navy/10 px-7 pb-[18px] pt-[22px]">
        <div className="min-w-0">
          <p className="label mb-1">
            {stage === "review" ? "Review · new version" : "Fact sheet · draft"}
          </p>
          {/* The NAME, not the domain. The API already resolves it — from what
              was typed on the Start screen, then the sheet, then the domain as
              a last resort — so a title reading "blackpropeller.com" was
              throwing away an answer we already had. */}
          <h1 className="page-title truncate">{session.business_name || session.domain}</h1>
          {session.business_name && session.business_name !== session.domain ? (
            <p className="mt-1 text-[13px] text-harbour">{session.domain}</p>
          ) : null}
          {/* THE RAIL IS THE LAUNCHER. It already says "Question 1 of 18", so
              the "17 questions left" pill that floated above the composer was
              the same fact twice — and a progress indicator you can click to
              see what is coming is the more obvious place for it anyway. */}
          {stage === "conversation" && progress ? (
            <button
              type="button"
              onClick={() => remaining.length > 0 && setLauncherOpen((v) => !v)}
              disabled={remaining.length === 0}
              aria-expanded={remaining.length > 0 ? launcherOpen : undefined}
              className={cn(
                "mt-2.5 -ml-1.5 flex items-center gap-2.5 rounded-md px-1.5 py-1 transition-colors",
                remaining.length > 0 ? "hover:bg-navy/[0.04]" : "cursor-default",
              )}
            >
              <PlumeRail
                marks={progress.marks}
                ariaLabel={`Question ${Math.min(progress.answered + 1, progress.total)} of ${progress.total}`}
              />
              <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-harbour">
                {done
                  ? `All ${progress.total} asked · ${progress.confirmed} confirmed`
                  : `Question ${progress.answered + 1} of ${progress.total}`}
              </span>
              {remaining.length > 0 ? (
                <span aria-hidden className="text-[9px] text-harbour">
                  {launcherOpen ? "▾" : "▸"}
                </span>
              ) : null}
            </button>
          ) : null}
          {stage === "review" ? (
            <p className="mt-2 max-w-[660px] text-[13px] leading-relaxed text-[color:var(--ink-secondary)]">
              Everything you told Sable, and the questions it wrote from it. Both are editable until
              you approve.
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <span className="inline-flex items-center gap-[7px] rounded-full border border-navy/25 px-2.5 py-[3px] text-[10px] font-semibold uppercase tracking-[0.2em]">
            <span
              aria-hidden
              className="anim-plume-breathe h-1.5 w-1.5 rounded-full bg-navy"
            />
            {stage === "review" ? "Ready to review" : "In progress"}
          </span>
          {stage === "conversation" ? (
            <span className="inline-flex rounded-full border border-[var(--rule)] bg-navy/[0.04] p-[3px]">
              {(["overview", "details"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setView(v)}
                  aria-pressed={view === v}
                  className={cn(
                    "rounded-full px-4 py-[5px] text-[10px] font-semibold uppercase tracking-[0.2em] transition-colors",
                    view === v ? "bg-white text-navy" : "text-harbour hover:text-navy",
                  )}
                >
                  {v}
                </button>
              ))}
            </span>
          ) : null}
        </div>
      </div>

      {/* ----------------------------------------------------------- stages */}
      {stage === "review" && review ? (
        <ReviewStage
          review={review}
          domain={session.domain}
          approving={busy}
          error={error}
          onApprove={approve}
          onBackToConversation={() => {
            setStage("conversation");
            setError(null);
          }}
          onFixUnconfirmed={() => {
            setStage("conversation");
            setView("details");
            setError(null);
          }}
        />
      ) : (
        <div className="relative flex min-h-0 flex-1 flex-col">
          {view === "overview" ? (
            // NO CAPTION. A constellation with no nodes already means "nothing
            // yet"; a sentence explaining that is a label on an empty room, and
            // it was the only text competing with the conversation for the top
            // of the screen. Bounded to the upper 62% so the graph never crosses
            // a word — see the mask in constellation.tsx.
            <Constellation
              count={confirmedFacts.length}
              className="bottom-auto h-[62%] items-start pt-10"
            />
          ) : (
            <div className="absolute inset-0 overflow-auto px-7 pb-[300px] pt-6">
              <div className="mx-auto flex max-w-[760px] flex-col gap-3.5">
                <div className="flex items-center gap-3 rounded-r-[10px] border-l-[3px] border-navy bg-white px-3.5 py-2.5">
                  <TierMeter confirmed={confirmedFacts.length > 0} />
                  <span className="text-[13px]">
                    {confirmedFacts.length > 0
                      ? "Every one of these came from you, so this sheet can flag anything — at any severity."
                      : "Nothing confirmed yet. Until it is, this sheet can only flag low and medium issues."}
                  </span>
                </div>
                {confirmedFacts.length === 0 ? (
                  <p className="text-[12.5px] text-navy/55">
                    No confirmed claims yet. Answer a question and it lands here.
                  </p>
                ) : null}
                {confirmedFacts.map((fact, i) => (
                  <div
                    key={`${fact.key}-${i}`}
                    className="rounded-md border border-[var(--rule)] bg-white px-4 py-3.5"
                  >
                    <div className="flex items-baseline gap-4">
                      <span className="min-w-0 flex-1 text-[14px] font-medium leading-snug">
                        {fact.value}
                      </span>
                      <span className="shrink-0 text-[11px] tabular-nums text-harbour">
                        FS-{String(i + 1).padStart(2, "0")}
                      </span>
                    </div>
                    <p className="mt-2 text-[11px] text-harbour">you confirmed this</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ------------------------------------------ conversation strip */}
          <ol className="relative z-[2] mt-auto flex flex-col items-center gap-2 px-7">
            {turns.slice(-3).map((turn, i, shown) => {
              const back = shown.length - 1 - i;
              const opacity = back === 0 ? 1 : back === 1 ? 0.5 : 0.22;
              if (turn.role === "pending") {
                return (
                  <li key={turn.id} className="flex w-[720px] max-w-full justify-start">
                    <span className="inline-flex items-end gap-[3px] rounded-[16px_16px_16px_4px] border border-[var(--rule)] bg-white px-3.5 py-2.5">
                      <ThinkingPlumes />
                    </span>
                  </li>
                );
              }
              const isSable = turn.role === "sable";
              return (
                <li
                  key={turn.id}
                  style={{ opacity }}
                  className={cn(
                    "flex w-[720px] max-w-full",
                    isSable ? "justify-start" : "justify-end",
                  )}
                >
                  <span
                    className={cn(
                      "anim-bubble-in max-w-[84%] px-3.5 py-2.5 text-[13.5px] leading-normal",
                      isSable
                        ? "rounded-[16px_16px_16px_4px] border border-[var(--rule)] bg-white text-navy"
                        : "rounded-[16px_16px_4px_16px] bg-navy text-white",
                    )}
                  >
                    {turn.text}
                  </span>
                </li>
              );
            })}
          </ol>

          {/* --------------------------------------------------- launcher */}
          {launcherOpen && remaining.length > 0 ? (
            <div className="relative z-[3] flex justify-center px-7 pt-2.5">
              <div className="anim-bubble-in w-[720px] max-w-full overflow-hidden rounded-lg border border-navy/15 bg-white">
                <div className="flex items-center justify-between border-b border-[var(--rule-inner)] px-4 py-3">
                  <span>
                    <span className="block text-[10px] font-semibold uppercase tracking-[0.28em] text-harbour">
                      Open questions
                    </span>
                    <span className="mt-0.5 block text-[11.5px] text-harbour">
                      {remaining.length} waiting on you
                      {remaining.length > upcoming.length ? ` · the next ${upcoming.length}` : ""}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setLauncherOpen(false)}
                    aria-label="Close open questions"
                    className="text-[16px] leading-none text-harbour"
                  >
                    ×
                  </button>
                </div>
                <div className="max-h-[200px] overflow-auto">
                  {upcoming.map((q) => (
                    <div
                      key={q.id}
                      className="border-b border-[var(--rule-soft)] px-4 py-3 last:border-b-0"
                    >
                      <span className="block text-[13px] leading-snug">
                        {fill(q.prompt, session.business_name)}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-harbour">{q.why}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          {/* ------------------------------------------------- the composer ---
              ONE OBJECT, not a stack. Quick replies, fields, the textarea and
              the action row used to float separately on the Paper ground, which
              read as four things to deal with instead of one place to answer.
              A single bordered container is most of what makes this feel calm.

              What left this region entirely:
              · the "N questions left" pill — the header rail already says
                "Question 1 of 18", and the rail is now the thing you click;
              · "Save and come back later" — every answer is a POST and the
                header says so, so it was a row spent on reassurance;
              · Attach — it was disabled, and a control that cannot be used is
                clutter with a tooltip.
          */}
          <div className="flex justify-center px-7 pb-6 pt-4">
            <div
              ref={cardRef}
              tabIndex={-1}
              role="group"
              aria-labelledby="intake-current-question"
              className="w-[720px] max-w-full rounded-xl border border-navy/20 bg-white outline-none focus-visible:border-blue"
            >
              <span id="intake-current-question" className="sr-only">
                {prompt}
              </span>

              <div className="flex flex-col gap-3 p-4">
                {/* The helper says why we're asking; the for-instance line is
                    the ONLY text business kind is allowed to change, and it is
                    resolved server-side so there is no branch on this side of
                    the wire either. */}
                {current && (current.helper || current.example) ? (
                  <div className="flex flex-col gap-0.5">
                    {current.helper ? (
                      <p className="text-[12.5px] text-harbour">{current.helper}</p>
                    ) : null}
                    {current.example ? (
                      <p className="text-[12px] text-harbour">
                        <span className="font-medium">For instance —</span> {current.example}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {nudge.length > 0 && !nudgeDismissed ? (
                  // A NUDGE, never a block. Stopping an owner from describing
                  // their own business is worse than one unfireable claim.
                  <div className="flex items-start gap-2.5 rounded-md bg-navy/[0.04] px-3 py-2.5 text-[12.5px]">
                    <span className="flex-1">
                      An assistant can&rsquo;t be wrong about &ldquo;{nudge[0]}&rdquo; — only about
                      what you do. Want to rephrase?
                    </span>
                    <button
                      type="button"
                      onClick={() => setNudgeDismissed(true)}
                      className="shrink-0 text-[11.5px] text-blue hover:underline"
                    >
                      Keep it anyway
                    </button>
                  </div>
                ) : null}

                {/* A composite card renders itself from the registry's `parts`.
                    The negative halves — "we don't have a phone line", "closed
                    Sunday", "not licensed in Nevada" — sit at the same weight as
                    the positive ones, because they are what make an
                    over-claiming AI answer flaggable at all. */}
                {current && isStructuredKind(current) ? (
                  <StructuredAnswer
                    question={current}
                    value={structured}
                    onChange={setStructured}
                  />
                ) : null}

                {current &&
                !isStructuredKind(current) &&
                (current.kind === "batch_confirm" || current.kind === "links") ? (
                  <div className="flex flex-col gap-2.5">
                    {/* WHAT WE ALREADY KNOW IS NOT ASKED AGAIN. A field is a
                        question whether or not it has a value in it, so a known
                        value renders as a settled line and only the genuinely
                        open fields get inputs. The value is still SUBMITTED, so
                        the claim is still made; it just isn't re-asked. */}
                    {knownKeys.length > 0 && !editingKnown ? (
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-md bg-navy/[0.04] px-3 py-2.5">
                        {knownKeys.map((key) => (
                          <span key={key} className="text-[12.5px]">
                            <span className="text-harbour">{current.keyLabels[key] ?? key}:</span>{" "}
                            <span className="font-medium">{fields[key]}</span>
                          </span>
                        ))}
                        <button
                          type="button"
                          onClick={() => setEditingKnown(true)}
                          className="ml-auto text-[11.5px] text-blue hover:underline"
                        >
                          Change
                        </button>
                      </div>
                    ) : null}

                    {(editingKnown ? current.keys : openKeys).length > 0 ? (
                      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                        {(editingKnown ? current.keys : openKeys).map((key) => (
                          <label key={key} className="block">
                            <span className={FIELD_LABEL_CLS}>
                              {current.keyLabels[key] ?? key}
                            </span>
                            <input
                              value={fields[key] ?? ""}
                              onChange={(e) =>
                                setFields((f) => ({ ...f, [key]: e.target.value }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                  e.preventDefault();
                                  void send(false);
                                }
                              }}
                              className={cn(INPUT_CLS, "mt-1")}
                            />
                          </label>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {current && !isStructuredKind(current) && current.options.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {current.options.map((o) => {
                      const on = picked.includes(o.value);
                      return (
                        <button
                          key={o.value}
                          type="button"
                          aria-pressed={on}
                          onClick={() =>
                            setPicked((p) =>
                              current.kind === "multi"
                                ? on
                                  ? p.filter((x) => x !== o.value)
                                  : [...p, o.value]
                                : on
                                  ? []
                                  : [o.value],
                            )
                          }
                          className={cn(
                            "inline-flex items-center gap-[7px] rounded-full px-3.5 py-[5px] text-[12.5px] transition-colors",
                            on
                              ? "border border-navy bg-navy text-white"
                              : "border border-navy/20 bg-white text-navy hover:bg-navy/[0.04]",
                          )}
                        >
                          {o.label}
                          {on ? <Check className="h-3 w-3" aria-hidden /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : null}

                {/* A composite card has no free-text tail: everything it asks
                    for has a field, and a stray textarea beside them is a place
                    for an answer to go nowhere. */}
                {current &&
                (isStructuredKind(current) ||
                  current.kind === "batch_confirm" ||
                  current.kind === "links") ? null : (
                  <textarea
                    rows={3}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        void send(false);
                      }
                    }}
                    placeholder={
                      done
                        ? "Keep adding context, or hit Review & create."
                        : current?.placeholder ||
                          "Answer here, or tell Sable something it didn't ask about…"
                    }
                    className="w-full resize-none border-0 bg-transparent p-0 text-[13.5px] leading-normal outline-none placeholder:text-harbour"
                  />
                )}
              </div>

              {/* The action row, inside the box. The assertion preview sits on
                  the left rather than floating above the composer: it is the
                  mechanism that makes this screen trustworthy — the owner sees
                  the exact sentence they will be quoted on — so it gets quieter,
                  never further away. */}
              <div className="flex items-center gap-3 border-t border-[var(--rule-inner)] px-4 py-2.5">
                <p
                  className="min-w-0 flex-1 truncate text-[12px] text-harbour"
                  aria-live="polite"
                >
                  {previewText ? (
                    <>
                      This will read:{" "}
                      <span className="font-medium text-navy">“{previewText}”</span>
                    </>
                  ) : (
                    "Nothing will be checked on this yet."
                  )}
                </p>
                {/* Skip is ALWAYS visible, never behind an overflow: a blank is
                    the safe default and hiding it makes guessing the easy path. */}
                {current?.skippable && !done ? (
                  <button
                    type="button"
                    onClick={() => void send(true)}
                    className="shrink-0 text-[11.5px] text-harbour hover:text-navy"
                  >
                    Skip
                  </button>
                ) : null}
                <span className="hidden shrink-0 text-[11px] text-harbour lg:inline">
                  Enter to send
                </span>
                {done ? (
                  <Button variant="hero" size="lg" onClick={toReview} disabled={busy}>
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
                    Review &amp; create
                  </Button>
                ) : (
                  <Button onClick={() => void send(false)} disabled={pending}>
                    {pending ? "Thinking…" : "Send"}
                  </Button>
                )}
              </div>

              {error ? (
                <div className="px-4 pb-4">
                  <Notice tone="problem">{error}</Notice>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
