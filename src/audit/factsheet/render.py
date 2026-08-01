"""The two renderers a :class:`FactSheet` supports (plan §2).

Renderer 1 is the flat one the machine reads: ``block,key,value,intent,persona``
rows that ``src/prompts/csv_loader.py`` merges into the ``fact_sheet`` string the
judge is given. It is flat by construction — ``_build_fact_sheet`` joins
``"{key}: {value}"`` lines, so nothing below the key survives the trip, which is
why the key has to carry the section (``hours_sunday``, not ``sunday``).

Renderer 2 is the one a human reads: the §A–§G template layout plus a provenance
appendix. Its extra job is honesty — a claim the owner never vouched for renders
visibly marked, so a signature on the document cannot launder provenance the
client never gave (plan §8).

Both are pure: no fetching, no clock, no environment. The same sheet renders the
same bytes on any machine, which is what makes the round-trip test in
``tests/test_factsheet_render.py`` an oracle rather than a smoke test.
"""

from __future__ import annotations

import csv
import io
import re

from src.audit.factsheet.models import (
    BusinessKind,
    FactSheet,
    SheetSection,
    Verification,
    assigned_claims,
)

__all__ = [
    "FACT_CSV_HEADER",
    "to_fact_rows",
    "to_csv",
    "to_markdown",
    "expected_fact_sheet_text",
    "suggested_run_inputs",
]

# Mirrors ``csv_loader._COLUMNS``. Duplicated rather than imported because that
# name is private to the input-contract layer and F0 does not own that file; if a
# third writer ever appears, promote it there instead of copying it again.
FACT_CSV_HEADER: tuple[str, str, str, str, str] = ("block", "key", "value", "intent", "persona")

_FACT_BLOCK = "fact"

# Headings lifted verbatim from docs/fact-sheet-template-local.md, so a generated
# sheet and a hand-written one are the same document to a reader.
_LOCAL_SECTION_TITLES: dict[SheetSection, str] = {
    SheetSection.IDENTITY: "A · Identity & basics",
    SheetSection.CONTACT: "B · Contact & location → `wrong_contact`",
    SheetSection.HOURS: "C · Hours & availability → `wrong_hours`",
    SheetSection.SERVICE_AREA: "D · Service area → `wrong_service_area`",
    SheetSection.LICENSING: "E · Licensing, insurance & credentials → `licensing`",
    SheetSection.SERVICES_PRICING: (
        "F · Services & pricing → `wrong_pricing`, `missing_or_invented_feature`"
    ),
    SheetSection.PRESENCE: "G · Reputation & presence",
}

# docs/fact-sheet-template.md organises a product around identity / pricing /
# features / positioning, so only three sections have a home there. The other
# four keep their local headings rather than being dropped: a cited claim that
# exists is never worth losing to a layout, and a product sheet that happens to
# carry a phone number should still show it.
_PRODUCT_SECTION_TITLES: dict[SheetSection, str] = {
    **_LOCAL_SECTION_TITLES,
    SheetSection.IDENTITY: "A · Identity & basics",
    # A product's features live here too — the consumer template splits them into
    # "C · Features & capabilities", but both are `wrong_pricing` /
    # `missing_or_invented_feature` territory and the key already disambiguates.
    SheetSection.SERVICES_PRICING: "B · Pricing, features & capabilities",
    SheetSection.PRESENCE: "D · Positioning & competitors",
}

# What a reader sees next to a claim. Anything short of `client_confirmed` says
# UNCONFIRMED in as many words (plan §8) — "cross_confirmed" reads like an
# endorsement to someone skimming, and two public sources can be stale together.
_VERIFICATION_NOTES: dict[Verification, str] = {
    Verification.PUBLIC_SOURCE_ONLY: "**UNCONFIRMED** — one public source",
    Verification.CROSS_CONFIRMED: "**UNCONFIRMED** — two public sources agree",
    Verification.CLIENT_CONFIRMED: "client-confirmed",
}


def to_fact_rows(sheet: FactSheet) -> list[tuple[str, str, str, str, str]]:
    """The sheet as platform CSV rows: ``(block, key, value, intent, persona)``.

    ``intent`` and ``persona`` are empty because they are query columns; the
    parser reads them only on ``query`` rows. Claims come out in claim-ID order
    so a diff between two regenerations is a diff of facts, not of ordering.
    """
    return [
        (_FACT_BLOCK, claim.key, claim.value, "", "")
        for claim in assigned_claims(sheet.claims)
    ]


