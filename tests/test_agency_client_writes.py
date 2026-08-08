"""LIC-T18/T19: an agency can add and release client companies, and nothing more.

Two policy bugs are pinned here, both found by testing the live database rather
than by reading the DDL:

1. **An agency could not create a client at all.** LIC-T10's `with check` on
   `companies` is `private.has_company_access(id)`, which on an INSERT can never
   be true — the function is `stable`, so it runs against the statement's
   snapshot and cannot see the row being inserted. That made LIC-T19's "adding a
   client is one INSERT" and LIC-T18's intake onboarding both impossible.

2. **That same `with check` was vacuous on UPDATE.** It reads `companies` by id,
   so on an update it sees the OLD row and merely re-answers `using`. An agency
   could therefore reassign a company it manages to an organization it has no
   membership in — handing a client, and every audit and share link under it, to
   a third party.

Everything runs as the `authenticated` role with `request.jwt.claims` set, which
is how PostgREST executes a per-user query, inside a transaction that is rolled
back.
"""

from __future__ import annotations

import pytest

from src.config import settings

_DSN = settings.SUPABASE_DB_URL
needs_db = pytest.mark.skipif(not _DSN, reason="needs SUPABASE_DB_URL (a real database)")

_OWNER = "00000000-0000-0000-0000-00000000ac01"
_RIVAL = "00000000-0000-0000-0000-00000000ac02"
_MINE = "00000000-0000-0000-0000-00000000acb1"
_THEIRS = "00000000-0000-0000-0000-00000000acb2"


@pytest.fixture
def agencies():  # type: ignore[no-untyped-def]  # psycopg cursor type is not exported cleanly
    """Two agencies, each with an owner and one managed client. Rolled back."""
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(_DSN, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into auth.users (instance_id, id, aud, role, email, created_at,
                                    updated_at, is_anonymous)
            values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated',
                    'authenticated', 'acw-owner@test.invalid', now(), now(), false),
                   ('00000000-0000-0000-0000-000000000000', %s, 'authenticated',
                    'authenticated', 'acw-rival@test.invalid', now(), now(), false)
            on conflict (id) do nothing
            """,
            (_OWNER, _RIVAL),
        )
        cur.execute(
            "insert into public.organizations (id, name) values (%s,'Mine'), (%s,'Theirs')",
            (_MINE, _THEIRS),
        )
        cur.execute(
            "insert into public.memberships (user_id, organization_id, role, accepted_at) "
            "values (%s,%s,'AGENCY_OWNER',now()), (%s,%s,'AGENCY_OWNER',now())",
            (_OWNER, _MINE, _RIVAL, _THEIRS),
        )
        cur.execute(
            "insert into public.companies (name, slug, domain, managing_agency_id) "
            "values ('Mine Co','acw-mine.test','acw-mine.test',%s) returning id",
            (_MINE,),
        )
        mine = cur.fetchone()[0]
        cur.execute(
            "insert into public.companies (name, slug, domain, managing_agency_id) "
            "values ('Their Co','acw-theirs.test','acw-theirs.test',%s) returning id",
            (_THEIRS,),
        )
        theirs = cur.fetchone()[0]
        yield cur, mine, theirs
        conn.rollback()


def _as_owner(cur) -> None:  # type: ignore[no-untyped-def]
    cur.execute("set local role authenticated")
    cur.execute(
        "select set_config('request.jwt.claims', json_build_object('sub', %s::text)::text, true)",
        (_OWNER,),
    )


@needs_db
def test_an_agency_owner_can_create_a_client_under_their_own_agency(agencies) -> None:  # type: ignore[no-untyped-def]
    """LIC-T19's "adding a client is one INSERT", which did not work before."""
    cur, _mine, _theirs = agencies
    cur.execute("savepoint sp")
    _as_owner(cur)
    cur.execute(
        "insert into public.companies (name, slug, domain, managing_agency_id) "
        "values ('New Client','acw-new.test','acw-new.test',%s)",
        (_MINE,),
    )
    assert cur.rowcount == 1
    cur.execute("reset role")
    cur.execute("rollback to savepoint sp")


@needs_db
@pytest.mark.parametrize(
    ("label", "sql", "args"),
    [
        (
            "under an agency they do not belong to",
            "insert into public.companies (name, slug, domain, managing_agency_id) "
            "values ('X','acw-x.test','acw-x.test',%s)",
            (_THEIRS,),
        ),
        (
            "with no managing agency at all",
            "insert into public.companies (name, slug, domain) "
            "values ('Y','acw-y.test','acw-y.test')",
            (),
        ),
    ],
)
def test_an_agency_owner_cannot_create_a_company_any_other_way(  # type: ignore[no-untyped-def]
    agencies, label: str, sql: str, args: tuple[object, ...]
) -> None:
    """The unowned case is not pedantry: without `managing_agency_id is not null`
    in the policy, `is_org_member(null)` is null and the check collapses to
    "authenticated" — any signed-in user could mint companies."""
    psycopg = pytest.importorskip("psycopg")
    cur, _mine, _theirs = agencies
    cur.execute("savepoint sp")
    _as_owner(cur)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql, args)
    cur.execute("rollback to savepoint sp")
    cur.execute("reset role")


