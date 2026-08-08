"""Provisioning an agency (LIC-T14) and the agency console (LIC-T19).

Two audiences, one router, and the split between them is the only thing here
that really matters:

- **`/admin/*` is platform-admin only.** Creating an organization, setting its
  plan and its entitlement overrides. This is the first link in the chain — the
  spec's own note is that nothing else creates the organization, so without it
  every other piece of the licence works and no agency can ever be onboarded.
- **`/agency/*` is the owner's own console.** Adding and releasing client
  companies inside the resolved slot band, inviting staff, seeing the roster.

**Access is computed, never copied.** Adding a client is one INSERT with
`managing_agency_id` set; no per-company grant rows are written, and every
existing staffer reaches the new client immediately because
`private.has_company_access` reads `memberships` and `companies` live on every
query. Removing a staffer is one `deactivated_at`.

**Entitlements are checked by capability, never by plan name.** `if org.plan ==
'pro'` scattered through handlers is the anti-pattern LIC-T4 exists to prevent;
everything here goes through `entitlements.resolve()` and `check_slot()`.

**The API check IS the security boundary.** A frontend that greys out the "add
client" button is UX. Every limit enforced here is enforced again nowhere else,
so it has to be right here.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api import identity as identity_mod
from src.licensing import entitlements
from src.storage import db

logger = logging.getLogger(__name__)

router = APIRouter()

#: How long an invitation stays redeemable. Long enough to survive a weekend and
#: a forwarded-to-the-right-person detour, short enough that a token sitting in
#: an abandoned inbox is not a standing grant.
INVITE_TTL_SECONDS = 14 * 24 * 3600

#: Roles an agency owner may hand out from the console. `AGENCY_OWNER` is
#: deliberately ABSENT: an owner minting other owners is how an agency ends up
#: with a staffer who can retarget its billing and cannot be removed by the
#: person who hired them. Founders can do it through the admin path.
INVITABLE_ROLES = ("AGENCY_MANAGER", "BILLING_ONLY")


def _hash_token(token: str) -> str:
    """sha256 of an invite token. The table stores this; the email carries the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _require_platform_admin() -> identity_mod.CallerIdentity:
    identity = identity_mod.current_identity()
    if not identity.is_platform_admin:
        # 404, not 403: the existence of a platform-admin surface is not
        # something an agency user needs confirmed.
        raise HTTPException(status_code=404, detail="not found")
    return identity


def _require_agency() -> tuple[identity_mod.CallerIdentity, str]:
    """The caller's own agency, or a 403. Never takes the org from the request.

    An `organization_id` accepted as a parameter is an organization_id an
    attacker supplies. It comes from the verified identity or not at all.
    """
    identity = identity_mod.current_identity()
    organization_id = identity.organization_id
    if not organization_id:
        raise HTTPException(status_code=403, detail="this endpoint is for agency staff")
    return identity, organization_id


