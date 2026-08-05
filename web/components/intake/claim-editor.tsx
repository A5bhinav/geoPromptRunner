"use client";

import * as React from "react";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { Chips, StructuredAnswer, isStructuredKind } from "@/components/intake/structured-answer";
import {
  draftIsEmpty,
  draftRaw,
  draftValue,
  seedDraft,
  usesChips,
  usesFields,
  type Draft,
} from "@/components/intake/answer-draft";
import { cn } from "@/lib/utils";
import { FIELD_LABEL_CLS, INPUT_CLS } from "@/lib/ui";
import {
  answerIntake,
  previewIntake,
  type IntakeQuestion,
  type IntakeStoredAnswer,
} from "@/lib/api";

/**
 * Re-answering one card, in place on the review screen.
 *
 * WHY EDITING IS RE-ANSWERING AND NOT EDITING. The sheet's claims are sentences
 * the owner will be quoted on in front of a judge, and each one's provenance is
 * "you said this, on this card, on this date". Let someone edit the sentence
 * directly and that stops being true — the quote no longer matches anything
 * anybody said. So this control opens the CARD, seeded with the stored answer,
 * and saves through the same `/answer` endpoint the conversation uses. That
 * endpoint is idempotent per question id, which is what makes this free.
 *
 * A CARD IS THE UNIT, NOT A CLAIM. Q-WHAT-01 carries four facts and Q-REACH-01
 * carries six; opening one of them from a single line has to show the whole
 * card, or saving would silently drop the siblings the owner could not see.
 * `alsoAffects` names them above the controls rather than letting that be a
 * surprise.
 *
 * NOTHING HERE SENDS ON ENTER. Enter is a newline in the textareas and adds a
 * chip in the lists; the only way to commit is the Save button. An answer that
 * commits on a keystroke is an answer somebody was still typing.
 */

export function ClaimEditor({
  sessionId,
  question,
  stored,
  alsoAffects,
  onSaved,
  onCancel,
}: {
  sessionId: string;
  question: IntakeQuestion;
  stored: IntakeStoredAnswer | undefined;
  /** The other claims this card produces, so saving cannot surprise anyone. */
  alsoAffects: string[];
  onSaved: () => Promise<void> | void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = React.useState<Draft>(() => seedDraft(question, stored?.skipped ? undefined : stored?.value));
  const [preview, setPreview] = React.useState<string[]>([]);
  const [nudge, setNudge] = React.useState<string[]>([]);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const empty = draftIsEmpty(question, draft);

  // The sentences this card WOULD produce, from the server's own builder. Same
  // round trip the composer makes, and for the same reason: a client-side copy
  // of the phrasing drifts the first time a card is reworded, and the owner
  // gets shown one sentence and quoted on another.
  React.useEffect(() => {
    if (empty) {
      setPreview([]);
      setNudge([]);
      return;
    }
    let cancelled = false;
    const handle = setTimeout(() => {
      previewIntake(sessionId, {
        question_id: question.id,
        value: draftValue(question, draft),
        raw: draftRaw(question, draft),
      })
        .then((r) => {
          if (cancelled) return;
          setPreview(r.assertions.map((a) => a.value));
          setNudge(r.nudge);
        })
        // Nothing rather than a guess: the one thing this must never do is show
        // a sentence we did not build.
        .catch(() => !cancelled && setPreview([]));
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [sessionId, question, draft, empty]);

  const commit = async (skipped: boolean) => {
    setSaving(true);
    setError(null);
    try {
      await answerIntake(sessionId, {
        question_id: question.id,
        value: skipped ? null : draftValue(question, draft),
        raw: skipped ? "" : draftRaw(question, draft),
        skipped,
      });
      await onSaved();
    } catch (e) {
      setSaving(false);
      setError(e instanceof Error ? e.message : "That change did not save. Try again.");
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-navy/20 bg-white">
      <div className="flex flex-col gap-3 p-3.5">
        <div>
          <p className="text-[13px] font-medium leading-snug">{question.prompt}</p>
          {question.helper ? (
            <p className="mt-1 text-[12px] text-harbour">{question.helper}</p>
          ) : null}
          {alsoAffects.length > 0 ? (
            // Named, never counted. "This also changes 3 other facts" with no
            // way to see which is the surprise this line exists to prevent.
            <p className="mt-1.5 text-[11.5px] text-harbour">
              This card also carries: {alsoAffects.join(" · ")}
            </p>
          ) : null}
        </div>

        {isStructuredKind(question) ? (
          <StructuredAnswer
            question={question}
            value={draft.structured}
            onChange={(structured) => set("structured", structured)}
          />
        ) : null}

        {usesFields(question) ? (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {question.keys.map((key) => (
              <label key={key} className="block">
                <span className={FIELD_LABEL_CLS}>{question.keyLabels[key] ?? key}</span>
                <input
                  value={draft.fields[key] ?? ""}
                  onChange={(e) => set("fields", { ...draft.fields, [key]: e.target.value })}
                  className={cn(INPUT_CLS, "mt-1")}
                />
              </label>
            ))}
          </div>
        ) : null}

        {!isStructuredKind(question) && question.options.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {question.options.map((o) => {
              const on = draft.picked.includes(o.value);
              return (
                <button
                  key={o.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    set(
                      "picked",
                      question.kind === "multi"
                        ? on
                          ? draft.picked.filter((x) => x !== o.value)
                          : [...draft.picked, o.value]
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

        {usesChips(question) ? (
          <Chips
            items={draft.items}
            placeholder={question.placeholder}
            onChange={(items) => set("items", items)}
          />
        ) : null}

        {!isStructuredKind(question) && !usesFields(question) && !usesChips(question) ? (
          <textarea
            rows={question.kind === "longtext" ? 3 : 2}
            value={draft.typed}
            placeholder={question.placeholder}
            onChange={(e) => set("typed", e.target.value)}
            className={cn(INPUT_CLS, "resize-y leading-normal")}
          />
        ) : null}

        {nudge.length > 0 ? (
          // A NUDGE, never a block. Stopping an owner from describing their own
          // business is worse than one unfireable claim.
          <p className="rounded-md bg-navy/[0.04] px-3 py-2.5 text-[12.5px]">
            An assistant can&rsquo;t be wrong about &ldquo;{nudge[0]}&rdquo; — only about what you
            do. Want to rephrase?
          </p>
        ) : null}

        {error ? <Notice tone="problem">{error}</Notice> : null}
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--rule-inner)] px-3.5 py-2.5">
        <div className="min-w-0 flex-1" aria-live="polite">
          {preview.length > 0 ? (
            <>
              <p className="text-[11px] text-harbour">This will read:</p>
              {preview.map((line) => (
                <p key={line} className="truncate text-[12px] font-medium">
                  “{line}”
                </p>
              ))}
            </>
          ) : (
            <p className="text-[12px] text-harbour">
              {empty
                ? "Blank — nothing on this card gets checked."
                : "Nothing will be checked on this yet."}
            </p>
          )}
        </div>
        {/* Clearing a card is a real answer, and the safe one. Offered plainly
            rather than hidden, because a guess is worse than a blank. */}
        {question.skippable ? (
          <button
            type="button"
            onClick={() => void commit(true)}
            disabled={saving}
            className="shrink-0 text-[11.5px] text-harbour hover:text-navy"
          >
            Drop these facts
          </button>
        ) : null}
        <Button variant="ghost" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={() => void commit(false)} disabled={saving || empty}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
          Save
        </Button>
      </div>
    </div>
  );
}
