"""Crawl-wide adaptive pacing: the shared signal a bounded per-page retry cannot give.

The failure this exists to fix is not "a page got a 429". It is that a 429 taught
the crawl NOTHING: each page retried twice inside its own budget, gave up, and the
next page went out at the original cadence. Measured on a real site — a 20-page
crawl yielded one usable page, and every fact on the resulting sheet came from
that single URL.

So the tests are about behaviour over a SEQUENCE. A single call proves nothing.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.audit.crawl.fetcher import AdaptiveThrottle, FetchConfig, _retry_after_seconds


def _throttle(**over: float) -> AdaptiveThrottle:
    cfg = FetchConfig(**over)  # type: ignore[arg-type]  # kwargs are FetchConfig fields
    return AdaptiveThrottle(cfg.polite_delay_s, cfg)


def _response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after else {}
    return httpx.Response(
        status, headers=headers, request=httpx.Request("GET", "https://x.example/")
    )


# --- the crawl slows down and STAYS slowed ------------------------------------


def test_a_rejection_slows_every_later_request() -> None:
    t = _throttle()
    base = t.delay
    t.penalise()
    assert t.delay > base, "a 429 must change the pace of the rest of the crawl"


def test_repeated_rejections_compound() -> None:
    t = _throttle()
    seen = []
    for _ in range(4):
        t.penalise()
        seen.append(t.delay)
    assert seen == sorted(seen), "each rejection should back off further"
    assert len(set(seen)) > 1


def test_the_delay_is_capped() -> None:
    # Unbounded growth turns a rate-limited host into a crawl that never finishes.
    t = _throttle(max_polite_delay_s=8.0)
    for _ in range(20):
        t.penalise()
    assert t.delay == 8.0


def test_an_explicit_retry_after_is_never_undercut() -> None:
    """The host named a number; pacing faster than it asked for is the one thing
    a polite crawler must not do."""
    t = _throttle()
    t.penalise(retry_after=12.0)
    assert t.delay >= 12.0


# --- recovery, and why it needs a streak --------------------------------------


def test_one_success_does_not_undo_the_backoff() -> None:
    """Recovering on a single 200 is how a crawler oscillates between hammering and
    backing off instead of settling on the rate the host will serve."""
    t = _throttle(throttle_recovery_streak=3)
    t.penalise()
    slowed = t.delay
    t.reward()
    assert t.delay == slowed


def test_a_streak_of_successes_decays_the_delay() -> None:
    t = _throttle(throttle_recovery_streak=3)
    t.penalise()
    slowed = t.delay
    for _ in range(3):
        t.reward()
    assert t.delay < slowed


def test_recovery_never_goes_below_the_polite_base() -> None:
    # The base delay is politeness, not punishment — success must not remove it.
    t = _throttle()
    base = t.delay
    t.penalise()
    for _ in range(50):
        t.reward()
    assert t.delay == base


def test_rewards_on_an_unthrottled_crawl_are_a_no_op() -> None:
    t = _throttle()
    base = t.delay
    for _ in range(10):
        t.reward()
    assert t.delay == base


def test_a_rejection_resets_a_partial_recovery_streak() -> None:
    t = _throttle(throttle_recovery_streak=3)
    t.penalise()
    t.penalise()
    high = t.delay
    t.reward()
    t.reward()  # two of the three needed
    t.penalise()  # ...then pushed back again
    t.reward()
    t.reward()
    assert t.delay >= high, "a fresh rejection must not inherit the old streak"


# --- peak reporting -----------------------------------------------------------


def test_the_peak_is_remembered_after_recovery() -> None:
    """A crawl that quietly ran at 20s spacing looks identical to a fast one in the
    page count. The peak is how anyone knows the host pushed back."""
    t = _throttle()
    t.penalise()
    t.penalise()
    peak = t.peak_delay
    for _ in range(30):
        t.reward()
    assert t.delay < peak
    assert t.peak_delay == peak


# --- Retry-After parsing ------------------------------------------------------


def test_retry_after_seconds_is_read_and_capped() -> None:
    cfg = FetchConfig(retry_after_max_s=30.0)
    assert _retry_after_seconds(_response(429, "5"), cfg) == 5.0
    assert _retry_after_seconds(_response(429, "600"), cfg) == 30.0


def test_an_http_date_retry_after_falls_through_rather_than_being_guessed() -> None:
    cfg = FetchConfig()
    assert _retry_after_seconds(_response(503, "Wed, 21 Oct 2026 07:28:00 GMT"), cfg) is None


def test_a_missing_retry_after_is_none() -> None:
    assert _retry_after_seconds(_response(429), FetchConfig()) is None


def test_wait_sleeps_for_the_current_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    # asyncio.run rather than pytest-asyncio: this repo carries no async plugin,
    # and one coroutine does not justify a dependency.
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("src.audit.crawl.fetcher.asyncio.sleep", _fake_sleep)
    t = _throttle()

    async def _exercise() -> None:
        await t.wait()
        t.penalise()
        await t.wait()

    asyncio.run(_exercise())
    assert len(slept) == 2
    assert slept[1] > slept[0]
