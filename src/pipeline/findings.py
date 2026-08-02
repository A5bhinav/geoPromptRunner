"""Turn 235 anonymous flags into ≤15 themed findings a client can act on.

This is the layer between the judge and the reader, and it is where the report
stops being a blob. Everything it does is deterministic Python — no LLM call —
so re-rendering the same run always produces the same groups in the same order
(``docs/audit-packaging-spec.md`` P1-T1).

The pipeline, in order:

1. **Escalate** severity onto the four-level scale (:mod:`src.pipeline.severity`).
2. **Classify** each flag's root cause (:mod:`src.pipeline.themes`).
3. **Cluster** claims into stable ``cluster_id``s (:mod:`src.pipeline.finding_id`).
4. **Group** by ``(theme, cluster_id)`` — theme first, because two clusters with
   no words in common can still be one root cause with one fix.
5. **Evidence** each group with a verbatim prompt, a named model, a date, and an
   honest "observed in N of M runs".
6. **Route and rank** it (:mod:`src.pipeline.priority`).

**One counting unit.** ``instance_count`` is individual observations;
client-facing headline counts are THEMES. Mixing the two on one page invites a
reader to do the subtraction and catch a contradiction, after which every number
on the page is suspect. This module exposes both and labels which is which.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.pipeline import finding_id, themes
from src.pipeline import severity as sev
from src.pipeline.priority import FixChannel, priority_score, routing_for
from src.storage.models import AccuracyFlag

__all__ = [
    "Occurrence",
    "Evidence",
    "FindingGroup",
    "GroupingResult",
    "build_finding_groups",
]

#: How many verbatim claims a card quotes. Two or three shows the reader the
#: error is a pattern rather than one odd sentence; more is a wall of near-
#: identical text that stops being evidence and starts being noise.
_MAX_REPRESENTATIVE_CLAIMS = 3

#: How many observations a card EVIDENCES, one per surface first.
#:
#: The evidence bundle's job is to make a finding checkable, and one verbatim
#: example per surface plus an honest "N of M runs" does that completely. Printing
#: every observation does not do it better — the first real PDF ran to 32 pages
#: with 16 of them a single finding's 94 near-identical excerpts, which is the
#: 235-identical-cards blob rebuilt one level down.
#:
#: Breadth beats depth in the selection too: four excerpts from four different
#: engines show the error is not one model's quirk, which is the question a reader
#: actually has. Four from one engine show nothing extra. `evidence_total` keeps
#: the real count, and the full set stays in the payload's `accuracy_flags`.
_MAX_EVIDENCE_PER_GROUP = 4

#: A borderline judge call is worth less in the ranking than a direct fact-sheet
#: contradiction. `med`/`low` are where the judge's own uncertainty concentrates.
_CONFIDENCE_BY_SEVERITY: dict[str, float] = {
    "critical": 1.0,
    "high": 1.0,
    "med": 0.6,
    "low": 0.6,
}


@dataclass(frozen=True)
class Occurrence:
    """How reproducibly a finding showed up. **Never render one without the other.**

    ``observed`` counts the runs that produced this finding; ``total`` counts the
    runs of the same (query, engine) cells that returned an answer at all. A cell
    that errored is excluded from both — "not measured" is not "not found", and
    conflating them is how a report tells a client something is fixed when an
    engine timed out.
    """

    observed: int
    total: int
    #: ISO dates of the first and last observation. Equal on a single-day run.
    first_seen_date: str
    last_seen_date: str

    @property
    def rate(self) -> float:
        return self.observed / self.total if self.total else 0.0

    def phrase(self) -> str:
        """The per-finding short form of the non-reproducibility disclosure."""
        if self.total <= 0:
            # A run stored before per-cell provenance existed. Say what is known
            # — the observation count — and refuse the denominator rather than
            # rounding it up to `observed`, which would assert perfect
            # reproducibility off a run that recorded no cells at all.
            times = "once" if self.observed == 1 else f"{self.observed} times"
            return f"observed {times}; this run predates per-answer provenance"
        span = (
            f" across {self.first_seen_date} → {self.last_seen_date}"
            if self.first_seen_date and self.last_seen_date != self.first_seen_date
            else (f" on {self.first_seen_date}" if self.first_seen_date else "")
        )
        return f"observed in {self.observed} of {self.total} runs{span}"


@dataclass(frozen=True)
class Evidence:
    """What makes a finding checkable rather than assertable.

    A finding without engine + timestamp + verbatim prompt is not shippable. This
    is that record, and the reason every field is here rather than "most of them".
    """

    #: The verbatim question asked. NEVER the query id — `cat-01` is a join key.
    prompt: str
    engine_name: str
    #: The pinned model that produced it, from the run's `engine_models`. Empty
    #: when the run predates the recording; the report says "model not recorded"
    #: rather than inventing one.
    model_id: str
    intent: str
    observed_at: str
    #: The model's own words. Quoted, never paraphrased — a paraphrase of a
    #: hallucination is a second hallucination.
    excerpt: str
    #: The fact-sheet line it contradicts, verbatim.
    reality: str


@dataclass(frozen=True)
class FindingGroup:
    """One root cause, one card, one action.

    **The group key is the THEME, not the cluster.** That is the whole point of
    having a theme axis: "confused with Fitbit", "confused with a pickleball app"
    and "not a recognized brand" cluster apart — they share almost no tokens — but
    they are one root cause with one fix, and a client wants one card. Grouping by
    ``(theme, cluster_id)`` instead produced 54 cards from the real Fort run,
    which is the blob this work exists to remove.

    It also settles the counting unit: client-facing counts are themes, and the
    number of groups IS the number of themes. ``member_cluster_ids`` keeps the
    per-instance identity the lifecycle engine needs (P2-T2), one level down.

    Ordered by ``priority`` descending within severity; see
    :func:`src.pipeline.priority.sort_key`.
    """

    #: The group's stable id — the theme itself. Stable by construction across
    #: weeks, which is exactly what a recurring report needs at the card level.
    theme: str
    theme_label: str
    #: Client-facing headline, already substituted. Templated off the classifying
    #: rule, never assembled from model prose.
    title: str
    #: The worst severity among the members — a group is as serious as its worst
    #: instance, not as its average.
    severity: str
    #: Individual observations. A SECONDARY figure; headline counts are themes.
    instance_count: int
    engines: list[str]
    intents: list[str]
    occurrence: Occurrence
    #: 2–3 verbatim model excerpts, one per distinct cluster, biggest first — so
    #: the card shows the range of ways the models get this wrong rather than
    #: three near-identical restatements of the same sentence.
    representative_claims: list[str]
    #: Every distinct claim-cluster folded into this theme. The lifecycle engine
    #: tracks THESE across weeks; the card tracks the theme.
    member_cluster_ids: list[str]
    #: The fact-sheet ground truth, verbatim.
    reality: str
    evidence: list[Evidence]
    #: How many observations COULD have been evidenced. `len(evidence)` is capped
    #: at `_MAX_EVIDENCE_PER_GROUP`; this is the real number, so a card can say
    #: "showing 4 of 94" rather than implying it showed everything.
    evidence_total: int
    # --- routing (priority.py) ---
    fix_channel: str
    owner: str
    effort: str
    action: str
    verification: str
    priority: float
    #: The judge flag types folded into this group, for the appendix. Not rendered
    #: on the card — the theme is the client-facing axis.
    flag_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FlagIdentity:
    """What one input flag resolved to. Keyed by ``(type, claim)``, which is the
    same key the display list dedups on — so the appendix and the cards can never
    disagree about a flag's tier, theme or id."""

    flag_type: str
    claim: str
    cluster_id: str
    row_hash: str
    theme: str
    severity: str


