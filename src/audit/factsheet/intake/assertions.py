"""Answer → a complete, quotable sentence. The part that actually matters.

THE PROBLEM THIS SOLVES. The judge quotes ``FactClaim.value`` verbatim and
nothing else. ``hours_sunday: closed`` is not quotable — it is a form field that
leaked into a document. ``after_hours: no`` is not a contradiction of anything;
an answer claiming 24/7 emergency service does not contradict the string "no".
Every answer therefore has to become a sentence that stands on its own:

    Closed Sunday.
    No after-hours or emergency service.
    Does not serve Marin County.
    There is no free tier.

THE OTHER THING IT SOLVES. The owner sees this sentence BEFORE the card commits
— not their raw input ("No"), the assertion ("No after-hours or emergency
service."). That is the trust mechanism, the teaching mechanism, and the
cheapest defence available against a false accusation in a document we send a
stranger.

Nothing here fetches, and nothing reads a clock: ``as_of`` is passed in. That is
what lets this module be tested exhaustively for free and lets I2 and I4 land
independently of it.
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
#: NOT hours, and NOT presence, though an earlier draft of the plan listed both.
#: A stamp on all seven day claims ("Closed Sunday (as of 2026-08-04).") is seven
#: pieces of noise on the shortest, most-quoted lines of a local sheet, and a
#: profile URL does not go stale the way a price does. Opening hours are covered
#: by the sheet's own ``generated_at`` and each claim's ``as_of`` column, which
#: is what a human reviewer reads. Prices and version numbers are the two places
#: a model is systematically behind reality, and they are the two stamped here.
_VOLATILE_PREFIXES = ("pricing_", "features_current_", "features_recent")

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
    id, a list of towns) and a quote must not be.
    """

    question_id: str
    #: ``str`` for text/choice, ``list[str]`` for multi/list, ``dict`` for the
    #: structured kinds, ``None`` for a skip.
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

#: An assistant cannot be WRONG about "the leading platform" — there is nothing
#: to check. A line like that on the sheet is a line that can never fire, and it
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


# --- per-question builders ----------------------------------------------------
#
# One function per card, because the phrasing is bespoke and a generic template
# engine would produce sentences nobody would sign. Each returns the assertions
# the card yields; an empty list is normal (rule 2).


def _positive(key: str, text: str, quote: str) -> list[Assertion]:
    return [Assertion(key=key, value=text, polarity=Polarity.POSITIVE, quote=quote)] if text else []


def _negative(key: str, text: str, quote: str) -> list[Assertion]:
    return [Assertion(key=key, value=text, polarity=Polarity.NEGATIVE, quote=quote)] if text else []


def _identity_kind(a: Answer, business: str, _as_of: str) -> list[Assertion]:
    value = str(a.value or "")
    if value == "local_service":
        text = f"{business} is a local business people call or visit."
    elif value == "product":
        text = f"{business} sells something people buy online."
    else:
        return []
    return _positive("identity_kind", text, a.raw or value)


_BATCH_TEMPLATES: dict[str, str] = {
    "identity_name": "The business is called {v}.",
    "identity_website": "The official website is {v}.",
    "identity_founded": "The business has operated since {v}.",
    "identity_category": "It is {v}.",
    "contact_phone": "The published phone number is {v}.",
    "contact_address": "The business address is {v}.",
    "contact_email": "The published email address is {v}.",
}


