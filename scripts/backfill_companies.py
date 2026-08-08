#!/usr/bin/env python3
"""Backfill `companies` and every `company_id`, from the data already stored (LIC-T1).

    python -m scripts.backfill_companies --dry-run     # derive and report, write nothing
    python -m scripts.backfill_companies               # apply, in ONE transaction

Run AFTER `python -m scripts.apply_schema data/schema_tenancy.sql`.

WHICH CREDENTIAL. `SUPABASE_DB_URL`, the direct Postgres connection — same choice
and same reasoning as `scripts/apply_schema.py`. This is a migration: it writes
columns that do not yet have RLS policies, across tables PostgREST would make us
page through one by one. It is emphatically not a runtime path.

THE KEYS COME FROM `src/api/company_keys.py`, NOT FROM A COPY. The UI has been
showing project keys derived by those functions since before companies existed;
if this script derived them even slightly differently it would mint a second
tenant for a client who already has one, and under RLS that is a client who
cannot see their own reports. So the rows are read here in SQL and the KEY is
computed in Python by the same code the API calls.

WHAT IT REFUSES TO DO. Two different clients whose names slugify to one
`name:<slug>` key are a COLLISION, and this exits non-zero rather than merging
them. Today's grouping would silently show them as one project; that is a
cosmetic bug while a project is a GROUP BY, and a cross-tenant data leak the
moment it becomes a tenant with memberships attached.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from src.api.company_keys import domains_of, key_for, norm_domain
from src.config import settings


class BackfillError(RuntimeError):
    """The backfill cannot proceed without a human decision."""


@dataclass
class Derived:
    """One company as derived from the stored rows, before it is written."""

    key: str
    label: str
    domain: str | None
    run_ids: list[str] = field(default_factory=list)
    teaser_ids: list[str] = field(default_factory=list)
    #: Every distinct raw client/company name seen for this key. More than one
    #: DISTINCT name under a `name:` key is the collision this script refuses.
    names: set[str] = field(default_factory=set)


def derive(
    runs: list[tuple[str, str, object]],
    teasers: list[tuple[str, str | None, str | None]],
    sheet_domains: list[tuple[str, str | None]] | None = None,
) -> dict[str, Derived]:
    """Bucket runs, teasers and fact-sheet domains into companies.

    ``runs`` is (id, client_name, client_domains); ``teasers`` is
    (id, company_name, prospect_url); ``sheet_domains`` is (domain, business_name).

    The first two mirror `projects._collect()` exactly. The THIRD is a source
    `_collect()` has never known about, and leaving it out was a real gap: a
    business can have a fact sheet and an intake conversation before it has any
    run or teaser — `blackpropeller.com` is exactly that in this database, with 36
    claims and no measurement yet. Deriving only from runs and teasers left its
    sheet with no tenant, and an untenanted row under RLS is a row nobody can
    read, including the client it belongs to.

    A company derived only from a sheet has no runs and no teasers, so it stays
    out of `list_projects()` (which drops empties) and the dashboard is unchanged.
    `get_project` still resolves it, which is what LIC-T18 needs.
    """
    out: dict[str, Derived] = {}

    def ensure(key: str, label: str, domain: str | None) -> Derived:
        acc = out.get(key)
        if acc is None:
            acc = Derived(key=key, label=label, domain=domain)
            out[key] = acc
        elif domain and not acc.domain:
            # We learned a real domain for a bucket first seen via a name only.
            acc.domain, acc.label = domain, domain
        return acc

    for run_id, client_name, raw_domains in runs:
        doms = domains_of(raw_domains)
        key, label, domain = key_for(norm_domain(doms[0]) if doms else "", client_name)
        acc = ensure(key, label, domain)
        acc.run_ids.append(run_id)
        if client_name:
            acc.names.add(str(client_name).strip())

    for teaser_id, company_name, prospect_url in teasers:
        key, label, domain = key_for(norm_domain(prospect_url), company_name)
        acc = ensure(key, label, domain)
        acc.teaser_ids.append(teaser_id)
        if company_name:
            acc.names.add(str(company_name).strip())

    # Fact sheets and intake sessions. Domain-keyed only: `fact_sheets.domain` is
    # already a normalised registrable domain, and a sheet without one has nothing
    # to identify a business by — inventing a name key for it would create a
    # tenant that no run could ever join back to.
    for domain_raw, business_name in sheet_domains or []:
        domain = norm_domain(domain_raw)
        if not domain:
            continue
        key, label, resolved = key_for(domain, business_name)
        acc = ensure(key, label, resolved)
        if business_name:
            acc.names.add(str(business_name).strip())

    return out


def check_collisions(derived: dict[str, Derived]) -> list[str]:
    """Name-keyed buckets holding more than one distinct client name.

    Only `name:` keys can collide in a way that matters. A DOMAIN bucket holding
    several names is normal and correct — "FORT" and "Fort Security" on fort.cx
    are one company under two labels — because the domain, not the name, is what
    identifies the business.
    """
    bad: list[str] = []
    for key, acc in sorted(derived.items()):
        if key.startswith("name:") and len({n.casefold() for n in acc.names}) > 1:
            bad.append(f"{key}: {sorted(acc.names)}")
    return bad


# Every child table that reaches its tenant through `audit_runs.id`. Backfilled by
# a single correlated UPDATE each — including the four high-volume run children,
# which carry `company_id` themselves precisely so no RLS policy ever has to make
# this join at read time.
_RUN_CHILD_TABLES = (
    "query_results",
    "query_citations",
    "judgments",
    "local_pack_entities",
    "site_audit_page",
    "site_audit_check",
    "site_audit_offsite_finding",
)


def _table_exists(cur: object, name: str) -> bool:
    cur.execute("select to_regclass(%s) is not null", (f"public.{name}",))  # type: ignore[attr-defined]  # psycopg cursor, untyped here
    row = cur.fetchone()  # type: ignore[attr-defined]  # psycopg cursor, untyped here
    return bool(row and row[0])


def run(*, dry_run: bool) -> int:
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
            if not _table_exists(cur, "companies"):
                print(
                    "error: public.companies does not exist. Apply the schema first:\n"
                    "  python -m scripts.apply_schema data/schema_tenancy.sql",
                    file=sys.stderr,
                )
                return 2

            cur.execute("select id::text, client_name, client_domains from public.audit_runs")
            runs = [(r[0], r[1], r[2]) for r in cur.fetchall()]
            cur.execute("select id::text, company_name, prospect_url from public.teasers")
            teasers = [(r[0], r[1], r[2]) for r in cur.fetchall()]

            # The third identity source (see `derive`). Both tables are read
            # because an intake conversation can be opened for a domain the sheet
            # generator has never produced a row for.
            sheet_domains: list[tuple[str, str | None]] = []
            if _table_exists(cur, "fact_sheets"):
                cur.execute("select domain, business_name from public.fact_sheets")
                sheet_domains.extend((r[0], r[1]) for r in cur.fetchall())
            if _table_exists(cur, "factsheet_intake_sessions"):
                cur.execute("select domain, null from public.factsheet_intake_sessions")
                sheet_domains.extend((r[0], r[1]) for r in cur.fetchall())

            derived = derive(runs, teasers, sheet_domains)
            collisions = check_collisions(derived)
            if collisions:
                print(
                    "error: two different clients slugify to one project key.\n"
                    "  Merging them would make one tenant out of two businesses.\n"
                    "  Give one of them a domain, or rename it, then re-run:",
                    file=sys.stderr,
                )
                for line in collisions:
                    print(f"    {line}", file=sys.stderr)
                return 1

            print(f"derived {len(derived)} companies from {len(runs)} runs / {len(teasers)} teasers")
            for key, acc in sorted(derived.items()):
                print(
                    f"  {key:34} label={acc.label:28} "
                    f"runs={len(acc.run_ids):<3} teasers={len(acc.teaser_ids)}"
                )
            if dry_run:
                print("\n-- dry run: nothing written, transaction rolled back")
                conn.rollback()
                return 0

            # 1. The company rows. `on conflict (slug) do nothing` makes a re-run
            #    a no-op rather than an error, and `returning` does not report
            #    skipped rows — so the ids are read back separately.
            for acc in derived.values():
                cur.execute(
                    "insert into public.companies (name, slug, domain) values (%s, %s, %s) "
                    "on conflict (slug) do nothing",
                    (acc.label, acc.key, acc.domain),
                )
            cur.execute("select slug, id::text from public.companies")
            ids: dict[str, str] = dict(cur.fetchall())

            # 2. The two rooted tables.
            counts: dict[str, int] = defaultdict(int)
            for key, acc in derived.items():
                cid = ids[key]
                if acc.run_ids:
                    cur.execute(
                        "update public.audit_runs set company_id = %s "
                        "where id = any(%s::uuid[]) and company_id is null",
                        (cid, acc.run_ids),
                    )
                    counts["audit_runs"] += cur.rowcount
                if acc.teaser_ids:
                    cur.execute(
                        "update public.teasers set company_id = %s "
                        "where id = any(%s::uuid[]) and company_id is null",
                        (cid, acc.teaser_ids),
                    )
                    counts["teasers"] += cur.rowcount

            # 3. Everything reachable from a run.
            for table in _RUN_CHILD_TABLES:
                if not _table_exists(cur, table):
                    print(f"  (skipping {table}: not present in this project)")
                    continue
                cur.execute(
                    f"update public.{table} t set company_id = r.company_id "  # noqa: S608 - name from a fixed tuple
                    "from public.audit_runs r "
                    "where t.run_id = r.id and t.company_id is null "
                    "and r.company_id is not null"
                )
                counts[table] += cur.rowcount

            # `audit_deliverables.run_id` is NULLABLE (a deliverable can be built
            # by hand), so it gets the run join AND a domain fallback.
            if _table_exists(cur, "audit_deliverables"):
                cur.execute(
                    "update public.audit_deliverables d set company_id = r.company_id "
                    "from public.audit_runs r "
                    "where d.run_id = r.id and d.company_id is null "
                    "and r.company_id is not null"
                )
                counts["audit_deliverables"] += cur.rowcount

            # 4. Domain-keyed tables. Only a company that HAS a domain can match;
            #    a `name:` company has no verified domain to join on, and guessing
            #    one is how a fact sheet ends up attached to the wrong business.
            for table in ("fact_sheets", "factsheet_intake_sessions"):
                if not _table_exists(cur, table):
                    print(f"  (skipping {table}: not present in this project)")
                    continue
                cur.execute(
                    f"update public.{table} t set company_id = c.id "  # noqa: S608 - name from a fixed tuple
                    "from public.companies c "
                    "where c.domain is not null and t.domain = c.domain "
                    "and t.company_id is null"
                )
                counts[table] += cur.rowcount

            if _table_exists(cur, "fact_claims"):
                cur.execute(
                    "update public.fact_claims fc set company_id = fs.company_id "
                    "from public.fact_sheets fs "
                    "where fc.fact_sheet_id = fs.id and fc.company_id is null "
                    "and fs.company_id is not null"
                )
                counts["fact_claims"] += cur.rowcount

            # 5. Name-keyed operational tables. `client_configs` and
            #    `findings_registry` carry `client_name` and nothing else, so they
            #    are matched through the runs that used that same name. A name
            #    used by two companies matches neither — `count(distinct) = 1`
            #    makes that ambiguity a skipped row instead of a wrong tenant.
            for table in ("client_configs", "findings_registry"):
                if not _table_exists(cur, table):
                    print(f"  (skipping {table}: not present in this project)")
                    continue
                cur.execute(
                    f"update public.{table} t set company_id = m.company_id "  # noqa: S608 - name from a fixed tuple
                    "from (select client_name, min(company_id::text)::uuid as company_id "
                    "      from public.audit_runs where company_id is not null "
                    "      group by client_name having count(distinct company_id) = 1) m "
                    "where t.client_name = m.client_name and t.company_id is null"
                )
                counts[table] += cur.rowcount

            print("\nrows tenanted:")
            for table in sorted(counts):
                print(f"  {table:34} {counts[table]:>7}")

            # 6. Report what is still untenanted, per table. This is the input to
            #    LIC-T9's per-table NOT NULL decision, so it is printed even when
            #    it is all zeros.
            print("\nstill NULL after backfill (LIC-T9 reads this):")
            for table in ("audit_runs", "teasers", *_RUN_CHILD_TABLES, "fact_sheets",
                          "fact_claims", "factsheet_intake_sessions", "audit_deliverables",
                          "client_configs", "findings_registry"):
                if not _table_exists(cur, table):
                    continue
                cur.execute(
                    f"select count(*) from public.{table} where company_id is null"  # noqa: S608 - fixed tuple
                )
                n = cur.fetchone()[0]
                flag = "" if n == 0 else "   <-- decide: customer data or fixture?"
                print(f"  {table:34} {n:>7}{flag}")

        conn.commit()
    print("\napplied.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="derive and report, write nothing")
    args = p.parse_args(argv)
    try:
        return run(dry_run=args.dry_run)
    except BackfillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
