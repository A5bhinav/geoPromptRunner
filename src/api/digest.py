"""The weekly digest — the deliverable that doesn't require opening a page (P3-T3).

Client format preference splits ~35% calls / 35% static / 27% dashboards, and
clients rank "clear visual representation" (84%) far above comprehensiveness —
which is exactly what a 41-page PDF optimises for. A short email is the format
most of them actually read.

Three rules the shape encodes:

**The subject line carries the delta.** *"Fort mentioned in 6 of 10 ChatGPT runs
this week (+2)"*, never "Your Weekly GEO Report". A subject that is identical
every week trains the reader to skip it, and the open rate is the whole product
for a format nobody has to visit.

**Every digest has a "what we're doing" line — including when the answer is
"nothing, holding steady".** Recurring reports lose readers precisely when no
action can be derived from them. A flat week with an explicit "no action needed"
is a decision; a flat week with the section missing is a shrug.

**Flat is a claim.** Same rule as the report: *"held steady at 8 of 12 runs"*,
never an empty bullet.

Generation only. Delivery transport is out of scope — this returns the text and
the HTML, and something else decides how it travels.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

from src.api.reports import FindingGroupRow, ReportPayload

__all__ = ["Digest", "build_digest"]

#: Bullets per section. Past this it stops being a digest.
_MAX_CHANGES = 5
_MAX_ACTIONS = 3


@dataclass(frozen=True)
class Digest:
    """One cycle's email. Subject carries the news; body carries the proof."""

    subject: str
    text: str
    html: str


def build_digest(report: ReportPayload, report_url: str = "", answers_url: str = "") -> Digest:
    """Render a report payload as a digest. Pure — no I/O, no model.

    Every number here is READ FROM THE PAYLOAD, never recomputed. A digest that
    derives its own figures is a second source of truth, and the first thing a
    client notices is when the email and the report disagree.
    """
    client = report["client_name"]
    visibility = report["scorecard"].get("ai_visibility")
    changed = report.get("what_changed")
    actions = report.get("priority_actions") or []

    subject = _subject(client, report, visibility, changed)
    headline = report.get("exec_summary") or f"{client} — AI visibility report"

    changes = _changes(report, changed)
    doing = _doing(actions, changed)
    why = _why(report, changed)

    lines = [
        headline,
        "",
        "WHAT CHANGED",
        *(f"  - {c}" for c in changes),
        "",
        "WHY IT MOVED",
        f"  {why}",
        "",
        "WHAT WE'RE DOING",
        *(f"  - {d}" for d in doing),
        "",
    ]
    if report_url:
        lines.append(f"Full report: {report_url}")
    if answers_url:
        lines.append(f"Every answer we collected: {answers_url}")
    text = "\n".join(lines)

    html = "".join(
        [
            f"<p><strong>{escape(headline)}</strong></p>",
            "<h3>What changed</h3><ul>",
            *(f"<li>{escape(c)}</li>" for c in changes),
            "</ul><h3>Why it moved</h3>",
            f"<p>{escape(why)}</p>",
            "<h3>What we're doing</h3><ul>",
            *(f"<li>{escape(d)}</li>" for d in doing),
            "</ul>",
            f'<p><a href="{escape(report_url)}">Full report</a></p>' if report_url else "",
        ]
    )
    return Digest(subject=subject, text=text, html=html)


def _subject(
    client: str,
    report: ReportPayload,
    visibility: object,
    changed: object,
) -> str:
    """A subject that is different every week, and says the number.

    Always contains a count and a direction, in all four states — that is what
    makes it worth opening, and what the golden tests pin.
    """
    rate = ""
    if isinstance(visibility, dict) and visibility.get("n"):
        rate = f"{visibility['successes']} of {visibility['n']} answers"
    else:
        rate = "no measurable answers"

    delta = ""
    if isinstance(changed, dict) and changed.get("available"):
        moved = [m for m in changed["movements"] if m["direction"] in ("up", "down")]
        if moved:
            total = sum(
                m["after_successes"] - m["before_successes"]
                for m in moved
            )
            delta = f" ({total:+d})"
        else:
            delta = " (held steady)"
    elif report.get("comparison_blocked_reason") == "query_set_changed":
        delta = " (new question set)"
    else:
        delta = " (first cycle)"

    return f"{client} appears in {rate} this cycle{delta}"


def _changes(report: ReportPayload, changed: object) -> list[str]:
    """≤5 bullets. Flat surfaces included — flat is a claim, not a blank."""
    if isinstance(changed, dict) and changed.get("available"):
        bullets = [changed["accountability"]]
        bullets += [m["phrase"] for m in changed["movements"][: _MAX_CHANGES - 1]]
        return bullets

    reason = report.get("comparison_blocked_reason")
    if reason == "query_set_changed":
        return [
            "The question set changed this cycle, so we are not showing a comparison "
            "against the last one — the two are not the same instrument."
        ]
    open_findings = report["scorecard"].get("open_findings")
    count = open_findings["themes"] if isinstance(open_findings, dict) else 0
    return [
        f"This is the first cycle, so there is nothing to compare against yet. "
        f"{count} finding{'s' if count != 1 else ''} opened."
    ]


def _why(report: ReportPayload, changed: object) -> str:
    """One honest sentence. Never a causal claim we cannot support.

    The models are stochastic and the sample is small; attributing a move to a
    specific cause would be the same overclaim the report's own disclosure warns
    against.
    """
    if not (isinstance(changed, dict) and changed.get("available")):
        return (
            "Nothing to attribute yet — this is the first comparable cycle for this "
            "question set."
        )
    moved = [m for m in changed["movements"] if m["direction"] in ("up", "down")]
    if not moved:
        return (
            "No surface moved beyond what this sample size can distinguish from normal "
            "variation between runs. That is a result, not a missing one."
        )
    names = ", ".join(m["key"] for m in moved)
    return (
        f"The movement is concentrated on {names}. We report what we observed and when; "
        f"we do not claim a cause we cannot evidence."
    )


def _doing(actions: Sequence[FindingGroupRow], changed: object) -> list[str]:
    """≤3 bullets, and NEVER empty.

    A digest with no "what we're doing" is where recurring reports lose readers.
    When there is genuinely nothing to do, saying so is the action.
    """
    if actions:
        return [
            f"{a['action']} (Owner: {a['owner']} · Effort: {a['effort']})"
            for a in actions[:_MAX_ACTIONS]
        ]
    if isinstance(changed, dict) and changed.get("available") and changed.get("closing") == 0:
        return [
            "Nothing needed this cycle — no findings are open. We keep measuring so a "
            "regression shows up the week it happens."
        ]
    return [
        "Nothing actionable surfaced this cycle. We keep measuring; the value of a flat "
        "week is knowing it was flat."
    ]
