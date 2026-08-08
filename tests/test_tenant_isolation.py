"""LIC-T7/T8: org A must get ZERO rows for org B, through the real API.

**Why every assertion here is about EMPTINESS.** RLS denies by returning no rows,
not by raising. So a completely broken policy — or no policy at all — looks
exactly like "this tenant has no data yet": the page renders, nothing errors,
and a test that asserts "user A sees their own data" passes against a database
that would hand every tenant's rows to anyone. Only "user A gets zero rows for
org B" can tell the two apart.

**These were `xfail(strict=True)` until LIC-T10 wrote the policies** — the
failure was the mechanism proving isolation was not yet real, and the strict
marker guaranteed a loud failure the day it started working. It works, verified
against the live schema, so the markers came off; removing them was LIC-T10's
stated acceptance criterion. They are ordinary tests now, and a failure here is a
real cross-tenant leak rather than expected progress.

What is NOT xfail: the routing tests below. Which credential a query runs under is
decided in our code, not by the database, so it is testable today — and it is the
half that actually matters, because policies written while the API still connects
with the service-role key change nothing an attacker would notice.
"""

from __future__ import annotations

import pytest

from src.api import identity as identity_mod
from src.api.identity import CallerIdentity
from src.config import settings
from src.storage import db

# --- Routing: which credential does each operation run under? ----------------
#
# Testable now, and the load-bearing half of LIC-T7.


@pytest.fixture(autouse=True)
def _clear_client_caches() -> None:
    db._user_clients.clear()


def _fake_clients(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Record which client each operation asked for, without touching a network."""
    built: dict[str, object] = {}

    class _Fake:
        def __init__(self, kind: str) -> None:
            self.kind = kind

    monkeypatch.setattr(
        db, "_service_client", lambda: built.setdefault("service", _Fake("service"))
    )
    monkeypatch.setattr(
        db, "_user_client", lambda token: built.setdefault(f"user:{token}", _Fake("user"))
    )
    return built


def test_a_tenant_read_runs_as_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: with a request identity bound, a tenant query carries the
    caller's token so PostgREST can evaluate `auth.uid()` and apply the policy."""
    _fake_clients(monkeypatch)
    with identity_mod.use_identity(
        CallerIdentity(user_id="u1", is_platform_admin=False, access_token="tok-a")
    ):
        client = db._client()
    assert getattr(client, "kind", None) == "user"


def test_the_judge_cache_still_runs_as_the_service_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """A verdict is content-addressed and carries no tenant. Two clients asking
    the same question SHOULD share it — tenanting the cache would halve the hit
    rate and double judge spend for no isolation gain."""
    _fake_clients(monkeypatch)
    with identity_mod.use_identity(
        CallerIdentity(user_id="u1", is_platform_admin=False, access_token="tok-a")
    ):
        client = db._client(system=True)
    assert getattr(client, "kind", None) == "service"


def test_work_outside_a_request_runs_as_the_service_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI, the orchestrator, the resume scan and the crawler have no user to
    attribute a query to. They run as us, and that is correct."""
    _fake_clients(monkeypatch)
    client = db._client()
    assert getattr(client, "kind", None) == "service"


def test_two_callers_never_share_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client cached across identities would serve tenant B's request with
    tenant A's credentials — the cross-tenant leak the design warns about, in the
    one form this architecture can still produce it."""
    _fake_clients(monkeypatch)
    with identity_mod.use_identity(
        CallerIdentity(user_id="a", is_platform_admin=False, access_token="tok-a")
    ):
        first = db._client()
    with identity_mod.use_identity(
        CallerIdentity(user_id="b", is_platform_admin=False, access_token="tok-b")
    ):
        second = db._client()
    assert first is not second


def test_an_identity_does_not_leak_out_of_its_block() -> None:
    """`use_identity` restores the PREVIOUS identity, not the default — otherwise
    a nested anonymous scope would silently demote an outer authenticated one."""
    outer = CallerIdentity(user_id="outer", is_platform_admin=False, access_token="tok-outer")
    with identity_mod.use_identity(outer):
        with identity_mod.use_identity(identity_mod.ANONYMOUS):
            assert identity_mod.current_identity().user_id == ""
        assert identity_mod.current_identity() is outer
    assert identity_mod.current_identity() is identity_mod.PLATFORM_ADMIN


def test_a_missing_anon_key_refuses_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE failure mode this task exists to prevent. Falling back to the
    service-role key when the anon key is missing would silently restore the RLS
    bypass on every request, and the system would look like it was enforcing
    isolation while enforcing nothing."""
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", None)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://project.supabase.co")
    with pytest.raises(db.StorageError, match="SUPABASE_ANON_KEY"):
        db._user_client("tok-a")


def test_the_user_client_really_carries_the_callers_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mechanism itself, not a mock of it.

    Two things have to be true at once for RLS to apply, and getting either wrong
    fails silently: the connection must be made with the ANON key (a service-role
    connection bypasses policies no matter what token rides along), and the
    caller's token must be the bearer (so `auth.uid()` resolves). This asserts
    both on the real supabase-py client.
    """
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "the-anon-key")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "the-service-role-key")

    client = db._user_client("the-callers-token")
    headers = client.postgrest.headers

    assert headers["Authorization"] == "Bearer the-callers-token"
    # The apikey identifies the PROJECT and must be the anon key; the service-role
    # key appearing here would mean every policy is bypassed while the request
    # still looks authenticated.
    assert headers.get("apikey") == "the-anon-key"
    assert "the-service-role-key" not in str(dict(headers))


