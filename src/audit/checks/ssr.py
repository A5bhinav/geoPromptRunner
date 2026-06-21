"""SSR-vs-CSR detector — the highest-value finding in the audit (§2).

Most AI crawlers (GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot, CCBot) do
**not** execute JavaScript, so content that only exists after a browser render is
invisible to them regardless of robots.txt. This checker measures how much of a
page's main text is present in the raw byte stream versus the rendered DOM.

Method (§2.1–§2.4):
- Metric is a **word-count ratio** on trafilatura-extracted main text (precision
  favored), ``effective_raw_words / rendered_words`` — not byte length (inflated
  by inline SVG/CSS-in-JS) and not semantic similarity (wrong question).
- ``effective_raw`` **credits inline raw-stream payloads** (``__NEXT_DATA__``,
  ``application/json`` scripts, JSON-LD prose) — AI crawlers ingest those without
  JS, so a Next.js site whose content is in ``__NEXT_DATA__`` must not FAIL (§2.3).
- We **never FAIL on the ratio alone**: a hard FAIL also requires an *empty* SPA
  mount node; a filled/absent mount vetoes it down to PARTIAL (§2.4).

Operates on a freshly-crawled in-memory :class:`PageRecord` (which holds both
``raw_html`` and ``rendered_html``). A page that never escalated to a render had
a sufficient raw fetch by definition → PASS.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.audit.crawl.dom import spa_shell_state
from src.audit.crawl.models import PageRecord

__all__ = ["SSRClass", "SSRResult", "classify_ssr", "PASS_RATIO", "FAIL_RATIO"]

logger = logging.getLogger(__name__)

# Thresholds (§2.2) — calibrate against a labeled set, but start here.
PASS_RATIO = 0.90  # ≥ this: crawler sees ~everything (SSR/SSG)
FAIL_RATIO = 0.10  # < this AND empty shell: content only in rendered DOM (CSR)

# Count a JSON string as prose only if it's long and has a space — avoids counting
# GUIDs/URLs/enum values as content (§2.3).
_PROSE_MIN_CHARS = 40

# Inline JSON the raw stream carries (not ld+json — that arrives via PageRecord.json_ld).
_JSON_SCRIPT_RE = re.compile(
    r"""<script[^>]+type=["']application/json["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)


class SSRClass(StrEnum):
    PASS = "pass"  # SSR/SSG — content in the raw stream
    PARTIAL = "partial"  # hybrid/hydration/lazy-load
    FAIL = "fail"  # CSR — content only in the rendered DOM
    UNGRADEABLE = "ungradeable"  # blocked / consent wall / no rendered text


@dataclass
class SSRResult:
    """Verdict for one page, with the numbers behind it for the report/evidence."""

    classification: SSRClass
    ratio: float | None
    raw_words: int
    inline_credit_words: int
    rendered_words: int
    shell_state: str  # empty | filled | absent
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _precision_word_count(html: str, url: str) -> int:
    """Word count of trafilatura main text, precision-favored (§2.1)."""
    if not html:
        return 0
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            favor_precision=True,
            include_comments=False,
            include_tables=True,
        )
    except Exception as exc:  # extractor error on pathological HTML
        logger.warning("precision extract failed for %s: %s", url, exc)
        return 0
    return len((text or "").split())


def _prose_words(text: str) -> int:
    return len(text.split()) if len(text) > _PROSE_MIN_CHARS and " " in text else 0


def _walk_json_prose(obj: Any) -> int:
    """Sum prose word counts over every string in a nested JSON structure."""
    if isinstance(obj, str):
        return _prose_words(obj)
    if isinstance(obj, dict):
        return sum(_walk_json_prose(value) for value in obj.values())
    if isinstance(obj, list):
        return sum(_walk_json_prose(item) for item in obj)
    return 0


def _inline_payload_words(raw_html: str, json_ld: list[dict[str, Any]]) -> int:
    """Prose words present in the raw stream's inline payloads (ingested without JS)."""
    words = 0
    for block in _JSON_SCRIPT_RE.findall(raw_html):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue  # not parseable JSON — skip this block
        words += _walk_json_prose(data)
    for block in json_ld:
        words += _walk_json_prose(block)
    return words


