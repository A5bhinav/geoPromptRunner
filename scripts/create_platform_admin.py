#!/usr/bin/env python3
"""Create (or promote) a founder account — a platform admin (LIC-T5).

    python -m scripts.create_platform_admin --email abhi@example.com
    python -m scripts.create_platform_admin --email josh@example.com --dry-run
    python -m scripts.create_platform_admin --email x@example.com --demote

WHY A SCRIPT AND NOT A MIGRATION. An email address is not schema. Hard-coding the
founders' addresses into `data/*.sql` would put personal data in the repo and make
the migration unrunnable by anyone else; leaving it to the dashboard makes it a
step that gets skipped (the same reasoning that produced `scripts/apply_schema`).

THE FOUNDERS ARE A FLAG, NOT A TENANT. This sets `public.users.is_platform_admin`,
which `private.is_platform_admin()` reads. It deliberately does NOT create a
"founders agency" organization: a placeholder tenant pollutes every agency-level
list, chart and invoice, and has to be migrated away from later.

NO PASSWORD IS SET. The account is created with an email identity only; the
founder signs in through the ordinary magic-link flow. A script that mints
passwords is a script that leaves them in a shell history.

Idempotent: an existing account is promoted rather than duplicated, so re-running
is safe.
"""

from __future__ import annotations

import argparse
import sys

from src.config import settings


def _exists(cur: object, email: str) -> str | None:
    cur.execute("select id::text from auth.users where lower(email) = lower(%s)", (email,))  # type: ignore[attr-defined]  # psycopg cursor, untyped here
    row = cur.fetchone()  # type: ignore[attr-defined]  # psycopg cursor, untyped here
    return str(row[0]) if row else None


def run(email: str, *, dry_run: bool, demote: bool) -> int:
    email = email.strip()
    if "@" not in email:
        print(f"error: {email!r} is not an email address", file=sys.stderr)
        return 2

    dsn = settings.SUPABASE_DB_URL
    if not dsn:
        print(
            "error: SUPABASE_DB_URL is not set — it is the direct Postgres\n"
            "  connection string (SUPABASE_KEY is a REST key). See .env.example.",
            file=sys.stderr,
        )
        return 2
    try:
        import psycopg
    except ImportError:
        print("error: psycopg is not installed.\n  pip install 'psycopg[binary]'", file=sys.stderr)
        return 2

    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('public.users') is not null")
            if not cur.fetchone()[0]:
                print(
                    "error: public.users does not exist. Apply the schema first:\n"
                    "  python -m scripts.apply_schema data/schema_memberships.sql",
                    file=sys.stderr,
                )
                return 2

            user_id = _exists(cur, email)
            wanted = not demote
            action = "promote" if wanted else "demote"

            if user_id is None:
                if demote:
                    print(f"no account for {email}; nothing to demote")
                    return 0
                action = "create"

            if dry_run:
                print(f"-- would {action} {email} (is_platform_admin={wanted})")
                conn.rollback()
                return 0

            if user_id is None:
                # Insert into auth.users directly. The `on_auth_user_created`
                # trigger from schema_memberships.sql mirrors the row into
                # public.users, so this is one write, not two.
                #
                # `aud`/`role` are the values Supabase's own signup path writes;
                # an account missing them authenticates but is rejected by
                # PostgREST later, which is a confusing failure to debug.
                cur.execute(
                    """
                    insert into auth.users
                        (instance_id, id, aud, role, email, created_at, updated_at,
                         is_anonymous, raw_app_meta_data, raw_user_meta_data)
                    values ('00000000-0000-0000-0000-000000000000', gen_random_uuid(),
                            'authenticated', 'authenticated', %s, now(), now(), false,
                            '{"provider":"email","providers":["email"]}'::jsonb,
                            '{}'::jsonb)
                    returning id::text
                    """,
                    (email,),
                )
                user_id = str(cur.fetchone()[0])
                print(f"created auth account for {email}")

            cur.execute(
                "update public.users set is_platform_admin = %s where id = %s::uuid",
                (wanted, user_id),
            )
            if cur.rowcount == 0:
                # The trigger fires on INSERT only, so an account that predates it
                # has no mirror row. Create it rather than reporting success on a
                # write that touched nothing.
                cur.execute(
                    "insert into public.users (id, email, is_platform_admin) "
                    "values (%s::uuid, %s, %s) "
                    "on conflict (id) do update set is_platform_admin = excluded.is_platform_admin",
                    (user_id, email, wanted),
                )
                print("  (mirrored into public.users — the account predates the trigger)")

        conn.commit()

    print(f"{email}: is_platform_admin = {wanted}")
    print(
        "\nNo password was set. Sign in with the magic-link flow.\n"
        "Nothing is enforced yet: the API still connects with the service-role key,\n"
        "so RLS remains a no-op until LIC-T7 and LIC-T10 land."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--email", required=True, help="the founder's email address")
    p.add_argument("--dry-run", action="store_true", help="report, write nothing")
    p.add_argument(
        "--demote",
        action="store_true",
        help="clear is_platform_admin instead of setting it",
    )
    args = p.parse_args(argv)
    return run(args.email, dry_run=args.dry_run, demote=args.demote)


if __name__ == "__main__":
    raise SystemExit(main())