def to_csv(sheet: FactSheet) -> str:
    """The fact block as CSV text, quoted the way ``csv_loader`` expects.

    The header row is mandatory, not optional: ``parse_csv_files`` builds a
    ``csv.DictReader`` per file, so the first line of every uploaded file is
    consumed as the header. A headerless fact file loses its first claim to that
    and then fails ``_normalize_header``, which is a confusing way to report a
    missing column. ``csv.writer``'s defaults (``\\r\\n``, minimal quoting) are
    what ``build_template_csv`` already emits and what the reader round-trips.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FACT_CSV_HEADER)
    writer.writerows(to_fact_rows(sheet))
    return buffer.getvalue()


def expected_fact_sheet_text(sheet: FactSheet) -> str:
    """What ``csv_loader._build_fact_sheet`` will produce from these rows.

    The judge's view of the sheet, without a CSV round trip — an oracle for the
    round-trip test, and the honest answer to "what will the model actually see"
    for anything that has to reason about prompt size or content.
    """
    return "\n".join(f"{claim.key}: {claim.value}" for claim in assigned_claims(sheet.claims))


def to_markdown(sheet: FactSheet) -> str:
    """The human render: template layout, then the provenance appendix.

    Used by ``geo audit --fact-sheet``, the paid audit deliverable and the F4
    review screen. Sections with no claims are omitted rather than rendered
    empty — blank is safe (§4.2), and an empty heading is an invitation to fill
    it in from memory.
    """
    claims = assigned_claims(sheet.claims)
    titles = (
        _LOCAL_SECTION_TITLES
        if sheet.business_kind is BusinessKind.LOCAL_SERVICE
        else _PRODUCT_SECTION_TITLES
    )
    unconfirmed = [c for c in claims if c.verification is not Verification.CLIENT_CONFIRMED]

    lines: list[str] = [_heading(sheet), ""]
    lines.extend(_meta_block(sheet, len(claims)))
    lines.append("")

    if unconfirmed:
        lines.extend(
            [
                f"**{len(unconfirmed)} of {len(claims)} claims are NOT client-confirmed.** "
                "A signature covers only the lines the owner vouched for; a line marked "
                "UNCONFIRMED may not be cited as the correct fact from a signed sheet "
                "(plan §8).",
                "",
            ]
        )

    lines.append("---")
    for section in SheetSection:
        in_section = [c for c in claims if c.section is section]
        if not in_section:
            continue
        lines.extend(["", f"## {titles[section]}", ""])
        for claim in in_section:
            note = _VERIFICATION_NOTES[claim.verification]
            lines.append(f"- **{claim.key}:** {claim.value} — {note} [`{claim.claim_id}`]")

    if sheet.questions:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Open questions",
                "",
                "*Sources disagreed, or the answer cannot be derived from a closed "
                "enumeration. Nothing below is a fact yet — ask, then add (§4.3, §4.4).*",
                "",
            ]
        )
        lines.extend(f"{i}. {q}" for i, q in enumerate(sheet.questions, start=1))

    lines.extend(
        [
            "",
            "---",
            "",
            "## Provenance appendix",
            "",
            "*Every line above, with the source text it was taken from. A claim whose "
            "quote is not a literal substring of its source never ships (§4.1).*",
            "",
            "| claim_id | quote | source_url | as_of | verification |",
            "|---|---|---|---|---|",
        ]
    )
    for claim in claims:
        tier = claim.verification.value
        if claim.verification is not Verification.CLIENT_CONFIRMED:
            tier = f"{tier} (UNCONFIRMED)"
        lines.append(
            f"| {claim.claim_id} | {_cell(claim.verbatim_quote)} | {_cell(claim.source_url)} "
            f"| {_cell(claim.as_of)} | {tier} |"
        )

    return "\n".join(lines) + "\n"


def _heading(sheet: FactSheet) -> str:
    kind = " (LOCAL SERVICE)" if sheet.business_kind is BusinessKind.LOCAL_SERVICE else ""
    return f"# Client Fact Sheet{kind} — {sheet.business_name}"


def _meta_block(sheet: FactSheet, n_claims: int) -> list[str]:
    lines = [
        "> **Meta**",
        f"> - Domain: {sheet.domain}",
        f"> - Business kind: {sheet.business_kind.value} · "
        f"Status: {sheet.sheet_status.value} · Version: {sheet.version}",
        f"> - Generated: {sheet.generated_at} · "
        f"Weakest verification: {sheet.verification_tier.value}",
        f"> - Claims: {n_claims} · Open questions: {len(sheet.questions)}",
    ]
    if sheet.lead_ref is not None:
        lines.append(f"> - Lead ref: {sheet.lead_ref}")
    return lines


def _cell(text: str) -> str:
    """One markdown table cell: whitespace collapsed, pipes escaped.

    A verbatim quote is whatever the page said, which routinely includes newlines
    and the occasional ``|`` — both break the table silently, taking the rest of
    the row's provenance with them.
    """
    collapsed = " ".join(text.split())
    return collapsed.replace("|", r"\|") if collapsed else "—"


# --- derived run inputs (the "start from a lead" prefill) ---------------------

# "…, Abingdon, Maryland 21009" — city, then a state spelled in FULL. Two-letter
# forms are deliberately not matched: nothing in this repo expands "MD" to
# "Maryland", because the SERP vendors reject the short form and return an empty
# surface, which reads as the business being absent. Better to leave the field
# blank and let a human type it than to guess a market.
_CITY_FULL_REGION_RE = re.compile(
    r",\s*([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3})\s*,\s*([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]+)?)\b"
)


def suggested_run_inputs(sheet: FactSheet) -> dict[str, str | None]:
    """What a run's config can be PREFILLED with from an approved sheet.

    The sheet was extracted from the business's own website, so retyping its name,
    domain and city into a run form is copying data we already hold. This reads it
    back out.

    Best-effort and honest about it: `city`/`region` come from parsing an address
    claim, and either may be None. A None means "ask the human", never "guess" —
    which is why a two-letter state yields None rather than an expansion.
    """
    by_key = {c.key: c.value for c in sheet.claims}
    city: str | None = None
    region: str | None = None

    # The postal address first: it is the one claim that reliably spells a state in
    # full. `service_area_primary` is often the lead's own "Abingdon, MD" shorthand.
    for key in ("contact_address", "contact_address_berkeley", "service_area_primary"):
        value = by_key.get(key)
        if not value:
            continue
        match = _CITY_FULL_REGION_RE.search(value)
        if match:
            city, region = match.group(1).strip(), match.group(2).strip()
            break

    return {
        "business": sheet.business_name or None,
        "website": by_key.get("identity_website") or sheet.domain or None,
        "city": city,
        "region": region,
    }