def _batch(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """A batch_confirm carries one value per key it confirmed or corrected.

    Keys the owner did not touch are ABSENT from the value, not empty — a fact
    nobody looked at is not a fact anybody confirmed, and rule 2 says silence
    produces nothing.
    """
    out: list[Assertion] = []
    for key, raw in _mapping(a.value).items():
        template = _BATCH_TEMPLATES.get(key)
        text = _clean(str(raw))
        if not template or not text:
            continue
        out.extend(_positive(key, _stamped(_sentence(template.format(v=text)), key, as_of), text))
    return out


def _identity_what(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    return _positive("identity_what", _sentence(str(a.value or "")), a.raw or str(a.value or ""))


def _identity_not(a: Answer, business: str, _as_of: str) -> list[Assertion]:
    names = _as_list(a.value)
    if not names:
        return []
    return _negative(
        "identity_not",
        _sentence(f"{business} is not affiliated with {_join(names)}"),
        a.raw or ", ".join(names),
    )


def _contact_retired(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _negative(
        "contact_retired",
        _sentence(
            f"{_join(items)} {'are' if len(items) > 1 else 'is'} no longer in use by this business"
        ),
        a.raw or ", ".join(items),
    )


def _hours(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """One claim per day. Closed days are the point of this card.

    A day the owner did not fill in produces nothing — "we don't know Tuesday"
    and "closed Tuesday" are different facts and only one of them is ours to
    assert.
    """
    out: list[Assertion] = []
    for day, raw in _mapping(a.value).items():
        name = day.strip().casefold()
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
    return out


def _after_hours(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    value = str(a.value or "")
    key = "hours_after_hours"
    if value == "no":
        return _negative(
            key, _stamped("No after-hours or emergency service.", key, as_of), a.raw or "No"
        )
    if value == "yes_same_rate":
        return _positive(
            key,
            _stamped("After-hours calls are taken at the same rate.", key, as_of),
            a.raw or "Yes, same rate",
        )
    if value == "yes_surcharge":
        return _positive(
            key,
            _stamped("After-hours calls are taken at a higher rate.", key, as_of),
            a.raw or "Yes, costs more",
        )
    return []


def _service_towns(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    towns = _as_list(a.value)
    if not towns:
        return []
    return _positive(
        "service_area_towns",
        _sentence(f"The service area is {_join(towns)}"),
        a.raw or ", ".join(towns),
    )


def _service_excluded(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    places = _as_list(a.value)
    if not places:
        return []
    return _negative(
        "service_area_excluded",
        _sentence(f"Does not serve {_join(places)}"),
        a.raw or ", ".join(places),
    )


def _licensing(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    text = _clean(str(a.value or ""))
    if not text:
        return []
    return _positive("licensing_number", _sentence(f"Licensed: {text}"), a.raw or text)


def _services_offered(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _positive(
        "services_offered",
        _sentence(f"Services offered: {_join(items)}"),
        a.raw or ", ".join(items),
    )


def _services_excluded(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _negative(
        "services_excluded",
        _sentence(f"Does not offer {_join(items)}"),
        a.raw or ", ".join(items),
    )


def _callout_fee(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    text = _clean(str(a.value or ""))
    key = "pricing_callout_fee"
    if not text:
        return []
    if text.casefold() in {"0", "$0", "free", "none", "no"}:
        return _negative(
            key,
            _stamped("Estimates are free; there is no call-out fee.", key, as_of),
            a.raw or text,
        )
    return _positive(
        key, _stamped(_sentence(f"The call-out fee is {text}"), key, as_of), a.raw or text
    )


_LINK_TEMPLATES: dict[str, str] = {
    "presence_gbp": "The Google Business Profile is {v}.",
    "presence_yelp": "The Yelp listing is {v}.",
    "presence_bbb": "The BBB listing is {v}.",
    "presence_other": "Another official profile is {v}.",
}


def _links(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    out: list[Assertion] = []
    for key, raw in _mapping(a.value).items():
        template = _LINK_TEMPLATES.get(key)
        url = _clean(str(raw))
        if not template or not url:
            continue
        out.extend(_positive(key, _stamped(_sentence(template.format(v=url)), key, as_of), url))
    return out


# --- product branch -----------------------------------------------------------

_PRICING_MODELS: dict[str, str] = {
    "one_time": "It is a one-time purchase.",
    "subscription": "It is sold as a subscription.",
    "per_seat": "It is priced per seat.",
    "usage": "It is priced by usage.",
    "hardware_plus_subscription": "It is hardware plus a separate subscription.",
}


def _pricing_model(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    text = _PRICING_MODELS.get(str(a.value or ""), "")
    return _positive("pricing_model", _stamped(text, "pricing_model", as_of), a.raw or str(a.value))


def _tiers(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    """One sentence per plan. Not one sentence listing every plan: a wrong price
    on the Pro tier should flag the Pro tier, and a single combined line makes
    every finding about all of them."""
    out: list[Assertion] = []
    rows = a.value if isinstance(a.value, (list, tuple)) else []
    for i, row in enumerate(rows, start=1):
        data = _mapping(row)
        name = _clean(str(data.get("name", "")))
        price = _clean(str(data.get("price", "")))
        includes = _clean(str(data.get("includes", "")))
        if not name or not price:
            continue
        body = f"The {name} plan costs {price}"
        if includes:
            body += f", which includes {includes}"
        key = f"pricing_tier_{i}"
        out.extend(_positive(key, _stamped(_sentence(body), key, as_of), f"{name} {price}"))
    return out


def _mandatory_fee(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    text = _clean(str(a.value or ""))
    key = "pricing_mandatory_fee"
    if not text:
        return []
    if text.casefold() in {"no", "none", "nothing"}:
        return _negative(
            key,
            _stamped("Nothing is required on top of the purchase price.", key, as_of),
            a.raw or text,
        )
    return _positive(
        key,
        _stamped(_sentence(f"A {text} is required in addition to the purchase price"), key, as_of),
        a.raw or text,
    )


def _free_tier(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    value = str(a.value or "")
    key = "pricing_free_tier"
    if value == "no":
        return _negative(key, _stamped("There is no free tier.", key, as_of), a.raw or "No")
    if value == "trial_only":
        return _negative(
            key,
            _stamped("There is no free tier; there is a time-limited trial.", key, as_of),
            a.raw or "No, but there's a trial",
        )
    if value == "yes":
        return _positive(key, _stamped("There is a free tier.", key, as_of), a.raw or "Yes")
    return []


def _current_version(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    text = _clean(str(a.value or ""))
    key = "features_current_version"
    if not text:
        return []
    return _positive(key, _stamped(_sentence(f"The current version is {text}"), key, as_of), text)


def _features_core(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _positive("features_core", _sentence(f"It does {_join(items)}"), ", ".join(items))


def _features_recent(a: Answer, _business: str, as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    key = "features_recent"
    return _positive(
        key,
        _stamped(_sentence(f"Recently shipped: {_join(items)}"), key, as_of),
        ", ".join(items),
    )


def _features_excluded(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _negative(
        "features_excluded", _sentence(f"There is no {_join(items)}"), ", ".join(items)
    )


def _features_platforms(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _positive(
        "features_platforms", _sentence(f"It runs on {_join(items)}"), ", ".join(items)
    )


def _icp(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    text = _clean(str(a.value or ""))
    if not text:
        return []
    return _positive("positioning_icp", _sentence(f"It is for {text}"), text)


def _competitors(a: Answer, business: str, _as_of: str) -> list[Assertion]:
    items = _as_list(a.value)
    if not items:
        return []
    return _positive(
        "positioning_competitors",
        _sentence(f"Buyers compare {business} against {_join(items)}"),
        ", ".join(items),
    )


# --- tail ---------------------------------------------------------------------


def _watchlist(a: Answer, _business: str, _as_of: str) -> list[Assertion]:
    """One claim per bad answer the owner has seen.

    Stored as claims AND used to aim the reverse pass. As claims it is the most
    demo-able section of the sheet — "an assistant has claimed X; it is not
    true" is the sentence a sales call opens with — and as input it is cheaper
    and never wrong. Both, so neither use has to win.
    """
    out: list[Assertion] = []
    rows = a.value if isinstance(a.value, (list, tuple)) else []
    for i, row in enumerate(rows, start=1):
        data = _mapping(row)
        said = _clean(str(data.get("said", "")))
        truth = _clean(str(data.get("truth", "")))
        if not said:
            continue
        body = f"An assistant has claimed “{said}”. That is not true"
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
    "Q-ID-01": _identity_kind,
    "Q-ID-02": _batch,
    "Q-ID-03": _identity_what,
    "Q-ID-06": _identity_not,
    "Q-LOC-01": _batch,
    "Q-LOC-02": _contact_retired,
    "Q-LOC-03": _hours,
    "Q-LOC-04": _after_hours,
    "Q-LOC-06": _service_towns,
    "Q-LOC-07": _service_excluded,
    "Q-LOC-08": _licensing,
    "Q-LOC-09": _services_offered,
    "Q-LOC-10": _services_excluded,
    "Q-LOC-11": _callout_fee,
    "Q-LOC-12": _links,
    "Q-PRD-01": _pricing_model,
    "Q-PRD-02": _tiers,
    "Q-PRD-03": _mandatory_fee,
    "Q-PRD-04": _free_tier,
    "Q-PRD-05": _current_version,
    "Q-PRD-06": _features_core,
    "Q-PRD-07": _features_recent,
    "Q-PRD-08": _features_excluded,
    "Q-PRD-09": _features_platforms,
    "Q-PRD-11": _icp,
    "Q-PRD-12": _competitors,
    "Q-END-01": _watchlist,
    "Q-END-02": _watchlist_other,
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
