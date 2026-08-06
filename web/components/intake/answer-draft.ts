import {
  fromPayload,
  hasContent,
  isStructuredKind,
  summarize,
  toPayload,
  type StructuredValue,
} from "@/components/intake/structured-answer";
import type { IntakeQuestion } from "@/lib/api";

/**
 * One card's answer, in flight — and the only place that knows how a card's
 * controls turn into what `/answer` stores.
 *
 * THREE SURFACES ANSWER THE SAME SIXTEEN CARDS: the composer in the
 * conversation, the editor on the review screen, and a crawl that pre-fills a
 * card before anyone has looked at it. They had three different opinions about
 * what a `list` card submits, which is exactly the drift the registry exists to
 * prevent on the server side. One module, one shape.
 *
 * A SEED IS A SEED, WHATEVER FILLED IT. `seedDraft` takes the stored-answer
 * shape and does not care whether it came from the owner ten minutes ago or from
 * `prefill_answer` reading their JSON-LD — which is what lets a crawled card and
 * a re-answered card be the same code path rather than two that agree by
 * accident.
 */

export interface Draft {
  /** `batch_confirm` / `links` — one value per registry key. */
  fields: Record<string, string>;
  /** `choice` / `confirm` / `multi` — the selected option ids. */
  picked: string[];
  /** `list` / `multi` — the chips. `text` / `longtext` use `typed`. */
  items: string[];
  typed: string;
  /** Composite and `priced_rows` cards. */
  structured: StructuredValue;
}

export const EMPTY_DRAFT: Draft = {
  fields: {},
  picked: [],
  items: [],
  typed: "",
  structured: {},
};

const asStrings = (v: unknown): string[] =>
  Array.isArray(v) ? v.map((x) => String(x ?? "")).filter(Boolean) : [];

/** Chips, not a comma-split textarea — for the cards that are ONLY a list.
 *
 * BOTH OF THESE MUST EXCLUDE COMPOSITE CARDS, and forgetting it renders the card
 * twice. `Q-REACH-01` is `batch_confirm` AND has parts; `Q-PROOF-02` is `list`
 * AND has parts. A composite card is drawn by `StructuredAnswer` from its parts,
 * so a second test on `kind` alone drew Phone/Email/Booking/Address a second time
 * underneath the first — two sets of inputs for one answer, and only one of them
 * wired to anything.
 */
export const usesChips = (q: IntakeQuestion): boolean =>
  !isStructuredKind(q) && (q.kind === "list" || q.kind === "multi");

export const usesFields = (q: IntakeQuestion): boolean =>
  !isStructuredKind(q) && (q.kind === "batch_confirm" || q.kind === "links");

/** A stored (or crawled) answer, back in its controls. */
export function seedDraft(q: IntakeQuestion, value: unknown): Draft {
  if (isStructuredKind(q)) return { ...EMPTY_DRAFT, structured: fromPayload(q, value) };

  if (usesFields(q)) {
    const held = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
    return {
      ...EMPTY_DRAFT,
      fields: Object.fromEntries(q.keys.map((k) => [k, String(held[k] ?? "")])),
    };
  }

  if (usesChips(q)) {
    const ids = new Set(q.options.map((o) => o.value));
    const all = asStrings(value);
    // An option that was tapped comes back as a pill; anything typed comes back
    // as a chip. Both were stored in the same array.
    return {
      ...EMPTY_DRAFT,
      picked: all.filter((v) => ids.has(v)),
      items: all.filter((v) => !ids.has(v)),
    };
  }

  if (q.kind === "choice" || q.kind === "confirm") {
    const held = String(value ?? "");
    const ids = new Set(q.options.map((o) => o.value));
    return ids.has(held)
      ? { ...EMPTY_DRAFT, picked: [held] }
      : { ...EMPTY_DRAFT, typed: held };
  }

  return { ...EMPTY_DRAFT, typed: String(value ?? "") };
}

/** What `/answer` stores. */
export function draftValue(q: IntakeQuestion, draft: Draft): unknown {
  if (isStructuredKind(q)) return toPayload(q, draft.structured);
  if (usesFields(q)) {
    // A key left blank is ABSENT, not empty. A fact nobody filled in is not a
    // fact anybody confirmed, and an empty string would assert nothing.
    return Object.fromEntries(
      q.keys.map((k) => [k, (draft.fields[k] ?? "").trim()]).filter(([, v]) => v),
    );
  }
  if (usesChips(q)) return [...draft.picked, ...draft.items];
  if (q.kind === "choice" || q.kind === "confirm") return draft.picked[0] ?? draft.typed.trim();
  return draft.typed.trim();
}

/** The owner's own words — this becomes the claim's verbatim quote, so it is
 * never a serialized array. */
export function draftRaw(q: IntakeQuestion, draft: Draft): string {
  if (isStructuredKind(q)) return summarize(q, draft.structured);
  if (usesFields(q)) {
    return q.keys
      .map((k) => [q.keyLabels[k] ?? k, (draft.fields[k] ?? "").trim()] as const)
      .filter(([, v]) => v)
      .map(([label, v]) => `${label}: ${v}`)
      .join(" · ");
  }
  const labels = new Map(q.options.map((o) => [o.value, o.label]));
  const chosen = draft.picked.map((p) => labels.get(p) ?? p);
  if (usesChips(q)) return [...chosen, ...draft.items].join(", ");
  if (chosen.length && draft.typed.trim()) return `${chosen.join(", ")} — ${draft.typed.trim()}`;
  return chosen.join(", ") || draft.typed.trim();
}

/** An untouched card must not commit — it would be a skip pretending to be an
 * answer, and a skip is the honest version of that. */
export function draftIsEmpty(q: IntakeQuestion, draft: Draft): boolean {
  if (isStructuredKind(q)) return !hasContent(q, draft.structured);
  const value = draftValue(q, draft);
  if (Array.isArray(value)) return value.length === 0;
  if (value && typeof value === "object") return Object.keys(value).length === 0;
  return !String(value ?? "").trim();
}
