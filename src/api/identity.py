"""Who is making this request.

Authorization asks this module questions — "is this caller a platform admin",
"which organization" — and never inspects a credential or a plan name itself.
That indirection is what let LIC-T20's delivery gate be enforced before per-user
auth existed, and what let LIC-T6 switch the answer's source without touching a
single gate.

**Two credentials, two identities.**

- A **verified Supabase JWT** (LIC-T6) resolves to the real user: their id, and
  whether `public.users.is_platform_admin` is set. Roles are NOT read from the
  token — see `src/api/auth.py` for why — so this does one small indexed lookup
  per request.
- The **shared `GEO_API_KEY`**, on routes that have not migrated, resolves to
  :data:`PLATFORM_ADMIN`. That is not a permissive default: the key is held by
  the two founders and there is genuinely no second identity behind it. Saying so
  plainly is more honest than inventing an anonymous principal that the rest of
  the system would then have to special-case.

The identity is stored in a :class:`~contextvars.ContextVar` set by the auth
dependency. A ContextVar rather than a threaded parameter because FastAPI runs
handlers on a worker thread per request and copies the context into it, so the
value is genuinely per-request — and because the alternative was passing an
identity through every gate's signature, which is the change most likely to be
skipped on the one gate that mattered.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

__all__ = [
    "CallerIdentity",
    "PLATFORM_ADMIN",
    "ANONYMOUS",
    "current_identity",
    "bind",
    "use_identity",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallerIdentity:
    """The authenticated caller, reduced to what authorization actually needs."""

    #: Supabase `auth.users.id`. Empty for the shared-key and anonymous cases,
    #: where there is genuinely no user behind the request.
    user_id: str
    #: A founder (`public.users.is_platform_admin`). Bypasses the tenancy checks,
    #: because they operate the platform.
    is_platform_admin: bool
    #: The agency this caller belongs to, when they are agency staff.
    organization_id: str | None = None
    #: The access token this request arrived with, for LIC-T7 to hand to a
    #: per-request Supabase client so PostgREST evaluates RLS as this user.
    #: Empty on the shared-key path, which still uses the service-role client.
    access_token: str = ""

    @property
    def is_agency(self) -> bool:
        return self.organization_id is not None and not self.is_platform_admin


#: The identity behind the shared `GEO_API_KEY` — the two founders.
PLATFORM_ADMIN = CallerIdentity(user_id="", is_platform_admin=True)

#: No credential at all. The one route that legitimately reaches this is
#: `/shared/{token}/report`, where the token IS the authorisation and the visitor
#: has no account by design.
ANONYMOUS = CallerIdentity(user_id="", is_platform_admin=False)

_current: ContextVar[CallerIdentity] = ContextVar("current_identity", default=PLATFORM_ADMIN)


def current_identity() -> CallerIdentity:
    """The identity behind the current request.

    Defaults to :data:`PLATFORM_ADMIN` outside a request — the CLI, the
    orchestrator, a worker, a test. Those run as us, on our own machine, with our
    own keys, and there is no user to attribute them to. Once LIC-T7 routes
    user-facing reads through a per-request client, a background job keeps the
    service-role client precisely because of this.
    """
    return _current.get()


def bind(identity: CallerIdentity) -> None:
    """Bind an identity for the rest of this request. No unbind, by design.

    Starlette handles each request in its own task, and a task copies the context
    at creation — so this `set` is confined to the current request and cannot leak
    into the next one. Sync handlers run in a threadpool that receives a copy of
    this context, so they read it correctly.

    Use :func:`use_identity` instead wherever the scope really is a block (tests,
    a worker processing one job) and the previous value must come back.
    """
    _current.set(identity)


@contextmanager
def use_identity(identity: CallerIdentity) -> Iterator[CallerIdentity]:
    """Bind an identity for the duration of a block, then restore the previous one.

    Restoring via the token `ContextVar.set` returns, rather than resetting to the
    default: nesting has to unwind to whatever was actually there, or an inner
    anonymous scope would leave an outer authenticated one demoted.
    """
    token = _current.set(identity)
    try:
        yield identity
    finally:
        _current.reset(token)