def classify_ssr(page: PageRecord) -> SSRResult:
    """Classify one crawled page as PASS / PARTIAL / FAIL / UNGRADEABLE (§2)."""
    url = page.url
    raw_html = page.raw_html or ""
    inline = _inline_payload_words(raw_html, page.json_ld)
    raw_words = _precision_word_count(raw_html, url)
    effective_raw = raw_words + inline
    shell = spa_shell_state(raw_html)

    # Blocked by anti-bot / consent wall → can't judge what a crawler would see.
    if page.fetch_meta.blocked:
        return SSRResult(
            SSRClass.UNGRADEABLE,
            None,
            raw_words,
            inline,
            0,
            shell,
            "page blocked by an anti-bot/consent challenge",
            {"effective_raw_words": effective_raw},
        )

    # Never escalated → the raw fetch already had enough content (present without JS).
    if not page.fetch_meta.was_rendered:
        return SSRResult(
            SSRClass.PASS,
            None,
            raw_words,
            inline,
            raw_words,
            shell,
            "raw fetch sufficient — content present without executing JS",
            {"effective_raw_words": effective_raw},
        )

    rendered_words = _precision_word_count(page.rendered_html or "", url)
    if rendered_words == 0:
        return SSRResult(
            SSRClass.UNGRADEABLE,
            None,
            raw_words,
            inline,
            0,
            shell,
            "rendered page yielded no extractable text",
            {"effective_raw_words": effective_raw},
        )

    ratio = effective_raw / rendered_words
    evidence = {"effective_raw_words": effective_raw, "shell_state": shell}

    if ratio >= PASS_RATIO:
        return SSRResult(
            SSRClass.PASS,
            ratio,
            raw_words,
            inline,
            rendered_words,
            shell,
            f"crawler sees ~all content (ratio {ratio:.2f} ≥ {PASS_RATIO})",
            evidence,
        )
    if ratio < FAIL_RATIO and shell != "filled":
        # Empty shell confirms CSR; absent shell defers to the (very low) ratio.
        # Only a *filled* mount node vetoes the FAIL (§2.4).
        return SSRResult(
            SSRClass.FAIL,
            ratio,
            raw_words,
            inline,
            rendered_words,
            shell,
            f"content only in rendered DOM (ratio {ratio:.2f}, {shell} shell)",
            evidence,
        )
    if ratio < FAIL_RATIO:
        # Low ratio but the mount node is filled — veto the hard FAIL (§2.4).
        return SSRResult(
            SSRClass.PARTIAL,
            ratio,
            raw_words,
            inline,
            rendered_words,
            shell,
            f"low ratio ({ratio:.2f}) but mount node filled — hydration/lazy-load",
            evidence,
        )
    return SSRResult(
        SSRClass.PARTIAL,
        ratio,
        raw_words,
        inline,
        rendered_words,
        shell,
        f"hybrid — some content needs JS (ratio {ratio:.2f})",
        evidence,
    )


if __name__ == "__main__":
    import asyncio

    from src.audit.crawl.fetcher import FetchConfig, PlaywrightRenderer, fetch_page
    from src.audit.crawl.models import PageCategory

    logging.basicConfig(level=logging.WARNING)

    async def _demo() -> None:
        cfg = FetchConfig()
        urls = ["http://quotes.toscrape.com/", "http://quotes.toscrape.com/js/"]
        async with PlaywrightRenderer(cfg) as renderer:
            for url in urls:
                page = await fetch_page(url, PageCategory.OTHER, cfg, renderer)
                r = classify_ssr(page)
                print(f"\n{url}")
                print(f"  {r.classification.value.upper()} — {r.reason}")
                print(
                    f"  raw_words={r.raw_words} inline={r.inline_credit_words} "
                    f"rendered_words={r.rendered_words} ratio={r.ratio} shell={r.shell_state}"
                )

    asyncio.run(_demo())