@dataclass(frozen=True)
class GroupingResult:
    """The groups plus the health of the classification that produced them."""

    groups: list[FindingGroup]
    coverage: themes.Coverage
    #: Sum of every group's ``instance_count``. Must equal the input flag count —
    #: a grouping that loses a flag is worse than one that groups it oddly.
    total_instances: int
    #: One entry per input flag, in input order. Lets a caller re-attach identity
    #: to its own (differently deduped) view of the same flags rather than
    #: re-running the clustering, which would mint ids that disagree.
    identities: list[FlagIdentity] = field(default_factory=list)

    def identity_by_claim(self) -> dict[tuple[str, str], FlagIdentity]:
        """``(type, claim)`` -> identity. Later duplicates collapse onto the first."""
        out: dict[tuple[str, str], FlagIdentity] = {}
        for identity in self.identities:
            out.setdefault((identity.flag_type, identity.claim), identity)
        return out


def _spread_across_engines(flags: Sequence[AccuracyFlag], limit: int) -> list[AccuracyFlag]:
    """Up to ``limit`` flags, one per engine first, then round-robin.

    Deterministic: the input is already sorted, and this walks it in passes, so
    the same run always evidences the same observations. Taking the first ``n``
    instead would hand every slot to whichever engine sorts first — four excerpts
    from one model, which answers a question nobody asked.
    """
    by_engine: dict[str, list[AccuracyFlag]] = defaultdict(list)
    for f in flags:
        by_engine[f.engine_name].append(f)
    picked: list[AccuracyFlag] = []
    depth = 0
    while len(picked) < limit and any(len(v) > depth for v in by_engine.values()):
        for engine in sorted(by_engine):
            if len(picked) >= limit:
                break
            if len(by_engine[engine]) > depth:
                picked.append(by_engine[engine][depth])
        depth += 1
    return picked


