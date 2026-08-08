---
name: licensing
description: Standing rules for multi-tenancy, authentication and the agency licence in geoPromptRunner. Load this before touching ANY identity, tenancy or access-control code — src/api/app.py auth dependencies, src/storage/db.py client construction, RLS policies or data/*.sql schema, memberships/organizations/companies, entitlements or slot limits, invitation and magic-link flows, share links and report tokens, or anything that decides which rows a caller can see. Also load it when executing any task in docs/licensing-spec.md, when adding a table that holds client data, when adding an API route, or when answering how an agency gets access. These rules exist because the licence sells access to other people's clients' data; violating them leaks one customer's data to another or hands a competitor our model-vendor keys.
---

# Licensing, tenancy and access

We sell an agency the right to run audits **through our software, on our keys**, for its own client
companies. That single sentence is the whole security model: the agency gets reach into companies it
manages, never into anyone else's, and never into a raw vendor credential.

**Build spec:** `docs/licensing-spec.md` (22 tasks, dependency order, acceptance criteria).
**Design and code samples:** `docs/licensing-implementation.md` — the spec cites it by section and
deliberately does not reproduce the DDL, the access function, the interstitial component or the
entitlements module. **Research basis:** `docs/licensing-and-packaging-research.md`.
**Repo rules still apply on top of these** — see `CLAUDE.md` and the `geo-dev` skill. Where this file
and a hard invariant in `CLAUDE.md` seem to conflict, `CLAUDE.md` wins; flag the conflict rather than
resolving it yourself.

## The rules that are never negotiable

1. **Never share a raw model-vendor API key with an agency or its clients.** Not in a response body,
   an error payload, a log line, an export or a support screenshot. The agency runs audits through
   our software on our keys — that is what the licence *is*. `LIC-T21` tests this in CI.
2. **A user's tenant lives in `memberships`, never as a scalar FK on the user row.** One user works
   across many client brands; `user.company_id` makes that structurally impossible and retrofitting
   it touches auth, session and every permission check. This is the WagerU pattern the whole design
   exists to avoid.
3. **Access is computed at query time, never copied.** An agency reaches a company through
   `companies.managing_agency_id`, not through per-company grant rows. Adding a client is one INSERT
   and every existing staffer reaches it immediately; removing a staffer is one `deactivated_at`.
4. **Every business table carries `company_id`.** Never `organization_id` — a report is always about
   a company, agency-managed or not.
5. **Storage stays create-only.** RLS restricts reads; it introduces no deletes. The only delete path
   remains explicit project deletion.
6. **Secrets only via `src/config/settings.py`.** `os.getenv` appears nowhere else. Never log a value.

## What actually enforces isolation

**RLS is already enabled on five tables with no policies** (`data/schema_ui.sql:152-156`). It is a
no-op, and it will stay a no-op no matter how many policies you write, because
`src/storage/db.py:183-205` builds one process-wide client from `SUPABASE_KEY` — the **service-role**
key, which bypasses RLS entirely.

**So: enabling RLS proves nothing. Writing policies proves nothing.** The only thing that makes
isolation real is getting user-facing reads onto a per-request client carrying the caller's JWT
(`LIC-T7`). Service-role use survives only in a short, commented allowlist: cache writes, engine
fingerprints, the queue, and the single token-scoped share-link read.

Three details that are load-bearing, not style:

- **`security definer` on the access function** is a 178,000ms → 12ms difference, not a nicety.
  Without it, a policy on `audits` that joins `memberships` triggers RLS evaluation on `memberships`
  for every row of `audits`.
- **`FORCE ROW LEVEL SECURITY`, not just `ENABLE`.** The table owner bypasses RLS without it.
- **Filter on `user_id = (select auth.uid())` first**, never starting from `company_id`. The design
  measures 9,000ms → 20ms for reversing the join direction.

**Isolation tests assert emptiness.** "User A sees their own data" passes against a broken policy
that returns everything. Only "user A gets **zero rows** for org B" catches it, and it must run
through the real API, not a direct DB query.

## Identity, and the one credential doing two jobs

`GEO_API_KEY` is both the API auth credential **and** the share-link signing secret
(`src/api/sharing.py:56`). Retiring it as auth without first moving signing onto `SHARE_SIGNING_KEY`
invalidates every outstanding client report link. `LIC-T11` splits them and must land before
`LIC-T10`.

`require_api_key` is **not** on every route: `/shared/{token}/report` is deliberately mounted on
`app`, not the `api` router (`src/api/app.py:699-701`), because a share link that required the API
key would be useless. Preserve that property — an anonymous visitor with a valid token is a
first-class caller, and the token *is* the authorisation.

**Founders are `is_platform_admin` on the user row — a flag, not a tenant.** Never model them as a
"founders agency" organization; a placeholder tenant pollutes agency-level UI and reporting and has
to be migrated away from later.

## Entitlements

**Check by capability, never by plan name.** `if (org.plan === 'pro')` scattered through handlers is
the anti-pattern; adding a plan or granting one agency a custom limit then means hunting every check.
`resolveEntitlements(planId, overrides)` merges `entitlement_overrides` over `PLAN_ENTITLEMENTS`.

**A negotiated deal is an override, never a new plan name.** Plans stay `agency` (10 slots) and
`agencyPro` (25); an agency's real slot count and price live in `entitlement_overrides`.

**Slot enforcement is soft, then hard.** At or below the limit, silent. Within a 20% grace band,
allowed with a warning for the banner and invoice reconciliation — blocking a customer's business
over a billing technicality costs more than the overage. Beyond the band, refused. **The frontend
gate is UX; the API-boundary check is the security boundary** and must exist independently.

## Onboarding — the things that silently break launch

- **Supabase's built-in email is capped at 2/hour.** A hard limit. Custom SMTP raises it only to
  ~30/hour and stays dashboard-configurable. Email onboarding cannot launch until it is raised.
- **Sign-in is a 6-digit CODE, never a magic link** (LIC-T13, decided 2026-08-07). The auth email
  template carries `{{ .Token }}` and no `{{ .ConfirmationURL }}`; shipping both restores two entry
  paths and every failure mode below. No interstitial page, no PKCE callback — neither is built.
  Anything that reintroduces a clickable auth URL reopens the whole design, so raise it rather than
  adding one.
- **Why the link was dropped, in one line each.** Corporate scanners (Defender Safe Links, Barracuda,
  Proofpoint, Mimecast) prefetch emailed URLs and burn single-use tokens, and Supabase will not fix
  `/verify`; PKCE does not help, because the prefetching scanner *is* the first requester; and the
  browser-bound `code_verifier` breaks "request on laptop, open mail on phone." A code has none of
  these properties. Design §3.2–3.3 keeps the full reasoning.
- **A code is brute-forceable where a token hash is not.** So OTP validity must be turned down from
  Supabase's 1-hour default to ≤10 minutes, the 60s resend cooldown stays, and Supabase's
  verify-attempt limiting must be **confirmed, not assumed** — this is the one place code-only is
  weaker, and the mitigation is not optional.
- **Make `/auth/confirm` idempotent** — stamp `emailVerifiedAt` and treat "already verified" as
  success, because Supabase does not support multi-redemption.
- **A confirmed email with no membership is a broken product.** Write `accepted_at` and the
  membership in the **same transaction** as the identity, or the user logs in and sees nothing.
- **Revocation is DB-authoritative.** There is no first-party way to force-refresh a user's JWT claims
  mid-session, so keep RLS reading `memberships` live and call `admin.signOut(userId, 'global')` on
  revocation. Do not move roles into the token.

## Delivery to an agency's client

The agency's end client **usually has no account at all** — they receive a signed, expiring link.
Client-viewer logins come later, share links first. Report tokens are a **row**, not a stateless
HMAC: the design rejects stateless signing because it is revocable only by rotating the secret, which
kills every link at once. The token row carries `company_id`, so "this client's links stop working
when their membership is deactivated" is expressible at all.

Harden the report route: `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, and exchange the
URL token for an httpOnly cookie on first load so it stops leaking through referrers and history.

## Verdict provenance

Prejudge writes verdicts under the **production cache keyspace**, so a subscription-judged verdict
and an API-judged verdict are indistinguishable downstream. An agency pays for API-judged output and
must be able to tell it got it.

Tag every verdict `api` | `prejudge` | `opus_dev` at write time. **A report containing any non-`api`
verdict cannot be rendered for, or shared with, a non-platform organization.** Prejudge and Opus
verdicts stay dev-only and never feed calibration or gold labels.

## Scope boundaries

Not in scope, deliberately, until the second agency arrives: white-label theming and logo upload,
custom domains, Stripe invoicing and usage snapshots, client-viewer logins, JWT custom claims, and a
metered usage API. None is needed for an agency to run audits and deliver them. If a task seems to
require one, re-read `docs/licensing-spec.md` — it almost certainly does not.
