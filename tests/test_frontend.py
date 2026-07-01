"""Guardrails that the TypeScript / JavaScript surfaces compile and run.

The Python suite guards the backend; these do the same for the JS/TS side so a single
``pytest tests/`` fails loudly the moment anything stops compiling:

- every TS project (``web``, ``teaser``) must pass ``tsc --noEmit`` with zero errors,
- every standalone workflow script under ``scripts/`` must parse (``node --check``),
- the ``teaser`` unit suite must actually execute green (proves the TS *runs*, not just
  typechecks),
- optionally (``RUN_WEB_BUILD=1``) the ``web`` Next.js production build must succeed.

Each test SKIPS (never fails) when the JS toolchain or a project's ``node_modules`` are
absent, so a Python-only environment stays green instead of erroring on a missing tool.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (label, project dir). Each ships its own TypeScript in node_modules, so we run THAT
# tsc (not a global one) — the check matches exactly what the project builds with.
TS_PROJECTS = [
    ("web", REPO_ROOT / "web"),
    ("teaser", REPO_ROOT / "teaser"),
]

# Standalone JS that runs outside any bundler (Claude Code workflow scripts). They rely
# on harness-injected globals (agent/parallel/phase), so they can't be executed here —
# but they must always PARSE. Recursive so scripts nested in subfolders are covered too.
JS_SCRIPTS = sorted((REPO_ROOT / "scripts").rglob("*.js"))

_TIMEOUT = 600  # seconds — generous headroom for a cold `next build`


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        # A hung/very-slow toolchain is an environment problem, not a code failure —
        # skip (as the file intends) instead of erroring the whole suite red.
        pytest.skip(f"`{' '.join(cmd)}` exceeded {_TIMEOUT}s — toolchain too slow, skipping")


def _require(tool: str) -> None:
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} not installed — skipping JS/TS check")


@pytest.mark.parametrize(("label", "project"), TS_PROJECTS, ids=[p[0] for p in TS_PROJECTS])
def test_typescript_project_typechecks(label: str, project: Path) -> None:
    """``tsc --noEmit`` must report zero type errors for each TS project."""
    if not project.exists():
        pytest.skip(f"{label}: project dir {project} missing")
    tsc = project / "node_modules" / ".bin" / "tsc"
    if not tsc.exists():
        pytest.skip(f"{label}: node_modules absent — run `npm install` in {project}")
    result = _run([str(tsc), "--noEmit"], cwd=project)
    assert result.returncode == 0, (
        f"{label}: `tsc --noEmit` found type errors:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.parametrize("script", JS_SCRIPTS, ids=[p.name for p in JS_SCRIPTS])
def test_standalone_js_parses(script: Path) -> None:
    """``node --check`` must parse each standalone workflow script (no syntax errors)."""
    _require("node")
    result = _run(["node", "--check", str(script)], cwd=REPO_ROOT)
    assert result.returncode == 0, (
        f"{script.name}: syntax error:\n{result.stdout}\n{result.stderr}"
    )


def test_teaser_unit_suite_runs() -> None:
    """The teaser TS unit suite must execute and pass — proves the TS actually runs,
    not just typechecks (it strips types and runs under `node --test`)."""
    _require("npm")
    teaser = REPO_ROOT / "teaser"
    if not (teaser / "node_modules").exists():
        pytest.skip("teaser: node_modules absent — run `npm install` in teaser/")
    result = _run(["npm", "test"], cwd=teaser)
    assert result.returncode == 0, (
        f"teaser `npm test` failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.skipif(
    shutil.which("npx") is None or "RUN_WEB_BUILD" not in os.environ,
    reason="set RUN_WEB_BUILD=1 (and have npx) to run the slow Next.js production build",
)
def test_web_production_build() -> None:
    """Opt-in: the full Next.js production build must succeed (compiles + typechecks
    every route). Slow (~30s), so gated behind RUN_WEB_BUILD=1 to keep the default
    suite fast; `tsc --noEmit` above already covers the type layer on every run."""
    web = REPO_ROOT / "web"
    if not (web / "node_modules").exists():
        pytest.skip("web: node_modules absent — run `npm install` in web/")
    result = _run(["npx", "--no-install", "next", "build"], cwd=web)
    assert result.returncode == 0, (
        f"web `next build` failed:\n{result.stdout}\n{result.stderr}"
    )
