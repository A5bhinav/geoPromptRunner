# Gold-Set Labeling Guide (Google Sheets)

*Step-by-step instructions for the hand-labeling session. Keep this and the client fact sheet open while you label. These definitions are also the source of truth for the judge's prompt — when you make a ruling on an ambiguous case, write it down (notes column); it becomes a rule.*

---

## One-time Sheet setup (5 minutes)

1. **Import** `docs/gold-set-template.csv` into Google Sheets (File → Import → Upload).
2. **Freeze row 1** (View → Freeze → 1 row).
3. **Add dropdowns** (Data → Data validation) so typos can't corrupt the labels:
   - `present` → `yes`, `no`
   - `prominence` → `recommended_first`, `mid_pack`, `buried`, `also_ran`, `absent`
   - `framing` → `positive`, `neutral`, `negative`
   - `expect_accuracy_flags` → `true`, `false`
4. Widen `answer_text`; turn on text wrap for it.

**The unit of work:** one row = one brand within one answer. A single answer with the client + 3 competitors = 4 rows sharing the same `item_id`. Label **every** brand row, even when the brand is absent — absence is a recorded judgment, not a skipped row.

---

## The columns

### Identification (pre-filled — don't edit)
`item_id` · `engine` · `intent` · `query` · `answer_text`. If you spot a brand in the answer that isn't in the competitor set (e.g., Apple Watch shows up), **add a row** for it with a note "auto-discovered."

### `is_client`
`yes` on the client's row, `no` on everyone else's. Only client rows get `expect_accuracy_flags`.

### `present` — is the brand mentioned at all?
- `yes` if a reader would register that the brand/product was referenced. Name variants, obvious misspellings, and product names count ("Oura Ring" = Oura).
- `no` if it never appears.
- Edge rule: appearing **only** inside a URL or citation link, never in the prose → still `yes`, note it.
- **Disavowal rule — the "unknown brand" case → `no` / `absent`.** If the model is asked about a brand and responds that it doesn't recognize it or has no information ("there isn't a widely known device called X," "I don't have specific information about X," "a product that launched after my training data"), mark **`present = no`** (`prominence = absent`, `framing = neutral`). The name appears only because the user typed it — the model never surfaced the brand as a known entity, so counting it as present would inflate the visibility number. This is a **knowledge gap, not an accuracy flag** (no false claim about the brand → `expect_accuracy_flags = false`). Note it as "disavowal — model doesn't know the brand"; for a **pre-launch or obscure client this is the headline visibility finding**, so flag it for the report rather than skipping it.
- **Contrast — hallucination → `yes` + flags.** If instead the model *invents* the brand (makes up a product name, features, form factor, or pricing), that IS `present` — often `recommended_first` if the answer is built around it — **and** every invented claim is an accuracy flag (`identity` / `missing_or_invented_feature` / `competitor_confusion`). The line is: *blank slate* ("I don't know it") = absent; *confident fabrication* = present + flagged. (Example: an answer that disavows "Fort" is absent; an answer that reviews a made-up "Fortis by Fort Strength" is present + flagged.)

### `prominence` — how the brand ranks *within this answer*
Relative to the other brands in the same answer, not across answers. Pick exactly one:

| Label | Meaning | The test |
|---|---|---|
| `recommended_first` | The answer's primary recommendation | Named as the top/best pick, or the lead recommendation the answer is built around. An explicit "X is the best" beats position — if it's listed second but called the winner, it's still `recommended_first`. |
| `mid_pack` | One of several solid options | Presented alongside others with comparable weight — no special elevation, no put-down. |
| `buried` | Mentioned, but an afterthought | Appears late or in passing, little detail: "…others include X." The answer doesn't engage with it. |
| `also_ran` | Mentioned and *demoted* | Explicitly framed as lesser: "X exists but is pricier / weaker / only on iOS." The difference from `buried`: buried is *ignored*, also_ran is *put down*. |
| `absent` | Not mentioned | Use **if and only if** `present = no`. |

