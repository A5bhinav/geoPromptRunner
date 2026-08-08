"""The tenancy DDL still declares the invariants the design depends on.

This is a LINT, not a proof. It reads `data/schema_*.sql` as text and asserts the
load-bearing clauses are present; only `tests/sql/tenancy.test.sql` (pgTAP,
against a Supabase branch) can prove the database actually enforces them.

It exists because those clauses are each one line, each easy to lose in a
reformat, and each silently catastrophic: dropping `security definer` turns a
12ms lookup into a 178,000ms one, dropping `set search_path` makes the function
shadowable, and dropping the exclusivity CHECK lets one membership grant both
agency-wide and company-scoped access at once. A grep-level test runs in CI with
no database and catches all three.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_DATA = Path(__file__).resolve().parent.parent / "data"


def _sql(name: str) -> str:
    return (_DATA / name).read_text()


# --- LIC-T1: companies -------------------------------------------------------


def test_companies_and_organizations_ship_in_one_migration() -> None:
    """`companies.managing_agency_id` references `organizations`, so splitting
    them across two files leaves whichever applies first with a dangling FK."""
    sql = _sql("schema_tenancy.sql")
    assert "create table if not exists public.organizations" in sql
    assert "create table if not exists public.companies" in sql
    assert sql.index("public.organizations") < sql.index(
        "managing_agency_id uuid references public.organizations(id)"
    )


def test_company_slug_is_unique() -> None:
    """Two companies sharing a slug is two businesses sharing a tenant."""
    assert "slug text unique not null" in _sql("schema_tenancy.sql")


def test_managing_agency_is_nullable_and_reassignable() -> None:
    """No NOT NULL, no ON DELETE CASCADE: a client going direct is one UPDATE."""
    sql = _sql("schema_tenancy.sql")
    line = next(ln for ln in sql.splitlines() if "managing_agency_id uuid references" in ln)
    assert "not null" not in line.lower()
    assert "cascade" not in line.lower()


@pytest.mark.parametrize(
    "table",
    [
        # The four high-volume run children carry company_id THEMSELVES rather
        # than reaching it by joining audit_runs — a policy that joins back to
        # the parent re-introduces the per-row recursion `security definer`
        # exists to avoid, on the largest tables in the system.
        "query_results",
        "query_citations",
        "judgments",
        "local_pack_entities",
        "audit_runs",
        "teasers",
        "fact_sheets",
        "fact_claims",
        "factsheet_intake_sessions",
        "audit_deliverables",
        "site_audit_page",
        "site_audit_check",
        "site_audit_offsite_finding",
        "client_configs",
        "findings_registry",
    ],
)
def test_every_tenant_table_gets_company_id(table: str) -> None:
    assert f"'{table}'" in _sql("schema_tenancy.sql")


def test_company_id_is_nullable_with_no_default() -> None:
    """Nullable is required: existing rows have no tenant, and NOT NULL with a
    function default forces a full table rewrite. LIC-T9 tightens it."""
    sql = _sql("schema_tenancy.sql")
    assert "add column if not exists company_id uuid " in sql
    assert "company_id uuid not null" not in sql
    assert "company_id uuid default" not in sql


def test_the_judge_caches_are_not_tenanted() -> None:
    """A verdict is content-addressed. Tenanting the cache halves its hit rate
    and doubles judge spend for no isolation gain — the cached text is our own
    judge's output about a public answer, not client data."""
    sql = _sql("schema_tenancy.sql")
    body = sql.split("tenant_tables text[] :=")[1].split("];")[0]
    assert "judge_cache" not in body
    assert "content_judge_cache" not in body


# --- LIC-T2: memberships -----------------------------------------------------


def test_membership_scope_is_exclusive() -> None:
    """Exactly one of organization_id / company_id. Both would grant agency-wide
    and company-scoped access from one row; neither would grant it globally."""
    sql = _sql("schema_memberships.sql")
    assert "memberships_exactly_one_scope" in sql
    assert "(organization_id is not null and company_id is null)" in sql
    assert "(organization_id is null and company_id is not null)" in sql


def test_membership_uniqueness_is_partial() -> None:
    """Without the WHERE clause Postgres treats NULL scopes as distinct and the
    constraint silently never fires for the other kind of membership."""
    sql = _sql("schema_memberships.sql")
    assert "uq_memberships_user_org" in sql
    assert "where organization_id is not null" in sql
    assert "uq_memberships_user_company" in sql
    assert "where company_id is not null" in sql


def test_tenant_lives_in_memberships_not_on_the_user_row() -> None:
    """The WagerU pattern the whole design exists to avoid: a scalar FK on the
    user makes "one user, many client brands" structurally impossible."""
    sql = _sql("schema_memberships.sql")
    users_block = sql.split("create table if not exists public.users (")[1].split(");")[0]
    assert "company_id" not in users_block
    assert "organization_id" not in users_block


def test_founders_are_a_flag_not_a_tenant() -> None:
    sql = _sql("schema_memberships.sql")
    assert "is_platform_admin boolean not null default false" in sql


def test_entitlement_overrides_exist_so_a_deal_is_not_a_new_plan() -> None:
    sql = _sql("schema_memberships.sql")
    assert "add column if not exists plan_id text" in sql
    assert "add column if not exists entitlement_overrides jsonb" in sql


# --- LIC-T3: the access function ---------------------------------------------


def test_access_functions_are_security_definer_with_pinned_search_path() -> None:
    """Both clauses, on both functions. `security definer` is the 178,000ms ->
    12ms line; `set search_path = ''` is what stops the definer's rights being
    aimed at a shadowed `memberships` table."""
    sql = _sql("schema_tenancy_access.sql")
    for fn in ("private.is_platform_admin()", "private.has_company_access(target_company_id uuid)"):
        body = sql.split(f"create or replace function {fn}")[1].split("$$;")[0]
        assert "security definer" in body, fn
        assert "set search_path = ''" in body, fn
        assert "stable" in body, fn


def test_access_function_filters_on_the_user_first() -> None:
    """Reversing the join direction is measured at 9,000ms -> 20ms, and the
    `(select auth.uid())` subquery form at 179ms -> 9ms (InitPlan, once per
    query, not once per row)."""
    sql = _sql("schema_tenancy_access.sql")
    body = sql.split("create or replace function private.has_company_access")[1]
    assert "m.user_id = (select auth.uid())" in body
    assert "auth.uid() =" not in body  # never the bare, per-row form


def test_access_function_covers_all_three_paths() -> None:
    sql = _sql("schema_tenancy_access.sql")
    body = sql.split("create or replace function private.has_company_access")[1].split("$$;")[0]
    assert "private.is_platform_admin()" in body          # founders
    assert "m.company_id = target_company_id" in body      # direct membership
    assert "c.managing_agency_id = m.organization_id" in body  # agency-managed


def test_pending_invitations_do_not_grant_access() -> None:
    """A membership row exists from the moment staff are invited; access starts
    when they confirm. Departure from design §1.2, documented in the file."""
    sql = _sql("schema_tenancy_access.sql")
    body = sql.split("create or replace function private.has_company_access")[1].split("$$;")[0]
    assert body.count("m.accepted_at is not null") == 2


def test_execute_is_granted_to_authenticated_only() -> None:
    """Not to `anon`. The one anonymous read path is a share link, authorised by
    its token row (LIC-T17), never by a membership lookup."""
    sql = _sql("schema_tenancy_access.sql")
    assert "grant execute on function private.has_company_access(uuid) to authenticated;" in sql
    assert "to anon" not in sql
