"""Render crawled pages into a blind, human-fillable content-judge labeling sheet.

The Cat 3/4 content judge has never passed the κ≥0.6 ship gate because no gold set is
labeled (`content_calibration.py` has been built and unused since it shipped). This is
the missing half: the engine-answer gold sets have `build_labeling_sheet.py`, the content
gold set had nothing, so labeling meant hand-assembling page text and check definitions.

**Blind by construction.** The judge's own verdicts are never rendered, for the same
reason `build_labeling_sheet.py` withholds them: a labeler who can see the judge's call
rubber-stamps it, and the resulting κ measures agreement with an anchor rather than
agreement with a human. That is also why this script exists instead of an LLM writing the
labels directly — κ is meaningless if both sides of the comparison are models, since they
share failure modes and would agree for reasons unrelated to being right.

Each page's editable region is wrapped in ``<!-- LABELS url=... -->`` markers so
``parse_content_sheet.py`` can read the filled sheet back into the JSONL that
``content_calibration.load_gold_set`` expects.

Usage:
    python -m scripts.build_content_sheet callafterglow.com docs/content-labeling-sheet.md
    python -m scripts.build_content_sheet --run-id <run_id> docs/content-labeling-sheet.md
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.audit.checks.content_judge import CONTENT_CHECKS
from src.audit.crawl.crawl import run_site_audit_blocking

logger = logging.getLogger(__name__)

# Enough text to judge structure without turning the sheet into a novel. The judge reads
# the full extracted text; a labeler ruling on "is the LEAD answer-first" needs the top of
# the page, and the excerpt is marked so nobody mistakes it for the whole document.
_EXCERPT_CHARS = 2200
_MIN_TEXT_CHARS = 200


def _header() -> list[str]:
    return [
        "# Content-judge gold set — labeling sheet",
        "",
        "One section per crawled page. For each of the six checks, replace `____` with",
        "**pass**, **partial**, or **fail**. Leave a label blank to skip that page/check",
        "pair — a skipped pair is dropped, which is better than a guess.",
        "",
        "**Do not consult the audit's own output while labeling.** The judge's verdicts are",
        "deliberately absent from this sheet: κ measures whether the judge agrees with a",
        "human, and a labeler who has seen the judge's answer is no longer independent.",
        "",
        "Label against the **extracted text shown here**, not the rendered page. That text",
        "is what the judge reads, so labeling the pretty version would score the judge for",
        "a document it never saw.",
        "",
        "Per `docs/grade-calibration-guide.md`, two people should label **independently and",
        "blind**, then reconcile disagreements before the κ run.",
        "",
        "---",
        "",
        "## The six checks",
        "",
    ]


def _check_reference() -> list[str]:
    lines: list[str] = []
    for check in CONTENT_CHECKS:
        lines.append(f"**`{check.check_id}`** (Cat {check.category}) — {check.title}")
        for sub in check.sub_questions:
            lines.append(f"  - {sub.text}")
        lines.append("")
    lines.append(
        "A check is **pass** when every sub-question is yes, **fail** when none are, and"
    )
    lines.append("**partial** in between. Rule on the page in front of you, not the site.")
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


def build_sheet(domain: str) -> str:
    """Crawl ``domain`` and render the labeling sheet. Local-service page selection."""
    crawl = run_site_audit_blocking(f"label-{domain}", domain, business_kind="local_service")
    pages = [p for p in crawl.pages if len((p.extracted_text or "").strip()) >= _MIN_TEXT_CHARS]

    lines = _header() + _check_reference()
    lines.append(f"**Source:** {domain} · {len(pages)} pages with usable text "
                 f"(of {len(crawl.pages)} crawled)")
    lines.append("")

    for i, page in enumerate(pages, 1):
        text = (page.extracted_text or "").strip()
        excerpt = text[:_EXCERPT_CHARS]
        truncated = len(text) > _EXCERPT_CHARS
        lines.append("---")
        lines.append("")
        lines.append(f"## {i}. {page.url}")
        lines.append("")
        lines.append(f"_Category: {page.category.value} · {len(text)} chars extracted"
                     f"{' (excerpt below)' if truncated else ''}_")
        lines.append("")
        lines.append("```text")
        lines.append(excerpt)
        if truncated:
            lines.append(f"\n[... {len(text) - _EXCERPT_CHARS} more characters ...]")
        lines.append("```")
        lines.append("")
        lines.append(f"<!-- LABELS url={page.url} -->")
        for check in CONTENT_CHECKS:
            lines.append(f"- {check.check_id}: ____")
        lines.append("<!-- /LABELS -->")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", help="domain to crawl and label (e.g. callafterglow.com)")
    parser.add_argument("out", help="path to write the Markdown sheet")
    args = parser.parse_args()

    sheet = build_sheet(args.domain)
    Path(args.out).write_text(sheet, encoding="utf-8")
    n = sheet.count("<!-- LABELS url=")
    print(
        f"wrote {args.out}: {n} pages x {len(CONTENT_CHECKS)} checks "
        f"= {n * len(CONTENT_CHECKS)} labels"
    )
    print("Label it, then: python -m scripts.parse_content_sheet <sheet> data/content_gold.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
