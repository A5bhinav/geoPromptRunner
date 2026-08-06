"use client";

import * as React from "react";
import { Check, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { FIELD_HINT_CLS, FIELD_LABEL_CLS, INPUT_CLS } from "@/lib/ui";
import type { IntakePart, IntakeQuestion } from "@/lib/api";

/**
 * The composite cards, rendered from the registry rather than from a switch.
 *
 * WHY THIS IS NOT A PILE OF PER-CARD COMPONENTS. Six of the sixteen questions
 * ask two things at once — *where do you serve* **and** *where don't you*,
 * *what do you hold* **and** *what don't you*. Those halves are one card
 * because they are one decision for the owner, but two shapes for the answer.
 * The server describes that shape in `question.parts`; everything here is a
 * renderer for a `PartKind`, and adding a seventeenth composite card is a
 * registry edit, not a frontend one.
 *
 * THE NEGATIVE HALVES ARE THE POINT. "We don't have a phone line", "closed
 * Sunday", "not licensed in Nevada", "there is no free option" — these are what
 * make an over-claiming AI answer flaggable, because an omission is never a
 * finding and only a contradiction is. Every control below renders its negative
 * half at the same weight as its positive one. Do not tuck one behind a
 * disclosure to tidy the card up.
 */

/** What one composite card holds. Keyed by part key, exactly as the server's
 * assertion builders read it. */
export type StructuredValue = Record<string, unknown>;

export type PairRow = { a: string; b: string };
export type PricedRow = { what: string; price: string; basis: string; includes: string };

const EMPTY_PAIR: PairRow = { a: "", b: "" };
const EMPTY_PRICED: PricedRow = { what: "", price: "", basis: "", includes: "" };

/** Six rows before it scrolls. More than six prices is a conversation, not a
 * form — and a chip list of 140 SKUs is useless to the judge, which checks
 * whether an AI knows you sell single-origin, not the 12oz Ethiopian. */
const MAX_ROWS = 6;

export function isComposite(q: IntakeQuestion): boolean {
  return q.parts.length > 0;
}

/** A card that carries its whole answer in one structured control. `pairs` and
 * `priced_rows` cards have no free-text tail, so the composer hides its
 * textarea for them. */
export function isStructuredKind(q: IntakeQuestion): boolean {
  return isComposite(q) || q.kind === "priced_rows";
}

export function emptyValue(q: IntakeQuestion): StructuredValue {
  if (q.kind === "priced_rows") return { rows: [{ ...EMPTY_PRICED }] };
  const out: StructuredValue = {};
  for (const p of q.parts) {
    if (p.kind === "pairs") out[p.key] = [{ ...EMPTY_PAIR }];
    else if (p.kind === "list") out[p.key] = [] as string[];
    else if (p.kind === "days") out[p.key] = {} as Record<string, string>;
    // A TEXT part seeded from the crawl is a check-and-move-on, not a retype.
    else out[p.key] = p.prefill?.value ?? "";
  }
  return out;
}

/** The payload the API stores — the shape `assertions.py` reads.
 *
 * Empty fields are OMITTED rather than sent blank. Rule 2: a fact nobody
 * filled in is not a fact anybody confirmed, and an empty string would become a
 * claim asserting nothing. */
export function toPayload(q: IntakeQuestion, value: StructuredValue): unknown {
  if (q.kind === "priced_rows") {
    const rows = asPriced(value.rows)
      .filter((r) => r.what.trim() && r.price.trim())
      .map((r) => ({
        what: r.what.trim(),
        price: r.price.trim(),
        basis: r.basis,
        includes: r.includes.trim(),
      }));
    // THE ESCAPE HATCH, and it only appears when it was used. Four columns hold
    // a plumber's call-out fee and a SaaS's per-seat price, and they do not hold
    // "first hour billed at 1.5x after 6pm" or "we bill in 15-minute increments
    // after the first hour". Without somewhere to put those, an owner either
    // mangles them into the What column or leaves out the term a customer is
    // most likely to be surprised by.
    //
    // A bare array when there is no note: every answer stored before this shape
    // existed is an array, and `_priced_rows` reads both, so nothing already on
    // a sheet has to be migrated.
    const note = String(value.note ?? "").trim();
    return note ? { rows, note } : rows;
  }
  const out: Record<string, unknown> = {};
  for (const p of q.parts) {
    if (!visible(p, value)) continue;
    if (p.kind === "pairs") {
      // The pairs control names its columns `a`/`b`; the builders name them by
      // meaning. Translated here, once, rather than in seven call sites.
      const rows = asPairs(value[p.key])
        .filter((r) => r.a.trim())
        .map((r) => pairFields(p, r));
      if (rows.length) out[p.key] = rows;
    } else if (p.kind === "list") {
      const items = asList(value[p.key]).filter((s) => s.trim());
      if (items.length) out[p.key] = items;
    } else if (p.kind === "days") {
      const days = asDays(value[p.key]);
      const filled = Object.entries(days).filter(([, v]) => v.trim());
      if (filled.length) out[p.key] = Object.fromEntries(filled);
    } else {
      const text = String(value[p.key] ?? "").trim();
      if (text) out[p.key] = text;
    }
  }
  return out;
}

/** The inverse of `toPayload`: a stored answer, back in its controls.
 *
 * WITHOUT THIS THERE IS NO EDITING. Re-opening a card the owner already
 * answered has to show what they said — an editor that opens blank is a retype,
 * and a retype of nine price rows is how you get an owner clicking Approve on a
 * sheet they gave up on fixing.
 *
 * It deliberately does NOT fall back to prefill the way `emptyValue` does. A
 * text part the owner cleared is absent from the payload, and seeding it from
 * the crawl again would resurrect the value they just deleted.
 */
export function fromPayload(q: IntakeQuestion, stored: unknown): StructuredValue {
  if (q.kind === "priced_rows") {
    // Either shape: a bare array (what every answer stored before the note
    // existed looks like) or `{rows, note}`.
    const held =
      stored && typeof stored === "object" && !Array.isArray(stored)
        ? (stored as Record<string, unknown>)
        : { rows: stored, note: "" };
    const rows = asPriced(held.rows).map((r) => ({ ...EMPTY_PRICED, ...r }));
    return {
      rows: rows.length ? rows : [{ ...EMPTY_PRICED }],
      note: String(held.note ?? ""),
    };
  }
  const payload = stored && typeof stored === "object" ? (stored as Record<string, unknown>) : {};
  const out: StructuredValue = {};
  for (const p of q.parts) {
    const held = payload[p.key];
    if (p.kind === "pairs") {
      const rows = (Array.isArray(held) ? held : [])
        .map((row) => unpairFields(p, row))
        .filter((r) => r.a || r.b);
      out[p.key] = rows.length ? rows : [{ ...EMPTY_PAIR }];
    } else if (p.kind === "list") {
      out[p.key] = asList(held);
    } else if (p.kind === "days") {
      out[p.key] = asDays(held);
    } else {
      out[p.key] = typeof held === "string" ? held : "";
    }
  }
  return out;
}

/** True when the owner has actually put something in. An untouched composite
 * card must not commit — it would be a skip pretending to be an answer. */
export function hasContent(q: IntakeQuestion, value: StructuredValue): boolean {
  const payload = toPayload(q, value);
  if (Array.isArray(payload)) return payload.length > 0;
  const held = payload as Record<string, unknown>;
  // A `{rows: [], note: ""}` object has keys and no content. Counting keys alone
  // would let an untouched priced-rows card commit as an answer.
  if ("rows" in held) {
    return asPriced(held.rows).length > 0 || Boolean(String(held.note ?? "").trim());
  }
  return Object.keys(held).length > 0;
}

/** The user's own bubble in the transcript, and the claim's verbatim quote. */
export function summarize(q: IntakeQuestion, value: StructuredValue): string {
  let payload = toPayload(q, value);
  if (q.kind === "priced_rows" && !Array.isArray(payload)) {
    const held = payload as { rows?: unknown; note?: unknown };
    const rows = summarizePriced(q, asPriced(held.rows));
    const note = String(held.note ?? "").trim();
    return [rows, note].filter(Boolean).join("; ");
  }
  if (Array.isArray(payload)) {
    return summarizePriced(q, payload as PricedRow[]);
  }
  return Object.entries(payload as Record<string, unknown>)
    .map(([key, v]) => {
      const part = q.parts.find((p) => p.key === key);
      const text = Array.isArray(v)
        ? v.map((x) => (typeof x === "string" ? x : Object.values(x as object).join(" — "))).join(", ")
        : typeof v === "object" && v !== null
          ? Object.entries(v as Record<string, string>).map(([d, h]) => `${d} ${h}`).join(", ")
          : String(v);
      return `${part?.label ?? key}: ${text}`;
    })
    .join(" · ");
}

function summarizePriced(q: IntakeQuestion, rows: PricedRow[]): string {
  return rows
    .map((row) => [row.what, row.price, basisLabel(q, row.basis)].filter(Boolean).join(" · "))
    .join("; ");
}

// --- helpers ------------------------------------------------------------------

function visible(p: IntakePart, value: StructuredValue): boolean {
  if (!p.showWhen) return true;
  return String(value[p.showWhen.part] ?? "") === p.showWhen.equals;
}

/** Which two field names this part's rows are stored under. One place, because
 * `pairFields` and `unpairFields` disagreeing is an edit that silently blanks a
 * row the owner already filled in. */
function pairKeys(p: IntakePart): readonly [string, string] {
  // `what`/`when`, `what`/`issuer`, `said`/`truth` — the builders accept a
  // couple of spellings each, so one generic mapping serves all three.
  if (p.key === "watchlist") return ["said", "truth"] as const;
  if (p.key === "credentials") return ["what", "issuer"] as const;
  return ["what", "when"] as const;
}

function pairFields(p: IntakePart, row: PairRow): Record<string, string> {
  const [first, second] = pairKeys(p);
  return { [first]: row.a.trim(), [second]: row.b.trim() };
}

function unpairFields(p: IntakePart, row: unknown): PairRow {
  const [first, second] = pairKeys(p);
  const held = row && typeof row === "object" ? (row as Record<string, unknown>) : {};
  return { a: String(held[first] ?? ""), b: String(held[second] ?? "") };
}

function basisLabel(q: IntakeQuestion, value: string): string {
  return q.basisOptions?.find((o) => o.value === value)?.label ?? value;
}

const asPairs = (v: unknown): PairRow[] => (Array.isArray(v) ? (v as PairRow[]) : []);
const asPriced = (v: unknown): PricedRow[] => (Array.isArray(v) ? (v as PricedRow[]) : []);
const asList = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
const asDays = (v: unknown): Record<string, string> =>
  v && typeof v === "object" ? (v as Record<string, string>) : {};

// --- the control --------------------------------------------------------------

interface Props {
  question: IntakeQuestion;
  value: StructuredValue;
  onChange: (next: StructuredValue) => void;
}

export function StructuredAnswer({ question, value, onChange }: Props) {
  const set = (key: string, next: unknown) => onChange({ ...value, [key]: next });

  if (question.kind === "priced_rows") {
    return (
      <PricedRows
        rows={asPriced(value.rows)}
        note={String(value.note ?? "")}
        basisOptions={question.basisOptions ?? []}
        onChange={(rows) => set("rows", rows)}
        onNoteChange={(note) => set("note", note)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3.5">
      {question.parts.filter((p) => visible(p, value)).map((p) => (
        <div key={p.key}>
          <span className={FIELD_LABEL_CLS}>{p.label}</span>
          {p.helper ? <span className={cn(FIELD_HINT_CLS, "block")}>{p.helper}</span> : null}
          <div className="mt-1">
            {p.kind === "text" ? (
              <input
                value={String(value[p.key] ?? "")}
                placeholder={p.placeholder}
                onChange={(e) => set(p.key, e.target.value)}
                className={INPUT_CLS}
              />
            ) : p.kind === "choice" ? (
              <ChoicePart part={p} value={String(value[p.key] ?? "")} onChange={(v) => set(p.key, v)} />
            ) : p.kind === "list" ? (
              <Chips
                items={asList(value[p.key])}
                placeholder={p.placeholder}
                onChange={(items) => set(p.key, items)}
              />
            ) : p.kind === "pairs" ? (
              <Pairs
                rows={asPairs(value[p.key])}
                labels={p.labels ?? ["", ""]}
                onChange={(rows) => set(p.key, rows)}
              />
            ) : (
              <Days
                days={asDays(value[p.key])}
                labels={question.dayLabels ?? []}
                onChange={(days) => set(p.key, days)}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** A choice whose "yes" reveals a text field. The TYPED TEXT is what gets
 * stored, so the answer is one value ("a $5.99/month membership") rather than a
 * flag plus a string the builder would have to reassemble. */
function ChoicePart({
  part,
  value,
  onChange,
}: {
  part: IntakePart;
  value: string;
  onChange: (v: string) => void;
}) {
  // "no" is stored literally; anything else is the revealed text. So the
  // revealed input is open whenever the value is neither empty nor a bare
  // option id.
  const ids = new Set(part.options.map((o) => o.value));
  const revealed = Boolean(value) && !ids.has(value);
  const [open, setOpen] = React.useState(revealed);

  // FOCUS ON REVEAL, NEVER ON ARRIVAL. This used to be `autoFocus`, which fires
  // on mount too — so a card that arrived already revealed (the crawl filled it
  // in) stole focus from the card container the moment it rendered, and a screen
  // reader landed in a text field without having heard the question. Focusing
  // only on the false→true transition keeps the tap-to-reveal behaviour and
  // leaves arrival to the composer.
  const input = React.useRef<HTMLInputElement>(null);
  const mounted = React.useRef(false);
  React.useEffect(() => {
    if (mounted.current && open) input.current?.focus();
    mounted.current = true;
  }, [open]);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-1.5">
        {part.options.map((o) => {
          const on = o.value === part.revealOn ? open || revealed : value === o.value;
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={on}
              onClick={() => {
                if (o.value === part.revealOn) {
                  setOpen(true);
                  if (ids.has(value)) onChange("");
                } else {
                  setOpen(false);
                  onChange(o.value);
                }
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
      {open || revealed ? (
        <input
          ref={input}
          value={ids.has(value) ? "" : value}
          placeholder={part.placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT_CLS}
        />
      ) : null}
    </div>
  );
}

/** Exported because the review editor renders `list` and `multi` cards with it
 * too. ENTER ADDS A CHIP, it does not submit: nothing in this flow sends on
 * Enter, and a control that did would be the one place a keystroke commits an
 * answer the owner was still typing. */
export function Chips({
  items,
  placeholder,
  onChange,
}: {
  items: string[];
  placeholder: string;
  onChange: (items: string[]) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const commit = () => {
    // COMMAS SPLIT. People paste a list, because a list is what was asked for:
    // one owner typed "Tinuiti, Directive, KlientBoost, Disruptive Advertising,
    // Power Digital, JumpFly" and it became a SINGLE competitor whose name was
    // that whole string. Downstream, `generate_query_set` then had one
    // competitor to build comparison questions from, could not produce the two
    // that leave the client unnamed, and the lint blocked approve with a message
    // about comparison coverage — three steps away from the chip that caused it.
    const parts = draft
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !items.some((existing) => existing.toLowerCase() === s.toLowerCase()));
    if (!parts.length) {
      setDraft("");
      return;
    }
    onChange([...items, ...parts]);
    setDraft("");
  };
  return (
    <div className="flex flex-col gap-1.5">
      {items.length ? (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item, i) => (
            <span
              key={`${item}-${i}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-navy bg-navy px-3 py-[4px] text-[12px] text-white"
            >
              {item}
              <button
                type="button"
                aria-label={`Remove ${item}`}
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              >
                <X className="h-3 w-3" aria-hidden />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <input
        value={draft}
        placeholder={placeholder || "Type and press Enter"}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            commit();
          }
          // Backspace on an empty field removes the last chip — the standard
          // chip-input gesture, and the only way to undo without a mouse.
          if (e.key === "Backspace" && !draft && items.length) {
            onChange(items.slice(0, -1));
          }
        }}
        onBlur={commit}
        className={INPUT_CLS}
      />
    </div>
  );
}

/** Remove one repeatable row.
 *
 * A REPEATABLE CONTROL WITHOUT A DELETE IS A TRAP. "Add another" was the only
 * button on these rows, so a mistyped price row or an "Add another" tapped by
 * accident could be blanked but never removed — and a blank row still renders,
 * still looks like an unanswered question, and is the reason a card that is
 * finished does not look finished.
 *
 * The last row stays: a repeatable control with nothing in it has nowhere to
 * type, and clearing is what the fields are for.
 */
function RemoveRow({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="shrink-0 rounded-md p-1.5 text-harbour transition-colors hover:bg-navy/[0.06] hover:text-navy"
    >
      <X className="h-3.5 w-3.5" aria-hidden />
    </button>
  );
}

function Pairs({
  rows,
  labels,
  onChange,
}: {
  rows: PairRow[];
  labels: [string, string];
  onChange: (rows: PairRow[]) => void;
}) {
  const list = rows.length ? rows : [{ ...EMPTY_PAIR }];
  const edit = (i: number, patch: Partial<PairRow>) =>
    onChange(list.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="flex flex-col gap-1.5">
      {list.map((row, i) => (
        <div key={i} className="flex items-start gap-1.5">
          <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5 sm:grid-cols-2">
            <input
              value={row.a}
              aria-label={labels[0]}
              placeholder={labels[0]}
              onChange={(e) => edit(i, { a: e.target.value })}
              className={INPUT_CLS}
            />
            <input
              value={row.b}
              aria-label={labels[1]}
              placeholder={labels[1]}
              onChange={(e) => edit(i, { b: e.target.value })}
              className={INPUT_CLS}
            />
          </div>
          {list.length > 1 ? (
            <RemoveRow
              label={`Remove row ${i + 1}`}
              onClick={() => onChange(list.filter((_, j) => j !== i))}
            />
          ) : null}
        </div>
      ))}
      {list.length < MAX_ROWS ? (
        <AddRow onClick={() => onChange([...list, { ...EMPTY_PAIR }])} />
      ) : null}
    </div>
  );
}

function PricedRows({
  rows,
  note,
  basisOptions,
  onChange,
  onNoteChange,
}: {
  rows: PricedRow[];
  note: string;
  basisOptions: { value: string; label: string }[];
  onChange: (rows: PricedRow[]) => void;
  onNoteChange: (note: string) => void;
}) {
  const list = rows.length ? rows : [{ ...EMPTY_PRICED }];
  const edit = (i: number, patch: Partial<PricedRow>) =>
    onChange(list.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="flex flex-col gap-1.5">
      {list.map((row, i) => (
        <div key={i} className="flex items-start gap-1.5">
          <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5 sm:grid-cols-[2fr_1fr_1fr_2fr]">
            <input
              value={row.what}
              aria-label="What"
              placeholder="What"
              onChange={(e) => edit(i, { what: e.target.value })}
              className={INPUT_CLS}
            />
            <input
              value={row.price}
              aria-label="Price"
              // Free, From $X, Varies by scope and Quote only are first-class
              // values here, not fallbacks — a business with no fixed price still
              // has a checkable fact to state.
              placeholder="$89 / Free"
              onChange={(e) => edit(i, { price: e.target.value })}
              className={INPUT_CLS}
            />
            {/* THE BASIS IS WHAT MAKES THE PRICE CHECKABLE. "$450" is not a claim
                the judge can grade; "$450 per hour" is. */}
            <select
              value={row.basis}
              aria-label="Basis"
              onChange={(e) => edit(i, { basis: e.target.value })}
              className={INPUT_CLS}
            >
              <option value="">Basis…</option>
              {basisOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <input
              value={row.includes}
              aria-label="What's included"
              placeholder="What's included"
              onChange={(e) => edit(i, { includes: e.target.value })}
              className={INPUT_CLS}
            />
          </div>
          {list.length > 1 ? (
            <RemoveRow
              label={`Remove price row ${i + 1}`}
              onClick={() => onChange(list.filter((_, j) => j !== i))}
            />
          ) : null}
        </div>
      ))}
      {list.length < MAX_ROWS ? (
        <AddRow onClick={() => onChange([...list, { ...EMPTY_PRICED }])} />
      ) : null}

      {/* THE EDGE CASES THE FOUR COLUMNS CANNOT HOLD. "First hour billed at
          1.5x after 6pm", "we bill in 15-minute increments", "materials at cost
          plus 15%" — terms a customer is surprised by, which is exactly the
          class of fact an AI answer gets wrong and the sheet exists to catch.
          Without somewhere to put them they get mangled into the What column or
          left out entirely.

          Optional, and last: the columns are still the better answer when they
          fit, because a price with a basis is checkable and a paragraph is
          harder to grade. */}
      <label className="mt-1 block">
        <span className={FIELD_LABEL_CLS}>Anything else about the pricing</span>
        <span className={cn(FIELD_HINT_CLS, "block")}>
          Optional. For terms the columns don&rsquo;t fit — minimums, surcharges, how you bill.
        </span>
        <textarea
          rows={2}
          value={note}
          placeholder="e.g. after 6pm the first hour is billed at 1.5x"
          onChange={(e) => onNoteChange(e.target.value)}
          className={cn(INPUT_CLS, "mt-1 resize-y leading-normal")}
        />
      </label>
    </div>
  );
}

/** The 7-day grid. CLOSED IS A TOGGLE, NEVER AN EMPTY TIME FIELD — the negative
 * is the whole point of the card, and a blank means "we didn't say", which is a
 * different fact and not ours to assert. */
function Days({
  days,
  labels,
  onChange,
}: {
  days: Record<string, string>;
  labels: { value: string; label: string }[];
  onChange: (days: Record<string, string>) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      {labels.map((day) => {
        const closed = (days[day.value] ?? "").toLowerCase() === "closed";
        return (
          <div key={day.value} className="flex items-center gap-2">
            <span className="w-[84px] shrink-0 text-[12.5px] text-harbour">{day.label}</span>
            <input
              value={closed ? "" : (days[day.value] ?? "")}
              disabled={closed}
              placeholder="8:00 AM to 5:00 PM"
              onChange={(e) => onChange({ ...days, [day.value]: e.target.value })}
              className={cn(INPUT_CLS, "flex-1", closed && "opacity-40")}
            />
            <button
              type="button"
              aria-pressed={closed}
              onClick={() => {
                const next = { ...days };
                if (closed) delete next[day.value];
                else next[day.value] = "closed";
                onChange(next);
              }}
              className={cn(
                "shrink-0 rounded-full px-3 py-[4px] text-[11.5px] transition-colors",
                closed
                  ? "border border-navy bg-navy text-white"
                  : "border border-navy/20 bg-white text-navy hover:bg-navy/[0.04]",
              )}
            >
              Closed
            </button>
          </div>
        );
      })}
    </div>
  );
}

function AddRow({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex w-fit items-center gap-1 text-[11.5px] text-blue hover:underline"
    >
      <Plus className="h-3 w-3" aria-hidden />
      Add another
    </button>
  );
}
