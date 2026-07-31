#!/usr/bin/env python3
"""Apply a `data/*.sql` schema file to the platform Postgres.

WHY THIS EXISTS. Every `data/schema_*.sql` header says "run in the project's SQL
editor", and that instruction is why two migrations (`audit_runs.judge_model`,
`audit_runs.location`) sat unapplied long enough for run provenance to degrade:
a manual step with no runner is a step that gets skipped. `SUPABASE_DB_URL` has
been declared in `.env.example` and read by `src/config/settings.py` since
before this script — it just had no consumer.

    python -m scripts.apply_schema data/schema_factsheets.sql
    python -m scripts.apply_schema data/schema_factsheets.sql --dry-run

WHICH CREDENTIAL. `SUPABASE_KEY` is a PostgREST key and cannot run DDL.
`SUPABASE_DB_URL` is the direct Postgres connection string and **bypasses RLS
entirely** — it is the same class of credential `geoWebsite/scripts/
leads-visibility.sql` forbids for reading the leads queue. Use it here, for
migrations, and nowhere else. The API, the runner and any worker keep the REST
key.

If `db.<project-ref>.supabase.co` does not resolve (Supabase has been moving
direct connections to IPv6-only), use the pooler string recorded by
`supabase link` in `supabase/.temp/pooler-url`.

The whole file runs in ONE transaction: a schema file that half-applies is worse
than one that did not run, because the next attempt starts from a state no
`if not exists` guard was written against.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import settings


def _redacted(dsn: str) -> str:
    """A DSN safe to print — everything between '//' and '@' is the credential."""
    if "@" not in dsn or "//" not in dsn:
        return "<dsn>"
    scheme, rest = dsn.split("//", 1)
    return f"{scheme}//<redacted>@{rest.split('@', 1)[1]}"


def apply(path: Path, *, dry_run: bool = False) -> int:
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    sql = path.read_text()
    if not sql.strip():
        print(f"error: {path} is empty", file=sys.stderr)
        return 2

    if dry_run:
        print(f"-- would apply {path} ({len(sql.splitlines())} lines) in one transaction")
        return 0

    dsn = settings.SUPABASE_DB_URL
    if not dsn:
        print(
            "error: SUPABASE_DB_URL is not set.\n"
            "  It is the direct Postgres connection string (SUPABASE_KEY is a REST\n"
            "  key and cannot run DDL). See .env.example. Alternatively paste the\n"
            "  file into the Supabase SQL editor by hand.",
            file=sys.stderr,
        )
        return 2

    try:
        import psycopg
    except ImportError:
        print(
            "error: psycopg is not installed.\n  pip install 'psycopg[binary]'",
            file=sys.stderr,
        )
        return 2

    print(f"applying {path} -> {_redacted(dsn)}")
    try:
        # autocommit=False: psycopg opens a transaction and `with` commits on
        # clean exit, rolls back on any exception. All-or-nothing by construction.
        with psycopg.connect(dsn, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
    except Exception as exc:  # noqa: BLE001 — the message is the product here
        print(f"failed (rolled back): {exc}", file=sys.stderr)
        return 1

    print("applied.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", type=Path, help="path to a data/*.sql file")
    p.add_argument("--dry-run", action="store_true", help="parse and report, connect to nothing")
    args = p.parse_args(argv)
    return apply(args.path, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
