"""The fact sheet as a client-facing, signed artifact (P5-T2).

The fact sheet is the ground truth behind every accuracy finding, and until now
it was invisible to the person it describes. That is a credibility problem before
it is a product one: research on LLM judges is consistent that a human-written
reference is the single most effective reliability mitigation, and a reference
the client has never seen makes every finding only as trustworthy as a black box.

Three things live here, and each closes a specific gap:

**A client render.** `render.to_markdown` is the INTERNAL document — claim ids,
verification tiers, provenance quotes, references to plan sections. Useful to us,
unreadable to a client, and it leaks our own working notes.
:func:`to_client_markdown` is the artifact a client reads and signs.

**A changelog.** "We changed your fact sheet" with no diff is the same failure as
retro-adjusting a prior cycle's numbers: the client cannot tell what moved.
:func:`changelog_between` produces the added/removed/changed list.

**A cache-key warning.** The sheet is IN THE JUDGE CACHE KEY. Editing it
invalidates every cached verdict for that client — correct behaviour, and
expensive if it happens by accident. :func:`cache_impact` is what the UI must
show before saving, and it is computed from the same text the cache keys on
rather than from a guess about which fields matter.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

from src.audit.factsheet.models import BusinessKind, FactSheet, Verification, assigned_claims
from src.audit.factsheet.render import expected_fact_sheet_text

__all__ = [
    "SignoffRecord",
    "ChangelogEntry",
    "CacheImpact",
    "to_client_markdown",
    "changelog_between",
    "cache_impact",
    "may_run_without_signoff",
]


@dataclass(frozen=True)
class SignoffRecord:
    """Who vouched for this version of the sheet, and when.

    A name and a date, not a checkbox. The claim being made is "a person at this
    company read these lines and says they are true", and that claim needs
    someone attached to it — an anonymous approval is an approval nobody can be
    asked about later.
    """

    sheet_version: int
    #: The text the signature covers, hashed. If the sheet changes, the old
    #: signature no longer describes it and `covers` says so.
    signed_text_sha256: str
    signed_by: str
    signed_role: str
    signed_at: str
    note: str = ""

    def covers(self, sheet: FactSheet) -> bool:
        """Whether this signature still describes the sheet in hand.

        Hash-based rather than version-based: a version number is a label someone
        remembers to bump, and the one failure mode that matters here is a silent
        edit under a signature that was never re-obtained.
        """
        return self.signed_text_sha256 == _text_hash(sheet)


class ChangelogEntry(TypedDict):
    """One line of difference between two versions of a sheet."""

    kind: str  # added | removed | changed
    key: str
    before: str
    after: str


class CacheImpact(TypedDict):
    """What saving this edit costs, before it is saved."""

    invalidates_cache: bool
    before_key_fragment: str
    after_key_fragment: str
    changed_claims: int
    warning: str


def _text_hash(sheet: FactSheet) -> str:
    """Hash of exactly the text the judge sees and the cache keys on.

    NOT of the whole sheet object. Provenance quotes, source URLs and open
    questions never reach the judge, so an edit to one of them must not read as a
    measurement change — and a hash over the whole object would say it did.
    """
    return hashlib.sha256(expected_fact_sheet_text(sheet).encode("utf-8")).hexdigest()


_CLIENT_INTRO = (
    "This is the reference we check AI answers against. Every finding in your "
    "report is a difference between something a model said and a line below. If a "
    "line here is wrong, the finding built on it is wrong — so read it as the "
    "thing being measured, not as paperwork."
)

_UNCONFIRMED_NOTE = (
    "Lines marked *needs your confirmation* came from public sources and have not "
    "been vouched for by anyone at your company. We hold findings built on them to "
    "a lower severity until they are confirmed."
)


def to_client_markdown(
    sheet: FactSheet,
    changelog: Sequence[ChangelogEntry] = (),
    signoff: SignoffRecord | None = None,
) -> str:
    """The client-readable artifact: "Brand Fact Sheet v1.0", with a changelog.

    Deliberately NOT `render.to_markdown` with the internal bits stripped.
    Redacting a document leaves the redacted thing in the file; this builds the
    client version from the claims directly, so a claim id or a plan reference
    cannot survive by being missed.
    """
    claims = assigned_claims(sheet.claims)
    unconfirmed = [c for c in claims if c.verification is not Verification.CLIENT_CONFIRMED]
    kind = "local service" if sheet.business_kind is BusinessKind.LOCAL_SERVICE else "product"

    lines: list[str] = [
        f"# Brand Fact Sheet v{sheet.version}.0 — {sheet.business_name}",
        "",
        _CLIENT_INTRO,
        "",
        f"**{sheet.domain}** · {kind} · {len(claims)} facts · prepared {sheet.generated_at}",
        "",
    ]

    if signoff is not None and signoff.covers(sheet):
        lines.extend(
            [
                f"**Signed off by {signoff.signed_by}"
                f"{f' ({signoff.signed_role})' if signoff.signed_role else ''} "
                f"on {signoff.signed_at}.**",
                "",
            ]
        )
    elif signoff is not None:
        # A signature that no longer describes the document is worse than none:
        # it looks like assurance and is not.
        lines.extend(
            [
                f"**This sheet has changed since {signoff.signed_by} signed it on "
                f"{signoff.signed_at}. It needs to be signed again before the next "
                f"measurement.**",
                "",
            ]
        )
    else:
        lines.extend(
            ["**Not yet signed off.** Please confirm or correct every line below.", ""]
        )

    lines.append("## The facts we check against")
    lines.append("")
    for claim in claims:
        # No claim id, no verification enum, no provenance quote. The client
        # needs the fact and whether we have their word for it.
        confirmed = claim.verification is Verification.CLIENT_CONFIRMED
        suffix = "" if confirmed else " *(needs your confirmation)*"
        lines.append(f"- **{claim.key.replace('_', ' ')}:** {claim.value}{suffix}")

    if unconfirmed:
        lines.extend(["", _UNCONFIRMED_NOTE])

    if sheet.questions:
        lines.extend(
            [
                "",
                "## What we still need from you",
                "",
                "Sources disagreed, or the answer is not something we can look up. "
                "Nothing here is treated as a fact until you answer it.",
                "",
            ]
        )
        lines.extend(f"{i}. {q}" for i, q in enumerate(sheet.questions, start=1))

    if changelog:
        lines.extend(["", f"## What changed in v{sheet.version}.0", ""])
        for entry in changelog:
            key = entry["key"].replace("_", " ")
            if entry["kind"] == "added":
                lines.append(f"- **Added** {key}: {entry['after']}")
            elif entry["kind"] == "removed":
                lines.append(f"- **Removed** {key} (was: {entry['before']})")
            else:
                lines.append(f"- **Changed** {key}: {entry['before']} → {entry['after']}")

    lines.extend(
        [
            "",
            "---",
            "",
            "Changes go through us rather than being edited in place, so that every "
            "past report stays readable against the sheet it was measured with.",
            "",
        ]
    )
    return "\n".join(lines)


def changelog_between(before: FactSheet, after: FactSheet) -> list[ChangelogEntry]:
    """What changed between two versions, by claim key.

    Keyed on the claim KEY rather than the claim id: ids are minted per
    extraction, so a re-extracted sheet would otherwise report every line as
    removed-and-added — a diff that says everything changed says nothing.
    """
    old = {c.key: c.value for c in assigned_claims(before.claims)}
    new = {c.key: c.value for c in assigned_claims(after.claims)}
    entries: list[ChangelogEntry] = []
    for key in sorted(set(old) | set(new)):
        was, now = old.get(key), new.get(key)
        if was == now:
            continue
        if was is None:
            entries.append(ChangelogEntry(kind="added", key=key, before="", after=now or ""))
        elif now is None:
            entries.append(ChangelogEntry(kind="removed", key=key, before=was, after=""))
        else:
            entries.append(ChangelogEntry(kind="changed", key=key, before=was, after=now))
    return entries


def cache_impact(before: FactSheet, after: FactSheet) -> CacheImpact:
    """What saving this edit does to the judge cache. Show it BEFORE saving.

    The sheet is in the cache key, so any change to the text the judge sees
    invalidates every cached verdict for that client. That is correct — a verdict
    reached against different ground truth is a different verdict — but it is
    also the difference between a free re-judge and a paid one, and a client-
    facing edit screen must say so rather than discovering it afterwards.

    An edit that does NOT change the judge's view (a fixed typo in a source URL,
    a reworded open question) reports no invalidation, because it causes none.
    """
    old_hash, new_hash = _text_hash(before), _text_hash(after)
    changed = [e for e in changelog_between(before, after)]
    invalidates = old_hash != new_hash
    warning = ""
    if invalidates:
        warning = (
            f"Saving this changes {len(changed)} fact"
            f"{'s' if len(changed) != 1 else ''} the judge reads, which invalidates "
            f"every cached verdict for this client. The next judging pass will be "
            f"charged rather than served from cache. Past reports are unaffected — "
            f"they keep the sheet they were measured against."
        )
    return CacheImpact(
        invalidates_cache=invalidates,
        before_key_fragment=old_hash[:12],
        after_key_fragment=new_hash[:12],
        changed_claims=len(changed),
        warning=warning,
    )


def may_run_without_signoff(sheet: FactSheet, signoff: SignoffRecord | None) -> bool:
    """Whether a FIRST measurement may proceed against this sheet.

    False without a current signature. The findings a fact sheet produces are
    assertions that a named vendor's model said something untrue about a company,
    and making that assertion against ground truth nobody at the company has
    confirmed is the one place this product could be badly wrong in public.

    Re-runs are not gated here: the signature covers the sheet, and a sheet that
    has not changed does not need signing twice.
    """
    return signoff is not None and signoff.covers(sheet)
