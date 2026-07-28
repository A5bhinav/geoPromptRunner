"""The local-service audit report — ``docs/report-template-local.md`` as code.

Same instrument as the consumer report, different reader: a shop owner who wants to
know *whether customers are being sent to someone else*, not a growth lead reading a
dashboard. Selected on ``business_kind == "local_service"``; the consumer renderer
(``query_report.render_audit_report``) is untouched and stays the default.

The six hard rules from the template are enforced here in code, not left to whoever
writes the copy. Each exists because breaking it produces a claim we cannot back:

1. **No aggregate appearance ratio.** "Appears in 4 of 11 queries" reads as a
   visibility rate and is not one — the denominator is a query set *we* chose. This
   module never computes one.
2. **Never claim more than the judge measured.** Every verb about a rival grades off
   judged prominence via ``_competitor_verb`` — "recommends" is reserved for
   ``recommended_first``. Mirrors ``competitorVerb`` in ``teaser/src/render/copy.ts``;
   the two must stay in step.
3. **Never name a competitor that did not come from a captured local-pack entity.**
   ``_rival_is_captured`` gates every rival name. Claude does not reliably know the
   plumbers in a given city, and a fabricated rival printed in a report handed to a
   real shop owner is the unrecoverable failure for this product.
4. **No accuracy or agreement FIGURE** until W3.4 calibration passes. The individual
   flags still render — each carries its own verbatim evidence, which is the point of
   §4 — but no rate, precision or agreement number appears, and the section carries an
   uncalibrated banner. Mention, prominence and framing are unaffected and quotable.
5. **No cadence delta without a measured noise floor.** This renderer emits no trend
   section at all; when one is added it must carry ``local_cadence_warning(trade)``.
6. **Print the location, always.** An audit whose location was ``None`` measured an
   unpinned locale and is not a local audit — ``render_local_report`` refuses to render
   without one rather than printing a report that quietly describes the wrong market.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.api.reports import LocalPackPayload, SiteAuditPayload
from src.audit.offsite.tools import LOCAL_REVIEW_PLATFORMS
from src.pipeline.local_sampling import sampling_note
from src.pipeline.orchestrator import AuditOutcome
from src.prompts.intent import IntentBucket
from src.storage.models import AccuracyFlag, AnswerJudgment

__all__ = ["render_local_report", "LocalLead"]

# Google Business Profile, probed via its Maps listing. Scored separately from the
# other directories at weight 3.0 (W4.3) because the local pack — and the AI answers
# built on it — are generated FROM this entity: no profile means structurally absent,
# and averaging that into "3 of 8 directories present" would hide it.
_GBP_PLATFORM = "google.com/maps"

#: The four local accuracy flags, in the order a shop owner cares about. A wrong phone
#: number or wrong hours costs a job today; licensing is slower but more damaging.
_LOCAL_FLAG_ORDER: tuple[str, ...] = (
    "wrong_contact",
    "wrong_hours",
    "wrong_service_area",
    "licensing",
)

#: Display noun for a trade — "best PLUMBER in Berkeley", not "best plumbing in
#: Berkeley". The template's §1/§3 headings read as a customer's own question, so the
#: trade key (a slug) is never printed raw. Unknown trades fall through to the key,
#: which is ugly but never wrong.
_TRADE_NOUN: dict[str, str] = {
    "plumbing": "plumber",
    "hvac": "HVAC contractor",
    "barbershop": "barber",
}


def _trade_noun(trade: str) -> str:
    return _TRADE_NOUN.get(trade.strip().lower(), trade.strip())


_FLAG_LABELS: dict[str, str] = {
    "wrong_contact": "Wrong phone or address",
    "wrong_hours": "Wrong opening hours / availability",
    "wrong_service_area": "Wrong service area",
    "licensing": "Wrong licensing or insurance claim",
}


class LocalLead:
    """The single (query, engine) cell §1 is built from.

    Not a NamedTuple/dataclass by accident — it carries the *judged* prominence beside
    the verbatim answer so the copy can never be graded off anything else.
    """

    def __init__(
        self,
        *,
        prompt: str,
        engine_name: str,
        answer: str,
        competitor: str,
        prominence: str,
        runs_observed: int,
        runs_confirming: int,
    ) -> None:
        self.prompt = prompt
        self.engine_name = engine_name
        self.answer = answer
        self.competitor = competitor
        self.prominence = prominence
        self.runs_observed = runs_observed
        self.runs_confirming = runs_confirming


def _competitor_verb(prominence: str) -> str:
    """Present-tense verb for what an engine did with a rival, graded by prominence.

    Rule 2. Mirrors ``competitorVerb`` in ``teaser/src/render/copy.ts`` — "recommends"
    is reserved for ``recommended_first`` and anything weaker grades down, so the
    report never claims more than the judge actually saw.
    """
    if prominence == "recommended_first":
        return "recommends"
    if prominence == "mid_pack":
        return "features"
    return "mentions"


def _prominence_word(prominence: str) -> str:
    """Past participle, graded by the same rule as ``_competitor_verb``."""
    if prominence == "recommended_first":
        return "recommended"
    if prominence == "mid_pack":
        return "featured"
    return "mentioned"


def _captured_rivals(local_pack: LocalPackPayload | None, client: str) -> set[str]:
    """Business names captured from Google's local pack, excluding the client.

    Rule 3's allowlist: the ONLY names this report may print as competitors.
    """
    if local_pack is None:
        return set()
    return {
        row["name"] for row in local_pack["entities"] if not row["is_client"] and row["name"]
    }


def _rival_is_captured(name: str, captured: set[str]) -> bool:
    """Whether ``name`` matches a captured local-pack entity.

    Containment either way, case-folded — a Google listing is routinely longer than the
    name an engine says ("Albert Nahman Plumbing, Heating, and Cooling" vs "Albert
    Nahman Plumbing"). Deliberately NOT fuzzy: this gate exists to stop fabricated
    rivals, and a fuzzy match would eventually let one through.
    """
    needle = name.strip().casefold()
    if not needle:
        return False
    return any(needle in c.casefold() or c.casefold() in needle for c in captured)


def _select_lead(
    outcome: AuditOutcome,
    judgments: list[AnswerJudgment],
    captured: set[str],
) -> LocalLead | None:
    """The most damaging local-intent cell: a rival named, the client absent.

    Only ``local_intent`` queries qualify — §1 is the buying moment, not an
    informational question. Ranked by the rival's prominence, because "recommends
    first" is a stronger artifact than "mentions". Returns None when nothing qualifies,
    which is a real outcome (the client may simply be present everywhere) and must not
    be faked.
    """
    client = outcome.client_name.strip().casefold()
    answers = {(r["query_id"], r["engine_name"], r["run_index"]): r for r in outcome.results}
    rank = {"recommended_first": 0, "mid_pack": 1, "buried": 2, "also_ran": 3}

    best: tuple[int, LocalLead] | None = None
    for judgment in judgments:
        if not judgment.assessed or judgment.intent != IntentBucket.LOCAL_INTENT.value:
            continue
        client_present = any(
            b.present for b in judgment.brands if b.brand.strip().casefold() == client
        )
        if client_present:
            continue  # §1 is about the client being ABSENT
        for brand in judgment.brands:
            if not brand.present or brand.brand.strip().casefold() == client:
                continue
            # Rule 3: a rival the local pack never captured may not be named.
            if not _rival_is_captured(brand.brand, captured):
                continue
            row = answers.get((judgment.query_id, judgment.engine_name, judgment.run_index))
            if row is None or not (row["response"] or "").strip():
                continue
            observed, confirming = _reproducibility(
                judgments, judgment.query_id, judgment.engine_name, brand.brand
            )
            lead = LocalLead(
                prompt=row["prompt"],
                engine_name=judgment.engine_name,
                answer=(row["response"] or "").strip(),
                competitor=brand.brand,
                prominence=brand.prominence,
                runs_observed=observed,
                runs_confirming=confirming,
            )
            score = rank.get(brand.prominence, 9)
            if best is None or score < best[0]:
                best = (score, lead)
    return best[1] if best else None


def _reproducibility(
    judgments: list[AnswerJudgment], query_id: str, engine_name: str, competitor: str
) -> tuple[int, int]:
    """(runs observed, runs the rival was present in) for one (query, engine) cell."""
    target = competitor.strip().casefold()
    observed = confirming = 0
    for j in judgments:
        if j.query_id != query_id or j.engine_name != engine_name or not j.assessed:
            continue
        observed += 1
        if any(b.present and b.brand.strip().casefold() == target for b in j.brands):
            confirming += 1
    return observed, confirming


def _local_flags(judgments: list[AnswerJudgment]) -> list[AccuracyFlag]:
    """Local accuracy flags across the run, deduped, in owner-priority order."""
    seen: set[tuple[str, str, str]] = set()
    out: list[AccuracyFlag] = []
    for judgment in judgments:
        for flag in judgment.accuracy_flags:
            key = (str(flag.type), flag.claim, flag.reality)
            if key in seen or str(flag.type) not in _LOCAL_FLAG_ORDER:
                continue
            seen.add(key)
            out.append(flag)
    return sorted(out, key=lambda f: _LOCAL_FLAG_ORDER.index(str(f.type)))


def _directory_rows(site_audit: SiteAuditPayload | None) -> dict[str, str]:
    """platform -> 'present' | 'missing' | 'unknown', from the Cat 6 offsite findings.

    ``unknown`` is distinct from ``missing`` on purpose: the offsite agent needs a
    search tool, and without one it runs a deterministic pre-pass only. Reporting
    "not listed on Yelp" when nobody looked would be an invented finding.
    """
    status: dict[str, str] = dict.fromkeys(LOCAL_REVIEW_PLATFORMS, "unknown")
    if site_audit is None:
        return status
    for finding in site_audit["offsite"]:
        # Only the reviews finding carries a per-platform breakdown; everything else
        # leaves the checklist alone rather than guessing from a title string.
        for host, present in (finding.get("platforms") or {}).items():
            if host in status:
                status[host] = "present" if present else "missing"
    return status


def _light(state: str) -> str:
    return {"present": "🟢 listed", "missing": "🔴 not found", "unknown": "⚪ not checked"}[state]


def render_local_report(
    outcome: AuditOutcome,
    *,
    trade: str,
    location: str,
    local_pack: LocalPackPayload | None = None,
    judgments: list[AnswerJudgment] | None = None,
    site_audit: SiteAuditPayload | None = None,
    run_date: str | None = None,
) -> str:
    """Render the local-service markdown report.

    ``location`` is required and must be non-blank (rule 6): a report built from an
    unpinned locale describes the wrong market, and printing it without saying so is
    the failure this refuses to commit. Raises ``ValueError`` rather than degrade.

    Pure and deterministic — no network, no clock beyond ``run_date``.
    """
    market = location.strip()
    if not market:
        raise ValueError(
            "render_local_report requires a location: a local report built from an "
            "unpinned locale describes a different market than the client's."
        )

    client = outcome.client_name
    judged = [j for j in (judgments or []) if j.assessed]
    captured = _captured_rivals(local_pack, client)
    run_date = run_date or datetime.now(UTC).date().isoformat()
    city = market.split(",")[0].strip()

    noun = _trade_noun(trade)
    lines: list[str] = [f"# What AI tells customers looking for a {noun} in {city}", ""]
    lines.append(f"**{client}** · {market} · {run_date}")
    lines.append("")

    # --- 1 · The one answer that matters ------------------------------------------
    lines.append("## 1 · What a customer sees right now")
    lines.append("")
    lead = _select_lead(outcome, judged, captured) if judged else None
    if lead is not None:
        verb = _competitor_verb(lead.prominence)
        lines.append(
            f"Asked **“{lead.prompt}”**, {lead.engine_name} {verb} "
            f"**{lead.competitor}** — and does not mention {client}."
        )
        lines.append("")
        lines.append("> " + lead.answer.replace("\n", "\n> "))
        lines.append("")
    elif not judged:
        lines.append(
            "_Not available: this run has not been judged, and the verbatim answer "
            "shown here must be graded by the judge rather than pattern-matched._"
        )
        lines.append("")
    elif not captured:
        # Rule 3, made visible rather than silently producing a rival-less section.
        lines.append(
            "_No local-pack entities were captured for this market, so no competitor "
            "can be named here. Every rival this report prints must come from a "
            "captured Google local-pack listing._"
        )
        lines.append("")
    else:
        lines.append(
            f"_On the buying-moment queries we measured, no captured competitor was "
            f"named while {client} was absent._"
        )
        lines.append("")

    # --- 2 · Reproducibility -------------------------------------------------------
    lines.append("## 2 · How many times we asked")
    lines.append("")
    if lead is not None and lead.runs_observed >= 2 and lead.runs_confirming == lead.runs_observed:
        lines.append(
            f"Asked {lead.runs_observed} separate times — {lead.competitor} was "
            f"{_prominence_word(lead.prominence)} every time. This is not a one-off."
        )
    else:
        lines.append(
            "Not enough repeat observations to claim this result reproduces, so no "
            "reproducibility claim is made."
        )
    lines.append("")
    lines.append(f"_{sampling_note(trade)}_")
    lines.append("")

    # --- 3 · Where AI looks --------------------------------------------------------
    lines.append(f"## 3 · Where AI looks for a {noun} in {city}")
    lines.append("")
    status = _directory_rows(site_audit)
    lines.append(
        f"**Google Business Profile — {_light(status[_GBP_PLATFORM])}**  "
        "\n_The local pack, and the AI answers built on it, are generated from this "
        "profile. It is scored separately because no profile means structurally absent._"
    )
    lines.append("")
    lines.append("| Directory | Status |")
    lines.append("|---|---|")
    for platform in LOCAL_REVIEW_PLATFORMS:
        if platform == _GBP_PLATFORM:
            continue
        lines.append(f"| {platform} | {_light(status[platform])} |")
    lines.append("")

    if local_pack is not None and local_pack["entities"]:
        lines.append(f"**Who Google's local pack shows in {city}:**")
        lines.append("")
        for query_id, rank in sorted(local_pack["client_positions"].items()):
            prompt = next(
                (e["prompt"] for e in local_pack["entities"] if e["query_id"] == query_id), query_id
            )
            place = f"**#{rank}**" if rank is not None else "**not in the pack**"
            lines.append(f"- “{prompt}” — {client} ranks {place}")
        lines.append("")

    # --- 4 · What AI gets wrong ----------------------------------------------------
    lines.append("## 4 · What AI gets wrong about you")
    lines.append("")
    flags = _local_flags(judged)
    if flags:
        # Rule 4: the flags render with their evidence, but no rate/precision/agreement
        # figure appears, and the reader is told the layer is uncalibrated.
        lines.append(
            "_These are individual findings, each quoted against your fact sheet. "
            "The accuracy layer has not been re-calibrated since the last judge change, "
            "so no accuracy rate is quoted here._"
        )
        lines.append("")
        for flag in flags:
            label = _FLAG_LABELS.get(str(flag.type), str(flag.type))
            lines.append(f"**{label}** ({flag.severity})")
            lines.append(f"- AI says: “{flag.claim}”")
            lines.append(f"- Actually: “{flag.reality}”")
            lines.append("")
    else:
        lines.append("No contradictions of your fact sheet were found in the answers we read.")
        lines.append("")

    # --- 5 · What to fix, in order -------------------------------------------------
    lines.append("## 5 · What to fix, in order")
    lines.append("")
    roadmap = list(site_audit["roadmap"]) if site_audit is not None else []
    if roadmap:
        for i, item in enumerate(roadmap, 1):
            lines.append(f"{i}. **{item.get('title', '')}** — {item.get('why', '')}")
        lines.append("")
    else:
        lines.append("_No site audit was run for this client, so there is no roadmap yet._")
        lines.append("")

    # --- 6 · How this was measured -------------------------------------------------
    lines.append("## 6 · How this was measured")
    lines.append("")
    engines = sorted({r["engine_name"] for r in outcome.results if r["response"] is not None})
    lines.append(f"- **Location:** {market}")
    lines.append(f"- **Engines that answered:** {', '.join(engines) or 'none'}")
    lines.append(f"- **Query set:** {outcome.query_set_version}")
    lines.append(f"- **Runs per query:** {outcome.runs_per_query}")
    lines.append(f"- **Date:** {run_date}")
    if local_pack is not None:
        lines.append(f"- **Local pack source:** {', '.join(local_pack['sources'])}")
    lines.append("")
    lines.append(
        "_Only Google's local pack and AI Overviews/AI Mode are pinned to your market; "
        "the model APIs have no locale setting and answer un-localized._"
    )
    return "\n".join(lines)