@needs_db
def test_an_agency_can_release_its_own_client_to_direct(agencies) -> None:  # type: ignore[no-untyped-def]
    """LIC-T19's acceptance case. LIC-T10's policy refused this, because the
    resulting row is one the agency can no longer reach — which is the intended
    outcome and exactly why it has to be allowed."""
    cur, mine, _theirs = agencies
    cur.execute("savepoint sp")
    _as_owner(cur)
    cur.execute("update public.companies set managing_agency_id = null where id = %s", (mine,))
    assert cur.rowcount == 1
    cur.execute("reset role")
    cur.execute("rollback to savepoint sp")


@needs_db
def test_an_agency_cannot_hand_its_client_to_a_third_party(agencies) -> None:  # type: ignore[no-untyped-def]
    """The vacuous-`with check` hole. This passed before the fix.

    `using` never stopped it: the agency legitimately reaches its own client. The
    only thing that could refuse it is a `with check` testing the INCOMING row's
    columns, which `has_company_access(id)` — reading the table by id, from a
    snapshot that predates the update — structurally cannot do.
    """
    psycopg = pytest.importorskip("psycopg")
    cur, mine, _theirs = agencies
    cur.execute("savepoint sp")
    _as_owner(cur)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(
            "update public.companies set managing_agency_id = %s where id = %s", (_THEIRS, mine)
        )
    cur.execute("rollback to savepoint sp")
    cur.execute("reset role")


@needs_db
def test_another_agencys_client_is_not_even_visible(agencies) -> None:  # type: ignore[no-untyped-def]
    """Zero rows, not an error — RLS denies by returning nothing, so an UPDATE
    against a foreign company is a silent no-op rather than a refusal. Asserting
    on `rowcount` is the only way to tell "refused" from "matched nothing"."""
    cur, _mine, theirs = agencies
    cur.execute("savepoint sp")
    _as_owner(cur)
    cur.execute("select 1 from public.companies where id = %s", (theirs,))
    assert cur.fetchall() == []
    cur.execute("update public.companies set managing_agency_id = null where id = %s", (theirs,))
    assert cur.rowcount == 0
    cur.execute("reset role")
    cur.execute("rollback to savepoint sp")


@needs_db
def test_companies_has_no_for_all_policy_left(agencies) -> None:  # type: ignore[no-untyped-def]
    """A drift guard with teeth. Re-running `schema_tenancy_rls.sql` with
    `companies` back in its loop would recreate `tenant_access` — and because
    permissive policies are OR'd, that one vacuous policy would silently defeat
    every narrower one in this file. The table must have per-command policies and
    no `for all`."""
    cur, _mine, _theirs = agencies
    cur.execute(
        "select polname, polcmd from pg_policy "
        "where polrelid = 'public.companies'::regclass order by polname"
    )
    policies = dict(cur.fetchall())
    assert "tenant_access" not in policies, (
        "the FOR ALL policy is back on companies; its with-check is vacuous on "
        "UPDATE and impossible on INSERT, and it ORs with everything else"
    )
    # '*' is FOR ALL; r/w/a/d are select/update/insert/delete.
    assert "*" not in policies.values()
    assert set(policies.values()) >= {"r", "a", "w"}


# --- LIC-T18: the intake surface migrates as a unit --------------------------


def test_every_intake_route_is_covered_by_the_declared_prefixes() -> None:
    """The migration is by PREFIX, so a route outside the declared set would keep
    taking the shared key while the rest of the flow moved to per-user auth —
    leaving one endpoint through which an agency's intake reaches every tenant.

    Asserted against the real router rather than a hand-kept list, so adding a
    route to `intake.py` outside these prefixes fails here rather than in
    production.
    """
    from src.api import app as api_app
    from src.api import intake

    paths = {
        route.path  # type: ignore[attr-defined]  # APIRoute; the router holds nothing else
        for route in intake.router.routes
    }
    assert paths, "the intake router has no routes"
    uncovered = [
        p
        for p in paths
        if not any(p == q or p.startswith(q + "/") for q in api_app.INTAKE_PREFIXES)
    ]
    assert not uncovered, f"intake routes outside INTAKE_PREFIXES: {sorted(uncovered)}"


def test_the_intake_prefixes_actually_gate_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declaring the prefixes is only half of it — they have to be what
    `is_jwt_route` matches on."""
    from src.api import app as api_app

    monkeypatch.setattr(settings, "JWT_MIGRATED_ROUTES", ",".join(api_app.INTAKE_PREFIXES))
    assert api_app.is_jwt_route("/intake/start")
    assert api_app.is_jwt_route("/fact-sheets/abc/intake")
    # The share link must keep needing neither credential, migrated or not.
    assert not api_app.is_jwt_route("/shared/sometoken/report")