def test_the_service_role_allowlist_is_small_and_deliberate() -> None:
    """A drift alarm, not a proof. `system=True` is the RLS bypass; if it starts
    spreading, isolation quietly stops meaning anything. The number is allowed to
    change — but only in a commit that says why."""
    source = (db.__file__ or "").replace(".pyc", ".py")
    with open(source) as fh:
        text = fh.read()
    # Count only the call-site keyword, not the parameter declarations or the
    # allowlist prose in the docstring.
    marked = text.count("system=True,")
    # Raised 12 -> 15 by LIC-T17, for the anonymous share-link visitor and nothing
    # else. That visitor has no `auth.uid()` and can satisfy no policy, so the
    # token row IS the authorisation: `get_share_token_row` resolves the single id
    # they presented, `record_share_view` stamps that same id, and
    # `company_delivery_live` reads the two rows that say whether the client has
    # been offboarded. All four are scoped to one token's tenant. MINTING a link
    # is deliberately absent — it runs as the caller so the policy's `with check`
    # half stops an agency stamping a link with another tenant's company_id.
    # Raised 15 -> 20 by LIC-T14/T19, for provisioning and the console. Each is a
    # case where NO policy could apply, not a case where one was inconvenient:
    # `create_organization` and `create_invitation` write rows nobody has a
    # membership in yet (the organization does not exist; the invitee has no
    # identity); `accept_invitation` is redeemed BY a user with no membership, by
    # definition; `list_org_memberships` and `deactivate_membership` exist because
    # LIC-T10 deliberately gave `public.users` a policy that is NOT "everyone in
    # my organization" — that would leak every staffer's email to every client
    # user sharing a tenant — so the console reads its own roster here, scoped to
    # one organization the API has already checked the caller belongs to.
    #
    # What is NOT here is the tell: adding a client company runs as the CALLER, so
    # `companies_agency_insert` decides whether the agency may create it.
    assert marked <= 20, (
        f"{marked} operations now bypass RLS. Each one must be in the allowlist "
        f"documented in db._execute, with a reason."
    )


# --- End-to-end emptiness, against the real policies (LIC-T10) ----------------
#
# The xfail(strict=True) markers these replaced were correct while LIC-T10 was
# outstanding: they made the suite green AND guaranteed a loud failure the day
# isolation started working. It does now, verified against the live schema, so the
# markers came off — which is LIC-T10's stated acceptance criterion.
#
# These run as the `authenticated` role with `request.jwt.claims` set, which is
# exactly how PostgREST executes a per-user query, so they exercise the SAME code
# path a real request takes. Everything happens inside a transaction that is rolled
# back, including the fixture tenants.
#
# Skipped without a database connection so CI and a fresh clone stay green.

_DSN = settings.SUPABASE_DB_URL
needs_db = pytest.mark.skipif(not _DSN, reason="needs SUPABASE_DB_URL (a real database)")

_A_USER = "00000000-0000-0000-0000-00000000fa01"
_B_USER = "00000000-0000-0000-0000-00000000fa02"
_C_USER = "00000000-0000-0000-0000-00000000fa03"
_ORG_A = "00000000-0000-0000-0000-00000000fb01"
_ORG_B = "00000000-0000-0000-0000-00000000fb02"

