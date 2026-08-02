"""Root-cause themes — the second axis the report groups on.

:class:`~src.storage.models.AccuracyFlagType` says *what kind of fact* was wrong.
That is not what gets fixed. "Confused with Fitbit", "confused with a pickleball
app" and "not a recognized brand" are all ``identity``, but they are one root
cause — the models cannot disambiguate the entity — and one fix. This module adds
that second axis (``docs/audit-packaging-spec.md`` P0-T3).

The split that matters most is ``feature_invented`` vs ``feature_omitted``. Both
come out of the judge as ``missing_or_invented_feature``, and their fixes are
*opposite*: retract a claim the models made up, versus publish a capability they
never learned about. One theme for both would produce an action nobody can take.

**Deterministic by construction — no LLM call.** An ordered decision list, first
match wins, specific rules before catch-alls. It must be reproducible (the same
run re-rendered must group identically), free (this runs on every render), and
readable (a rule is a regex you can argue with). If the rule set ever outgrows
one person's ability to order it by hand, the escalation is weak supervision, not
a model call here.

**Coverage is a metric, not a silence.** :func:`classify` records *how* it
decided — a text rule, the flag type's default, or nothing — and
:func:`coverage` rolls that up. A rising ``type_default`` share is the leading
indicator that the rule set has stopped keeping up with what the engines say;
``UNCLASSIFIED`` never silently disappears into a bucket.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from src.storage.models import AccuracyFlagType

__all__ = [
    "Theme",
    "THEME_LABELS",
    "Classification",
    "Coverage",
    "classify",
    "coverage",
    "theme_label",
]


class Theme(StrEnum):
    """Level-1 root causes. Level 2 (per-theme sub-causes) is deliberately unbuilt."""

    IDENTITY_DISAMBIGUATION = "identity_disambiguation"
    CATEGORY_CONFUSION = "category_confusion"
    LIFECYCLE_STATUS = "lifecycle_status"
    PRICING_OFFER = "pricing_offer"
    FEATURE_INVENTED = "feature_invented"
    FEATURE_OMITTED = "feature_omitted"
    COMPETITOR_MISCHARACTERIZATION = "competitor_mischaracterization"
    COMPANY_FACTS = "company_facts"
    AVAILABILITY_GEOGRAPHY = "availability_geography"
    SOURCE_CITATION_QUALITY = "source_citation_quality"
    RISK_REPUTATION = "risk_reputation"
    #: Not a root cause — the honest absence of one. Tracked, never rendered as a
    #: theme heading.
    UNCLASSIFIED = "unclassified"


#: Client-facing headings. Sentence case, no jargon, no internal ids — a reader
#: sees "Models can't tell you apart from another company", never
#: ``identity_disambiguation``.
THEME_LABELS: dict[str, str] = {
    Theme.IDENTITY_DISAMBIGUATION.value: "Models can't reliably identify you",
    Theme.CATEGORY_CONFUSION.value: "Models place you in the wrong category",
    Theme.LIFECYCLE_STATUS.value: "Models describe the wrong launch or trading status",
    Theme.PRICING_OFFER.value: "Models state the wrong price or offer",
    Theme.FEATURE_INVENTED.value: "Models describe capabilities you don't have",
    Theme.FEATURE_OMITTED.value: "Models omit capabilities you do have",
    Theme.COMPETITOR_MISCHARACTERIZATION.value: "Models apply a competitor's attributes to you",
    Theme.COMPANY_FACTS.value: "Models state the wrong company details",
    Theme.AVAILABILITY_GEOGRAPHY.value: "Models describe the wrong availability or coverage",
    Theme.SOURCE_CITATION_QUALITY.value: "Models cite weak or wrong sources for you",
    Theme.RISK_REPUTATION.value: "Models raise credentials or trust concerns",
    Theme.UNCLASSIFIED.value: "Uncategorized",
}


@dataclass(frozen=True)
class Rule:
    """One text pattern and the theme (and card title) it implies."""

    rule_id: str
    theme: Theme
    #: The card headline. A template keyed off the *rule*, not scraped from the
    #: claim text: a title assembled from model prose would inherit the model's
    #: phrasing, which is the thing under audit. ``{client}`` is the only slot.
    title: str
    patterns: tuple[re.Pattern[str], ...]
    #: When set, the rule only fires for these flag types. Used where the same
    #: words mean different things in different dimensions.
    only_types: frozenset[str] | None = None

    def matches(self, normalized: str, flag_type: str) -> bool:
        if self.only_types is not None and flag_type not in self.only_types:
            return False
        return any(p.search(normalized) for p in self.patterns)


def _re(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


#: Ordered, first match wins. Specific before general — an "already shipping"
#: claim is a lifecycle error even though it also mentions availability, so the
#: lifecycle rules sit above the geography ones.
RULES: tuple[Rule, ...] = (
    # --- identity: the model does not know the entity exists ------------------
    Rule(
        "identity.unrecognized",
        Theme.IDENTITY_DISAMBIGUATION,
        "{client} is not a recognized entity",
        _re(
            r"\bno[nt]?\b[^.]{0,30}\b(?:widely\s+)?recogni[sz]ed\b",
            r"\b(?:isn'?t|is not|there is no|there isn'?t)\b[^.]{0,40}\b(?:brand|company|"
            r"product|business)\b",
            r"\bno\s+(?:specific|public|available)\s+information\b",
            r"\bnot\s+(?:aware|familiar)\b",
            r"\b(?:i|we)\s+(?:don'?t|do not)\s+have\s+(?:any\s+)?(?:specific\s+)?information\b",
            r"\bfictional\b|\bmade[- ]up\b|\bdoes not (?:appear to )?exist\b",
        ),
    ),
    Rule(
        "identity.confused_with",
        Theme.IDENTITY_DISAMBIGUATION,
        "{client} is confused with another company",
        _re(
            r"\bassuming you mean\b",
            r"\bif by\b[^.]{1,30}\byou mean\b",
            r"\bdid you mean\b",
            r"\b(?:confus|conflat)(?:es|ed|ing)\b",
            r"\bmistak(?:es|en|ing)\b[^.]{0,30}\bfor\b",
            r"\ba(?:lso)? known as\b",
        ),
    ),
    # --- category: the entity is known but filed under the wrong thing ---------
    Rule(
        "category.wrong_category",
        Theme.CATEGORY_CONFUSION,
        "{client} is described as the wrong kind of product",
        _re(
            r"\b(?:is|as)\s+an?\s+[a-z ]{0,24}\b(?:app|platform|agency|saas|marketplace|"
            r"service|tool|startup|retailer|manufacturer)\b[^.]{0,40}\b(?:for|that)\b",
            r"\bcategor(?:y|ised|ized|isation|ization)\b",
            r"\btype of (?:product|business|company)\b",
        ),
        only_types=frozenset({AccuracyFlagType.IDENTITY.value}),
    ),
    # --- lifecycle: exists, but at the wrong point in its life -----------------
    Rule(
        "lifecycle.availability_state",
        Theme.LIFECYCLE_STATUS,
        "{client}'s launch or trading status is stated wrongly",
        _re(
            r"\balready (?:shipping|available|launched|out)\b",
            r"\b(?:is|are|now)\s+(?:shipping|available|on sale|in stock)\b",
            r"\bout of business\b|\bshut down\b|\bceased (?:trading|operations)\b",
            # The qualifier is REQUIRED. A bare "closed" is far more often about
            # opening hours ("closed on weekends"), which is an availability
            # finding with a completely different fix, and this rule sits above
            # the availability one.
            r"\b(?:permanently|now|recently)\s+closed\b",
            r"\bclosed\s+(?:down|permanently|for good|its doors)\b",
            r"\bdiscontinued\b|\bno longer (?:operating|available|in business|sold)\b",
            r"\bacquired by\b|\bmerged with\b",
            r"\b(?:pre[- ]?order|pre[- ]?launch|coming soon|not yet (?:released|launched|"
            r"available|shipping))\b",
            r"\b(?:launched|founded|established|released)\s+in\s+\d{4}\b",
            r"\b(?:new|recent)(?:ly)?\s+(?:player|entrant|entry|arrival|startup)\b",
            # Ship-date phrasing. Added after the real Fort run: "expected to ship
            # in Q3 2026" and "shipping starting June 2026" are the single most
            # common lifecycle error the engines make about a pre-launch product,
            # and none of the patterns above caught either — so they fell through
            # to whichever general rule happened to match the surrounding prose.
            r"\bexpected to (?:ship|launch|release|arrive|begin)\b",
            r"\b(?:ship|ships|shipping|shipment|deliver(?:y|ies)|launch(?:es|ing)?)\b"
            r"[^.]{0,40}\b(?:q[1-4]\b|20\d{2}|january|february|march|april|may|june|july|"
            r"august|september|october|november|december|summer|spring|fall|autumn|winter)\b",
        ),
    ),
    # --- pricing -------------------------------------------------------------
    Rule(
        "pricing.figure",
        Theme.PRICING_OFFER,
        "{client}'s pricing is stated wrongly",
        _re(
            r"[$£€]\s?\d",
            r"\b\d+\s*(?:dollars|usd|pounds|euros)\b",
            r"\b(?:price|pricing|cost[s]?|fee|subscription|per month|per year|monthly|"
            r"annually|free tier|freemium|price point)\b",
        ),
    ),
    # --- features: the invented/omitted split, and it must come out right ------
    Rule(
        "feature.omitted",
        Theme.FEATURE_OMITTED,
        "{client}'s capabilities are understated or missing",
        _re(
            r"\b(?:does not|doesn'?t|cannot|can'?t|won'?t|lacks|missing|without|no|"
            r"there is no|there'?s no)\b"
            r"[^.]{0,40}\b(?:support|offer|include|track|provide|have|feature|integrat|"
            r"app|version|option|plan|mode|export|api)\b",
            r"\bonly (?:available|works|supports|offers)\b",
            r"\b(?:ios|android)[- ]only\b",
            r"\bnot available (?:on|for|in)\b",
            r"\bunable to\b",
        ),
        only_types=frozenset({AccuracyFlagType.MISSING_OR_INVENTED_FEATURE.value}),
    ),
    Rule(
        "feature.invented",
        Theme.FEATURE_INVENTED,
        "{client} is credited with capabilities it doesn't have",
        _re(
            r"\b(?:offers|includes|supports|features|provides|comes with|has|measures|"
            r"tracks|monitors|integrates)\b",
            r"\b(?:blood pressure|ecg|gps|ai[- ]powered)\b",
        ),
        only_types=frozenset({AccuracyFlagType.MISSING_OR_INVENTED_FEATURE.value}),
    ),
    # --- competitor attributes applied to the client ---------------------------
    Rule(
        "competitor.attributes",
        Theme.COMPETITOR_MISCHARACTERIZATION,
        "A competitor's attributes are applied to {client}",
        _re(
            r"\b(?:like|similar to|same as|equivalent to|a\s+\w+\s+alternative to|"
            r"competitor to|rival)\b",
            r"\bjust (?:a|an|another)\b",
            r"\b(?:class|style|clone|knock[- ]?off)\b",
        ),
    ),
    # --- availability / geography ---------------------------------------------
    Rule(
        "availability.geography",
        Theme.AVAILABILITY_GEOGRAPHY,
        "{client}'s coverage area or hours are stated wrongly",
        _re(
            r"\b(?:serves?|serving|service area|covers?|coverage|operates? in|based in|"
            r"located in|ships? to|available in)\b",
            r"\b(?:open|closes?|closing|hours|24/7|weekend|emergency|same[- ]day|"
            r"appointment)\b",
            r"\b(?:county|region|metro|zip code|postcode|nationwide|statewide)\b",
        ),
    ),
    # --- risk / reputation ----------------------------------------------------
    Rule(
        "risk.credentials",
        Theme.RISK_REPUTATION,
        "Models raise trust or credential concerns about {client}",
        _re(
            r"\b(?:licen[sc]ed?|licen[sc]ing|bonded|insured|insurance|certifi(?:ed|cation)"
            r"|accredit(?:ed|ation)|permit)\b",
            r"\b(?:scam|fraud|lawsuit|complaint|recall|investigat(?:ion|ed)|banned|"
            r"warning|unsafe)\b",
            r"\b(?:rating|reviews?|bbb|better business bureau)\b",
        ),
    ),
    # --- company facts (catch-all for verifiable corporate detail) -------------
    Rule(
        "company.facts",
        Theme.COMPANY_FACTS,
        "{client}'s company details are stated wrongly",
        _re(
            r"\b(?:founder|founded|ceo|headquarter|hq|employees|headcount|funding|raised|"
            r"investors|series [a-e]\b|owned by|parent company)\b",
            r"\b(?:phone|telephone|address|email|website|domain)\b",
        ),
    ),
    # --- source quality: LAST, because it is the most general. Attribution
    # language ('according to', 'some sources') appears INSIDE claims whose
    # real error is something else entirely — a stale ship date cited to a
    # launch page is a lifecycle finding, not a source-quality one.
    Rule(
        "source.citation_quality",
        Theme.SOURCE_CITATION_QUALITY,
        "Models rely on weak or wrong sources for {client}",
        _re(
            r"\b(?:according to|cited|citation|source[sd]?|referenc(?:e|ed|es)|per their"
            r"|as reported by)\b",
            r"\b(?:wikipedia|crunchbase|g2|trustpilot|yelp|reddit|linkedin)\b",
        ),
    ),
)


#: Last resort before UNCLASSIFIED: the flag type's own root cause. Every member
#: of :class:`~src.storage.models.AccuracyFlagType` appears here, which is what
#: guarantees a known flag can never classify as ``None``.
TYPE_DEFAULTS: dict[str, Theme] = {
    AccuracyFlagType.WRONG_PRICING.value: Theme.PRICING_OFFER,
    # The invented arm, not the omitted one: a model asserting a capability is
    # the more common and the more damaging half, so an unmatched claim defaults
    # to the reading that gets reviewed rather than the one that gets filed.
    AccuracyFlagType.MISSING_OR_INVENTED_FEATURE.value: Theme.FEATURE_INVENTED,
    AccuracyFlagType.COMPETITOR_CONFUSION.value: Theme.COMPETITOR_MISCHARACTERIZATION,
    AccuracyFlagType.IDENTITY.value: Theme.IDENTITY_DISAMBIGUATION,
    AccuracyFlagType.STALE.value: Theme.LIFECYCLE_STATUS,
    AccuracyFlagType.WRONG_HOURS.value: Theme.AVAILABILITY_GEOGRAPHY,
    AccuracyFlagType.WRONG_SERVICE_AREA.value: Theme.AVAILABILITY_GEOGRAPHY,
    AccuracyFlagType.WRONG_CONTACT.value: Theme.COMPANY_FACTS,
    AccuracyFlagType.LICENSING.value: Theme.RISK_REPUTATION,
}

#: Title used when the flag type, not a text rule, decided the theme.
_DEFAULT_TITLES: dict[Theme, str] = {
    Theme.PRICING_OFFER: "{client}'s pricing is stated wrongly",
    Theme.FEATURE_INVENTED: "{client} is credited with capabilities it doesn't have",
    Theme.FEATURE_OMITTED: "{client}'s capabilities are understated or missing",
    Theme.COMPETITOR_MISCHARACTERIZATION: "A competitor's attributes are applied to {client}",
    Theme.IDENTITY_DISAMBIGUATION: "Models can't reliably identify {client}",
    Theme.LIFECYCLE_STATUS: "{client}'s launch or trading status is stated wrongly",
    Theme.AVAILABILITY_GEOGRAPHY: "{client}'s coverage area or hours are stated wrongly",
    Theme.COMPANY_FACTS: "{client}'s company details are stated wrongly",
    Theme.RISK_REPUTATION: "Models raise trust or credential concerns about {client}",
    Theme.CATEGORY_CONFUSION: "{client} is described as the wrong kind of product",
    Theme.SOURCE_CITATION_QUALITY: "Models rely on weak or wrong sources for {client}",
    Theme.UNCLASSIFIED: "Uncategorized finding about {client}",
}


@dataclass(frozen=True)
class Classification:
    """A theme plus how it was reached — the second half is the coverage metric."""

    theme: str
    #: ``"rule"`` (a text pattern fired) | ``"type_default"`` (the flag type
    #: decided) | ``"none"`` (neither — an unknown flag type).
    classified_by: str
    #: The rule that fired, for auditing. Empty on the non-rule paths.
    rule_id: str
    #: The card headline template, ``{client}`` unsubstituted.
    title: str


def classify(flag_type: str, claim: str, reality: str = "") -> Classification:
    """Root cause for one flag. Total — every input returns a Classification.

    Matching runs over the claim first and the fact-sheet ``reality`` second. The
    claim is what the model said and is the thing being themed; ``reality`` is
    consulted only as a tiebreaker for claims too terse to pattern-match ("no",
    "$0"), where the correction names the dimension the claim silently referred to.
    """
    normalized_claim = _normalize(claim)
    haystacks = [normalized_claim]
    # The fact-sheet correction is a LAST resort, and only for a claim too short
    # to carry any signal of its own ("No.", "$0"). It used to be consulted for
    # every unmatched claim, which filed a real Fort shipping-date error under
    # "weak sources" because the sheet line it contradicted happened to cite one.
    # The correction describes the fix, not the error, so reading it as the error
    # is wrong whenever the claim can speak for itself.
    if reality and len(normalized_claim.split()) <= _TERSE_CLAIM_WORDS:
        haystacks.append(_normalize(reality))

    for haystack in haystacks:
        if not haystack:
            continue
        for rule in RULES:
            if rule.matches(haystack, flag_type):
                return Classification(
                    theme=rule.theme.value,
                    classified_by="rule",
                    rule_id=rule.rule_id,
                    title=rule.title,
                )

    default = TYPE_DEFAULTS.get(flag_type)
    if default is not None:
        return Classification(
            theme=default.value,
            classified_by="type_default",
            rule_id="",
            title=_DEFAULT_TITLES[default],
        )
    return Classification(
        theme=Theme.UNCLASSIFIED.value,
        classified_by="none",
        rule_id="",
        title=_DEFAULT_TITLES[Theme.UNCLASSIFIED],
    )


#: A claim at or below this many words carries no themeable signal on its own,
#: so the fact-sheet correction is consulted instead. Four is deliberate: it
#: covers "No.", "$0", "iOS only" and "not licensed", and excludes anything that
#: states a fact.
_TERSE_CLAIM_WORDS = 4

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace. Punctuation is KEPT — `$` and `/` carry
    meaning here (``$349``, ``24/7``), unlike in `finding_id.normalize` where the
    job is the opposite."""
    return _WS_RE.sub(" ", text.casefold()).strip()