def _dates(values: Sequence[str]) -> tuple[str, str]:
    """(earliest, latest) ISO date from timestamps, ignoring blanks."""
    dates = sorted({v[:10] for v in values if v})
    if not dates:
        return "", ""
    return dates[0], dates[-1]


def build_finding_groups(
    flags: Sequence[AccuracyFlag],
    *,
    client: str,
    prompts_by_query: dict[str, str],
    runs_by_cell: dict[tuple[str, str], int],
    engine_models: dict[str, str] | None = None,
    total_engines: int = 0,
    registry: finding_id.FindingRegistry | None = None,
) -> GroupingResult:
    """Collapse a run's accuracy flags into themed, evidenced, ranked findings.

    Pure. ``runs_by_cell`` maps ``(query_id, engine_name)`` to how many runs of
    that cell RETURNED AN ANSWER — the honest denominator for "N of M runs", and
    the reason a timed-out engine cannot make a finding look intermittent.

    ``flags`` must be the per-cell stamped list (one entry per observation), not a
    deduped display list: the occurrence counts are computed from it, so a
    pre-deduped input would report every finding as happening exactly once.
    """
    engine_models = engine_models or {}
    if not flags:
        return GroupingResult(groups=[], coverage=themes.coverage([]), total_instances=0)

    # Steps 1–3, all in the caller's order so the zip below stays aligned.
    escalated = [sev.escalate(f.type, f.severity, f.claim) for f in flags]
    classified = [themes.classify(f.type, f.claim, f.reality) for f in flags]
    assignments = finding_id.assign_clusters([f.claim for f in flags], registry=registry)

    # Step 4. Group by THEME. The cluster is the instance identity inside it, not
    # the card boundary — see FindingGroup's docstring for why that distinction
    # is the difference between 11 cards and 54.
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, classification in enumerate(classified):
        buckets[classification.theme].append(i)

    groups: list[FindingGroup] = []
    for theme, members in buckets.items():
        member_flags = [flags[i] for i in members]
        group_severity = sev.worst([escalated[i] for i in members])
        engines = sorted({f.engine_name for f in member_flags if f.engine_name})
        intents = sorted({f.intent for f in member_flags if f.intent})
        has_provenance = any(f.has_provenance for f in member_flags)

        # Occurrence: only the cells this finding actually appeared in contribute
        # a denominator. Counting every cell in the run would bury a finding that
        # reproduced 3/3 times on the one query that surfaces it.
        cells = {(f.query_id, f.engine_name) for f in member_flags if f.query_id}
        observed = (
            len({(f.query_id, f.engine_name, f.run_index) for f in member_flags})
            if has_provenance
            else len(members)
        )
        total = sum(runs_by_cell.get(cell, 0) for cell in cells)
        first_date, last_date = _dates([f.observed_at for f in member_flags])
        occurrence = Occurrence(
            observed=observed,
            # `total=0` on a run whose flags carry no provenance. It is NOT
            # rounded up to `observed`: "observed in 4 of 4 runs" asserts perfect
            # reproducibility, and a run that never recorded which cell produced
            # what has no basis for that claim. `phrase()` says so instead.
            total=(max(total, observed) if has_provenance else 0),
            first_seen_date=first_date,
            last_seen_date=last_date,
        )

        # Step 5. Only flags with real provenance can be evidence — the standing
        # rule is that a finding without engine + timestamp + verbatim prompt is
        # not shippable, and a legacy flag has none of the three.
        evidenced = [
            f
            for f in sorted(member_flags, key=lambda f: (f.engine_name, f.query_id, f.run_index))
            if f.has_provenance and prompts_by_query.get(f.query_id)
        ]
        evidence = [
            Evidence(
                prompt=prompts_by_query.get(f.query_id, ""),
                engine_name=f.engine_name,
                model_id=engine_models.get(f.engine_name, ""),
                intent=f.intent,
                observed_at=f.observed_at,
                excerpt=f.claim,
                reality=f.reality,
            )
            for f in _spread_across_engines(evidenced, _MAX_EVIDENCE_PER_GROUP)
        ]

        # One representative per CLUSTER, largest cluster first. Quoting three
        # near-identical restatements of one sentence wastes the card; quoting
        # one per cluster shows the reader the range of ways this goes wrong.
        by_cluster: dict[str, list[int]] = defaultdict(list)
        for i in members:
            by_cluster[assignments[i].cluster_id].append(i)
        ranked_clusters = sorted(
            by_cluster.items(), key=lambda kv: (-len(kv[1]), kv[0])  # size desc, id for stability
        )
        claims = [assignments[idxs[0]].representative for _, idxs in ranked_clusters]

        routing = routing_for(theme)
        score = priority_score(
            severity=group_severity,
            intents=intents,
            observed=occurrence.observed,
            # A finding with no recorded denominator is treated as fully
            # reproducible for RANKING only, so a legacy run still orders by
            # severity and breadth instead of collapsing every score to zero.
            # The card still says the denominator is unknown.
            total=occurrence.total or occurrence.observed,
            # Likewise breadth: unknown provenance means at least one surface
            # produced it, not zero. Zero would rank a real Critical below a Low.
            engine_count=len(engines) or 1,
            total_engines=total_engines or max(len(engines), 1),
            channel=FixChannel(routing.channel),
            confidence=_CONFIDENCE_BY_SEVERITY.get(group_severity, 0.6),
        )

        groups.append(
            FindingGroup(
                theme=theme,
                theme_label=themes.theme_label(theme),
                title=classified[members[0]].title.format(client=client),
                severity=group_severity,
                instance_count=len(members),
                engines=engines,
                intents=intents,
                occurrence=occurrence,
                representative_claims=claims[:_MAX_REPRESENTATIVE_CLAIMS],
                member_cluster_ids=sorted(by_cluster),
                # The most severe member's correction, not an arbitrary one: it is
                # the line the card's headline claim is measured against.
                reality=min(
                    member_flags,
                    key=lambda f: sev.sort_key(sev.escalate(f.type, f.severity, f.claim)),
                ).reality,
                evidence=evidence,
                evidence_total=len(evidenced),
                fix_channel=routing.channel.value,
                owner=routing.owner.value,
                effort=routing.effort.value,
                action=routing.action.format(client=client),
                verification=routing.verification.format(client=client),
                priority=score,
                flag_types=sorted({f.type for f in member_flags}),
            )
        )

    from src.pipeline.priority import sort_key

    groups.sort(key=lambda g: sort_key(g.severity, g.priority, g.theme))
    return GroupingResult(
        groups=groups,
        coverage=themes.coverage(classified),
        total_instances=sum(g.instance_count for g in groups),
        identities=[
            FlagIdentity(
                flag_type=flags[i].type,
                claim=flags[i].claim,
                cluster_id=assignments[i].cluster_id,
                row_hash=assignments[i].row_hash,
                theme=classified[i].theme,
                severity=escalated[i],
            )
            for i in range(len(flags))
        ],
    )


