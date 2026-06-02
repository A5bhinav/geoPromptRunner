from __future__ import annotations

from collections.abc import Callable

from src.audit.technical_check import (
    CheckResult,
    check_crawler_access,
    check_gated_content,
    check_llms_txt,
    check_rendering,
    check_robots_txt,
    check_sitemap,
)

__all__ = ["CHECKS", "run_all_checks", "run_competitive", "render_technical"]

# Category-1 (technical accessibility) checks, run as a set.
CHECKS: dict[str, Callable[[str], CheckResult]] = {
    "robots.txt": check_robots_txt,
    "crawler_access": check_crawler_access,
    "llms.txt": check_llms_txt,
    "sitemap": check_sitemap,
    "rendering": check_rendering,
    "gated_content": check_gated_content,
}


def run_all_checks(domain: str) -> dict[str, CheckResult]:
    """Run every Category-1 technical check against one domain."""
    return {name: fn(domain) for name, fn in CHECKS.items()}


def run_competitive(domains: list[str]) -> dict[str, dict[str, CheckResult]]:
    """Run the technical checks across client + competitor domains (Step 5)."""
    return {domain: run_all_checks(domain) for domain in domains}


def render_technical(results_by_domain: dict[str, dict[str, CheckResult]]) -> str:
    """Render a technical-accessibility matrix (checks x domains) as markdown."""
    domains = list(results_by_domain)
    lines: list[str] = ["# Technical Accessibility (Category 1)", ""]
    if not domains:
        return lines[0] + "\n\n_No domains checked._\n"

    header = "| Check | " + " | ".join(domains) + " |"
    sep = "| --- | " + " | ".join("---" for _ in domains) + " |"
    lines.append(header)
    lines.append(sep)
    for check in CHECKS:
        cells = []
        for domain in domains:
            result = results_by_domain[domain].get(check)
            cells.append(result["status"] if result else "n/a")
        lines.append(f"| {check} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    results = run_competitive(["example.com"])
    print(render_technical(results))
    for domain, checks in results.items():
        print(f"\n{domain}:")
        for name, result in checks.items():
            print(f"  [{result['status'].upper():7s}] {name}: {result['details']}")
