#!/usr/bin/env python3
"""Measure what a deterministic fact-sheet layer can actually reach on real sites.

    python -m scripts.measure_jsonld_coverage --urls sites.txt
    python -m scripts.measure_jsonld_coverage https://a.com https://b.com

WHY. `docs/factsheet-autogen-plan.md` F1 (deterministic extraction: JSON-LD +
NAP, no LLM) rests on an assumption nobody has measured — that real local trade
sites carry usable structured data. If eight in ten do, F1 is a schema parser
and it is most of a local fact sheet. If two in ten do, F1 is a `tel:`-and-
footer-prose parser and the LLM layer matters much sooner. Same code either way;
very different place to spend the effort. §13.3 A2.

HOW IT MEASURES. Deliberately the same view the product takes:

  * **Raw HTML only, no JS.** The audit's whole premise is that major AI crawlers
    do not execute JavaScript (see docs/project-queue.md §2), so schema that only
    appears after hydration is schema the engines never see. Measuring the
    rendered DOM would overstate coverage — and overstating it is exactly the
    error that would send F1 down the wrong path.
  * **extruct, `syntaxes=["json-ld"], uniform=True`** — byte-identical to
    `src/audit/crawl/fetcher.py::_extract_json_ld`, so the number describes what
    the crawler will hand the generator, not what some other parser could find.
  * **A GPTBot UA**, matching the crawler's bot's-eye fetch.

Homepage only. A site whose homepage carries no LocalBusiness rarely carries one
on an interior page, and this is a coverage sample, not the crawl.

Output: one line per site, then a summary. Nothing is written or uploaded.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Matches the crawler's raw-fetch identity: what a non-rendering AI crawler sees.
_UA = "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)"
_TIMEOUT = 20.0

# Schema.org types that carry the fields a local fact sheet needs. LocalBusiness
# has ~80 subtypes (Plumber, HVACBusiness, HairSalon…); match on the suffix so a
# Plumber counts, and keep Organization separate because it does NOT imply hours
# or a service area.
_LOCAL_TYPES = re.compile(r"(LocalBusiness|Store|Restaurant|Plumber|HVACBusiness|HomeAndConstructionBusiness|ProfessionalService|Dentist|Physician|AutoRepair|HairSalon|BeautySalon|Electrician|RoofingContractor|Locksmith|MovingCompany|Contractor)$", re.I)

_TEL_RE = re.compile(r'href=["\']tel:([^"\']+)', re.I)
# A US licence number as trade sites actually write it in a footer.
_LICENCE_RE = re.compile(r"(?:lic(?:ense|ence)?\.?|CSLB|reg(?:istration)?\.?)\s*(?:#|no\.?|number)?\s*[:#]?\s*([A-Z]{0,3}\d{4,10})", re.I)
# "Mon-Fri 8am-5pm", "Monday through Friday", "Open 7 days"
_HOURS_RE = re.compile(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*(?:-|–|to|through|,)\s*(mon|tue|wed|thu|fri|sat|sun)|open\s+\d+\s+days|24/7|24 hours", re.I)
_AREA_RE = re.compile(r"(areas?[\s-]we[\s-]serve|service[\s-]areas?|areas?[\s-]served|communities[\s-]we[\s-]serve|proudly[\s-]serving)", re.I)


@dataclass
class SiteResult:
    url: str
    ok: bool = False
    status: int | None = None
    error: str | None = None
    blocked: bool = False
    bytes: int = 0
    jsonld_blocks: int = 0
    has_local_schema: bool = False
    schema_types: list[str] = field(default_factory=list)
    # Fields the deterministic layer would actually harvest.
    schema_phone: bool = False
    schema_address: bool = False
    schema_hours: bool = False
    schema_area: bool = False
    schema_sameas: bool = False
    # The fallbacks, when there is no schema.
    tel_link: bool = False
    hours_text: bool = False
    area_link: bool = False
    licence_text: bool = False


def _types_of(block: dict[str, Any]) -> list[str]:
    raw = block.get("@type") or []
    types = [raw] if isinstance(raw, str) else [t for t in raw if isinstance(t, str)]
    return types


def _walk(blocks: list[Any]) -> list[dict[str, Any]]:
    """Flatten @graph containers — extruct's uniform mode leaves them nested."""
    out: list[dict[str, Any]] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        out.append(b)
        graph = b.get("@graph")
        if isinstance(graph, list):
            out.extend(x for x in graph if isinstance(x, dict))
    return out


