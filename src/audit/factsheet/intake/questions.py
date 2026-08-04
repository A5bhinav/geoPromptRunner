"""The intake question registry: data, no logic.

This is the single source of truth for what the intake asks. The API serves it,
the UI renders it, and neither hardcodes a question — a card that exists in the
frontend but not here is a card whose answer has nowhere to go.

ONE SPINE OF SIXTEEN, FOR EVERY BUSINESS. This registry used to fork:
``BusinessKind`` picked a local branch or a product branch and the two were
maintained separately. That design had three faults and the third one is fatal.
Two half-maintained trees drift. A ``show_if`` graph has to be re-reasoned about
every time a card moves. And it has **no answer at all** for the businesses that
are neither — an agency, a restaurant, a clinic, a nonprofit, a marketplace, a
company that sells software *and* sends technicians. ``business_kind`` is no
longer a router. It picks the *for-instance* line inside a card and the query
allocation afterwards; nothing structural (agent plan §4.1).

THE FOUR RULES THAT GOVERN EVERY ENTRY, because they are why the questions are
worded the way they are and not a nicer way:

1. **Only falsifiable facts.** A price, a licence number, a closing time. Never
   "the leading platform." The judge can only check things that are true or
   false, and a marketing line on the sheet is a line that can never fire.
2. **Blank is safe, and it is the default.** A skipped card produces ZERO
   claims. A dimension the sheet is silent on is not checked, so it can never
   produce a false flag. Coverage is not the metric — fourteen confirmed lines
   beat forty with six guesses. **Every one of the sixteen is skippable**: there
   is no gate question, because a router that cannot be skipped is a router that
   produces guesses.
3. **Negatives are where the value is.** *Closed Sunday.* *No after-hours
   service.* *There is no free option.* These are what make an over-claiming
   answer flaggable. Cards marked ``negative_first`` exist for this and must not
   be reworded into positives by anyone tidying the copy.
4. **The owner always sees the exact sentence they will be quoted on** — which
   is `assertions.py`'s job, and the reason every question here knows which keys
   it produces.

THE MAINTENANCE RULE. If you want to reword a *prompt* for one kind of business,
the prompt is too narrow: widen it and put the specificity in
:class:`Examples`. A question that needed rewriting for a law firm would also
have needed rewriting for the restaurant nobody thought of.

The old ``Q-ID-*``/``Q-LOC-*``/``Q-PRD-*``/``Q-END-*`` ids are gone rather than
aliased. They named a branch that no longer exists, and a stored session that
refers to one is a session from before the spine — its answers key off ids with
no card behind them, which `claims_from_answers` already skips by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.audit.factsheet.models import BusinessKind, SheetSection

__all__ = [
    "AnswerKind",
    "Examples",
    "Option",
    "Part",
    "PartKind",
    "IntakeQuestion",
    "REGISTRY",
    "BY_ID",
    "MAX_CARDS",
    "KEY_LABELS",
    "BASIS_OPTIONS",
    "DAY_LABELS",
    "question",
]


class AnswerKind(StrEnum):
    """How a card collects its answer.

    The UI renders one component per member. A card is not a field: a
    ``batch_confirm`` carries three to five facts and still costs the owner one
    decision, which is what keeps the median session at eleven cards rather than
    sixteen.

    ELEVEN KINDS COVER ALL SIXTEEN CARDS FOR EVERY BUSINESS. The test to apply
    before adding a twelfth is whether one control can hold a plumber's answer
    and a SaaS's answer — ``availability`` and ``priced_rows`` both exist
    because the naive version (a bare 7-day grid, a bare price field) could not.
    """

    CHOICE = "choice"  # 2–4 options, single select; an option may reveal a sub-input
    MULTI = "multi"  # options, multi-select, plus "add your own"
    CONFIRM = "confirm"  # "I found X. Right?" → yes | fix (reveals an input)
    BATCH_CONFIRM = "batch_confirm"  # N pre-filled facts, tap the wrong ones
    TEXT = "text"  # one line
    LONGTEXT = "longtext"  # 2–4 lines
    LIST = "list"  # repeatable chips
    AVAILABILITY = "availability"  # always / set hours / by arrangement; grid only on set hours
    PRICED_ROWS = "priced_rows"  # repeatable {what, price, basis, includes}
    LINKS = "links"  # labelled URL fields
    PAIRS = "pairs"  # repeatable two-field rows


@dataclass(frozen=True, kw_only=True)
class Option:
    value: str
    label: str


@dataclass(frozen=True, kw_only=True)
class Examples:
    """The for-instance line, and THE ONLY THING ``business_kind`` may change.

    Never the prompt, never the helper, never the keys, never whether a card
    appears. ``neutral`` is required and is written to be true of anyone, so an
    unknown business kind is never a broken card.
    """

    neutral: str
    product: str = ""
    local: str = ""

    def pick(self, kind: BusinessKind | None) -> str:
        """The for-instance line for one business kind, falling back to neutral."""
        if kind is BusinessKind.PRODUCT and self.product:
            return self.product
        if kind is BusinessKind.LOCAL_SERVICE and self.local:
            return self.local
        return self.neutral


class PartKind(StrEnum):
    """The control for one sub-field of a composite card."""

    TEXT = "text"
    LIST = "list"
    PAIRS = "pairs"
    CHOICE = "choice"  # an option may reveal a free-text input
    DAYS = "days"  # the 7-day grid, with Closed as a first-class toggle


@dataclass(frozen=True, kw_only=True)
class Part:
    """One sub-control inside a composite card, and the key it writes.

    WHY THIS EXISTS AT ALL. Six of the sixteen cards ask two things — *where do
    you serve* **and** *where don't you*, *what do you hold* **and** *what don't
    you*. Those halves are one card because they are one decision for the owner,
    but they are two shapes for the answer. Without a description of that shape
    in the registry, the frontend has to know which card is which, and the whole
    contract of this module — the UI renders whatever the registry contains and
    hardcodes no question — quietly stops being true.

    A card with parts stores its answer as ``{part.key: value}``.
    """

    key: str
    label: str
    kind: PartKind
    helper: str = ""
    placeholder: str = ""
    #: Column headings for a ``PAIRS`` part.
    labels: tuple[str, str] = ("", "")
    options: tuple[Option, ...] = ()
    #: A ``CHOICE`` option that reveals a free-text input; the typed text is what
    #: gets stored, so "Yes — a $5.99/mo membership" is one value, not two.
    reveal_on: str = ""
    #: ``(sibling_part_key, value)`` — render only when that sibling holds it.
    #: This is the ONLY conditional in the intake, and it is within one card
    #: rather than across cards: a 7-day grid asked of a SaaS is a form nobody
    #: fills, and "which towns" asked of a business that answered "anywhere" is a
    #: question with no answer.
    show_when: tuple[str, str] | None = None


@dataclass(frozen=True, kw_only=True)
class IntakeQuestion:
    """One card.

    ``keys`` are the fact-row keys this card CAN produce — not the ones it will.
    A card that produces nothing (skipped, or answered in a way that yields no
    falsifiable line) is normal and is rule 2 working.
    """

    id: str
    #: Which dimension this card establishes. Purely for grouping in the UI's
    #: launcher; nothing routes on it.
    group: str
    kind: AnswerKind
    prompt: str
    #: The one-line rationale shown in the open-questions launcher. Every card
    #: has one: a question whose point cannot be stated in a line is a question
    #: that should not be asked.
    why: str
    examples: Examples
    #: ``None`` only for a card that produces no claim of its own.
    section: SheetSection | None = None
    keys: tuple[str, ...] = ()
    helper: str = ""
    placeholder: str = ""
    options: tuple[Option, ...] = ()
    #: The sub-controls of a composite card, in render order. Empty means the
    #: card is a single control and ``kind`` alone describes it.
    parts: tuple[Part, ...] = ()
    #: True for all sixteen. Kept as a field rather than deleted because the API
    #: refuses a skip on a card that says it cannot be skipped, and that backstop
    #: should keep working if a future card ever earns the exception.
    skippable: bool = True
    #: "No" is the valuable answer. Lead with it, and never reword to a positive.
    negative_first: bool = False
    #: Some answers are RUN INPUTS, not ground truth: name variants, the city,
    #: the trade. Asserting "Also known as Acme Plumbing." puts a line the judge
    #: cannot falsify in front of it (agent plan §4.4). These cards still get
    #: asked — they feed the query set and the brand roster — they just never
    #: become a FactClaim.
    produces_claims: bool = True


#: The ``basis`` column on ``Q-COST-01``. A PRICE WITH NO BASIS IS UNCHECKABLE:
#: a law firm bills hourly, a SaaS per seat per month, a dentist per visit and a
#: plumber per job, and "450" on its own is not a claim the judge can grade or an
#: AI answer can contradict. This is the four-column fix (questions doc §5.2).
BASIS_OPTIONS: tuple[Option, ...] = (
    Option(value="one_time", label="one-time"),
    Option(value="per_hour", label="per hour"),
    Option(value="per_seat_month", label="per seat/mo"),
    Option(value="per_month", label="per month"),
    Option(value="per_year", label="per year"),
    Option(value="per_visit", label="per visit"),
    Option(value="per_project", label="per project"),
    Option(value="per_unit", label="per unit"),
)


REGISTRY: tuple[IntakeQuestion, ...] = (
    # --- Q-WHAT: who you are, what you're called -----------------------------
    IntakeQuestion(
        id="Q-WHAT-01",
        group="WHAT",
        kind=AnswerKind.BATCH_CONFIRM,
        section=SheetSection.IDENTITY,
        keys=("identity_name", "identity_website", "identity_founded", "identity_category"),
        prompt="Quick check — tap anything that's wrong.",
        why="Four facts in one tap, and the category is what an AI gets asked for.",
        helper="Only what we actually found is shown. Anything blank, we just don't claim.",
        examples=Examples(
            neutral=(
                "“What you'd call it” is the words you'd want an AI to use — "
                "“employment law firm”, not “professional services company”."
            ),
        ),
    ),
    IntakeQuestion(
        id="Q-WHAT-02",
        group="WHAT",
        kind=AnswerKind.LONGTEXT,
        section=SheetSection.IDENTITY,
        keys=("identity_what",),
        prompt="In one sentence, what does {business} actually do?",
        why="This is the line every answer gets measured against.",
        helper=(
            "Plain and factual. Skip the sales language — an AI can't be wrong about "
            "“the best”, only about what you do."
        ),
        placeholder="What you do, who for, and where — one plain sentence",
        examples=Examples(
            neutral="“A two-person design studio doing brand identity for restaurants.”",
            local="“Family-owned plumbing contractor serving the East Bay since 1998.”",
            product="“A smart ring that tracks sleep, recovery and readiness.”",
        ),
    ),
    IntakeQuestion(
        id="Q-WHAT-03",
        group="WHAT",
        kind=AnswerKind.LIST,
        keys=("identity_aliases",),
        prompt="Any other ways people write your name?",
        why="So we count a mention that spells you differently.",
        helper=(
            "Misspellings, your legal name, an old name. We use these to catch a mention "
            "we'd otherwise miss — they aren't fact-checked."
        ),
        placeholder="Type a name and press Enter",
        # A matcher input, never a claim (agent plan §4.4). "Also known as Acme
        # Plumbing." is not falsifiable, and putting it on the sheet spends a
        # line that can never fire — while MISSING a mention scores as absence,
        # which is the most expensive kind of wrong the measurement can be.
        produces_claims=False,
        examples=Examples(
            neutral="“& Sons” vs “and Sons”, an old trading name, the LLC on your paperwork.",
        ),
    ),
    IntakeQuestion(
        id="Q-WHAT-04",
        group="WHAT",
        kind=AnswerKind.LIST,
        section=SheetSection.IDENTITY,
        keys=("identity_not",),
        prompt="Is there anyone people mix you up with?",
        why="One of the things AI gets wrong most often, and one of the easiest to catch.",
        helper="Same-name businesses, a former partner, a company you were spun out of.",
        negative_first=True,
        examples=Examples(
            neutral="a company you were spun out of, someone with a near-identical name.",
            local="a same-name shop two towns over, a franchise you left.",
            product="a competitor with a similar name, a parent company you're not part of.",
        ),
    ),
    # --- Q-OFFER: what you provide -------------------------------------------
    IntakeQuestion(
        id="Q-OFFER-01",
        group="OFFER",
        kind=AnswerKind.LIST,
        section=SheetSection.SERVICES_PRICING,
        keys=("services_offered",),
        prompt="What do you actually offer?",
        why="The list an AI is supposed to be reading off.",
        # CATEGORY LEVEL, NOT SKU LEVEL. The original wording invited a coffee
        # roaster to type 140 SKUs into a chip input: unusable as a control and
        # useless to the judge, which checks whether an AI knows you sell
        # single-origin, not whether it knows the 12oz Ethiopian.
        helper=(
            "Name the level a customer would ask about — the categories, not every "
            "individual item. Ten or so is plenty."
        ),
        examples=Examples(
            neutral=(
                "the services, product lines or practice areas you'd put on a menu. "
                "If you have a catalogue, name the categories."
            ),
            local="drain cleaning, water heater install, repiping, leak detection.",
            product="sleep tracking, HRV, readiness score, the iOS app.",
        ),
    ),
    IntakeQuestion(
        id="Q-OFFER-02",
        group="OFFER",
        kind=AnswerKind.LIST,
        section=SheetSection.SERVICES_PRICING,
        keys=("services_excluded",),
        prompt="What do people ask for that you don't do?",
        # THE SINGLE HIGHEST-VALUE CARD IN THE SET. An invented capability is
        # unflaggable without a negative to contradict it: an omission is never a
        # finding, only a contradiction is.
        why="Without it, nobody can catch an AI volunteering you for work you don't take.",
        helper="The thing you turn down every week.",
        negative_first=True,
        examples=Examples(
            neutral="the thing you turn down every week.",
            local="“No septic work.” “No commercial jobs.” “We don't do new construction.”",
            product="“No Android app.” “No offline mode.” “We're not a CRM.”",
        ),
    ),
    IntakeQuestion(
        id="Q-OFFER-03",
        group="OFFER",
        kind=AnswerKind.PAIRS,
        section=SheetSection.FEATURES,
        keys=("features_current", "features_added", "features_removed"),
        prompt="What's new, and what have you stopped doing?",
        why="The fastest way to catch an AI still describing you as you were last year.",
        helper=(
            "AI training data lags by months. The things you've stopped doing matter most — "
            "an AI recommending a service you dropped sends a customer to a dead end."
        ),
        parts=(
            Part(
                key="current",
                label="Newest version or release, if you have one",
                kind=PartKind.TEXT,
                placeholder="e.g. the Ring 5, released 2026-05-28",
            ),
            Part(
                key="added",
                label="What you've added",
                kind=PartKind.PAIRS,
                labels=("What changed", "When"),
            ),
            # The valuable half. An AI recommending a service you dropped sends a
            # customer to a dead end, and only a "no longer offers" line catches it.
            Part(
                key="removed",
                label="What you've stopped doing",
                kind=PartKind.PAIRS,
                labels=("What you stopped", "When"),
            ),
        ),
        examples=Examples(
            neutral="a new location, a new service line, a price change, something you retired.",
            local="“Added emergency water damage, March.” “Stopped duct cleaning, January.”",
            product="“Ring 5 shipped, May 28.” “Retired the Basic plan, February.”",
        ),
    ),
    # --- Q-COST: what it costs ------------------------------------------------
    IntakeQuestion(
        id="Q-COST-01",
        group="COST",
        kind=AnswerKind.PRICED_ROWS,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_rows",),
        prompt="What does it cost?",
        why="Prices are the single most-hallucinated thing about any business.",
        helper=(
            "Exact numbers, today's. “Free”, “From $X”, “Varies by scope” and “Quote only” "
            "are all real answers."
        ),
        examples=Examples(
            neutral="“Partner time · $450 · per hour”. One row per thing that has a price.",
            local="“Diagnostic visit · $89 · per visit · applied to the repair”.",
            product="“Premium · $499 · one-time · plus membership”.",
        ),
    ),
    IntakeQuestion(
        id="Q-COST-02",
        group="COST",
        kind=AnswerKind.CHOICE,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_mandatory_extra", "pricing_free_option"),
        prompt="Is there anything people have to pay on top of that?",
        # THE MOST DEMO-ABLE CLAIM THE SYSTEM CAN MAKE. A required $5.99/mo
        # membership on top of a $399 ring is the canonical case, and every kind
        # of business has its own version of it.
        why="AI quotes the headline price and misses this constantly.",
        helper=(
            "And: is there a free option — a free tier, a free trial, a free consult, "
            "free shipping? “No” is a valuable answer to both."
        ),
        parts=(
            Part(
                key="extra",
                label="Anything paid on top",
                kind=PartKind.CHOICE,
                options=(
                    Option(value="no", label="No, that's the full price"),
                    Option(value="yes", label="Yes —"),
                ),
                reveal_on="yes",
                placeholder="What it is, and what it costs",
            ),
            Part(
                key="free",
                label="A free option — free tier, trial, consult, shipping",
                kind=PartKind.CHOICE,
                options=(
                    Option(value="no", label="No"),
                    Option(value="yes", label="Yes —"),
                ),
                reveal_on="yes",
                placeholder="e.g. 30-minute consult, shipping over $50",
            ),
        ),
        negative_first=True,
        examples=Examples(
            neutral="anything that surprises someone at checkout.",
            local="a trip charge outside the city, a weekend surcharge, a minimum callout.",
            product="a required membership, an activation fee, a mandatory add-on.",
        ),
    ),
    # --- Q-REACH: how to get you ---------------------------------------------
    IntakeQuestion(
        id="Q-REACH-01",
        group="REACH",
        kind=AnswerKind.BATCH_CONFIRM,
        section=SheetSection.CONTACT,
        keys=(
            "contact_phone",
            "contact_email",
            "contact_booking",
            "contact_address",
            "contact_none",
            "contact_retired",
        ),
        prompt="This is the most important card here — tap anything that's wrong.",
        why="A wrong way to reach you is a customer you never hear about.",
        # ROWS ARE WHATEVER CHANNELS EXIST, never four fixed fields — four fixed
        # rows left a software company with three empty ones and no way to say
        # the thing that is both true and valuable: THERE IS NO PHONE LINE. An AI
        # inventing a support number for a SaaS is a real and frequent failure,
        # and it is completely unflaggable unless the absence is asserted.
        helper=(
            "“We don't have a phone line” and “no public address” are real answers here, "
            "and good ones. Then: any old number, address or link still floating around?"
        ),
        # The card opens as a confirm, but its VALUE is in the two negative
        # halves — the absent channel and the retired one. Both are bolded in the
        # flag-type table as the only producers `wrong_contact` has, so this
        # carries the flag that keeps a tidy-up from rewording them away.
        negative_first=True,
        parts=(
            Part(key="contact_phone", label="Phone", kind=PartKind.TEXT),
            Part(key="contact_email", label="Email", kind=PartKind.TEXT),
            Part(key="contact_booking", label="Booking or support link", kind=PartKind.TEXT),
            Part(key="contact_address", label="Address", kind=PartKind.TEXT),
            Part(
                key="none",
                label="We don't have one of these",
                kind=PartKind.LIST,
                helper="phone · email · booking · address",
                placeholder="phone",
            ),
            Part(
                key="retired",
                label="Old numbers, addresses or links still online",
                kind=PartKind.LIST,
                placeholder="(510) 555-0100",
            ),
        ),
        examples=Examples(
            neutral="a disconnected line, a previous office, a support address you retired.",
            local="the old number still on a directory listing after you moved.",
            product=(
                "“We don't have a phone line” is a valuable answer — an AI inventing a "
                "support number can't be caught unless you say so."
            ),
        ),
    ),
    IntakeQuestion(
        id="Q-REACH-02",
        group="REACH",
        kind=AnswerKind.CHOICE,
        section=SheetSection.SERVICE_AREA,
        keys=("service_area_scope", "service_area_included", "service_area_excluded"),
        prompt="Where can people get you?",
        why="So a “near me” answer can be checked against a real boundary.",
        # WIDENED FROM GEOGRAPHY TO JURISDICTION. For a regulated profession
        # "where do you serve" means "where are you admitted to practise", and an
        # AI telling someone a firm can take their out-of-state matter is a
        # liability rather than an inconvenience.
        helper=(
            "Then: anywhere you don't serve — or aren't licensed to? Without that, nobody "
            "can catch an AI promising someone in the next county that you'll cover them."
        ),
        parts=(
            Part(
                key="scope",
                label="Where can people get you",
                kind=PartKind.CHOICE,
                options=(
                    Option(value="anywhere", label="Anywhere"),
                    Option(value="places", label="Specific places"),
                ),
            ),
            Part(
                key="included",
                label="Which ones",
                kind=PartKind.LIST,
                show_when=("scope", "places"),
            ),
            Part(
                key="city",
                label="Home city",
                kind=PartKind.TEXT,
                helper="The run is anchored here. Not asserted — it's a query input, not a fact.",
                show_when=("scope", "places"),
            ),
            # SPELLED OUT, NEVER ABBREVIATED. `_ABBREVIATED_REGION_RE` rejects
            # "CA", and the SERP vendors answer an abbreviation with an EMPTY
            # local surface — which reads downstream as the brand being absent
            # rather than as a bad request.
            Part(
                key="region",
                label="State",
                kind=PartKind.TEXT,
                helper="Spelled out in full — “California”, not “CA”.",
                show_when=("scope", "places"),
            ),
            Part(
                key="excluded",
                label="Anywhere you don't serve, or aren't licensed to",
                kind=PartKind.LIST,
            ),
        ),
        negative_first=True,
        examples=Examples(
            neutral="the boundary you'd have to explain on a phone call.",
            local="“Berkeley, Oakland, Albany, El Cerrito.” Not: “Marin County.”",
            product="“Anywhere.” Not: “We don't ship to the EU.”",
        ),
    ),
    IntakeQuestion(
        id="Q-REACH-03",
        group="REACH",
        kind=AnswerKind.AVAILABILITY,
        section=SheetSection.HOURS,
        keys=(
            "hours_scope",
            "hours_monday",
            "hours_tuesday",
            "hours_wednesday",
            "hours_thursday",
            "hours_friday",
            "hours_saturday",
            "hours_sunday",
            "hours_after_hours",
        ),
        # "REACH A PERSON", not "available". Without that word a SaaS answers
        # "always" — truthfully, about a self-serve product — and the claim reads
        # as "support is reachable at 3am", which is false and which we would
        # then send to a stranger. Self-serve availability is not support
        # availability and only one of them is a fact a customer acts on.
        prompt="When can someone actually reach a person?",
        why="AI invents round-the-clock cover constantly.",
        helper=(
            "This is about reaching a person, not whether the product is up. Be blunt about "
            "the gaps — “closed Sunday” and “no weekend support” are the same answer."
        ),
        parts=(
            Part(
                key="scope",
                label="When someone can reach a person",
                kind=PartKind.CHOICE,
                options=(
                    Option(value="always", label="Any time — round the clock"),
                    Option(value="set_hours", label="Set hours"),
                    Option(value="by_arrangement", label="By appointment or arrangement"),
                ),
            ),
            # THE GRID RENDERS ONLY ON "SET HOURS". Seven rows asked of a
            # software company is a form nobody fills; a shop still gets its grid
            # and a 24/7 self-serve business answers in one tap.
            Part(
                key="days",
                label="Which days, and which are you closed",
                kind=PartKind.DAYS,
                helper="Closed is an answer, and it's the valuable one.",
                show_when=("scope", "set_hours"),
            ),
            Part(
                key="after_hours",
                label="Anything outside those hours — emergency, on-call, after-hours",
                kind=PartKind.CHOICE,
                options=(
                    Option(value="no", label="No"),
                    Option(value="yes_same_rate", label="Yes, same rate"),
                    Option(value="yes_surcharge", label="Yes, costs more"),
                ),
            ),
        ),
        negative_first=True,
        examples=Examples(
            neutral="the day and time someone would try you and get nothing.",
            local="closed Sunday, no after-hours.",
            product="self-serve any time, support 9–5 Eastern, weekdays only.",
        ),
    ),
    # --- Q-PROOF: what you can prove, who you're up against -------------------
    IntakeQuestion(
        id="Q-PROOF-01",
        group="PROOF",
        kind=AnswerKind.PAIRS,
        section=SheetSection.LICENSING,
        keys=("licensing_credentials", "licensing_not_held"),
        prompt="Anything you're licensed, certified or accredited for?",
        # `licensing` is declared, titled and never emitted anywhere else in the
        # system — this card is its only producer. And it generalizes further
        # than the enum name suggests: a CSLB number and a SOC 2 report are the
        # same dimension, checked the same way, with the same consequence.
        why="An AI claiming a credential you don't have is a real liability.",
        helper=(
            "A licence, an insurance policy, an industry body, a compliance report. "
            "Then: anything people assume you hold that you don't?"
        ),
        parts=(
            Part(
                key="credentials",
                label="What you hold",
                kind=PartKind.PAIRS,
                labels=("What you hold", "Who issued it"),
            ),
            # The liability guard. An AI asserting a credential the business does
            # not hold is the expensive direction of this error.
            Part(
                key="not_held",
                label="Anything people assume you hold that you don't",
                kind=PartKind.LIST,
            ),
        ),
        examples=Examples(
            neutral="a licence, an insurance policy, an industry body, a compliance report.",
            local="“Licence 123456 · CSLB”, “Bonded and insured”, “EPA 608”.",
            product="“SOC 2 Type II · Prescient”, “CE mark”, “Not HIPAA compliant”.",
        ),
    ),
    IntakeQuestion(
        id="Q-PROOF-02",
        group="PROOF",
        kind=AnswerKind.LIST,
        section=SheetSection.POSITIONING,
        # NEVER "who are your competitors". A nonprofit, a law firm and a solo
        # practice all answer "nobody, really" — which produces an empty list and
        # breaks a hard downstream constraint: every competitor named here must
        # appear in at least one comparison query, so an empty list leaves the
        # comparison bucket measuring nothing.
        prompt="If someone didn't pick you, who else would they be looking at?",
        keys=("positioning_competitors", "positioning_for"),
        why="Every name here gets its own comparison question.",
        helper=(
            "We'll ask the AIs about each of these by name, so this list decides a good "
            "chunk of what gets measured. Then: and who is it for?"
        ),
        parts=(
            Part(
                key="competitors",
                label="Who else they'd look at",
                kind=PartKind.LIST,
            ),
            Part(key="for", label="And who is it for", kind=PartKind.TEXT),
        ),
        examples=Examples(
            neutral="who you lose deals to — or who else does what you do.",
            local="the three other shops that show up when someone searches your trade.",
            product="the names on a buyer's shortlist next to yours.",
        ),
    ),
    # --- Q-AI: what AI already gets wrong ------------------------------------
    IntakeQuestion(
        id="Q-AI-01",
        group="AI",
        kind=AnswerKind.PAIRS,
        section=SheetSection.WATCHLIST,
        keys=("watchlist",),
        prompt="Have you ever seen ChatGPT or Google's AI say something wrong about you?",
        why="Usually the first thing we go and check.",
        helper="Anything you've already caught.",
        parts=(
            Part(
                key="watchlist",
                label="What you've seen",
                kind=PartKind.PAIRS,
                labels=("What did it say", "What's actually true"),
            ),
        ),
        negative_first=True,
        examples=Examples(
            neutral="something a customer quoted back at you that wasn't right.",
        ),
    ),
    IntakeQuestion(
        id="Q-AI-02",
        group="AI",
        kind=AnswerKind.LONGTEXT,
        section=SheetSection.WATCHLIST,
        keys=("watchlist_other",),
        prompt="Anything else an AI could get wrong about you?",
        why="The catch-all. Often the best line on the sheet.",
        helper="Last one. Skip it if nothing comes to mind.",
        examples=Examples(
            neutral="the thing you'd correct if you overheard someone describing you.",
        ),
    ),
)


#: What a multi-key card calls each of its fields. Here rather than in the
#: frontend for the same reason the prompts are: the UI renders whatever the
#: registry contains, and a label that lives only in TypeScript is a label that
#: drifts from the key it names.
KEY_LABELS: dict[str, str] = {
    "identity_name": "Business name",
    "identity_website": "Website",
    "identity_founded": "In business since",
    "identity_category": "What you'd call it",
    "contact_phone": "Phone",
    "contact_email": "Email",
    "contact_booking": "Booking or support link",
    "contact_address": "Address",
    "contact_none": "We don't have one of these",
    "contact_retired": "Old contact details still online",
    "service_area_scope": "Where you can be got",
    "service_area_included": "Places you serve",
    "service_area_excluded": "Places you don't serve, or aren't licensed for",
    "hours_scope": "When someone can reach a person",
    "hours_after_hours": "Out-of-hours cover",
    "features_current": "Current version",
    "features_added": "Added lately",
    "features_removed": "Stopped doing",
    "pricing_rows": "Prices",
    "pricing_mandatory_extra": "Paid on top",
    "pricing_free_option": "Free option",
    "licensing_credentials": "What you hold",
    "licensing_not_held": "What you don't hold",
    "positioning_competitors": "Who else they'd look at",
    "positioning_for": "Who it's for",
}

#: The 7-day grid's rows, in the order a week is read. Here rather than in the
#: frontend for the same reason everything else is: `assertions.py` matches on
#: these names, and a grid that emitted "Tues" would produce no claim at all.
DAY_LABELS: tuple[tuple[str, str], ...] = (
    ("monday", "Monday"),
    ("tuesday", "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday", "Thursday"),
    ("friday", "Friday"),
    ("saturday", "Saturday"),
    ("sunday", "Sunday"),
)

BY_ID: dict[str, IntakeQuestion] = {q.id: q for q in REGISTRY}

#: The ceiling on one session, and also the floor: sixteen cards, always, for
#: every business. There is no trimming pass any more — the old one existed
#: because trunk-plus-branch-plus-tail could overrun a budget, and one spine
#: cannot. The median session is shorter than sixteen *decisions* because the two
#: batch-confirm cards carry four facts each.
MAX_CARDS = 16


def question(question_id: str) -> IntakeQuestion:
    """One question by id. Raises rather than returning None: every caller here
    has already been handed the id BY this registry, so a miss is a bug in the
    caller and a `None` would surface it three frames later as an attribute
    error on the wrong object."""
    try:
        return BY_ID[question_id]
    except KeyError:
        raise KeyError(f"no intake question {question_id!r} in the registry") from None
