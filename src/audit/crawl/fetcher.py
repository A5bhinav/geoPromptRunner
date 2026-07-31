"""Two-tier fetch: raw httpx first, headless Playwright only when needed (§1.1).

A headless render costs ~10–50× a raw GET, so we fetch raw with httpx and
escalate to Playwright only when the raw fetch is genuinely insufficient (thin
extracted text, not reader-able, or an empty SPA shell). Raw HTML is fetched with
GPTBot's real User-Agent so we measure what the non-JS AI crawlers actually see
(§2.5). All outbound requests go through :mod:`src.net_guard` for SSRF safety,
reused from the existing technical-audit checks — every redirect hop is
re-validated, so a public URL can't bounce the fetcher into an internal one.

The full tier is implemented: ``fetch_raw`` (raw httpx), ``should_escalate`` (the
render-escalation ladder), ``PlaywrightRenderer`` (headless render), and
``fetch_page`` (the per-page raw→render→extract→JSON-LD pipeline).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from src.audit.crawl.dom import is_empty_spa_shell
from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord
from src.audit.crawl.urls import content_hash, normalize_url
from src.net_guard import UnsafeUrlError, assert_public_url

__all__ = [
    "AdaptiveThrottle",
    "FetchConfig",
    "RawFetch",
    "GPTBOT_UA",
    "BROWSER_UA",
    "should_escalate",
    "fetch_raw",
    "PlaywrightRenderer",
    "fetch_page",
]

logger = logging.getLogger(__name__)

# Fetch raw HTML as GPTBot so the SSR check measures what the non-JS AI crawlers
# see (Vercel/MERJ: GPTBot/ClaudeBot/PerplexityBot/CCBot do not execute JS).
GPTBOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot"

# The headless render uses a real Chrome UA (JS on) — we already have the true
# GPTBot view from the raw fetch, so the rendered pass measures the browser view.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Resource types blocked during render — we audit the client's own site, so
# images/media/fonts add latency without changing the text/DOM we measure (§1.2).
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})

# Re-validate at most this many redirect hops before giving up (mirrors net_guard).
_MAX_REDIRECTS = 5

# Inline raw-stream payloads AI crawlers ingest without running JS (§1.1 / §2.3).
_NEXT_DATA_RE = re.compile(r"""id=["']__NEXT_DATA__["']""")
_NEXT_F_RE = re.compile(r"self\.__next_f\.push")
_INLINE_JSON_RE = re.compile(
    r"""<script[^>]+type=["'](?:application/(?:ld\+)?json)["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)
# A page thinner than this in extracted text, with no inline payload, is worth a render.
_INLINE_PAYLOAD_MIN_CHARS = 1000

# A challenge interstitial is a page with nothing on it: Cloudflare's runs ~1-3 KB,
# and the 429 bodies from the same host measured 1,100 chars. A real page is orders
# of magnitude larger. 15 KB leaves generous headroom above every interstitial seen
# while sitting far below any served page, and it is what stops the JS-detection
# script tag Cloudflare injects into GOOD pages from reading as a block (see
# `_is_blocked`). Raising this trades false "blocked" verdicts back in; lowering it
# risks letting a fat challenge page through as real content.
_CHALLENGE_MAX_BODY_CHARS = 15_000

# Cloudflare / anti-bot challenge body markers — recorded as "blocked", never
# bypassed. Only consulted on a body small enough to BE an interstitial.
_CF_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "challenge-platform",
    "cf_chl_opt",
    "attention required",
)


@dataclass
class FetchConfig:
    """Tunables for the fetch tier. Defaults follow impl guide §1.1–§1.2 / §6.5."""

    request_ua: str = GPTBOT_UA
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 20.0
    # Escalate to a headless render when raw extracted text is thinner than this.
    thin_text_chars: int = 300  # impl guide §1.1 range 200–500
    # Bounded retry honoring Retry-After on 429/503 (§1.5).
    max_retries: int = 2
    retry_base_wait_s: float = 0.5
    retry_max_wait_s: float = 10.0
    render_ua: str = BROWSER_UA
    # Honor robots.txt Disallow + Crawl-delay (§1.5). Off lets an owner audit a
    # site that blocks crawlers; on (default) is the polite, faithful behavior.
    respect_robots: bool = True
    # Bound concurrent headless renders (RAM ~700MB–1GB/slot, §6.5 Layer 0).
    max_render_concurrency: int = 3
    # Bound concurrent HTTP fetches. SEPARATE from max_render_concurrency, which is a
    # memory bound for Chromium and was being reused as a request-rate bound — a category
    # error that only surfaced once a crawl fetched more than a couple of pages.
    #
    # Serial by default, measured rather than guessed: a real client site (WP Engine
    # behind Cloudflare) 429'd 14 of 20 pages at 3 concurrent, and still 14 of 20 at 2
    # concurrent with 0.75s pauses (~2.7 req/s). The same URLs returned 200 every time at
    # ~2s spacing, under BOTH the GPTBot and a browser UA — so it is a pure rate limit,
    # not AI-crawler discrimination, and the fix is to go slower rather than to disguise
    # ourselves. Small-business hosting is the norm in this niche; an audit crawl is ~20
    # pages and has no reason to be fast.
    fetch_concurrency: int = 1
    # Pause between fetches when robots.txt specifies no Crawl-delay. 1.5s sits above the
    # 1s that still tripped the limit on that site and below the 2s that reliably passed.
    polite_delay_s: float = 1.5
    # Minimum wait after a 429 that carries no Retry-After. See _retry_wait.
    rate_limit_floor_s: float = 2.5
    # --- crawl-wide adaptive pacing (see AdaptiveThrottle) --------------------
    # `polite_delay_s` used to be a CONSTANT for the whole crawl, so a host that
    # started rejecting at page 3 kept receiving pages 4-20 at the same cadence.
    # Each retried twice in isolation and gave up, and a 20-page crawl collapsed to
    # one usable page — which is how a fact sheet ends up built from a single URL.
    # These let the crawl slow itself down and stay slowed.
    #
    # Ceiling on the adaptive delay. 20s is well past any reasonable small-business
    # rate limit while still finishing a ~20 page crawl inside a few minutes.
    max_polite_delay_s: float = 20.0
    # Multiplier applied to the current delay on each 429/503.
    throttle_growth: float = 2.0
    # Consecutive clean fetches before the delay decays one step back toward base.
    # Deliberately >1: recovering after a single success is how a crawl oscillates
    # between hammering and backing off instead of settling.
    throttle_recovery_streak: int = 3
    # Cap on an explicit `Retry-After`. Separate from retry_max_wait_s (10s), which
    # bounds OUR guesswork — this bounds a number the SERVER asked for, so it is
    # allowed to be much larger before we treat it as a refusal rather than a wait.
    retry_after_max_s: float = 60.0
    # Per-render nav + wall-clock caps — Playwright can *hang* on OOM (§6.5 locked #2).
    render_nav_timeout_s: float = 20.0
    render_stabilize_cap_s: float = 5.0


@dataclass
class RawFetch:
    """Result of the raw httpx fetch — the true byte stream a non-JS crawler sees."""

    requested_url: str
    final_url: str
    status_code: int
    html: str
    raw_bytes: bytes
    headers: dict[str, str]
    request_ua: str
    blocked: bool
    fetched_at: str  # ISO-8601 UTC


# --- escalation decision -----------------------------------------------------


def _has_inline_payload(raw_html: str) -> bool:
    """True if content rides in the raw byte stream (``__NEXT_DATA__`` / inline JSON).

    AI crawlers ingest these without executing JS, so their presence means a thin
    *extracted* text does not justify a render (§2.3).
    """
    if _NEXT_DATA_RE.search(raw_html) or _NEXT_F_RE.search(raw_html):
        return True
    total = sum(len(block) for block in _INLINE_JSON_RE.findall(raw_html))
    return total >= _INLINE_PAYLOAD_MIN_CHARS


def _is_readerable(raw_html: str) -> bool:
    """Mozilla-Readability gate, ported in trafilatura. Errors → bias toward rendering."""
    try:
        from lxml.html import fromstring
        from trafilatura.readability_lxml import is_probably_readerable

        return bool(is_probably_readerable(fromstring(raw_html)))
    except Exception as exc:  # parse failure → treat as not reader-able so we render
        logger.warning("readerable check failed, assuming not reader-able: %s", exc)
        return False


def should_escalate(
    raw_html: str, extracted_text: str | None, config: FetchConfig
) -> tuple[bool, str | None]:
    """Decide whether the raw fetch was insufficient and a headless render is needed.

    Returns ``(escalate, reason)``. No render when the extracted main text is
    already substantial, or when content rides inline in the raw byte stream
    (``__NEXT_DATA__``/large inline JSON) — AI crawlers ingest that without JS.
    Otherwise escalate, tagging the most specific trigger. Pure function — no
    network.
    """
    text_len = len((extracted_text or "").strip())
    if text_len >= config.thin_text_chars:
        return (False, None)
    if _has_inline_payload(raw_html):
        return (False, None)
    if is_empty_spa_shell(raw_html):
        return (True, "empty SPA mount node — content assembled client-side")
    if not _is_readerable(raw_html):
        return (True, "raw HTML not reader-able — no extractable main content")
    return (True, f"thin extracted text ({text_len} < {config.thin_text_chars} chars)")


# --- raw fetch ---------------------------------------------------------------


def _is_blocked(response: httpx.Response, body: str) -> bool:
    """Detect a Cloudflare/anti-bot challenge so we record it rather than bypass it.

    Not gated on status: Cloudflare serves the "Just a moment…" interstitial at
    HTTP **200** as often as 403/503. Gating on 403/503 (as this did) let a 200
    challenge slip through as a normal-but-thin page, which then escalated to a
    real-browser render, passed the challenge, and got mislabeled CSR/FAIL instead
    of the intended "blocked/ungradeable". Mirrors technical_check._is_challenge.

    **A marker in a LARGE body is not a challenge.** Cloudflare injects its
    JS-detection tag — ``/cdn-cgi/challenge-platform/scripts/jsd/main.js`` — into
    pages it serves NORMALLY, so ``challenge-platform`` appears in perfectly good
    HTML. Measured on albertnahmanplumbing.com 2026-07-31: HTTP 200, no
    ``cf-mitigated`` header, 207,768 chars of real content, and the marker matched
    at offset 207,088 inside that injected script. Every page of the site was
    recorded blocked, which discarded the whole crawl — and small-business sites
    are overwhelmingly behind Cloudflare, so this silently ungraded a large share
    of real prospects.

    An interstitial is, by construction, a page with no content on it. Requiring
    the body to be small keeps every genuine challenge (they run ~1-3 KB) while
    letting a served page carrying a bot-detection script through. The
    ``cf-mitigated`` header stays unconditional: it is Cloudflare stating outright
    that it acted on the request, and it needs no corroboration.
    """
    if "cf-mitigated" in response.headers:
        return True
    server = response.headers.get("server", "").lower()
    if "cloudflare" in server and len(body) <= _CHALLENGE_MAX_BODY_CHARS:
        low = body.lower()
        return any(marker in low for marker in _CF_CHALLENGE_MARKERS)
    return False


class AdaptiveThrottle:
    """One crawl's request pacing, which slows down when the host pushes back.

    The per-page retry in :func:`fetch_raw` is bounded and LOCAL: it waits, retries
    twice, gives up, and tells the next page nothing. So a host that starts
    rejecting mid-crawl received every remaining page at the original cadence and
    rejected those too. Measured on blackpropeller.com 2026-07-31 — a 20-page crawl
    yielded ONE usable page, and every fact on the resulting sheet came from that
    single URL.

    This is the missing shared signal. A 429 or 503 anywhere raises the delay for
    every subsequent request in the crawl; a run of clean fetches lowers it again.
    Recovery needs a STREAK rather than one success, because decaying immediately
    is how a crawler oscillates between hammering and backing off instead of
    settling on the rate the host will actually serve.

    Not thread-safe and does not need to be: a crawl is one event loop, and the
    mutations are single statements between awaits.
    """

    def __init__(self, base_delay: float, config: FetchConfig) -> None:
        self._base = max(base_delay, 0.0)
        self._config = config
        self._delay = self._base
        self._clean_streak = 0
        #: Peak delay reached — worth logging, since a crawl that quietly ran at
        #: 20s spacing looks identical to a fast one in the page count.
        self.peak_delay = self._base

    @property
    def delay(self) -> float:
        return self._delay

    def penalise(self, retry_after: float | None = None) -> None:
        """Called on every 429/503. Grows the delay for the rest of the crawl."""
        self._clean_streak = 0
        grown = max(self._delay * self._config.throttle_growth, self._config.rate_limit_floor_s)
        if retry_after is not None:
            # The host named a number. Never pace faster than it asked for.
            grown = max(grown, retry_after)
        self._delay = min(grown, self._config.max_polite_delay_s)
        self.peak_delay = max(self.peak_delay, self._delay)

    def reward(self) -> None:
        """Called on every clean fetch. Decays one step after a streak."""
        if self._delay <= self._base:
            return
        self._clean_streak += 1
        if self._clean_streak >= self._config.throttle_recovery_streak:
            self._clean_streak = 0
            self._delay = max(self._base, self._delay / self._config.throttle_growth)

    async def wait(self) -> None:
        if self._delay > 0:
            await asyncio.sleep(self._delay)


def _backoff(attempt: int, config: FetchConfig) -> float:
    return min(config.retry_base_wait_s * (2.0**attempt), config.retry_max_wait_s)


def _retry_after_seconds(response: httpx.Response, config: FetchConfig) -> float | None:
    """``Retry-After`` in seconds, or None when absent/unparseable.

    Only the delta-seconds form is read; the HTTP-date form falls through to our
    own backoff rather than risking a clock-skew parse.
    """
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return min(float(int(raw)), config.retry_after_max_s)
    except ValueError:
        return None


def _retry_wait(response: httpx.Response, attempt: int, config: FetchConfig) -> float:
    """Honor ``Retry-After`` (seconds form) on 429/503, else exponential backoff.

    A 429 with no ``Retry-After`` gets a floor of ``rate_limit_floor_s`` rather than the
    generic backoff: the generic curve starts at 0.5s, which on a rate-limited host is
    another immediate 429 and burns a retry for nothing. Observed exactly that — two
    retries at 0.5s and 1s both rejected, so the page was recorded as blocked when
    waiting a little longer would have fetched it.
    """
    retry_after = _retry_after_seconds(response, config)
    if retry_after is not None:
        return retry_after
    if response.status_code == 429:
        return max(_backoff(attempt, config), config.rate_limit_floor_s)
    return _backoff(attempt, config)


async def _get_following_redirects(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET ``url`` following redirects manually, re-validating every hop for SSRF.

    ``assert_public_url`` does a blocking DNS resolution, so it runs in a thread to
    avoid stalling the event loop.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        await asyncio.to_thread(assert_public_url, current)
        response = await client.get(current)
        if response.is_redirect and "location" in response.headers:
            current = str(response.url.join(response.headers["location"]))
            continue
        return response
    raise UnsafeUrlError(f"too many redirects from {url}")


async def fetch_raw(
    url: str, config: FetchConfig, throttle: AdaptiveThrottle | None = None
) -> RawFetch:
    """Raw httpx GET through net_guard's per-hop SSRF validation, returning :class:`RawFetch`.

    Reads the *full* body (httpx is non-streaming here, so later RSC chunks are
    captured, §2.3), retries transport errors and 429/503 honoring ``Retry-After``,
    and flags a Cloudflare challenge as ``blocked`` instead of trying to bypass it
    (§1.5). Raises ``UnsafeUrlError`` on an unsafe hop and ``httpx.HTTPError`` if
    transport errors persist past the retry budget.

    ``throttle`` is the crawl-wide pacer. Reporting a 429 to it is what makes the
    rejection visible to the REST of the crawl instead of dying inside this one
    page's retry budget.
    """
    timeout = httpx.Timeout(
        connect=config.connect_timeout_s,
        read=config.read_timeout_s,
        write=config.read_timeout_s,
        pool=config.connect_timeout_s,
    )
    headers = {
        "User-Agent": config.request_ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, headers=headers
    ) as client:
        for attempt in range(config.max_retries + 1):
            try:
                response = await _get_following_redirects(client, url)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt < config.max_retries:
                    await asyncio.sleep(_backoff(attempt, config))
                    continue
                raise
            if response.status_code in (429, 503):
                # Tell the whole crawl, not just this page's retry loop.
                if throttle is not None:
                    throttle.penalise(_retry_after_seconds(response, config))
                if attempt < config.max_retries:
                    await asyncio.sleep(_retry_wait(response, attempt, config))
                    continue
            body = response.text
            if throttle is not None and response.status_code == 200:
                throttle.reward()
            return RawFetch(
                requested_url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                html=body,
                raw_bytes=response.content,
                headers=dict(response.headers),
                request_ua=config.request_ua,
                blocked=_is_blocked(response, body),
                fetched_at=datetime.now(UTC).isoformat(),
            )
    raise RuntimeError("unreachable: fetch_raw retry loop exited without returning")


# --- headless render ---------------------------------------------------------

# Lean launch flags: shared-memory fix + sandbox off for container/CI (§6.2).
_LAUNCH_ARGS = ["--disable-dev-shm-usage", "--no-sandbox"]


async def _block_heavy_resources(route: Any) -> None:
    if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()


class PlaywrightRenderer:
    """One long-lived browser; a fresh ``new_context()`` per page, closed in finally.

    Recycled per audit job so Chromium's memory creep can't survive across jobs
    (§6.5). Blocks images/media/fonts, uses ``wait_until="domcontentloaded"`` plus
    a content-stabilization poll (never ``networkidle``), and enforces per-render
    nav + wall-clock timeouts. Use as an async context manager so the browser is
    launched and closed inside one event loop (never shared across loops).
    """

    def __init__(self, config: FetchConfig) -> None:
        self._config = config
        self._playwright: Any = None
        self._browser: Any = None
        self._semaphore = asyncio.Semaphore(config.max_render_concurrency)

    async def __aenter__(self) -> PlaywrightRenderer:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        return self

    async def __aexit__(self, *exc: object) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            if self._playwright is not None:
                await self._playwright.stop()

    async def _stabilize(self, page: Any) -> None:
        """Poll until visible text stops growing (cap), so lazy/hydrated content lands."""
        previous = -1
        try:
            async with asyncio.timeout(self._config.render_stabilize_cap_s):
                while True:
                    length = await page.evaluate(
                        "() => document.body ? document.body.innerText.length : 0"
                    )
                    if length == previous:
                        return
                    previous = length
                    await asyncio.sleep(0.25)
        except TimeoutError:
            logger.info("render stabilization hit cap; capturing as-is (low confidence)")

    async def render(self, url: str) -> str:
        """Render ``url`` and return the stabilized DOM HTML (``page.content()``).

        SSRF is enforced before navigation; a fresh context is closed in
        ``finally`` (leaked contexts are the #1 cause of the RAM climb, §1.2).
        """
        if self._browser is None:
            raise RuntimeError("PlaywrightRenderer used outside its context manager")
        await asyncio.to_thread(assert_public_url, url)
        async with self._semaphore:
            context = await self._browser.new_context(
                user_agent=self._config.render_ua,
                viewport={"width": 1280, "height": 1024},
            )
            try:
                page = await context.new_page()
                await page.route("**/*", _block_heavy_resources)
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self._config.render_nav_timeout_s * 1000,
                )
                await self._stabilize(page)
                html: str = await page.content()
                return html
            finally:
                await context.close()


# --- extraction --------------------------------------------------------------


def _extract_text(html: str, url: str) -> str | None:
    """Main-content text via trafilatura (recall-favored — missing a table is worse)."""
    try:
        import trafilatura

        return trafilatura.extract(
            html,
            url=url,
            favor_recall=True,
            include_comments=False,
            include_tables=True,
        )
    except Exception as exc:  # extractor errors on pathological HTML — degrade to None
        logger.warning("text extraction failed for %s: %s", url, exc)
        return None


#: Structured-data syntaxes read from every page, in descending authority.
#:
#: Only `json-ld` was requested before, and extruct parsed the rest and dropped
#: them on the floor. Microdata (`itemscope`/`itemprop`) is still what plenty of
#: older WordPress themes and small-business site builders emit, and RDFa turns up
#: in the same places — so a site could carry a complete, machine-readable
#: LocalBusiness block and yield ZERO claims purely because of the syntax it chose.
#:
#: `uniform=True` is what makes this safe to merge: extruct normalises microdata
#: and RDFa into the same `@type`/property shape as JSON-LD, so the downstream
#: extractor needs no per-syntax branch and cannot drift between them.
_STRUCTURED_SYNTAXES: list[str] = ["json-ld", "microdata", "rdfa"]


def _extract_json_ld(html: str, url: str) -> list[dict[str, Any]]:
    """Structured-data nodes via extruct, run on rendered HTML when we escalated.

    Named for JSON-LD because that is the authoritative syntax and the one every
    caller thinks in, but it returns the union of :data:`_STRUCTURED_SYNTAXES`.
    JSON-LD comes FIRST in the returned list: `resolve_conflicts` keeps the earlier
    claim when two sources agree and raises a question when they differ, so a
    hand-written JSON-LD block outranks a theme-generated microdata one.
    """
    try:
        import extruct

        data = extruct.extract(html, base_url=url, syntaxes=_STRUCTURED_SYNTAXES, uniform=True)
    except Exception as exc:  # malformed block in any syntax — don't sink the page
        logger.warning("structured-data extraction failed for %s: %s", url, exc)
        return []

    blocks: list[dict[str, Any]] = []
    for syntax in _STRUCTURED_SYNTAXES:
        for block in data.get(syntax) or []:
            if isinstance(block, dict):
                blocks.append(block)
    return blocks


async def fetch_page(
    url: str,
    category: PageCategory,
    config: FetchConfig,
    renderer: PlaywrightRenderer | None = None,
    throttle: AdaptiveThrottle | None = None,
) -> PageRecord:
    """Fetch one page end to end: raw → (escalate?) render → extract → JSON-LD.

    Builds the full :class:`PageRecord`. Text uses trafilatura (``favor_recall``);
    JSON-LD uses extruct on the rendered HTML when we escalated (some sites inject
    JSON-LD via JS, §1.7). A render failure is non-fatal — we keep the raw view
    and flag it.
    """
    raw = await fetch_raw(url, config, throttle)
    raw_text = _extract_text(raw.html, url)

    rendered_html: str | None = None
    render_reason: str | None = None
    if renderer is not None and not raw.blocked:
        escalate, reason = should_escalate(raw.html, raw_text, config)
        if escalate:
            try:
                rendered_html = await renderer.render(url)
                render_reason = reason
            except Exception as exc:  # render is best-effort; fall back to raw
                logger.warning("render failed for %s, using raw HTML: %s", url, exc)

    was_rendered = rendered_html is not None
    effective_html = rendered_html if rendered_html is not None else raw.html
    extracted_text = _extract_text(effective_html, url) if was_rendered else raw_text
    json_ld = _extract_json_ld(effective_html, url)

    meta = FetchMeta(
        status_code=raw.status_code,
        final_url=raw.final_url,
        fetched_at=raw.fetched_at,
        was_rendered=was_rendered,
        request_ua=config.render_ua if was_rendered else raw.request_ua,
        render_reason=render_reason,
        blocked=raw.blocked,
        headers=raw.headers,
    )
    return PageRecord(
        url=url,
        normalized_url=normalize_url(url),
        category=category,
        fetch_meta=meta,
        content_sha256=content_hash(raw.raw_bytes),
        raw_html=raw.html,
        rendered_html=rendered_html,
        extracted_text=extracted_text,
        json_ld=json_ld,
    )
