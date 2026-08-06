"""Crawled claims → a draft answer the owner confirms or corrects.

THE WHOLE POINT OF A CRAWL. A fact sheet built from markup is a document nobody
has vouched for, so it is permanently `public_source_only` and can never flag a
HIGH finding. The only thing that upgrades it is an owner saying "yes, that's
right" — and the difference between an intake that takes four minutes and one
that takes fifteen is whether the cards arrive pre-filled or blank.

WHY A TRANSLATION LAYER EXISTS AT ALL. A `FactClaim.value` is a finished
sentence — `"Founded 1998."`, `"Serves Berkeley and Oakland."`, `"Open
08:00-17:00."` — because the sheet's job is to state things the judge can quote.
A control's value is a field: `"1998"`, `["Berkeley", "Oakland"]`,
`{"monday": "08:00-17:00"}`. Dropping a claim's sentence straight into the input
produced `"The business has operated since Founded 1998."`, which is why the
sentences get taken apart here rather than at either end.

WHAT THIS PRODUCES IS EXACTLY WHAT `/answer` STORES. Not a parallel shape: a
prefill is a draft answer, so it is built in the same form the composer would
have submitted and the same form the assertion builders read. That is what lets
one seeding path serve a card the owner is answering fresh, a card being
re-answered from the review screen, and a card the crawl already filled in.

NOTHING HERE IS A CLAIM. A prefilled card that the owner never confirms produces
nothing — the crawl's claims stay `public_source_only` on the old sheet and the
intake's sheet simply omits the line. Rule 2 of the registry survives contact
with the crawler: blank is safe, and so is unconfirmed.

Pure: no clock, no network, no storage, no model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from src.audit.factsheet.intake.questions import IntakeQuestion

__all__ = [
    "PREFILLED_QUESTIONS",
    "prefill_answer",
    "has_prefill",
    "prefilled_keys",
]

#: The seven days, in the spelling `assertions._availability` matches on. A grid
#: emitting "Tues" produces no claim at all.
_DAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# --- taking the extractor's sentences apart -----------------------------------
#
# Each of these is the inverse of one line in `extract.py`, and each is anchored
# rather than fuzzy: a pattern that half-matches returns nothing, which costs one
# blank field. A pattern that matches loosely puts a mangled value in front of an
# owner who is about to click "yes, that's right", and that is on the sheet
# forever.

_FOUNDED_RE = re.compile(r"^Founded\s+(?P<value>.+?)\.?$", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"^(?P<year>\d{4})(-\d{2}){0,2}$")
_CATEGORY_RE = re.compile(r"^It is\s+(?P<value>.+?)\.?$", re.IGNORECASE)
_SERVES_RE = re.compile(r"^Serves\s+(?P<value>.+?)\.?$", re.IGNORECASE)
_SERVICES_RE = re.compile(r"^Services offered include\s+(?P<value>.+?)\.?$", re.IGNORECASE)
_OPEN_RE = re.compile(r"^Open\s+(?P<value>.+?)\.?$", re.IGNORECASE)
_CLOSED_RE = re.compile(r"^Closed\s+\w+\.?$", re.IGNORECASE)


def _text(entry: Any) -> str:
    """The value out of one prefill entry, whatever shape the row is in."""
    if isinstance(entry, Mapping):
        return str(entry.get("value") or "").strip()
    return str(entry or "").strip()


def _capture(pattern: re.Pattern[str], entry: Any) -> str:
    match = pattern.match(_text(entry))
    return match.group("value").strip() if match else ""


def _split_oxford(text: str) -> list[str]:
    """The inverse of `extract._oxford`: "A, B and C" → ``["A", "B", "C"]``.

    Splits on the final "and" first so a two-item list ("Berkeley and Oakland")
    works without a comma, then on commas. Items are kept verbatim otherwise —
    a town or a service is the owner's words and this is not the place to tidy
    them.
    """
    if not text:
        return []
    head, sep, tail = text.rpartition(" and ")
    parts = [*head.split(","), tail] if sep else text.split(",")
    return [p.strip() for p in parts if p.strip()]


def _founded(prefill: Mapping[str, Any]) -> str:
    """``"Founded 1998-03-01."`` → ``"1998"``.

    The card is labelled "In business since" and the assertion reads "The
    business has operated since {v}." — a year is what completes that sentence.
    A `foundingDate` that is not an ISO date ("1998", "the 1970s") is passed
    through untouched, because guessing at it is how a wrong year gets confirmed.
    """
    value = _capture(_FOUNDED_RE, prefill.get("identity_founded"))
    iso = _ISO_DATE_RE.match(value)
    return iso.group("year") if iso else value


def _category(prefill: Mapping[str, Any]) -> str:
    """``"It is a plumber."`` → ``"a plumber"``.

    The article is KEPT: the assertion template is "It is {v}." and the sheet's
    line has to read as English in front of a client.
    """
    return _capture(_CATEGORY_RE, prefill.get("identity_category"))


def _towns(prefill: Mapping[str, Any]) -> list[str]:
    """Where the business works, from either producer.

    `service_area_towns` is `areaServed` markup and is the better source;
    `service_area_primary` is whatever a lead form's "area" field said, kept as
    one item because it was never a list.
    """
    towns = _split_oxford(_capture(_SERVES_RE, prefill.get("service_area_towns")))
    if towns:
        return towns
    primary = _text(prefill.get("service_area_primary"))
    return [primary] if primary else []


def _services(prefill: Mapping[str, Any]) -> list[str]:
    return _split_oxford(_capture(_SERVICES_RE, prefill.get("services_offered")))


def _hours(prefill: Mapping[str, Any]) -> dict[str, str]:
    """``{"hours_sunday": "Closed Sunday."}`` → ``{"sunday": "closed"}``.

    THE HIGHEST-VALUE CARD TO PRE-FILL, and the one that was silently dropping
    everything the crawler found: the extractor emits seven `hours_{day}` claims
    and the card's grid is one part named `days`, so nothing ever matched.

    "closed" is spelled the way the grid's toggle tests for it, so a crawled
    closure arrives as a pressed Closed button rather than as the word "closed"
    typed into a time field. Negatives are where the value is — "Closed Sunday."
    is what makes an "open 7 days" answer flaggable — so they seed exactly like
    the positives do.
    """
    grid: dict[str, str] = {}
    for day in _DAYS:
        raw = _text(prefill.get(f"hours_{day}"))
        if not raw:
            continue
        if _CLOSED_RE.match(raw):
            grid[day] = "closed"
            continue
        spans = _capture(_OPEN_RE, raw)
        if spans:
            grid[day] = spans
    return grid


# --- one builder per card the crawl can speak to ------------------------------


def _identity_batch(prefill: Mapping[str, Any]) -> dict[str, str]:
    fields = {
        "identity_name": _text(prefill.get("identity_name")),
        "identity_website": _text(prefill.get("identity_website")),
        "identity_founded": _founded(prefill),
        "identity_category": _category(prefill),
    }
    # Absent, never empty. A key the crawl said nothing about must not arrive as
    # "" — `_identity_batch` in assertions.py skips blanks, but a blank in the
    # payload also tells the composer to render a settled line with nothing in it.
    return {k: v for k, v in fields.items() if v}


def _identity_what(prefill: Mapping[str, Any]) -> str:
    """The description is the single highest-value line for a non-local business:
    without it the sheet says where a company is and not what it does."""
    return _text(prefill.get("identity_description"))


def _contact(prefill: Mapping[str, Any]) -> dict[str, str]:
    fields = {
        key: _text(prefill.get(key))
        for key in ("contact_phone", "contact_email", "contact_address")
    }
    # `contact_booking`, `none` and `retired` are never prefilled: no extractor
    # produces them, and the two negative halves are the card's whole value — a
    # crawl cannot know there is no phone line, only that it did not find one.
    return {k: v for k, v in fields.items() if v}


def _service_area(prefill: Mapping[str, Any]) -> dict[str, Any]:
    towns = _towns(prefill)
    if not towns:
        return {}
    # `scope` has to be set or the `included` part does not render at all — it is
    # `show_when=("scope", "places")`. `excluded` stays empty: absence in an
    # `areaServed` list means "not mentioned", never "does not serve", and
    # deriving one from the other is forbidden (§4.4).
    return {"scope": "places", "included": towns}


def _availability(prefill: Mapping[str, Any]) -> dict[str, Any]:
    grid = _hours(prefill)
    if not grid:
        return {}
    # Same reason as the service area: the grid is `show_when=("scope",
    # "set_hours")`. `after_hours` is left unanswered — published opening hours
    # say nothing about whether there is an on-call number.
    return {"scope": "set_hours", "days": grid}


#: Card → what a crawl can put in it. Only six of the seventeen appear, and that is
#: the honest number: nothing in markup says what you *don't* do, who people
#: confuse you with, or what an AI has already got wrong — which is why those
#: cards are where the intake earns its keep.
_BUILDERS: dict[str, Any] = {
    "Q-WHAT-01": _identity_batch,
    "Q-WHAT-02": _identity_what,
    "Q-OFFER-01": _services,
    "Q-REACH-01": _contact,
    "Q-REACH-02": _service_area,
    "Q-REACH-03": _availability,
}

#: The question ids this module can prefill. Exported so a test can assert every
#: one of them is a real card — a builder keyed to an id the registry dropped is
#: a silent no-op, which is the failure mode a table like this has.
PREFILLED_QUESTIONS: frozenset[str] = frozenset(_BUILDERS)


def prefill_answer(
    question: IntakeQuestion,
    prefill: Mapping[str, Any],
) -> Any | None:
    """The draft answer a crawl produced for one card, or ``None`` for nothing.

    ``None`` and an empty container are the same outcome to a caller and are
    collapsed here, so "is this card prefilled" is one `is not None` rather than
    a shape check at every call site.
    """
    builder = _BUILDERS.get(question.id)
    if builder is None:
        return None
    built = builder(prefill)
    if not built:
        return None
    return built


def has_prefill(question: IntakeQuestion, prefill: Mapping[str, Any]) -> bool:
    """Whether this card arrives as a confirm rather than a blank form."""
    return prefill_answer(question, prefill) is not None


def prefilled_keys(prefill: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    """Which of ``keys`` the crawl actually has something for. For the copy that
    tells the owner what was found before they are asked to vouch for it."""
    return [k for k in keys if _text(prefill.get(k))]
