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
import { Chips, StructuredAnswer, isStructuredKind } from "@/components/intake/structured-answer";
import {
  EMPTY_DRAFT,
  draftIsEmpty,
  draftRaw,
  draftValue,
  seedDraft,
  usesChips,
  usesFields,
  type Draft,
} from "@/components/intake/answer-draft";
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
  // ONE draft, whatever the card's kind. The composer used to hold four
  // overlapping states and its own opinion about how each kind is submitted —
  // which is how a `list` card ended up meaning something different here, in the
  // review editor, and in what a crawl could prefill. `answer-draft.ts` owns it.
  const [answer, setAnswer] = React.useState<Draft>(EMPTY_DRAFT);
  // Whether the owner has touched this card. The background crawl re-seeds a
  // card when it lands, and re-seeding one somebody is typing into would delete
  // what they wrote — so it only ever refills an untouched card.
  const [touched, setTouched] = React.useState(false);
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
                //
                // And the crawl now runs BESIDE this sentence rather than before
                // it, so "reading it now" is a third thing the opener has to be
                // able to say. Promising facts that are still being fetched is
                // how a blank first card reads as a broken one.
                text:
                  (s.crawl_state === "running"
                    ? `I'm reading ${s.domain} now — I'll fill in whatever I find as we go. `
                    : Object.values(s.prefill).some((p) => p.source_kind !== "client")
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

  // --- the crawl landing mid-conversation ------------------------------------
  //
  // The crawl runs beside the conversation, so its results arrive after the page
  // does. Polling rather than a socket: it runs once per session, finishes in
  // well under a minute, and a socket for one event is infrastructure to
  // maintain forever.
  //
  // It stops on its own — every terminal state is written, the failures
  // included, so this can never spin against a site we were 403'd from.
  React.useEffect(() => {
    if (session?.crawl_state !== "running") return;
    const sid = session.session_id;
    let stop = false;
    const tick = async () => {
      try {
        const fresh = await getIntake(sid);
        // A crawl result must never overwrite the answer in flight. Only the
        // session object moves; `answer` is re-seeded by the effect below, and
        // only when the card is untouched.
        if (!stop) setSession(fresh);
      } catch {
        // A dropped poll is not worth a banner — the next one covers it, and
        // the conversation is fully usable without the crawl ever landing.
      }
    };
    const handle = setInterval(() => void tick(), 3000);
    return () => {
      stop = true;
      clearInterval(handle);
    };
  }, [session?.crawl_state, session?.session_id]);

  // The crawl says how it went, once, in the conversation.
  //
  // IT HAS TO SAY WHEN IT FAILED. The opener promises "I'm reading your site
  // now"; if that promise just evaporates, an owner watching blank cards arrive
  // concludes the product is broken rather than that their host blocked us —
  // which, per the edge-block problem, is the common case and not a defect. A
  // line here costs nothing and is the difference between "it didn't work" and
  // "we'll do it the quick way".
  const lastCrawl = React.useRef<string | null | undefined>(undefined);
  React.useEffect(() => {
    const state = session?.crawl_state ?? null;
    const previous = lastCrawl.current;
    lastCrawl.current = state;
    if (previous !== "running" || state === "running" || !session) return;
    const text =
      state === "done"
        ? `Read ${session.domain} — I've filled in what I could find. Check each one before you send it.`
        : state === "nothing_found"
          ? `There wasn't much to read on ${session.domain}, so these are all yours. It's the same sheet either way.`
          : `I couldn't get into ${session.domain} — plenty of sites block us. Nothing lost; we'll just do it by hand.`;
    setTurns((t) => [...t, { id: `crawl-${state}`, role: "sable", text }]);
  }, [session?.crawl_state, session]);

  // Focus the CARD, not the input, on each new question — so a screen reader
  // hears the question before it lands in a text field.
  //
  // AND SEED IT FROM THE CRAWL. `prefillAnswer` is a whole draft answer in the
  // shape `/answer` stores, so every kind seeds the same way — the grid arrives
  // with Sunday's Closed toggle already pressed, the service list arrives as
  // chips. The flat `prefill` map this used to read could only ever fill a
  // `batch_confirm`: its keys are claim keys, and a composite card's controls
  // are named by part.
  //
  // Keyed on the card AND on what the crawl now knows, so a background crawl
  // that lands while the opener is still being read refills the card underneath
  // it — but never one the owner has already touched.
  // Serialized, not the object: every poll returns a fresh `prefillAnswer` with
  // a new identity, and keying the effect on that would re-seed (and re-request
  // a preview) every three seconds for the whole crawl.
  const seedKey = React.useMemo(
    () => JSON.stringify(current?.prefillAnswer ?? null),
    [current?.prefillAnswer],
  );
  React.useEffect(() => {
    if (stage === "conversation" && current) cardRef.current?.focus();
    if (touched) return;
    setEditingKnown(false);
    setAnswer(current ? seedDraft(current, current.prefillAnswer) : EMPTY_DRAFT);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, seedKey, stage]);

  // A new card is untouched by definition. Separate from the seeding effect so
  // that effect can bail on `touched` without resetting the flag it read.
  React.useEffect(() => {
    setTouched(false);
  }, [current?.id]);

  // Keys we already have a value for versus the ones still genuinely open.
  //
  // THE PARTITION IS THE CARD'S, NOT THE KEYSTROKE'S. It reads what the card was
  // SEEDED with and never the live field. Split on the live value and the first
  // character typed into an open field reclassifies it as known: the input
  // unmounts mid-word, focus is lost, and the half-typed value shows up in the
  // settled strip as a fact nobody finished stating.
  const [editingKnown, setEditingKnown] = React.useState(false);
  const seededKeys = React.useMemo(() => {
    if (!current || !usesFields(current)) return [];
    const seeded = seedDraft(current, current.prefillAnswer).fields;
    return current.keys.filter((k) => (seeded[k] ?? "").trim());
  }, [current]);
  // A seeded key the owner cleared drops out of the strip rather than sitting
  // there blank — it can only leave, never be joined by a field being typed.
  const knownKeys = React.useMemo(
    () => seededKeys.filter((k) => (answer.fields[k] ?? "").trim()),
    [seededKeys, answer.fields],
  );
  const openKeys = React.useMemo(
    () => (current ? current.keys.filter((k) => !seededKeys.includes(k)) : []),
    [current, seededKeys],
  );

  const prompt = React.useMemo(
    () => (current ? fill(current.prompt, session?.business_name ?? "") : ""),
    [current, session],
  );

  const send = async (skipped: boolean) => {
    if (!session || !current || pending) return;
    const submitted = answer;
    if (!skipped && draftIsEmpty(current, submitted)) return;

    const userText = skipped ? "Skip this one" : draftRaw(current, submitted);
    setTurns((t) => [
      ...t,
      { id: `u-${Date.now()}`, role: "user", text: userText },
      { id: `p-${Date.now()}`, role: "pending" },
    ]);
    setAnswer(EMPTY_DRAFT);
    setTouched(false);
    setPending(true);
    setLauncherOpen(false);
    setNudge([]);
    setNudgeDismissed(false);

    try {
      const result = await answerIntake(session.session_id, {
        question_id: current.id,
        value: skipped ? null : draftValue(current, submitted),
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
      setAnswer(submitted);
      setTouched(true);
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
    if (draftIsEmpty(current, answer)) {
      setPreviewText("");
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      previewIntake(session.session_id, {
        question_id: current.id,
        value: draftValue(current, answer),
        raw: draftRaw(current, answer),
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
  }, [session, current, answer]);

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
              {/* What the screen ACTUALLY does. This line used to promise that
                  both halves were editable while every claim rendered as static
                  text — so an owner who spotted a wrong founding date had no way
                  to fix it. The facts are editable; the questions are written
                  from them and rebuild on every change. */}
              Everything you told Sable, and the questions it wrote from it. Fix any fact until you
              approve — the questions follow.
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
          sessionId={session.session_id}
          plan={session.plan}
          answers={session.answers}
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
          // A saved edit rebuilds BOTH halves: the session (so the editor
          // re-seeds from what was actually stored, not from what was typed)
          // and the review (so the claims, the checks and the question set all
          // reflect the change). `complete` is what regenerates the set, and
          // re-running it is why the questions never have to be edited by hand.
          onEdited={async () => {
            setError(null);
            // Sequenced, not raced: `complete` rewrites run_inputs and the
            // query set, and a `getIntake` that overtook it would seed the
            // editor from the row as it was a moment ago.
            const rebuilt = await completeIntake(session.session_id);
            setSession(await getIntake(session.session_id));
            setReview(rebuilt);
            // The details view's list is the sheet, so it follows the sheet.
            // Left alone it would keep showing the sentence that was just
            // corrected, next to the correction.
            setConfirmedFacts(
              rebuilt.claims.map((c) => ({
                key: c.key,
                value: c.value,
                polarity: c.polarity === "negative" ? "negative" : "positive",
              })),
            );
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

                {/* THE CARD IS A CONFIRM WHEN WE HAVE SOMETHING TO CONFIRM.
                    Said out loud, because the difference between "fill this in"
                    and "check this" is the difference between a fifteen-minute
                    intake and a four-minute one — and because a card that
                    silently arrives pre-filled invites a click-through, while one
                    that says where the values came from invites a read.

                    NOTHING HERE IS ON THE RECORD YET. A crawl's claim is
                    `public_source_only` and stays that way; only sending this
                    card makes it something the owner is quoted on, which is why
                    the copy says "check" and never "confirmed". */}
                {current?.prefillAnswer && !touched ? (
                  <p className="rounded-r-[6px] border-l-[3px] border-navy bg-navy/[0.04] py-2 pl-3 pr-3 text-[12.5px]">
                    Filled in from {session.domain}. Check it and send, or change anything
                    that&rsquo;s wrong — nothing counts until you send it.
                  </p>
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
                    value={answer.structured}
                    onChange={(structured) => {
                      setTouched(true);
                      setAnswer((a) => ({ ...a, structured }));
                    }}
                  />
                ) : null}

                {current && usesFields(current) ? (
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
                            <span className="font-medium">{answer.fields[key]}</span>
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
                              value={answer.fields[key] ?? ""}
                              onChange={(e) => {
                                setTouched(true);
                                setAnswer((a) => ({
                                  ...a,
                                  fields: { ...a.fields, [key]: e.target.value },
                                }));
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
                      const on = answer.picked.includes(o.value);
                      return (
                        <button
                          key={o.value}
                          type="button"
                          aria-pressed={on}
                          onClick={() => {
                            setTouched(true);
                            setAnswer((a) => ({
                              ...a,
                              picked:
                                current.kind === "multi"
                                  ? on
                                    ? a.picked.filter((x) => x !== o.value)
                                    : [...a.picked, o.value]
                                  : on
                                    ? []
                                    : [o.value],
                            }));
                          }}
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

                {/* CHIPS, NOT A COMMA-SPLIT TEXTAREA. A list card used to be a
                    free-text box split on commas, which tore "Berkeley, Albany"
                    into two towns when it was one entry — and meant a crawled
                    service list had nowhere to render, so `hasOfferCatalog`
                    markup was read, stored, and never shown to anyone. */}
                {current && usesChips(current) ? (
                  <Chips
                    items={answer.items}
                    placeholder={current.placeholder}
                    onChange={(items) => {
                      setTouched(true);
                      setAnswer((a) => ({ ...a, items }));
                    }}
                  />
                ) : null}

                {/* A composite card has no free-text tail: everything it asks
                    for has a field, and a stray textarea beside them is a place
                    for an answer to go nowhere. */}
                {current && (isStructuredKind(current) || usesFields(current) || usesChips(current)) ? null : (
                  // ENTER IS A NEWLINE, NEVER A SEND. An answer here is often
                  // two or three sentences about the business, and a textarea
                  // that commits on the first Enter turns "what do you do?" into
                  // a race against your own keyboard. Send is a click.
                  <textarea
                    rows={3}
                    value={answer.typed}
                    onChange={(e) => {
                      setTouched(true);
                      setAnswer((a) => ({ ...a, typed: e.target.value }));
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