if __name__ == "__main__":
    demo = [
        AccuracyFlag(
            type="identity",
            claim="There isn't a widely recognized brand called 'Fort'.",
            reality="Fort is a pre-launch strength-training wearable (fort.cx).",
            severity="high",
            query_id="brd-01",
            engine_name="perplexity",
            intent="brand",
            run_index=r,
            observed_at="2026-06-11T10:00:00Z",
        )
        for r in range(3)
    ] + [
        AccuracyFlag(
            type="wrong_pricing",
            claim="The Fort band costs $349.",
            reality="$289 pre-order, $319 retail.",
            severity="high",
            query_id="cmp-02",
            engine_name="openai_search",
            intent="comparison",
            run_index=0,
            observed_at="2026-06-13T10:00:00Z",
        )
    ]
    result = build_finding_groups(
        demo,
        client="Fort",
        prompts_by_query={"brd-01": "what is Fort?", "cmp-02": "Fort vs Whoop pricing"},
        runs_by_cell={("brd-01", "perplexity"): 3, ("cmp-02", "openai_search"): 3},
        engine_models={"perplexity": "sonar", "openai_search": "gpt-5.6-luna"},
        total_engines=6,
    )
    for g in result.groups:
        print(f"[{g.severity:8s}] {g.title}")
        print(
            f"    {g.occurrence.phrase()} · {g.instance_count}x · {g.owner}/{g.effort}"
        )
        print(f"           priority {g.priority:.2f} · {g.theme}")
    print(f"\ninstances={result.total_instances} coverage_by_rule={result.coverage.by_rule}")
