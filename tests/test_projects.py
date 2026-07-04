"""Project roll-up helpers: _domains_of guards untyped DB row values."""

from __future__ import annotations

from src.api.projects import _domains_of


def test_domains_of_normalizes_a_list() -> None:
    assert _domains_of(["acme.io", "", "www.acme.io"]) == ["acme.io", "www.acme.io"]
    assert _domains_of([]) == []


def test_domains_of_guards_non_list_values() -> None:
    # A bare string must NOT be iterated character-by-character (the latent bug the
    # type guard closes) — non-list/None values yield [].
    assert _domains_of("acme.io") == []
    assert _domains_of(None) == []
    assert _domains_of(42) == []