Tie-breaker: if you're stuck between two adjacent labels, ask "what would the buyer take away about this brand's standing?" and pick the one matching that takeaway. Then record the ruling in notes.

### `framing` — the answer's attitude toward the brand
- `positive` — endorsed, praised, recommended ("excellent for students").
- `neutral` — mentioned factually, no clear valence. **Absent brands always get `neutral`** (system convention — there is no "n/a").
- `negative` — criticized or warned against ("avoid X," "X has gotten expensive").
- Mixed praise-and-criticism ("great app, but pricey"): judge the overall thrust; if genuinely balanced, `neutral` + a note.
- Framing and prominence are independent: a brand can be `also_ran` + `neutral` (dismissed without criticism) or `recommended_first` + `negative` is near-impossible — if you hit one, note it.

### `expect_accuracy_flags` — client rows only
Compare every claim the answer makes **about the client** to the fact sheet:
- `true` — at least one claim contradicts the fact sheet (wrong price, missing-but-real feature, invented feature, confused with a competitor, stale version/model, wrong identity facts).
- `false` — everything it says checks out, **or** it says nothing checkable about the client.
- Leave **blank** if this item has no fact sheet (accuracy isn't assessed for it).
- Critical rule: only count claims **checkable against the fact sheet**. If the answer claims something the sheet doesn't cover, that is *not* a flag — note it as a candidate fact-sheet addition instead.

### `notes` — the column that compounds in value
Use it for: the *specific* expected flags with their type (`wrong_pricing`, `missing_or_invented_feature`, `competitor_confusion`, `identity`, `stale`) — calibration v1 only checks the true/false, but these notes power type-level calibration later; "LOSING QUERY" when the client is absent but a competitor is present; "auto-discovered" brands; and **every ambiguity ruling you make** — those become the judge's prompt rules.

---

## Session rules

1. **Read the whole answer once before labeling anything.** Prominence is relative — you can't place anyone until you've seen everyone.
2. **Finish one answer completely** (all its brand rows) before moving to the next. Context-switching produces inconsistent calls.
3. **Fact sheet open beside you** for every client row.
4. **Decide, don't agonize.** ~3 minutes per answer. When a call is genuinely 50/50, pick one, write the ruling in notes, move on. A documented imperfect rule beats an undocumented perfect instinct.
5. **Calibrate each other first:** both label the same 5–10 answers independently, compare, and reconcile definitions *before* splitting the rest. If you two disagree on a label, the judge can't be graded on it.
6. **Don't consult any AI about what a label should be.** The entire value of this set is that it's independent human judgment — the answer key for grading the AI.
7. **When done: stop editing.** Export → hand it over → it gets converted to the system's JSON, frozen, and date-stamped. 3–5 of the clearest items get held aside as judge-prompt examples and excluded from scoring.

---

## Worked example

Answer (ChatGPT, "best smart ring 2026"): *"Top smart rings in 2026 are Oura and Samsung Galaxy Ring. The Oura Ring 4 ($349) is best for sleep, though it needs a $5.99/mo membership. The Galaxy Ring ($399) is a strong no-subscription alternative. Ultrahuman's Ring Air is also worth a look for battery."*

| brand | is_client | present | prominence | framing | expect_accuracy_flags | notes |
|---|---|---|---|---|---|---|
| Oura | yes | yes | recommended_first | positive | true | stale: Ring 4 presented as newest (Ring 5 launched 2026-05-28) |
| Samsung Galaxy Ring | no | yes | mid_pack | positive | | |
| Ultrahuman | no | yes | buried | neutral | | "also worth a look" — engaged with briefly, not demoted → buried not also_ran |
| Whoop | no | no | absent | neutral | | |

Why these calls: Oura is called "best" → `recommended_first` even though pricing criticism exists (overall thrust positive). The membership mention is *accurate* per the fact sheet, so it's not a flag — but "Ring 4 as newest" contradicts the sheet → `expect_accuracy_flags = true` with the specific stale-info note. Ultrahuman gets one engaged-but-brief sentence → `buried`, and the reasoning is recorded.
