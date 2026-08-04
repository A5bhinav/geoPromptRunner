"""Where the client-facing report actually renders.

Several rules in this suite are enforced by scanning source: never render an
internal id, never paraphrase a disclosure, expand the evidence when printing,
keep the brand behind one config object. Every one of them is really a rule
about *the report's render surface*, not about one file.

That distinction stopped being academic when TR-T11 split the surface in two:
`report-view.tsx` kept the chrome and the section content moved into
`report-contract.tsx`, driven by the registry. Tests pinned to a filename all
went green-by-absence overnight — they were still scanning a file, but the file
no longer contained what they were checking, which is the worst outcome a
source-scanning test has.

So the surface is named ONCE, here. Adding a component that renders report
content means adding it to this list, and every rule follows it automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "WEB",
    "REPORT_RENDER_FILES",
    "REPORT_CONTENT_FILES",
    "render_source",
    "render_code",
]

WEB = Path(__file__).resolve().parents[1] / "web"

#: The report's own components — the ones that decide WHAT a client reads.
#:
#: Separate from the full surface below because two rules are about authorship
#: rather than output: "take colour from tokens, not raw hex" and "no donut".
#: `marks.tsx` is where the four-step navy ramp is *defined* and where the
#: run-progress ring lives, so scanning it for hexes or for the word Donut would
#: ban the primitives from being primitives.
REPORT_CONTENT_FILES: tuple[Path, ...] = (
    WEB / "components" / "report-view.tsx",  # chrome, exports, the registry loop
    WEB / "components" / "report-contract.tsx",  # every section's content
    WEB / "lib" / "report-sections.tsx",  # the registry + thin-data fallbacks
    WEB / "components" / "badges.tsx",
)

#: Every file that renders something a client reads, primitives included.
REPORT_RENDER_FILES: tuple[Path, ...] = (
    *REPORT_CONTENT_FILES,
    WEB / "components" / "report-panels.tsx",
    WEB / "components" / "marks.tsx",
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def render_source() -> str:
    """The whole render surface as one string, comments included."""
    return "\n".join(p.read_text() for p in REPORT_RENDER_FILES if p.exists())


def render_code() -> str:
    """The render surface with comments stripped.

    Every content rule is about what the components RENDER, and the comments in
    these files necessarily quote the banned strings in order to explain why they
    are banned ("never `l.query_id`", "not 'hallucinates'"). Matching the prose
    would make the rules unwritable.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", render_source()))
