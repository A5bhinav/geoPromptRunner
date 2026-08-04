"""The intake question registry: data, no logic.

This is the single source of truth for what the intake asks. The API serves it,
the UI renders it, and neither hardcodes a question — a card that exists in the
frontend but not here is a card whose answer has nowhere to go.

THE FOUR RULES THAT GOVERN EVERY ENTRY (plan §1.6), because they are why the
questions are worded the way they are and not a nicer way:

1. **Only falsifiable facts.** A price, a licence number, a closing time. Never
   "the leading platform." The judge can only check things that are true or
   false, and a marketing line on the sheet is a line that can never fire.
2. **Blank is safe, and it is the default.** A skipped card produces ZERO
   claims. A dimension the sheet is silent on is not checked, so it can never
   produce a false flag. Coverage is not the metric — fourteen confirmed lines
   beat forty with six guesses.
3. **Negatives are where the value is.** *Closed Sunday.* *No after-hours
   service.* *There is no free tier.* These are what make an over-claiming
   answer flaggable. Cards marked ``negative_first`` exist for this and must not
   be reworded into positives by anyone tidying the copy.
4. **The owner always sees the exact sentence they will be quoted on** — which
   is `assertions.py`'s job, and the reason every question here knows which keys
   it produces.

Numbering has deliberate gaps (Q-ID-04, Q-ID-07, Q-LOC-05, Q-PRD-10). Those
questions were folded into neighbouring cards; the ids stay reserved so that
restoring one later does not renumber anything a stored session refers to.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from src.audit.factsheet.models import BusinessKind, SheetSection

__all__ = [
    "AnswerKind",
    "Option",
    "IntakeQuestion",
    "REGISTRY",
    "BY_ID",
    "TRUNK",
    "LOCAL_BRANCH",
    "PRODUCT_BRANCH",
    "TAIL",
    "MAX_CARDS",
    "question",
]


class AnswerKind(StrEnum):
    """How a card collects its answer.

    The UI renders one component per member. A card is not a field: a
    ``batch_confirm`` carries three to five facts and still costs the owner one
    decision, which is what keeps the median session at thirteen cards rather
    than thirty.
    """

    CHOICE = "choice"  # 2–4 options, single select
    MULTI = "multi"  # options, multi-select, plus "add your own"
    CONFIRM = "confirm"  # "I found X. Right?" → yes | fix (reveals an input)
    BATCH_CONFIRM = "batch_confirm"  # N pre-filled facts, tap the wrong ones
    TEXT = "text"  # one line
    LONGTEXT = "longtext"  # 2–4 lines
    LIST = "list"  # repeatable chips
    HOURS = "hours"  # 7-day grid, per-day open/closed
    MONEY = "money"  # currency, auto-stamped "as of"
    TIERS = "tiers"  # repeatable {name, price, includes}
    LINKS = "links"  # labelled URL fields
    WATCHLIST = "watchlist"  # repeatable {what the AI said, what is true}


@dataclass(frozen=True, kw_only=True)
class Option:
    value: str
    label: str


@dataclass(frozen=True, kw_only=True)
class IntakeQuestion:
    """One card.

    ``keys`` are the fact-row keys this card CAN produce — not the ones it will.
    A card that produces nothing (skipped, or answered in a way that yields no
    falsifiable line) is normal and is rule 2 working.
    """

    id: str
    kind: AnswerKind
    prompt: str
    #: The one-line rationale shown in the open-questions launcher. Every card
    #: has one: a question whose point cannot be stated in a line is a question
    #: that should not be asked.
    why: str
    #: ``None`` for a routing card that produces no claim of its own.
    section: SheetSection | None = None
    keys: tuple[str, ...] = ()
    helper: str = ""
    placeholder: str = ""
    options: tuple[Option, ...] = ()
    #: ``False`` only where the rest of the plan cannot be built without it.
    skippable: bool = True
    #: "No" is the valuable answer. Lead with it, and never reword to a positive.
    negative_first: bool = False
    #: Which branch this belongs to. ``None`` means everyone is asked.
    branch: BusinessKind | None = None
    #: ``(question_id, expected_value)`` — the card renders only when that
    #: earlier answer matches.
    show_if: tuple[str, str] | None = None
    #: Some answers are RUN INPUTS, not ground truth: name variants, the trade,
    #: the state. Asserting "Also known as Acme Plumbing." puts a line the judge
    #: cannot falsify in front of it (plan §4.4). These cards still get asked —
    #: they feed the query set and the brand roster — they just never become a
    #: FactClaim.
    produces_claims: bool = True
    #: Drop order when a plan would exceed MAX_CARDS: the HIGHEST rank goes
    #: first. 0 means "never dropped" — everything load-bearing sits there.
    drop_rank: int = 0


# --- Trunk: asked of everyone -------------------------------------------------

TRUNK: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        id="Q-ID-01",
        kind=AnswerKind.CHOICE,
        section=SheetSection.IDENTITY,
        keys=("identity_kind",),
        prompt=(
            "Let's start simple — is {business} a local business people call or visit, "
            "or something people buy online?"
        ),
        why="It changes every question after it.",
        options=(
            Option(value="local_service", label="A local business people call or visit"),
            Option(value="product", label="Something people buy online"),
        ),
        # Not skippable: it routes the whole tree. There is no sensible plan to
        # build without it, so "skip" would mean "end the session".
        skippable=False,
    ),
    IntakeQuestion(
        id="Q-ID-02",
        kind=AnswerKind.BATCH_CONFIRM,
        section=SheetSection.IDENTITY,
        keys=("identity_name", "identity_website", "identity_founded", "identity_category"),
        prompt="Here's what I found on your site. Anything wrong?",
        why="Four facts, one tap. Wrong ones are the expensive ones.",
        helper="Tap anything that's wrong and fix it. Leave the rest.",
    ),
    IntakeQuestion(
        id="Q-ID-03",
        kind=AnswerKind.LONGTEXT,
        section=SheetSection.IDENTITY,
        keys=("identity_what",),
        prompt=(
            "In one sentence, what does the business actually do? "
            "Plain and factual — no “best in town.”"
        ),
        why="This is the line every answer gets measured against.",
        placeholder="Family-owned plumbing and heating contractor serving the East Bay since 1982",
    ),
    IntakeQuestion(
        id="Q-ID-05",
        kind=AnswerKind.LIST,
        keys=("identity_aliases",),
        prompt="Any other names you go by? Legal name, a DBA, a common misspelling.",
        why="So we count a mention that spells you differently.",
        # A matcher input, never a claim (plan §4.4). "Also known as Acme
        # Plumbing." is not falsifiable, and putting it on the sheet spends a
        # line that can never fire.
        produces_claims=False,
        drop_rank=2,
    ),
    IntakeQuestion(
        id="Q-ID-06",
        kind=AnswerKind.LIST,
        section=SheetSection.IDENTITY,
        keys=("identity_not",),
        prompt="Who do people mix you up with?",
        why="Cheap to answer, and it catches the worst kind of wrong answer.",
        negative_first=True,
        drop_rank=4,
    ),
)


# --- Local-service branch -----------------------------------------------------

_LOCAL_CARDS: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        id="Q-LOC-00",
        kind=AnswerKind.CHOICE,
        prompt="Which trade is it?",
        why="It picks the question set we run against the assistants.",
        options=(
            Option(value="hvac", label="HVAC"),
            Option(value="plumbing", label="Plumbing"),
            Option(value="barbershop", label="Barbershop"),
            Option(value="other", label="Something else"),
        ),
        # A run input, not ground truth — identity_category already carries the
        # falsifiable version of this.
        produces_claims=False,
        skippable=False,
    ),
    IntakeQuestion(
        id="Q-LOC-01",
        kind=AnswerKind.BATCH_CONFIRM,
        section=SheetSection.CONTACT,
        keys=("contact_phone", "contact_address", "contact_email"),
        prompt="I found this contact block. Still right?",
        why="A wrong number is a job you never hear about.",
    ),
    IntakeQuestion(
        id="Q-LOC-02",
        kind=AnswerKind.LIST,
        section=SheetSection.CONTACT,
        keys=("contact_retired",),
        prompt="Any old numbers or addresses still floating around online?",
        why="The single most useful line on a local sheet.",
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-LOC-03",
        kind=AnswerKind.HOURS,
        section=SheetSection.HOURS,
        keys=(
            "hours_monday",
            "hours_tuesday",
            "hours_wednesday",
            "hours_thursday",
            "hours_friday",
            "hours_saturday",
            "hours_sunday",
        ),
        prompt=(
            "Which days are you closed? Be blunt about it — that's what catches "
            "an assistant saying you're open seven days."
        ),
        why="The negative is the valuable answer here.",
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-LOC-04",
        kind=AnswerKind.CHOICE,
        section=SheetSection.HOURS,
        keys=("hours_after_hours",),
        prompt="Do you take emergency or after-hours calls?",
        why="Assistants invent 24/7 emergency service constantly.",
        options=(
            Option(value="no", label="No"),
            Option(value="yes_same_rate", label="Yes, same rate"),
            Option(value="yes_surcharge", label="Yes, costs more"),
        ),
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-LOC-06",
        kind=AnswerKind.LIST,
        section=SheetSection.SERVICE_AREA,
        keys=("service_area_towns",),
        prompt="Which towns do you actually serve?",
        why="So a “near me” answer can be checked against a real boundary.",
    ),
    IntakeQuestion(
        id="Q-LOC-07",
        kind=AnswerKind.LIST,
        section=SheetSection.SERVICE_AREA,
        keys=("service_area_excluded",),
        prompt="Where do you NOT go? Towns or counties you turn down.",
        why="Without it, nobody can catch an assistant promising the next county over.",
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-LOC-08",
        kind=AnswerKind.TEXT,
        section=SheetSection.LICENSING,
        keys=("licensing_number", "licensing_bonded", "licensing_insured"),
        prompt="Licence number, and who issued it?",
        why="An assistant denying a licence you hold is as bad as inventing one.",
        placeholder="CSLB 1083634",
    ),
    IntakeQuestion(
        id="Q-LOC-09",
        kind=AnswerKind.LIST,
        section=SheetSection.SERVICES_PRICING,
        keys=("services_offered",),
        prompt="What do you actually do?",
        why="The list an assistant is supposed to be reading off.",
    ),
    IntakeQuestion(
        id="Q-LOC-10",
        kind=AnswerKind.LIST,
        section=SheetSection.SERVICES_PRICING,
        keys=("services_excluded",),
        prompt="Anything people ask for that you don't do?",
        why="Stops an assistant volunteering you for work you don't take.",
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-LOC-11",
        kind=AnswerKind.MONEY,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_callout_fee",),
        prompt="What's the call-out or diagnostic fee? Say so if estimates are free.",
        why="The number people ring up to ask.",
        drop_rank=3,
    ),
    IntakeQuestion(
        id="Q-LOC-12",
        kind=AnswerKind.LINKS,
        section=SheetSection.PRESENCE,
        keys=("presence_gbp", "presence_yelp", "presence_bbb", "presence_other"),
        prompt="Any profiles we're missing? Google, Yelp, BBB.",
        why="Where the assistants go looking when your site is quiet.",
        drop_rank=1,
    ),
)


# --- Product branch -----------------------------------------------------------

_PRODUCT_CARDS: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        id="Q-PRD-01",
        kind=AnswerKind.CHOICE,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_model",),
        prompt="How do people pay for it?",
        why="Gets the shape of the price right before the numbers.",
        options=(
            Option(value="one_time", label="One-time purchase"),
            Option(value="subscription", label="Subscription"),
            Option(value="per_seat", label="Per seat"),
            Option(value="usage", label="Usage-based"),
            Option(value="hardware_plus_subscription", label="Hardware plus a subscription"),
        ),
    ),
    IntakeQuestion(
        id="Q-PRD-02",
        kind=AnswerKind.TIERS,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_tiers",),
        prompt="What are the plans, what do they cost, and what's in each?",
        why="The highest-hallucination area on the whole sheet.",
    ),
    IntakeQuestion(
        id="Q-PRD-03",
        kind=AnswerKind.TEXT,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_mandatory_fee",),
        prompt="Is anything mandatory on top of the sticker price?",
        why="The single most demo-able claim on a product sheet.",
        placeholder="$5.99/month membership",
    ),
    IntakeQuestion(
        id="Q-PRD-04",
        kind=AnswerKind.CHOICE,
        section=SheetSection.SERVICES_PRICING,
        keys=("pricing_free_tier",),
        prompt="Is there a free tier?",
        why="“There is no free tier.” is a sentence that catches a lot.",
        options=(
            Option(value="no", label="No"),
            Option(value="trial_only", label="No, but there's a trial"),
            Option(value="yes", label="Yes"),
        ),
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-PRD-05",
        kind=AnswerKind.TEXT,
        section=SheetSection.FEATURES,
        keys=("features_current_version",),
        prompt="What's the newest version, and when did it ship?",
        why="The number one staleness hotspot — training data lags.",
        placeholder="Ring 5, released 2026-05-28",
    ),
    IntakeQuestion(
        id="Q-PRD-06",
        kind=AnswerKind.LIST,
        section=SheetSection.FEATURES,
        keys=("features_core",),
        prompt="What does it actually do?",
        why="The list an assistant is supposed to be reading off.",
    ),
    IntakeQuestion(
        id="Q-PRD-07",
        kind=AnswerKind.LIST,
        section=SheetSection.FEATURES,
        keys=("features_recent",),
        prompt="What shipped in the last six to twelve months?",
        why="The second staleness hotspot.",
        drop_rank=3,
    ),
    IntakeQuestion(
        id="Q-PRD-08",
        kind=AnswerKind.LIST,
        section=SheetSection.FEATURES,
        keys=("features_excluded",),
        prompt="What do people wrongly assume you do?",
        why="“There is no Android app.” catches an assistant inventing one.",
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-PRD-09",
        kind=AnswerKind.LIST,
        section=SheetSection.FEATURES,
        keys=("features_platforms",),
        prompt="Where does it run? Platforms, requirements, anything it plugs into.",
        why="Assistants guess at platform support more than anything else.",
        drop_rank=2,
    ),
    IntakeQuestion(
        id="Q-PRD-11",
        kind=AnswerKind.TEXT,
        section=SheetSection.POSITIONING,
        keys=("positioning_icp",),
        prompt="Who is it actually for?",
        why="Shapes the problem-aware questions we ask.",
    ),
    IntakeQuestion(
        id="Q-PRD-12",
        kind=AnswerKind.LIST,
        section=SheetSection.POSITIONING,
        keys=("positioning_competitors",),
        prompt="Who do buyers compare you against?",
        why="Every name here gets its own comparison question.",
    ),
)


# --- Tail: both branches ------------------------------------------------------

TAIL: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        id="Q-END-01",
        kind=AnswerKind.WATCHLIST,
        section=SheetSection.WATCHLIST,
        keys=("watchlist",),
        prompt=(
            "Last one — have you ever seen ChatGPT or Google's AI say something wrong about you?"
        ),
        why="Usually the first thing we go and check.",
        negative_first=True,
    ),
    IntakeQuestion(
        id="Q-END-02",
        kind=AnswerKind.LONGTEXT,
        section=SheetSection.WATCHLIST,
        keys=("watchlist_other",),
        prompt="Anything else an assistant could get wrong about you?",
        why="The catch-all. Often the best line on the sheet.",
        drop_rank=5,
    ),
)


def _branded(cards: tuple[IntakeQuestion, ...], kind: BusinessKind) -> tuple[IntakeQuestion, ...]:
    """Stamp every card in a branch with its branch.

    Derived rather than written out 23 times. `branch` is not decoration —
    `build_plan` reads it, and a card that forgot it would default to "asked of
    everyone", which is how a plumber ends up being asked about pricing tiers.
    Deriving it makes that mistake unrepresentable.
    """
    return tuple(replace(card, branch=kind) for card in cards)


LOCAL_BRANCH: tuple[IntakeQuestion, ...] = _branded(_LOCAL_CARDS, BusinessKind.LOCAL_SERVICE)
PRODUCT_BRANCH: tuple[IntakeQuestion, ...] = _branded(_PRODUCT_CARDS, BusinessKind.PRODUCT)

REGISTRY: tuple[IntakeQuestion, ...] = TRUNK + LOCAL_BRANCH + PRODUCT_BRANCH + TAIL

BY_ID: dict[str, IntakeQuestion] = {q.id: q for q in REGISTRY}

#: The ceiling on one session. Eighteen is not a round number — it is five trunk
#: cards plus the longest branch (eleven) plus the two-card tail. A plan longer
#: than its own longest possible branch is a bug in `build_plan`, not a long day.
MAX_CARDS = 18


def question(question_id: str) -> IntakeQuestion:
    """One question by id. Raises rather than returning None: every caller here
    has already been handed the id BY this registry, so a miss is a bug in the
    caller and a `None` would surface it three frames later as an attribute
    error on the wrong object."""
    try:
        return BY_ID[question_id]
    except KeyError:
        raise KeyError(f"no intake question {question_id!r} in the registry") from None