def _entitlements_for(organization_id: str) -> entitlements.Entitlements:
    try:
        org = db.get_organization(organization_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not read the organization") from exc
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if org.deactivated_at:
        raise HTTPException(status_code=403, detail="this organization is deactivated")
    return entitlements.resolve(org.plan_id, org.entitlement_overrides)


# --- LIC-T14: provisioning, platform admin only ------------------------------


class CreateAgencyRequest(BaseModel):
    name: str
    owner_email: str
    plan_id: str = entitlements.DEFAULT_PLAN_ID
    #: A negotiated deal is an OVERRIDE, never a new plan name. Plans stay
    #: `agency` (10 slots) and `agencyPro` (25); a bespoke slot count lives here.
    entitlement_overrides: dict[str, Any] | None = None


@router.post("/admin/agencies")
def create_agency(body: CreateAgencyRequest) -> dict[str, object]:
    """Provision an agency and invite its first owner. The start of the chain.

    The organization and the invitation are created together, and the invitation
    is what the owner redeems to get an `AGENCY_OWNER` membership — written in the
    same transaction as their identity by `db.accept_invitation`.

    Returns the raw invite token exactly once. It is stored only as a hash, so
    this response is the single opportunity to send it; there is no "resend"
    that recovers it, only a fresh invitation.
    """
    _require_platform_admin()
    if not body.name.strip() or not body.owner_email.strip():
        raise HTTPException(status_code=422, detail="name and owner_email are required")
    try:
        # Validates the plan and the override keys BEFORE anything is written —
        # an organization provisioned with an unknown plan is one whose every
        # later entitlement check raises.
        entitlements.resolve(body.plan_id, body.entitlement_overrides)
    except (entitlements.UnknownPlan, entitlements.UnknownEntitlement) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        org = db.create_organization(body.name.strip(), body.plan_id, body.entitlement_overrides)
        token = secrets.token_urlsafe(32)
        invitation_id = db.create_invitation(
            email=body.owner_email,
            role="AGENCY_OWNER",
            token_hash=_hash_token(token),
            expires_at=int(time.time()) + INVITE_TTL_SECONDS,
            organization_id=org.id,
        )
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not provision the agency") from exc

    resolved = _entitlements_for(org.id)
    return {
        "organization_id": org.id,
        "name": org.name,
        "plan_id": org.plan_id,
        "client_slots": resolved.client_slots,
        "invitation_id": invitation_id,
        # Shown once. Never logged — it is a bearer credential for a membership.
        "invite_token": token,
        "expires_in": INVITE_TTL_SECONDS,
    }


class AcceptInviteRequest(BaseModel):
    token: str
    user_id: str
    email: str


@router.post("/auth/accept-invite")
def accept_invite(body: AcceptInviteRequest) -> dict[str, object]:
    """Bind a confirmed identity to its membership. Idempotent by construction.

    Called by the confirm handler once Supabase has verified the address — never
    by a browser directly, which is why the underlying SQL function is not
    granted to `authenticated`.

    A replay returns the SAME membership rather than an error: corporate scanners
    replay these URLs (that is the whole reason LIC-T13's interstitial exists),
    and a second POST landing on "invalid" would strand a user whose membership
    was in fact created correctly the first time.
    """
    if not body.token or not body.user_id or not body.email:
        raise HTTPException(status_code=422, detail="token, user_id and email are required")
    try:
        membership_id = db.accept_invitation(_hash_token(body.token), body.user_id, body.email)
    except db.StorageError as exc:
        # The SQL function raises for not-found, expired and wrong-address. All
        # three are 403 with one message: which of them happened is useful to
        # someone probing tokens and useless to a real invitee, who needs a fresh
        # invitation either way.
        logger.info("invitation not accepted: %s", type(exc).__name__)
        raise HTTPException(
            status_code=403, detail="this invitation is not valid — ask for a new one"
        ) from exc
    return {"membership_id": membership_id}


# --- LIC-T19: the agency console ---------------------------------------------


@router.get("/agency/clients")
def list_clients() -> dict[str, object]:
    """Every company this agency manages, with its slot position.

    No per-company grants are consulted because none exist: the list comes back
    through `has_company_access`, which reaches these rows via
    `companies.managing_agency_id`.
    """
    _identity, organization_id = _require_agency()
    resolved = _entitlements_for(organization_id)
    try:
        companies = [c for c in db.list_companies() if c.managing_agency_id == organization_id]
        count = db.count_companies_for_agency(organization_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not read clients") from exc
    verdict = entitlements.check_slot(count, resolved)
    return {
        "clients": [
            {"id": c.id, "name": c.name, "slug": c.slug, "domain": c.domain} for c in companies
        ],
        "count": count,
        "client_slots": resolved.client_slots,
        # The banner copy. Present even when empty so the frontend has one place
        # to read rather than re-deriving the band it must not be the judge of.
        "warning": verdict.warning if verdict.allowed else "",
    }


class AddClientRequest(BaseModel):
    name: str
    domain: str | None = None


@router.post("/agency/clients")
def add_client(body: AddClientRequest) -> dict[str, object]:
    """Add a client company. One INSERT, and every staffer reaches it immediately.

    Slot enforcement is soft, then hard (LIC-T4, departing from design §5.2
    deliberately): silent at or below the limit, allowed with a warning inside a
    20% grace band so a billing technicality never blocks a customer's business,
    refused beyond it with the resolved limit named.
    """
    from src.api.company_keys import key_for, norm_domain

    _identity, organization_id = _require_agency()
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="a client needs a name")
    resolved = _entitlements_for(organization_id)
    try:
        count = db.count_companies_for_agency(organization_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not read the slot count") from exc

    verdict = entitlements.check_slot(count, resolved)
    if not verdict.allowed:
        # 402, not 403: this is a billing state the caller can resolve, not a
        # permission they will never have.
        raise HTTPException(status_code=402, detail=verdict.warning)

    key, label, resolved_domain = key_for(norm_domain(body.domain), body.name.strip())
    try:
        company = db.create_company(label, key, resolved_domain, organization_id)
    except db.CompanySlugTaken as exc:
        # Never silently reuse the existing row: that would attach this agency to
        # another agency's tenant, which is the cross-tenant merge LIC-T1's
        # slug-collision test exists to prevent.
        raise HTTPException(
            status_code=409, detail=f"{key} is already on the platform"
        ) from exc
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not add the client") from exc

    return {
        "id": company.id,
        "name": company.name,
        "slug": company.slug,
        "domain": company.domain,
        "warning": verdict.warning,
    }


@router.delete("/agency/clients/{company_id}")
def release_client(company_id: str) -> dict[str, object]:
    """Release a client to direct ownership. NOT a delete — storage is create-only.

    One UPDATE setting `managing_agency_id` to null. Agency reach disappears on
    the next call because access is computed, while the company's own
    `COMPANY_ADMIN` membership keeps working untouched — the client keeps their
    data and their logins, and only stops being managed.
    """
    _identity, organization_id = _require_agency()
    try:
        company = db.get_company(company_id)
        if company is None or company.managing_agency_id != organization_id:
            raise HTTPException(status_code=404, detail="not one of your clients")
        db.set_company_agency(company_id, None)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not release the client") from exc
    return {"id": company_id, "managed": False}


class InviteStaffRequest(BaseModel):
    email: str
    role: str = "AGENCY_MANAGER"


@router.post("/agency/staff")
def invite_staff(body: InviteStaffRequest) -> dict[str, object]:
    """Invite a staffer, who will reach every managed company with no grant written."""
    identity, organization_id = _require_agency()
    if body.role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"role must be one of {', '.join(INVITABLE_ROLES)}",
        )
    if not body.email.strip():
        raise HTTPException(status_code=422, detail="an invitation needs an email")
    token = secrets.token_urlsafe(32)
    try:
        invitation_id = db.create_invitation(
            email=body.email,
            role=body.role,
            token_hash=_hash_token(token),
            expires_at=int(time.time()) + INVITE_TTL_SECONDS,
            organization_id=organization_id,
            invited_by=identity.user_id or None,
        )
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not issue the invitation") from exc
    return {
        "invitation_id": invitation_id,
        "email": body.email.strip().lower(),
        "role": body.role,
        "invite_token": token,
        "expires_in": INVITE_TTL_SECONDS,
    }


@router.get("/agency/staff")
def list_staff() -> dict[str, object]:
    """The roster, plus invitations not yet redeemed."""
    _identity, organization_id = _require_agency()
    try:
        return {
            "members": db.list_org_memberships(organization_id),
            "pending": db.list_invitations(organization_id),
        }
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not read the roster") from exc


@router.delete("/agency/staff/{membership_id}")
def remove_staff(membership_id: str) -> dict[str, object]:
    """Remove a staffer. One `deactivated_at`, effective on their next query.

    Revocation is DB-authoritative: `has_company_access` reads `memberships` live,
    so this takes hold immediately rather than at the next token refresh. There is
    no first-party way to force-refresh a user's JWT claims mid-session, which is
    exactly why roles were never put in the token.
    """
    _identity, organization_id = _require_agency()
    try:
        roster = db.list_org_memberships(organization_id)
        if not any(str(m.get("id")) == membership_id for m in roster):
            raise HTTPException(status_code=404, detail="not one of your staff")
        removed = db.deactivate_membership(membership_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="could not remove the staffer") from exc
    return {"membership_id": membership_id, "removed": removed}