_CHECKED_TABLES = (
    ("companies", "id"),
    ("audit_runs", "company_id"),
    # The four denormalised run children, checked individually: each carries
    # `company_id` itself so its policy never joins back to `audit_runs`, and a
    # denormalised column is a column that can be missed on one table.
    ("query_results", "company_id"),
    ("query_citations", "company_id"),
    ("judgments", "company_id"),
    ("local_pack_entities", "company_id"),
    ("teasers", "company_id"),
    # LIC-T17. A share token names a run and a tenant, so a policy failure here
    # leaks which reports another agency has issued to whom — and the row is the
    # thing that makes per-client revocation possible, so an agency being able to
    # UPDATE another's would let it withdraw a competitor's client links.
    ("report_share_tokens", "company_id"),
)


@pytest.fixture
def tenants():  # type: ignore[no-untyped-def]  # psycopg cursor type is not exported cleanly
    """Two agencies, each managing one real company. Rolled back afterwards."""
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(_DSN, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into auth.users (instance_id, id, aud, role, email, created_at,
                                    updated_at, is_anonymous)
            values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated',
                    'authenticated', 'iso-a@test.invalid', now(), now(), false),
                   ('00000000-0000-0000-0000-000000000000', %s, 'authenticated',
                    'authenticated', 'iso-b@test.invalid', now(), now(), false),
                   ('00000000-0000-0000-0000-000000000000', %s, 'authenticated',
                    'authenticated', 'iso-c@test.invalid', now(), now(), false)
            on conflict (id) do nothing
            """,
            (_A_USER, _B_USER, _C_USER),
        )
        cur.execute(
            "insert into public.organizations (id, name) values (%s,'Iso A'), (%s,'Iso B')",
            (_ORG_A, _ORG_B),
        )
        cur.execute(
            "insert into public.memberships (user_id, organization_id, role, accepted_at) "
            "values (%s,%s,'AGENCY_MANAGER',now()), (%s,%s,'AGENCY_MANAGER',now())",
            (_A_USER, _ORG_A, _B_USER, _ORG_B),
        )
        # Two companies that actually have rows, so "zero" is a real finding
        # rather than an artefact of an empty tenant.
        cur.execute(
            "select c.id from public.companies c "
            "join public.audit_runs r on r.company_id = c.id "
            "group by c.id order by count(*) desc limit 2"
        )
        found = [row[0] for row in cur.fetchall()]
        if len(found) < 2:
            pytest.skip("needs two companies with audit runs in the database")
        company_a, company_b = found[0], found[1]
        cur.execute("update public.companies set managing_agency_id=%s where id=%s",
                    (_ORG_A, company_a))
        cur.execute("update public.companies set managing_agency_id=%s where id=%s",
                    (_ORG_B, company_b))
        # One share token per tenant (LIC-T17). Seeded rather than borrowed:
        # the table is new and legitimately empty, and an emptiness assertion
        # against an empty table proves nothing at all.
        for company in (company_a, company_b):
            cur.execute(
                "select id from public.audit_runs where company_id=%s limit 1", (company,)
            )
            run_id = cur.fetchone()[0]
            cur.execute(
                "insert into public.report_share_tokens "
                "(token_id, run_id, company_id, expires_at) "
                "values (%s, %s, %s, now() + interval '30 days')",
                (f"iso-{company}", run_id, company),
            )
        yield cur, company_a, company_b
        conn.rollback()


def _count_as(cur, uid: str, table: str, column: str, company: str) -> int:  # type: ignore[no-untyped-def]
    """Rows of ``table`` belonging to ``company`` that ``uid`` can actually see."""
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', json_build_object('sub', %s::text)::text, true)",
        (uid,),
    )
    cur.execute(f"select count(*) from public.{table} where {column} = %s", (company,))  # noqa: S608 - names from a fixed tuple
    n = int(cur.fetchone()[0])
    cur.execute("reset role")
    return n


def _count_unfiltered(cur, table: str, column: str, company: str) -> int:  # type: ignore[no-untyped-def]
    """The same count as the migration role, which bypasses RLS — the ground truth.

    This is what turns "saw zero" into a finding: compared against it, zero means
    "the policy hid rows that exist" rather than "the table was empty".
    """
    cur.execute(f"select count(*) from public.{table} where {column} = %s", (company,))  # noqa: S608 - names from a fixed tuple
    return int(cur.fetchone()[0])


@needs_db
def test_the_foreign_rows_really_exist(tenants) -> None:  # type: ignore[no-untyped-def]
    """The control. Without this, every 'zero' below could just mean 'empty table',
    and the whole suite would pass against a database with no data in it."""
    cur, _company_a, company_b = tenants
    cur.execute("select count(*) from public.audit_runs where company_id = %s", (company_b,))
    assert int(cur.fetchone()[0]) > 0


@needs_db
@pytest.mark.parametrize(("table", "column"), _CHECKED_TABLES)
def test_agency_a_gets_zero_rows_for_agency_b(tenants, table: str, column: str) -> None:  # type: ignore[no-untyped-def]
    """ZERO, not 'different'. RLS denies by returning nothing, so a broken policy
    looks exactly like an empty tenant — only an emptiness assertion tells them
    apart, and only against data that provably exists (see the control above)."""
    cur, _company_a, company_b = tenants
    assert _count_as(cur, _A_USER, table, column, company_b) == 0


@needs_db
@pytest.mark.parametrize(("table", "column"), _CHECKED_TABLES)
def test_agency_a_still_sees_all_of_its_own_rows(tenants, table: str, column: str) -> None:  # type: ignore[no-untyped-def]
    """The other half. A policy that returns nothing to ANYONE also passes every
    emptiness assertion above, and would be just as broken.

    Compared against the unfiltered count rather than asserted `> 0`: a tenant
    legitimately has zero rows in some tables (fort.cx has no local-pack entities,
    because those are only captured for local-intent runs), and `> 0` would fail
    on a correct policy for that reason alone. Equality is the real invariant —
    the tenant sees exactly its own rows, however many that is.
    """
    cur, company_a, _company_b = tenants
    assert _count_as(cur, _A_USER, table, column, company_a) == _count_unfiltered(
        cur, table, column, company_a
    )


@needs_db
@pytest.mark.parametrize(("table", "column"), _CHECKED_TABLES)
def test_a_user_with_no_membership_sees_nothing_at_all(tenants, table: str, column: str) -> None:  # type: ignore[no-untyped-def]
    cur, company_a, company_b = tenants
    assert _count_as(cur, _C_USER, table, column, company_a) == 0
    assert _count_as(cur, _C_USER, table, column, company_b) == 0


@needs_db
def test_a_tenant_cannot_write_into_another_tenant(tenants) -> None:  # type: ignore[no-untyped-def]
    """`using` governs what is VISIBLE, `with check` what may be WRITTEN. Without
    the latter, agency A could INSERT a row stamped with agency B's company_id —
    writing into another tenant rather than reading from it."""
    psycopg = pytest.importorskip("psycopg")
    cur, _company_a, company_b = tenants
    # A savepoint, because the refused INSERT aborts the surrounding transaction
    # and every later statement — including `reset role` — would then fail with
    # "current transaction is aborted" and mask what actually happened.
    cur.execute("savepoint smuggle")
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', json_build_object('sub', %s::text)::text, true)",
        (_A_USER,),
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "insert into public.teasers (id, company_name, company_id, status) "
            "values (gen_random_uuid(), 'smuggled', %s, 'draft')",
            (company_b,),
        )
    cur.execute("rollback to savepoint smuggle")
    cur.execute("reset role")


@needs_db
def test_force_row_level_security_is_on_every_tenant_table() -> None:  # type: ignore[no-untyped-def]
    """ENABLE alone leaves the table OWNER bypassing RLS. If migrations run as
    `postgres` and anything else ever connects as that role, every policy is
    silently skipped."""
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "select c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "       (select count(*) from pg_policy p where p.polrelid = c.oid) "
            "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind = 'r' "
            "  and c.relname = any(%s)",
            ([t for t, _ in _CHECKED_TABLES],),
        )
        rows = cur.fetchall()
    assert rows, "none of the tenant tables were found"
    for name, enabled, forced, policies in rows:
        assert enabled, f"{name}: RLS not enabled"
        assert forced, f"{name}: FORCE not set — the owner bypasses every policy"
        assert policies >= 1, f"{name}: RLS enabled with NO policy is a no-op"
