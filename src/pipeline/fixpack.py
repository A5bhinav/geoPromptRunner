"""One finding as a brief someone can paste into whatever tracker they use (P3-T6).

Markdown, copy-pasteable, self-contained. **Deliberately not a Jira or Linear
integration**: that is rebuilding a tracker for roughly 5% of the benefit, and
every client uses a different one. A block of markdown works in all of them.

The brief carries exactly what someone needs to act without opening the report:
the problem, the evidence they can check, the correct fact, where the fix lands,
who owns it, and — the field most fix-lists omit — how to tell next cycle whether
it worked.

Verification is stated as an OBSERVATION, never a promised outcome. "Check
whether next cycle's answers quote the published figure" is a check; "this will
get you cited" is the FTC-enforcement-pattern claim the whole product avoids.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.api.reports import FindingGroupRow

__all__ = ["render_fix_pack", "render_finding_brief"]

_EFFORT_LABEL = {"S": "Small", "M": "Medium", "L": "Large"}


def render_finding_brief(group: FindingGroupRow, client: str) -> str:
    """One finding as a standalone markdown brief."""
    lines: list[str] = [
        f"## {group['title']}",
        "",
        f"**Severity:** {group['severity'].capitalize()}  ·  "
        f"**Owner:** {group['owner']}  ·  "
        f"**Effort:** {_EFFORT_LABEL.get(group['effort'], group['effort'])}  ·  "
        f"**Where the fix lands:** {group['fix_channel'].replace('_', ' ')}",
        "",
        "### What the models say",
        "",
        f"{group['occurrence']['phrase']}, on "
        f"{', '.join(group['engines']) or 'no recorded surface'}.",
        "",
    ]
    for claim in group["representative_claims"]:
        lines.append(f"> {claim}")
        lines.append("")

    if group["reality"]:
        lines += ["### What your fact sheet says", "", group["reality"], ""]

    lines += [
        "### Fix",
        "",
        group["action"],
        "",
        "### How we'll check",
        "",
        group["verification"],
        "",
    ]

    if group["evidence"]:
        lines += ["### Evidence", ""]
        for item in group["evidence"]:
            model = item["model_id"] or "model not recorded"
            when = item["observed_at"][:19] or "no timestamp"
            lines += [
                f"- **{item['engine_name']}** ({model}, {when})",
                f'  - Asked: "{item["prompt"]}"',
                f'  - Answered: "{item["excerpt"]}"',
            ]
        if group["evidence_total"] > len(group["evidence"]):
            lines.append(
                f"- _Showing {len(group['evidence'])} of {group['evidence_total']} "
                f"observations, one per surface._"
            )
        lines.append("")

    lines += [
        "---",
        "",
        f"_Finding for {client}. We report what we observed and when — AI models are "
        f"updated frequently and produce different answers to identical prompts, so this "
        f"is not a guarantee of what you will see if you ask right now._",
        "",
    ]
    return "\n".join(lines)


def render_fix_pack(groups: Sequence[FindingGroupRow], client: str, run_date: str = "") -> str:
    """Every prioritised finding as one pasteable document.

    Ordered exactly as the report orders them, so the brief and the card cannot
    disagree about what matters most — the ordering IS a claim.
    """
    header = [
        f"# {client} — fix pack" + (f" ({run_date})" if run_date else ""),
        "",
        f"{len(groups)} finding{'s' if len(groups) != 1 else ''}, worst first. Each block "
        f"is self-contained: paste one into a ticket without the rest.",
        "",
    ]
    if not groups:
        return "\n".join(
            [
                *header,
                "No findings are open. Nothing to fix this cycle.",
                "",
            ]
        )
    return "\n".join(header + [render_finding_brief(g, client) for g in groups])
