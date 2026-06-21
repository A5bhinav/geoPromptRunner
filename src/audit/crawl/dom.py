"""Shared selectolax DOM helpers for the SPA-shell heuristics.

The empty-shell test is used in two places — the fetcher's render-escalation
decision (§1.1) and the SSR-vs-CSR detector's veto logic (§2.4) — so it lives
here once rather than being duplicated.
"""

from __future__ import annotations

import logging
from typing import Literal

from selectolax.parser import HTMLParser

__all__ = ["SPA_MOUNT_SELECTOR", "spa_shell_state", "is_empty_spa_shell"]

logger = logging.getLogger(__name__)

# Mount nodes a client-rendered SPA leaves behind. Their *presence* is not proof
# of CSR — modern Next.js/Nuxt SSR fill the same ids — so we measure whether the
# node is empty (§2.4).
SPA_MOUNT_SELECTOR = "#__next, #__nuxt, #root, #app, [data-reactroot]"

# Below this many words inside the mount node, we treat it as an empty shell.
_EMPTY_SHELL_MAX_WORDS = 5


def spa_shell_state(html: str) -> Literal["empty", "filled", "absent"]:
    """Classify the SPA mount node: ``empty`` (CSR signal), ``filled`` (SSR — vetoes
    a false CSR call), or ``absent`` (no known shell — defer to the ratio).

    Strips ``script``/``noscript``/``template`` noise (e.g. "enable JS" messages)
    before measuring the node's own text.
    """
    try:
        tree = HTMLParser(html)
    except Exception as exc:  # malformed HTML — can't locate a shell
        logger.warning("selectolax parse failed in shell test: %s", exc)
        return "absent"
    node = tree.css_first(SPA_MOUNT_SELECTOR)
    if node is None:
        return "absent"
    for stripped in node.css("script, noscript, template, style"):
        stripped.decompose()
    words = (node.text(deep=True) or "").split()
    return "empty" if len(words) < _EMPTY_SHELL_MAX_WORDS else "filled"


def is_empty_spa_shell(html: str) -> bool:
    """True only when a known SPA mount node exists and is empty (content via JS)."""
    return spa_shell_state(html) == "empty"
