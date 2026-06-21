"""Diagnostic CLI for the offsite agent.

  python -m src.audit.offsite                 # show which tools are configured
  python -m src.audit.offsite Notion notion.so  # run a live research pass

Use it after setting the offsite keys in .env to confirm the agent activates
beyond the keyless Wikidata baseline.
"""

from __future__ import annotations

import logging
import sys

from src.audit.offsite.agent import run_offsite_research
from src.audit.offsite.tools import configured_tools
from src.config import settings


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    print("Offsite tool configuration:")
    for name, ok in configured_tools().items():
        state = "configured" if ok else "not set (degrades to skip)"
        print(f"  {'✓' if ok else '·'} {name:11s} {state}")
    llm = "configured" if settings.ANTHROPIC_API_KEY else "no ANTHROPIC_API_KEY (pre-pass only)"
    print(f"  {'✓' if settings.ANTHROPIC_API_KEY else '·'} agent LLM   {llm}")

    if len(sys.argv) < 3:
        print("\nPass a brand and domain to run a live test, e.g.:")
        print("  python -m src.audit.offsite Notion notion.so")
        return

    brand, domain = sys.argv[1], sys.argv[2]
    print(f"\nRunning offsite research for {brand} ({domain})...\n")
    result = run_offsite_research(brand, domain)
    print(f"status={result.status} note={result.note!r}")
    for finding in result.findings:
        url = finding.url or ""
        conf = finding.confidence.value
        print(f"  [{finding.finding_type.value}] {finding.title} (conf={conf}) {url}")
    print(f"\naudit log ({len(result.audit_log)} calls):")
    for entry in result.audit_log:
        print(f"  step {entry.step} {entry.tool}: {entry.status} ({entry.latency_ms}ms)")


if __name__ == "__main__":
    main()