def inspect(url: str) -> SiteResult:
    r = SiteResult(url=url)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
        ) as client:
            resp = client.get(url)
        r.status = resp.status_code
        html = resp.text
        r.bytes = len(html)
        # Same signal the crawler records as fetch_meta.blocked: a challenge page
        # returns 200 with an interstitial, and counting it as "no schema" would
        # understate coverage.
        r.blocked = resp.status_code in (403, 429) or "cf-browser-verification" in html or "Just a moment..." in html
        if resp.status_code >= 400 or r.blocked:
            r.error = f"HTTP {resp.status_code}" + (" (challenge)" if r.blocked else "")
            return r
        r.ok = True
    except Exception as exc:  # noqa: BLE001 — a dead site is a data point
        r.error = f"{type(exc).__name__}: {exc}"
        return r

    try:
        import extruct

        data = extruct.extract(html, base_url=url, syntaxes=["json-ld"], uniform=True)
        blocks = _walk(data.get("json-ld") or [])
    except ImportError:
        print("error: extruct is not installed (it is a crawler dependency).", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:
        blocks = []

    r.jsonld_blocks = len(blocks)
    for b in blocks:
        types = _types_of(b)
        r.schema_types.extend(types)
        if any(_LOCAL_TYPES.search(t) for t in types):
            r.has_local_schema = True
            r.schema_phone |= bool(b.get("telephone"))
            r.schema_address |= bool(b.get("address"))
            r.schema_hours |= bool(b.get("openingHoursSpecification") or b.get("openingHours"))
            r.schema_area |= bool(b.get("areaServed"))
            r.schema_sameas |= bool(b.get("sameAs"))

    r.tel_link = bool(_TEL_RE.search(html))
    r.hours_text = bool(_HOURS_RE.search(html))
    r.area_link = bool(_AREA_RE.search(html))
    r.licence_text = bool(_LICENCE_RE.search(html))
    return r


def _flag(b: bool) -> str:
    return "yes" if b else " - "


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="JSON-LD / NAP coverage on real sites (plan §13.3 A2)")
    p.add_argument("urls", nargs="*", help="site URLs")
    p.add_argument("--urls", dest="url_file", type=Path, help="file with one URL per line (# comments ok)")
    p.add_argument("--json", action="store_true", help="emit raw results as JSON")
    args = p.parse_args(argv)

    urls = list(args.urls)
    if args.url_file:
        urls += [
            line.strip()
            for line in args.url_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not urls:
        p.error("give at least one URL, or --urls <file>")

    results = [inspect(u if u.startswith("http") else f"https://{u}") for u in urls]

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
        return 0

    print(f"{'site':<38} {'schema':>7} {'phone':>6} {'addr':>5} {'hours':>6} {'area':>5} | {'tel:':>5} {'hrs':>5} {'area':>5} {'lic':>5}")
    print("-" * 108)
    for r in results:
        name = r.url.replace("https://", "").replace("http://", "")[:37]
        if not r.ok:
            print(f"{name:<38} {'FAILED':>7}  {r.error}")
            continue
        print(
            f"{name:<38} {_flag(r.has_local_schema):>7} {_flag(r.schema_phone):>6} "
            f"{_flag(r.schema_address):>5} {_flag(r.schema_hours):>6} {_flag(r.schema_area):>5} | "
            f"{_flag(r.tel_link):>5} {_flag(r.hours_text):>5} {_flag(r.area_link):>5} {_flag(r.licence_text):>5}"
        )

    live = [r for r in results if r.ok]
    n = len(live) or 1
    print("-" * 108)
    print(f"reachable: {len(live)}/{len(results)}   (blocked/failed: {len(results) - len(live)})")
    print(f"  LocalBusiness-family schema : {sum(r.has_local_schema for r in live)}/{len(live)}")
    print(f"    with telephone            : {sum(r.schema_phone for r in live)}/{len(live)}")
    print(f"    with address              : {sum(r.schema_address for r in live)}/{len(live)}")
    print(f"    with opening hours        : {sum(r.schema_hours for r in live)}/{len(live)}")
    print(f"    with areaServed           : {sum(r.schema_area for r in live)}/{len(live)}")
    print(f"  tel: link (schema or not)   : {sum(r.tel_link for r in live)}/{len(live)}")
    print(f"  hours in prose              : {sum(r.hours_text for r in live)}/{len(live)}")
    print(f"  service-area page/link      : {sum(r.area_link for r in live)}/{len(live)}")
    print(f"  licence number in page text : {sum(r.licence_text for r in live)}/{len(live)}")
    print()
    schema_share = sum(r.has_local_schema for r in live) / n
    print(
        "READ IT LIKE THIS: the left block is what F1 gets for free and exactly right.\n"
        "The right block is what F1 must parse out of prose — cheap, but fuzzier, and\n"
        "it is where the deterministic layer stops being deterministic.\n"
        f"Schema share here is {schema_share:.0%}. Under ~40%, F1's centre of gravity is\n"
        "the right block, and the plan's L1 spec should say so before anyone writes it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
