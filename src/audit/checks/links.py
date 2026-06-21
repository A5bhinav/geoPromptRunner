"""Cat 2 — Internal linking / topical authority (deterministic, impl guide §3.2).

A site-level checker over the whole crawl: it builds a ``networkx`` directed graph
of **in-content** internal links (excluding nav/header/footer chrome) and reports
orphans, internal PageRank, and click-depth from the homepage, plus rule-based
anchor-text quality.

Boilerplate is identified with two signals (§3.2): DOM ancestry (a link inside
``<nav>``/``<header>``/``<footer>`` or a nav-ish role/class) as a fast first pass,
then **cross-page repetition** (a link present on >85% of pages is chrome
regardless of markup) as the robust confirmer. Only links that survive both are
treated as in-content edges.

Unlike SSR/schema this is one verdict for the site (persisted with ``page_url``
empty), with per-page detail in the evidence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlsplit

import networkx as nx
import tldextract
from selectolax.parser import HTMLParser

from src.audit.crawl.models import PageRecord
from src.audit.crawl.urls import normalize_url

__all__ = [
    "LinkGraphClass",
    "PageLinkInfo",
    "AnchorIssue",
    "LinkGraphResult",
    "analyze_link_graph",
]

logger = logging.getLogger(__name__)

# Offline eTLD+1 resolver (bundled public-suffix snapshot, no network fetch).
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

_BOILERPLATE_TAGS = {"nav", "header", "footer", "aside"}
_BOILERPLATE_ROLES = {"navigation", "banner", "contentinfo"}
_BOILERPLATE_CLASS_HINTS = ("nav", "navbar", "menu", "footer", "header", "sidebar", "breadcrumb")

# A link target present on more than this fraction of pages is site chrome (§3.2).
_CROSS_PAGE_BOILERPLATE_RATIO = 0.85

# Anchor text that tells a reader (or model) nothing about the destination.
_GENERIC_ANCHORS = frozenset(
    {
        "click here",
        "read more",
        "learn more",
        "more",
        "here",
        "this",
        "link",
        "this page",
        "read",
        "see more",
        "details",
        "view",
        "go",
        "continue",
    }
)
_BARE_URL_RE = re.compile(r"^\s*(https?://|www\.)", re.IGNORECASE)

# Need at least this many pages before an internal-linking verdict is meaningful.
_MIN_PAGES_TO_GRADE = 3
# Orphan share at or above this fails the site.
_ORPHAN_FAIL_RATIO = 0.5
# In-content links with a weak anchor at or above this share -> partial.
_ANCHOR_ISSUE_RATIO = 0.30


class LinkGraphClass(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    UNGRADEABLE = "ungradeable"  # too few pages to assess


@dataclass
class PageLinkInfo:
    url: str
    in_degree: int
    out_degree: int
    pagerank: float
    click_depth: int | None  # hops from homepage; None if unreachable
    is_orphan: bool


@dataclass
class AnchorIssue:
    source_url: str
    target_url: str
    anchor_text: str
    issue: str  # empty | generic | bare_url


@dataclass
class LinkGraphResult:
    classification: LinkGraphClass
    pages: list[PageLinkInfo]
    orphans: list[str]
    anchor_issues: list[AnchorIssue]
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class _RawLink:
    source: str  # normalized source page URL
    target: str  # normalized target URL (same-site)
    anchor: str
    dom_boilerplate: bool


def _effective_html(page: PageRecord) -> str:
    return page.rendered_html or page.raw_html or ""


def _registered_domain(url_or_host: str) -> str:
    host = urlsplit(url_or_host).hostname or url_or_host
    return _EXTRACT(host).top_domain_under_public_suffix.lower()


def _is_dom_boilerplate(node: Any) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag in _BOILERPLATE_TAGS:
            return True
        attrs = parent.attributes
        if (attrs.get("role") or "") in _BOILERPLATE_ROLES:
            return True
        cls = (attrs.get("class") or "").lower()
        if any(hint in cls for hint in _BOILERPLATE_CLASS_HINTS):
            return True
        parent = parent.parent
    return False


def _anchor_text(node: Any) -> str:
    text = (node.text(deep=True) or "").strip()
    if text:
        return text
    attrs = node.attributes
    return ((attrs.get("aria-label") or attrs.get("title")) or "").strip()


def _anchor_issue(text: str) -> str | None:
    if not text:
        return "empty"
    if _BARE_URL_RE.match(text):
        return "bare_url"
    if text.lower() in _GENERIC_ANCHORS:
        return "generic"
    return None


def _extract_links(page: PageRecord, site_domain: str) -> list[_RawLink]:
    """Same-site ``<a>`` links on one page, with anchor text + DOM-boilerplate flag."""
    html = _effective_html(page)
    if not html:
        return []
    try:
        tree = HTMLParser(html)
    except Exception as exc:  # malformed HTML — no links from this page
        logger.warning("link parse failed for %s: %s", page.url, exc)
        return []
    source = normalize_url(page.url)
    links: list[_RawLink] = []
    for node in tree.css("a"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page.url, href)
        if urlsplit(absolute).scheme not in ("http", "https"):
            continue
        if _registered_domain(absolute) != site_domain:
            continue  # external link — not part of the internal graph
        target = normalize_url(absolute)
        if target == source:
            continue  # self-link
        links.append(
            _RawLink(
                source=source,
                target=target,
                anchor=_anchor_text(node),
                dom_boilerplate=_is_dom_boilerplate(node),
            )
        )
    return links


def _pagerank(
    graph: nx.DiGraph[str], damping: float = 0.85, max_iter: int = 100, tol: float = 1e-6
) -> dict[str, float]:
    """Power-iteration PageRank — pure Python, so no numpy/scipy dependency.

    networkx's ``pagerank`` routes through scipy; at audit scale (≤~20 nodes) a
    handful of iterations is trivial and not worth the native-dep weight.
    """
    nodes = list(graph.nodes())
    n = len(nodes)
    if n == 0:
        return {}
    out_degree = {node: graph.out_degree(node) for node in nodes}
    rank = dict.fromkeys(nodes, 1.0 / n)
    for _ in range(max_iter):
        dangling = damping * sum(rank[node] for node in nodes if out_degree[node] == 0) / n
        base = (1.0 - damping) / n + dangling
        new = dict.fromkeys(nodes, base)
        for src in nodes:
            if out_degree[src]:
                share = damping * rank[src] / out_degree[src]
                for _src, dst in graph.out_edges(src):
                    new[dst] += share
        if sum(abs(new[node] - rank[node]) for node in nodes) < tol:
            return new
        rank = new
    return rank


def _homepage_node(pages: list[PageRecord], nodes: set[str]) -> str:
    for page in pages:
        if page.category.value == "homepage":
            return normalize_url(page.url)
    # Fall back to the shallowest path.
    return min(nodes, key=lambda u: len([s for s in urlsplit(u).path.split("/") if s]))


def analyze_link_graph(pages: list[PageRecord], domain: str) -> LinkGraphResult:
    """Build the in-content internal link graph and grade internal linking (Cat 2)."""
    gradable = [p for p in pages if not p.fetch_meta.blocked and _effective_html(p)]
    nodes = {normalize_url(p.url) for p in gradable}
    if len(nodes) < _MIN_PAGES_TO_GRADE:
        return LinkGraphResult(
            LinkGraphClass.UNGRADEABLE,
            [],
            [],
            [],
            f"only {len(nodes)} crawled page(s) — too few to assess internal linking",
            {"n_pages": len(nodes)},
        )

    site_domain = _registered_domain(domain if "://" in domain else f"https://{domain}")
    all_links = [link for page in gradable for link in _extract_links(page, site_domain)]

    # Cross-page repetition: how many distinct source pages carry each target.
    sources_per_target: dict[str, set[str]] = {}
    for link in all_links:
        sources_per_target.setdefault(link.target, set()).add(link.source)
    repeated = {
        target
        for target, srcs in sources_per_target.items()
        if len(srcs) / len(nodes) > _CROSS_PAGE_BOILERPLATE_RATIO
    }

    # In-content edges (survive both boilerplate signals) between crawled pages.
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(nodes)
    anchor_issues: list[AnchorIssue] = []
    in_content_links = 0
    for link in all_links:
        if link.dom_boilerplate or link.target in repeated:
            continue
        in_content_links += 1
        issue = _anchor_issue(link.anchor)
        if issue is not None:
            anchor_issues.append(AnchorIssue(link.source, link.target, link.anchor, issue))
        if link.target in nodes:
            graph.add_edge(link.source, link.target)

    home = _homepage_node(gradable, nodes)
    pagerank = _pagerank(graph)
    depths = nx.single_source_shortest_path_length(graph, home) if home in graph else {}

    page_infos: list[PageLinkInfo] = []
    orphans: list[str] = []
    for node in sorted(nodes):
        in_deg = graph.in_degree(node)
        is_orphan = node != home and in_deg == 0
        if is_orphan:
            orphans.append(node)
        page_infos.append(
            PageLinkInfo(
                url=node,
                in_degree=in_deg,
                out_degree=graph.out_degree(node),
                pagerank=round(pagerank.get(node, 0.0), 4),
                click_depth=depths.get(node),
                is_orphan=is_orphan,
            )
        )

    considered = len(nodes) - 1  # exclude homepage
    orphan_ratio = len(orphans) / considered if considered else 0.0
    anchor_ratio = len(anchor_issues) / in_content_links if in_content_links else 0.0
    evidence = {
        "n_pages": len(nodes),
        "n_in_content_links": in_content_links,
        "n_edges": graph.number_of_edges(),
        "orphans": orphans,
        "anchor_issue_count": len(anchor_issues),
        "max_click_depth": max((d for d in depths.values()), default=0),
        "homepage": home,
    }

    if orphan_ratio >= _ORPHAN_FAIL_RATIO:
        cls = LinkGraphClass.FAIL
        reason = f"{len(orphans)} of {considered} non-home pages have no in-content inbound link"
    elif orphans or anchor_ratio >= _ANCHOR_ISSUE_RATIO:
        cls = LinkGraphClass.PARTIAL
        reason = (
            f"{len(orphans)} orphan page(s); "
            f"{len(anchor_issues)} weak anchor(s) of {in_content_links} in-content links"
        )
    else:
        cls = LinkGraphClass.PASS
        reason = (
            f"well-linked: no orphans across {len(nodes)} pages, "
            f"{graph.number_of_edges()} in-content edges"
        )

    return LinkGraphResult(cls, page_infos, orphans, anchor_issues, reason, evidence)