@dataclass(frozen=True)
class Coverage:
    """How the rule set is holding up. Report it; don't average it away."""

    total: int
    by_rule: int
    by_type_default: int
    unclassified: int

    @property
    def unclassified_rate(self) -> float:
        return self.unclassified / self.total if self.total else 0.0

    @property
    def type_default_rate(self) -> float:
        """The leading indicator. Rising = the engines are saying something new."""
        return self.by_type_default / self.total if self.total else 0.0


def coverage(classifications: Sequence[Classification]) -> Coverage:
    """Roll up how a run's flags were classified."""
    by_rule = sum(1 for c in classifications if c.classified_by == "rule")
    by_default = sum(1 for c in classifications if c.classified_by == "type_default")
    return Coverage(
        total=len(classifications),
        by_rule=by_rule,
        by_type_default=by_default,
        unclassified=len(classifications) - by_rule - by_default,
    )


def theme_label(theme: str) -> str:
    """Client-facing heading for a theme. Unknown themes render readably, not raw."""
    return THEME_LABELS.get(theme, theme.replace("_", " ").capitalize())


if __name__ == "__main__":
    samples = [
        ("identity", "There isn't a widely recognized brand called 'Fort'."),
        ("identity", "Fort (assuming you mean Fitbit?) makes fitness trackers."),
        ("stale", "The Fort band is already shipping."),
        ("wrong_pricing", "The Fort band costs $349."),
        ("missing_or_invented_feature", "It measures blood pressure and ECG."),
        ("missing_or_invented_feature", "There is no Android app."),
        ("competitor_confusion", "It's just a heart-rate band like Whoop."),
        ("licensing", "It is unclear whether they are licensed and bonded."),
        ("wrong_service_area", "They serve the entire Bay Area."),
    ]
    results = [classify(t, c) for t, c in samples]
    for (_, claim), r in zip(samples, results, strict=True):
        print(f"{r.theme:32s} {r.classified_by:12s} {r.rule_id:26s} {claim[:44]}")
    cov = coverage(results)
    print(f"\nby_rule={cov.by_rule} default={cov.by_type_default} unclassified={cov.unclassified}")
