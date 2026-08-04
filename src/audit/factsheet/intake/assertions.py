"""Answer → a complete, quotable sentence. The part that actually matters.

THE PROBLEM THIS SOLVES. The judge quotes ``FactClaim.value`` verbatim and
nothing else. ``hours_sunday: closed`` is not quotable — it is a form field that
leaked into a document. ``after_hours: no`` is not a contradiction of anything;
an answer claiming 24/7 emergency service does not contradict the string "no".
Every answer therefore has to become a sentence that stands on its own:

    Closed Sunday.
    No after-hours service.
    Does not serve Marin County.
    There is no free option.
    There is no phone support.

THE OTHER THING IT SOLVES. The owner sees this sentence BEFORE the card commits
— not their raw input ("No"), the assertion ("No after-hours service."). That is
the trust mechanism, the teaching mechanism, and the cheapest defence available
against a false accusation in a document we send a stranger.

ONE BUILDER PER CARD, and the same card produces the same shape of sentence
whatever kind of business answered it. There is no per-business phrasing here
for the same reason there is no per-business question: two phrasings drift, and
the one nobody thought of has none at all.

Nothing here fetches, and nothing reads a clock: ``as_of`` is passed in. That is
what lets this module be tested exhaustively for free.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.audit.factsheet.intake.questions import IntakeQuestion
from src.audit.factsheet.models import Polarity

__all__ = [
    "Answer",
    "Assertion",
    "UNFALSIFIABLE_TERMS",
    "unfalsifiable_terms",
    "assertions_for",
    "to_assertion",
]

#: Keys whose truth EXPIRES, and whose sentence therefore carries its own date.
#:
#: "Stale" and "fabricated" are different findings with different severities, and
#: the judge reads ``value`` and nothing else — a date in a neighbouring column
#: is a date it never sees. So the stamp goes inside the sentence, but only where
#: it earns its clutter.
#:
#: NOT hours. A stamp on all seven day claims ("Closed Sunday (as of
#: 2026-08-04).") is seven pieces of noise on the shortest, most-quoted lines of
#: a sheet. Opening hours are covered by the sheet's own ``generated_at`` and
#: each claim's ``as_of`` column, which is what a human reviewer reads. Prices
#: and what-changed are the two places a model is systematically behind reality,
#: and they are the two stamped here.
_VOLATILE_PREFIXES = ("pricing_", "features_")

_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@dataclass(frozen=True, kw_only=True)
class Answer:
    """What the owner did with one card.

    ``raw`` is their input verbatim and becomes the claim's ``verbatim_quote``.
    It is kept separate from ``value`` because ``value`` is normalised (an option
    id, a list of towns, a table of priced rows) and a quote must not be.
    """

    question_id: str
    #: ``str`` for text/choice, ``list[str]`` for multi/list, ``list[dict]`` for
    #: ``priced_rows``, ``dict`` for the other structured kinds, ``None`` for a
    #: skip.
    value: object = None
    raw: str = ""
    skipped: bool = False

    @property
    def is_blank(self) -> bool:
        """Skipped, or answered with nothing. Both produce zero claims (rule 2)."""
        if self.skipped:
            return True
        if self.value is None:
            return True
        if isinstance(self.value, str):
            return not self.value.strip()
        if isinstance(self.value, (list, tuple, dict)):
            return len(self.value) == 0
        return False


@dataclass(frozen=True, kw_only=True)
class Assertion:
    """One sentence, its key, and the quote behind it."""

    key: str
    value: str
    polarity: Polarity
    quote: str


# --- the marketing-language guard --------------------------------------------

#: An AI cannot be WRONG about "the leading platform" — there is nothing to
#: check. A line like that on the sheet is a line that can never fire, and it
#: displaces one that could.
UNFALSIFIABLE_TERMS: frozenset[str] = frozenset(
    {
        "leading",
        "best",
        "premier",
        "top-rated",
        "world-class",
        "trusted",
        "innovative",
        "cutting-edge",
        "#1",
        "number one",
        "award-winning",
    }
)

_WORD = re.compile(r"[a-z0-9#-]+")


def unfalsifiable_terms(text: str) -> tuple[str, ...]:
    """Marketing words in ``text``, for the UI's nudge.

    A NUDGE AND NEVER A BLOCK. Stopping an owner from describing their own
    business in their own words is worse than one unfireable claim, and the
    escape hatch ("Keep it anyway") is part of the design rather than a
    concession. This function only reports; the decision is the owner's.
    """
    lowered = text.casefold()
    found = [t for t in UNFALSIFIABLE_TERMS if " " in t and t in lowered]
    words = set(_WORD.findall(lowered))
    found.extend(t for t in UNFALSIFIABLE_TERMS if " " not in t and t in words)
    return tuple(sorted(found))


# --- sentence helpers ---------------------------------------------------------


def _clean(text: str) -> str:
    """One line, no trailing stop, no double spaces.

    Collapsing whitespace is not cosmetic: ``FactClaim.__post_init__`` refuses a
    value containing a newline, because ``_build_fact_sheet`` joins claims with
    "\\n" and the tail of a two-line value would reach the judge as a second,
    keyless fact. A textarea produces newlines constantly.
    """
    return " ".join(text.split()).rstrip(".").strip()


def _sentence(text: str) -> str:
    """A cleaned fragment as a full stop-terminated sentence."""
    body = _clean(text)
    return f"{body}." if body else ""


def _stamped(text: str, key: str, as_of: str) -> str:
    """Volatile claims carry their date inside the quotable sentence.

    Inside the value, not beside it: the judge sees ``value`` and nothing else,
    so a date held in a neighbouring column is a date the judge never reads.
    """
    if not text or not any(key.startswith(p) for p in _VOLATILE_PREFIXES):
        return text
    return f"{text[:-1]} (as of {as_of})." if text.endswith(".") else f"{text} (as of {as_of})."


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _rows(value: object) -> list[Mapping[str, object]]:
    """A repeatable control's rows. Anything that is not a mapping is dropped
    rather than coerced — a stray string in a rows payload is a UI bug, and
    guessing at its shape would put an invented sentence on the sheet."""
    if not isinstance(value, (list, tuple)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _join(items: Sequence[str]) -> str:
    """ "a, b and c" — the way a person writes a list into a sentence."""
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _field(row: Mapping[str, object], *names: str) -> str:
    """The first non-empty field under any of ``names``.

    Repeatable rows arrive from a UI that names its own columns; accepting a
    couple of spellings here is cheaper than a schema negotiation and strictly
    safer than a positional read.
    """
    for name in names:
        text = _clean(str(row.get(name, "")))
        if text:
            return text
    return ""


def _positive(key: str, text: str, quote: str) -> list[Assertion]:
    return [Assertion(key=key, value=text, polarity=Polarity.POSITIVE, quote=quote)] if text else []


def _negative(key: str, text: str, quote: str) -> list[Assertion]:
    return [Assertion(key=key, value=text, polarity=Polarity.NEGATIVE, quote=quote)] if text else []


# --- per-question builders ----------------------------------------------------
#
# One function per card, because the phrasing is bespoke and a generic template
# engine would produce sentences nobody would sign. Each returns the assertions
# the card yields; an empty list is normal (rule 2).


# Q-WHAT-01 ────────────────────────────────────────────────────────────────────

_IDENTITY_TEMPLATES: dict[str, str] = {
    "identity_name": "The business is called {v}.",
    "identity_website": "The official website is {v}.",
    "identity_founded": "The business has operated since {v}.",
    # The category label is the load-bearing one: it is the exact framing the
    # judge checks AND the slot the query generator fills.
    "identity_category": "It is {v}.",
}


def _identity_batch(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """A batch_confirm carries one value per key it confirmed or corrected.

    Keys the owner did not touch are ABSENT from the value, not empty — a fact
    nobody looked at is not a fact anybody confirmed, and rule 2 says silence
    produces nothing.
    """
    out: list[Assertion] = []
    for key, raw in _mapping(a.value).items():
        template = _IDENTITY_TEMPLATES.get(str(key))
        text = _clean(str(raw))
        if not template or not text:
            continue
        out.extend(_positive(key, _stamped(_sentence(template.format(v=text)), key, as_of), text))
    return out


# Q-WHAT-02 ────────────────────────────────────────────────────────────────────


def _identity_what(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    return _positive("identity_what", _sentence(str(a.value or "")), a.raw or str(a.value or ""))


# Q-WHAT-04 ────────────────────────────────────────────────────────────────────


def _identity_not(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """One claim per confusable, not one listing them all.

    A wrong answer conflating this business with ONE of them should flag that
    one; a single combined line makes every finding about all of them.
    """
    out: list[Assertion] = []
    for i, name in enumerate(_as_list(a.value), start=1):
        out.extend(
            _negative(f"identity_not_{i}", _sentence(f"Not affiliated with {name}"), name)
        )
    return out


# Q-OFFER-01 / Q-OFFER-02 ──────────────────────────────────────────────────────


def _services_offered(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    # The quote is the joined items, NEVER `a.raw`. A chip control's raw is
    # whatever the composer summarised it as, and for a list that can arrive as a
    # serialised array — which puts "['drain cleaning', 'repiping']" in the
    # provenance column of a document a client reads.
    return _positive(
        "services_offered", _sentence(f"Services offered: {_join(items)}"), ", ".join(items)
    )


def _services_excluded(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """One claim per thing they don't do. THE HIGHEST-VALUE BUILDER HERE — an
    invented capability is unflaggable without one of these to contradict it."""
    out: list[Assertion] = []
    for i, item in enumerate(_as_list(a.value), start=1):
        out.extend(_negative(f"services_excluded_{i}", _sentence(f"Does not offer {item}"), item))
    return out


# Q-OFFER-03 ───────────────────────────────────────────────────────────────────


def _features_changed(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """The staleness card. Three groups, one control.

    ``{"current": str, "added": [{what, when}], "removed": [{what, when}]}``.
    The REMOVED half is the valuable one and it is a negative: an AI
    recommending a service that was dropped sends a customer to a dead end, and
    only a "no longer offers" line can catch it.
    """
    data = _mapping(a.value)
    out: list[Assertion] = []

    current = _clean(str(data.get("current", "")))
    if current:
        out.extend(
            _positive(
                "features_current",
                _stamped(_sentence(f"The current version is {current}"), "features_current", as_of),
                current,
            )
        )

    for i, row in enumerate(_rows(data.get("added")), start=1):
        what = _field(row, "what", "change")
        when = _field(row, "when")
        if not what:
            continue
        body = f"Now offers {what}" + (f", added {when}" if when else "")
        key = f"features_added_{i}"
        out.extend(_positive(key, _stamped(_sentence(body), key, as_of), f"{what} {when}".strip()))

    for i, row in enumerate(_rows(data.get("removed")), start=1):
        what = _field(row, "what", "change")
        when = _field(row, "when")
        if not what:
            continue
        body = f"No longer offers {what}" + (f", discontinued {when}" if when else "")
        key = f"features_removed_{i}"
        out.extend(_negative(key, _stamped(_sentence(body), key, as_of), f"{what} {when}".strip()))

    return out


# Q-COST-01 ────────────────────────────────────────────────────────────────────

#: How each basis reads inside a sentence. THE BASIS IS WHAT MAKES A PRICE
#: CHECKABLE: "$450" is not a claim, "$450 per hour" is. A law firm bills hourly,
#: a SaaS per seat per month, a dentist per visit and a plumber per job, and a
#: price row with no basis is one the judge cannot grade and an AI answer cannot
#: contradict.
#: Keyed by BOTH the option value and the label the owner sees, normalised.
#: The composer sends the value, but a pasted or hand-edited row sends the label,
#: and a basis that fails to match silently drops the "per hour" from a lawyer's
#: rate — which turns a correct claim into a wrong one rather than into no claim.
_BASIS_PHRASE: dict[str, str] = {
    "one_time": "",
    "per_hour": " per hour",
    "per_seat_month": " per seat per month",
    "per_seat_mo": " per seat per month",
    "per_month": " per month",
    "per_year": " per year",
    "per_visit": " per visit",
    "per_project": " per project",
    "per_unit": " per unit",
}


def _basis(raw: object) -> str:
    """The basis phrase for a row, or "" when there is none to add."""
    token = _clean(str(raw)).casefold()
    for char in ("/", " ", "-"):
        token = token.replace(char, "_")
    return _BASIS_PHRASE.get(token, "")

#: Price values that mean "no charge" rather than a number.
_FREE_PRICES = frozenset({"free", "0", "$0", "none", "no charge", "no cost"})

#: Price values that mean "there is no fixed number", which is itself a fact —
#: and a useful one, because an AI quoting a specific figure then contradicts it.
_UNPRICED: dict[str, str] = {
    "varies by scope": "varies by scope",
    "varies": "varies by scope",
    "quote only": "is quoted individually rather than at a fixed price",
    "by quote": "is quoted individually rather than at a fixed price",
    "on request": "is quoted individually rather than at a fixed price",
}


def _priced_rows(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """One sentence per priced thing. Not one listing every price: a wrong figure
    on the Business plan should flag the Business plan, and a combined line makes
    every finding about all of them.

    THE SENTENCE FRAME IS UNIFORM ON PURPOSE — "The price for {what} is …". The
    agent plan's worked examples read "The Business plan costs $12 per seat per
    month", which requires knowing that "Business" names a *plan* and "Diagnostic
    visit" names a *visit*. Nothing in the answer says which, so inferring it
    would put an invented noun into a document we send a stranger. A leading
    "The price for …" is grammatical for every row a plumber, a law firm or a
    roaster can type, and it keeps the number — the falsifiable part — intact.
    """
    out: list[Assertion] = []
    for i, row in enumerate(_rows(a.value), start=1):
        what = _field(row, "what", "name", "item")
        price = _field(row, "price")
        if not what or not price:
            # A row with a label and no number is not a price claim. Rule 2.
            continue
        includes = _field(row, "includes", "whats_included", "included")
        key = f"pricing_row_{i}"
        quote = " · ".join(p for p in (what, price, _clean(str(row.get("basis", "")))) if p)

        lowered = price.casefold()
        if lowered in _FREE_PRICES:
            body = f"There is no charge for {what}"
        elif lowered in _UNPRICED:
            body = f"The price for {what} {_UNPRICED[lowered]}"
        else:
            body = f"The price for {what} is {price}{_basis(row.get('basis', ''))}"
        if includes:
            body += f", which includes {includes}"
        out.extend(_positive(key, _stamped(_sentence(body), key, as_of), quote))
    return out


# Q-COST-02 ────────────────────────────────────────────────────────────────────


def _cost_extras(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """``{"extra": "no" | "<what it is>", "free": "no" | "<what it is>"}``.

    THE MOST DEMO-ABLE CLAIM THE SYSTEM CAN MAKE. An AI quotes the headline price
    and misses the required membership, the trip charge, the activation fee. Both
    halves are ``negative_first``: "There is no free option." is quotable, and
    therefore flaggable, in a way that a silent sheet is not.
    """
    data = _mapping(a.value)
    out: list[Assertion] = []

    extra = _clean(str(data.get("extra", "")))
    if extra:
        key = "pricing_mandatory_extra"
        if extra.casefold() in {"no", "none", "nothing"}:
            out.extend(
                _negative(
                    key,
                    _stamped("Nothing is required on top of the listed price.", key, as_of),
                    extra,
                )
            )
        else:
            out.extend(
                _positive(
                    key,
                    _stamped(
                        _sentence(f"A {extra} is required in addition to the listed price"),
                        key,
                        as_of,
                    ),
                    extra,
                )
            )

    free = _clean(str(data.get("free", "")))
    if free:
        key = "pricing_free_option"
        if free.casefold() in {"no", "none", "nothing"}:
            out.extend(_negative(key, _stamped("There is no free option.", key, as_of), free))
        else:
            out.extend(
                _positive(key, _stamped(_sentence(f"There is a free {free}"), key, as_of), free)
            )
    return out


# Q-REACH-01 ───────────────────────────────────────────────────────────────────

_CONTACT_TEMPLATES: dict[str, str] = {
    "contact_phone": "The published phone number is {v}.",
    "contact_email": "The published email address is {v}.",
    "contact_booking": "The booking or support link is {v}.",
    "contact_address": "The business address is {v}.",
}

#: "We don't have one of these" as a first-class answer, per channel. AN AI
#: INVENTING A SUPPORT PHONE NUMBER FOR A SOFTWARE COMPANY IS A REAL AND FREQUENT
#: FAILURE, and it is completely unflaggable unless the absence is asserted —
#: an omission is never a finding, only a contradiction is.
_CONTACT_ABSENT: dict[str, str] = {
    "phone": "There is no phone support.",
    "email": "There is no published email address.",
    "booking": "There is no online booking or support link.",
    "address": "There is no public office address.",
}


def _contact(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """``{contact_phone: …, …, "none": ["phone"], "retired": ["(510) 555-0100"]}``."""
    data = _mapping(a.value)
    out: list[Assertion] = []

    for key, template in _CONTACT_TEMPLATES.items():
        text = _clean(str(data.get(key, "")))
        if not text:
            continue
        out.extend(_positive(key, _sentence(template.format(v=text)), text))

    for channel in _as_list(data.get("none")):
        sentence = _CONTACT_ABSENT.get(channel.casefold())
        if not sentence:
            continue
        out.extend(_negative(f"contact_none_{channel.casefold()}", sentence, channel))

    # The retired-contact half. An old address in an old directory outlives the
    # lease, and this is the only place anything says so.
    for i, item in enumerate(_as_list(data.get("retired")), start=1):
        out.extend(
            _negative(
                f"contact_retired_{i}",
                _sentence(f"{item} is no longer in use by this business"),
                item,
            )
        )
    return out


# Q-REACH-02 ───────────────────────────────────────────────────────────────────


def _service_area(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """``{"scope": "anywhere"|"places", "included": [...], "excluded": [...]}``.

    The excluded half has NO OTHER PRODUCER ANYWHERE IN THE SYSTEM: the
    extractor is forbidden from deriving "does not serve X" from an open list,
    and nothing else asks. For a regulated profession it is a jurisdiction
    claim rather than a delivery radius, which is why the copy says "or aren't
    licensed to" and why an AI getting it wrong is a liability.

    ``city`` and ``region`` also ride in this answer and are deliberately NOT
    asserted — they are the run's location anchor (a query-generator input), not
    ground truth the judge can check.
    """
    data = _mapping(a.value)
    out: list[Assertion] = []

    if _clean(str(data.get("scope", ""))).casefold() == "anywhere":
        out.extend(_positive("service_area_scope", "Available anywhere.", "Anywhere"))

    included = _as_list(data.get("included"))
    if included:
        out.extend(
            _positive(
                "service_area_included",
                _sentence(f"The service area is {_join(included)}"),
                ", ".join(included),
            )
        )

    for i, place in enumerate(_as_list(data.get("excluded")), start=1):
        out.extend(
            _negative(f"service_area_excluded_{i}", _sentence(f"Does not serve {place}"), place)
        )
    return out


# Q-REACH-03 ───────────────────────────────────────────────────────────────────

_SCOPE_SENTENCES: dict[str, str] = {
    "always": "A person can be reached 24 hours a day, 7 days a week.",
    "by_arrangement": "A person can be reached by appointment or arrangement.",
}

_AFTER_HOURS: dict[str, tuple[str, Polarity]] = {
    "no": ("No after-hours service.", Polarity.NEGATIVE),
    "yes_same_rate": ("After-hours contact is available at the same rate.", Polarity.POSITIVE),
    "yes_surcharge": ("After-hours contact is available at a higher rate.", Polarity.POSITIVE),
}


def _availability(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """``{"scope": …, "days": {"sunday": "closed"}, "after_hours": "no"}``.

    The 7-day grid only exists under ``scope == "set_hours"`` — a grid asked of a
    SaaS is a form nobody fills, and a "24/7 self-serve" business answers in one
    tap. A day the owner did not fill in produces nothing: "we don't know
    Tuesday" and "closed Tuesday" are different facts and only one is ours to
    assert.

    Every sentence here says *a person*, not "available". Without that word a
    SaaS answers "always" truthfully about a self-serve product and the claim
    reads as "support is reachable at 3am" — a false line in a document we send
    a stranger.
    """
    data = _mapping(a.value)
    out: list[Assertion] = []

    scope = _clean(str(data.get("scope", ""))).casefold()
    sentence = _SCOPE_SENTENCES.get(scope)
    if sentence:
        out.extend(_positive("hours_scope", sentence, scope))

    for day, raw in _mapping(data.get("days")).items():
        name = str(day).strip().casefold()
        if name not in _DAYS:
            continue
        key = f"hours_{name}"
        label = name.capitalize()
        text = _clean(str(raw))
        if not text or text.casefold() in {"unknown", "-", "—"}:
            continue
        if text.casefold() in {"closed", "close", "no"}:
            out.extend(_negative(key, _stamped(f"Closed {label}.", key, as_of), text))
        else:
            out.extend(
                _positive(key, _stamped(_sentence(f"Open {label} {text}"), key, as_of), text)
            )

    after = _clean(str(data.get("after_hours", ""))).casefold()
    pair = _AFTER_HOURS.get(after)
    if pair is not None:
        body, polarity = pair
        out.append(
            Assertion(
                key="hours_after_hours",
                value=_stamped(body, "hours_after_hours", as_of),
                polarity=polarity,
                quote=after,
            )
        )
    return out


# Q-PROOF-01 ───────────────────────────────────────────────────────────────────


def _licensing(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """``{"credentials": [{what, issuer}], "not_held": ["HIPAA compliance"]}``.

    ``licensing`` is declared, titled and never emitted anywhere else in the
    system — this is its only producer. It generalizes further than the enum
    name suggests: a CSLB number and a SOC 2 report are the same dimension,
    checked the same way, with the same consequence when an AI gets it wrong.
    """
    data = _mapping(a.value)
    out: list[Assertion] = []

    for i, row in enumerate(_rows(data.get("credentials")), start=1):
        what = _field(row, "what", "credential", "held")
        issuer = _field(row, "issuer", "who", "issued_by")
        if not what:
            continue
        body = f"Holds {what}" + (f", issued by {issuer}" if issuer else "")
        quote = " · ".join(p for p in (what, issuer) if p)
        out.extend(_positive(f"licensing_credentials_{i}", _sentence(body), quote))

    # The liability guard. An AI asserting a credential the business does not
    # hold is the expensive direction of this error, and only a stated negative
    # can contradict it.
    for i, item in enumerate(_as_list(data.get("not_held")), start=1):
        out.extend(_negative(f"licensing_not_held_{i}", _sentence(f"Does not hold {item}"), item))
    return out


# Q-PROOF-02 ───────────────────────────────────────────────────────────────────


def _positioning(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """``{"competitors": [...], "for": "endurance athletes"}``.

    The competitor list also feeds a HARD query-generator constraint — every name
    here must appear in at least one comparison query — which is why the card
    asks "who else would they be looking at" rather than "who are your
    competitors": the second phrasing gets "nobody, really" from a nonprofit and
    a law firm, and an empty list leaves the comparison bucket measuring nothing.
    """
    data = _mapping(a.value)
    out: list[Assertion] = []

    names = _as_list(data.get("competitors"))
    if names:
        out.extend(
            _positive(
                "positioning_competitors",
                _sentence(f"Customers also consider {_join(names)}"),
                ", ".join(names),
            )
        )

    audience = _clean(str(data.get("for", "")))
    if audience:
        out.extend(_positive("positioning_for", _sentence(f"It is for {audience}"), audience))
    return out


# Q-AI-01 / Q-AI-02 ────────────────────────────────────────────────────────────


def _watchlist(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """``{"watchlist": [{said, truth}, …]}``. One claim per bad answer seen.

    Stored as claims AND used to aim the reverse pass. As claims it is the most
    demo-able section of the sheet — "an AI has claimed X; it is not true" is the
    sentence a sales call opens with — and as input it is cheaper and never
    wrong. Both, so neither use has to win. This is also the one section
    scraping structurally cannot produce, because it is about the *models*, not
    the business.
    """
    out: list[Assertion] = []
    for i, row in enumerate(_rows(_mapping(a.value).get("watchlist")), start=1):
        said = _field(row, "said", "what", "claim")
        truth = _field(row, "truth", "actual", "correction")
        if not said:
            continue
        body = f"An AI has claimed “{said}”. That is not true"
        if truth:
            body += f"; {truth}"
        out.extend(_negative(f"watchlist_{i}", _sentence(body), said))
    return out


def _watchlist_other(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    text = _clean(str(a.value or ""))
    if not text:
        return []
    return _negative("watchlist_other", _sentence(text), a.raw or text)


#: ``(answer, business_name, as_of) -> assertions``. A closed table: a question
#: with no builder produces no claims, which is what `produces_claims=False`
#: cards want and what an unfinished card gets until someone writes its sentence.
_Builder = Callable[[Answer, str, str], list[Assertion]]

_BUILDERS: dict[str, _Builder] = {
    "Q-WHAT-01": _identity_batch,
    "Q-WHAT-02": _identity_what,
    # Q-WHAT-03 (aliases) has no builder ON PURPOSE — §4.4, a matcher input.
    "Q-WHAT-04": _identity_not,
    "Q-OFFER-01": _services_offered,
    "Q-OFFER-02": _services_excluded,
    "Q-OFFER-03": _features_changed,
    "Q-COST-01": _priced_rows,
    "Q-COST-02": _cost_extras,
    "Q-REACH-01": _contact,
    "Q-REACH-02": _service_area,
    "Q-REACH-03": _availability,
    "Q-PROOF-01": _licensing,
    "Q-PROOF-02": _positioning,
    "Q-AI-01": _watchlist,
    "Q-AI-02": _watchlist_other,
}


def assertions_for(
    question: IntakeQuestion,
    answer: Answer,
    *,
    as_of: str,
    business_name: str,
) -> list[Assertion]:
    """Every claim this card produces. Empty is the normal case for a skip.

    Returning nothing is LOAD-BEARING, not a degenerate path: rule 2 says a
    blank produces zero claims, not an empty claim, and an empty claim would be
    a line on the sheet asserting nothing that the judge would still have to
    grade an answer against.
    """
    if answer.is_blank or not question.produces_claims:
        return []
    builder = _BUILDERS.get(question.id)
    if builder is None:
        return []
    built = builder(answer, business_name, as_of)
    # Belt and braces on the one invariant a caller cannot recover from: a value
    # with a newline raises inside FactClaim, three layers away from whichever
    # builder let a textarea through.
    return [a for a in built if a.value and "\n" not in a.value and "\r" not in a.value]


def to_assertion(
    question: IntakeQuestion,
    key: str,
    answer: Answer,
    *,
    as_of: str,
    business_name: str,
) -> str | None:
    """The sentence for one key, or ``None`` when this key produces no claim."""
    for assertion in assertions_for(question, answer, as_of=as_of, business_name=business_name):
        if assertion.key == key:
            return assertion.value
    return None
