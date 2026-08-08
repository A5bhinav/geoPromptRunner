# Licensing build spec — agency organizations, auth, and tenancy

**Written:** 2026-08-05 · **Executes:** `docs/licensing-implementation.md` (the design)
**Standing rules:** `.claude/skills/licensing/SKILL.md` — load it with this file.
**Decisions taken 2026-08-05:** full login now, not a scoped-key interim · entitlements keep the
design's `agency` = 10 slots / `agencyPro` = 25, with each agency's real slot count and price set
through `entitlement_overrides` rather than new plan names.

This file is to `licensing-implementation.md` what `audit-packaging-spec.md` is to
`audit-packaging-implementation.md`: the design holds the reasoning and the code samples, this holds
the ordered, testable tasks. **Where they disagree, this file wins** — it was written against the
code, the design was not. Every deliberate departure is called out in the task that makes it.

---

## The one-paragraph problem

There is no identity in this system. `require_api_key` (`src/api/app.py:107`) compares a single
static `GEO_API_KEY` with `hmac.compare_digest` and is applied as a router-wide dependency
(`app.py:124`), so one key grants everything to everyone who holds it. There is no `users`,
`organizations`, `memberships` or `companies` table in `data/*.sql`. Companies are not rows at all:
`projects._collect()` (`src/api/projects.py:152`) derives them per request from run records
(`runner.list_runs()`, `projects.py:175`) **and teaser records** (`db.list_teasers_with_url()`,
`projects.py:191`), keyed by `_key_for` (`projects.py:144`) on the registrable **domain** with a
name-slug fallback. **A membership, a slot count and an RLS predicate cannot reference a groupby**,
which is why the design's build order — "step 1, the memberships table" — cannot be executed as
written.

Two further facts the design predates, both load-bearing:

- **RLS is already enabled** on `audit_runs`, `query_results`, `query_citations`, `judgments` and
  `local_pack_entities` (`data/schema_ui.sql:152-156`) — with **no policies**. It is currently a
  no-op because the API connects with the service-role key. The work is policies, `FORCE`, and
  getting off that key — not enabling.
- **`GEO_API_KEY` is also the share-link signing secret** (`src/api/sharing.py:56`). Deleting it when
  auth moves to JWT would invalidate every outstanding client report link.

---

## Dependency graph

```
LIC-T0  verify launch-blocking assumptions (no code) ──► BLOCKS LIC-T6 (JWT shape), LIC-T12 (email cap)
LIC-T1  [KEYSTONE] materialise organizations + companies ──► LIC-T2 ──► everything downstream
   LIC-T2 (rest of tenancy DDL) ──┬── LIC-T3 (access function + indexes)
                                  └── LIC-T4 (entitlements)
   LIC-T5 (Supabase Auth, RLS still a no-op) ──► LIC-T6 (JWT per route)
   LIC-T6 ──► LIC-T7 (storage off the service-role client)
   LIC-T3 + LIC-T7 ──► LIC-T8 (isolation tests) ──► LIC-T10
   LIC-T1 + LIC-T6 ──► LIC-T9 (backfill, NOT NULL) ──► LIC-T10 (policies + FORCE)
   LIC-T11 (split the share-signing secret) ──► must land BEFORE LIC-T10 retires GEO_API_KEY
   LIC-T0 + LIC-T6 ──► LIC-T12 (Resend hook) ──► LIC-T13 (code-only sign-in)
   LIC-T13 + LIC-T4 ──► LIC-T14 (provision org, bind invite→membership)
   LIC-T13 ──► LIC-T15 (abuse gates)
   LIC-T16 (queue) — independent of tenancy; LIC-T18 must land before an agency uses it
   LIC-T1 ──► LIC-T17 (report-token table, replacing the stateless HMAC)
   LIC-T6 + LIC-T1 ──► LIC-T18 (intake under auth)
   LIC-T4 + LIC-T10 ──► LIC-T19 (agency console)
   LIC-T20 (verdict-source gate) — INDEPENDENT
   LIC-T21 (no-vendor-key test) — after LIC-T11, since it asserts on SHARE_SIGNING_KEY
   Both T20 and T21 must be green before the first agency-run audit reaches a client.
```

---

# Phase L0 — prerequisites, no code

## LIC-T0 — Verify the launch-blocking assumptions against the real Supabase project

**Blocking:**
- **Supabase's built-in email is capped at 2/hour** (design §3.1), a hard limit; custom SMTP raises
  it only to ~30/hour and stays dashboard-configurable. Confirm the current cap and raise it.
  **Blocks LIC-T12.**
- **Asymmetric JWT signing keys** moved backend verification from `getUser()` to `getClaims()`.
  Establish which is correct for this project **before** LIC-T6 is written. **Blocks LIC-T6.**

**Check, non-blocking:** stale `@supabase/auth-helpers-nextjs` imports vs `@supabase/ssr` · whether
there is still no first-party way to force-refresh JWT claims mid-session · Vercel's apex A-record
from the dashboard, never a blog · Supabase Storage `file_size_limit` / `allowed_mime_types`
parameter names in the current SDK · US state economic-nexus thresholds, to an advisor.

**Also add now:** `supabase db advisors` (security lint) to CI, per design §1.3.

**Done when:** each has a dated line in `docs/build-log.md`. No code.

---

# Phase L1 — make companies real, then add tenancy

## LIC-T1 — [KEYSTONE] Materialise `organizations` and `companies`

**Problem:** `audit_runs` carries `client_name text` and `client_domains jsonb` and nothing else
(`schema_ui.sql:14-15`). Projects are assembled per request from two sources and never persisted.

**Change:**
- Create `public.organizations` and `public.companies` **in the same migration** — companies'
  `managing_agency_id uuid null references organizations(id)` makes the order circular otherwise,
  which is why design §1.1 ships both in one block. LIC-T2 adds the remaining tenancy tables.
- `public.companies` (id, name, slug unique, `managing_agency_id`, created_at). `managing_agency_id`
  stays nullable and reassignable: a client going direct is one UPDATE, not a migration.
- **Backfill from both sources.** Reuse `_norm_domain` / `_slugify` / `_key_for` verbatim — do not
  write a second normaliser, or the slugs stop matching what the UI already shows. A teaser-only
  prospect with no `audit_runs` row still gets a company.
- Add `company_id uuid references companies(id)` — **nullable, no default** — to `audit_runs`,
  `teasers`, `fact_sheets`, `fact_claims`, `factsheet_intake_sessions`, `client_configs`,
  `findings_registry`, `audit_deliverables` and the `site_audit_*` tables. Nullable is required:
  existing rows have no tenant, and NOT NULL with a function default forces a full table scan.
- **The four run-child tables get `company_id` too, not a join.** `query_results`, `query_citations`,
  `judgments` and `local_pack_entities` carry only `run_id` (`schema_ui.sql:79-121`) and are exactly
  the tables that already have RLS enabled. A policy that joins back to `audit_runs` to find the
  tenant re-introduces the per-row recursion `security definer` exists to avoid, on the
  highest-volume tables in the system — 1,500 rows per run at the current scope. Denormalise
  `company_id` onto them and backfill from the parent run.
- **Backfill `company_id` only where the rows are genuinely customer data** (design §2 step 4). Where
  a table holds fixture or seed rows, record that in the build log and leave them null; LIC-T9
  decides per table whether NOT NULL is appropriate.
- Rewrite `projects.list_projects` / `get_project` / `project_history` / `delete_project` to read
  `companies`, keeping the public response shape byte-identical.

**Test:** golden test capturing `list_projects()` before the change and asserting an identical list
after, **with a teaser-only project in the fixture** · slug collision between two different clients
raises rather than silently merging them · every non-fixture `audit_runs` row has a `company_id`, and
every `query_results` row's `company_id` matches its parent run's.

## LIC-T2 — [Depends: LIC-T1] The rest of the tenancy DDL

`membership_role` enum · `public.users` mirroring `auth.users` with `is_platform_admin boolean` and
`deactivated_at` · `plan_id text` and `entitlement_overrides jsonb null` added to the
`public.organizations` table created in LIC-T1 · `public.memberships` with the design's exclusivity
CHECK — **exactly one of `organization_id` / `company_id`** — plus `invited_by`, `accepted_at`,
`deactivated_at` and both unique indexes.

Domain tables carry `company_id`, never `organization_id`: a report is always about a company.

**Test:** pgTAP asserting the CHECK rejects both-null and both-set, and that the unique indexes
reject a duplicate membership per (user, org) and (user, company).

## LIC-T3 — [Depends: LIC-T2] Access function and its indexes

`private.is_platform_admin()` and `private.has_company_access(uuid)`, both `language sql stable
security definer set search_path = ''`, granted to `authenticated`, exactly as design §1.2 — covering
platform-admin bypass, direct company membership, and the agency-managed path through
`companies.managing_agency_id`.

`security definer` is not optional: without it, a policy on `audits` that joins `memberships`
triggers RLS evaluation on `memberships` for every row of `audits`. The design's measured figure is
178,000ms → 12ms. Filter on `user_id = (select auth.uid())` first, never starting from `company_id`;
the design measures 9,000ms → 20ms for reversing the join direction.

Index `memberships(user_id)`, `memberships(organization_id)`, `memberships(company_id)`,
`companies(managing_agency_id)`.

**Test:** platform admin / direct member / agency member / unrelated user → true/true/true/false,
plus an EXPLAIN assertion that the index is used.

## LIC-T4 — [Depends: LIC-T2] Entitlements

`PLAN_ENTITLEMENTS` with `agency` = 10 slots and `agencyPro` = 25 (design §5.3, retained by
decision). `resolveEntitlements(planId, overrides)` merges `entitlement_overrides` over the plan.
**A negotiated deal is an override, never a new plan name.**

**Check by capability, never by plan name.** `if (org.plan === 'pro')` scattered through handlers is
the anti-pattern this task exists to prevent.

**Departure from design §5.2, deliberate.** The design says slot enforcement should be a *soft
warning* — "blocking slot creation risks blocking your customer's business over a billing
technicality." That reasoning holds for the paying agency's own growth, so: **soft within the limit,
warned in a grace band, hard-refused outside it.** At or below `clientSlots`, silent. Above it and
within a 20% grace band, allowed with a warning for the banner and invoice reconciliation. Beyond the
band, refused with the resolved limit named. The frontend gate is UX; the API check is the boundary.

**Test:** an override raising slots to 40 resolves without touching `PLAN_ENTITLEMENTS` · slot 11 of
10 succeeds with a warning · slot 13 of 10 is refused at the API with the limit in the error.

---

# Phase L2 — auth, before enforcement

## LIC-T5 — [Depends: LIC-T2] Enable Supabase Auth, backfill identities

Enable Auth · add the `handle_new_user` trigger mirroring `auth.users` into `public.users` · create
founder accounts with `is_platform_admin = true` · backfill memberships for existing work.

**Model the founders as a flag, not a "founders agency" organization.** A placeholder tenant pollutes
agency-level UI later and has to be migrated away from.

Nothing is enforced yet — the API still connects as service-role, so RLS remains a no-op.

## LIC-T6 — [Depends: LIC-T0, LIC-T5] JWT per route, feature-flagged

**Problem:** `require_api_key` is one shared secret across the whole `api` router. Note it is *not*
on every route — `/shared/{token}/report` is deliberately mounted on `app`, not `api`, because a
share link that required the API key would be useless (`app.py:699-701`). Keep that property.

**Change:** verify the Supabase JWT in FastAPI using whichever of `getClaims()` / `getUser()` LIC-T0
established, thread claims per design §1.4, and gate **per route behind a feature flag** so routes
migrate one at a time. `GEO_API_KEY` keeps working for unmigrated routes.

RLS stays a no-op here on purpose: this is where every "assumed one tenant" bug surfaces loudly
rather than silently.

**Test:** a migrated route rejects a valid `GEO_API_KEY` and accepts a valid JWT; an unmigrated route
does the reverse; no route accepts both; `/shared/{token}/report` still needs neither.

## LIC-T7 — [Depends: LIC-T6] Take the storage layer off the service-role client

**Problem — this is the task without which none of the RLS work does anything.** `src/storage/db.py`
builds one process-wide `_cached_client` from `SUPABASE_KEY` (`db.py:183-205`) and every read and
write goes through it. That is the **service-role** key, which bypasses RLS entirely. Enabling
policies while the API still connects this way changes nothing an attacker would notice.

Design §1.4 addresses this for a raw Postgres connection with transaction-scoped
`set_config(..., is_local => true)`. This codebase uses supabase-py / PostgREST with a cached
module-level client, so the design's recipe does not transfer directly.

**Change:** make the request's identity explicit at the storage boundary. Build a per-request client
carrying the caller's JWT for every user-facing read/write path, and keep the service-role client
**only** for genuinely system-level work — cache writes, engine fingerprints, the queue, and the
single token-scoped share-link read added by LIC-T17 — each named in a short allowlist in this task
with a comment saying why.

**Test:** an integration test proving a request authenticated as org A's user receives **zero rows**
for org B's company through the real API, not a direct DB query. Mark it
`@pytest.mark.xfail(strict=True, reason="isolation not enforced until LIC-T10")`.

## LIC-T8 — [Depends: LIC-T3, LIC-T7] Isolation tests that assert emptiness

pgTAP plus API-level integration tests asserting a user from org A gets **zero rows** — not
"different rows" — for org B's companies, audits, findings, reports and citations. A test asserting
"user A sees their own data" passes against a broken policy that returns everything; only emptiness
assertions catch it. Same `xfail(strict=True)` marker as LIC-T7; LIC-T10 removes both.

---

# Phase L3 — contract and enforce

## LIC-T9 — [Depends: LIC-T1, LIC-T6] Backfill to completion, then NOT NULL

Per table, decide from the build-log entry written in LIC-T1 whether the rows are customer data. For
those that are: verify `count(*) where company_id is null = 0`, then `SET NOT NULL` — on any large
table via `CHECK (company_id IS NOT NULL) NOT VALID` then a separate `VALIDATE CONSTRAINT`, to avoid
a long exclusive lock. Fixture-only tables stay nullable and are recorded as such.

## LIC-T10 — [Depends: LIC-T8, LIC-T9, LIC-T11] Policies, then FORCE

**RLS is already enabled with no policies** (`schema_ui.sql:152-156`), so this task writes policies
rather than turning anything on. Write and pgTAP-test every policy against the real schema in a
Supabase branch first. Then add `FORCE ROW LEVEL SECURITY` table by table, re-running LIC-T8 after
each — `FORCE` matters because the table owner bypasses RLS without it.

Every policy calls `private.has_company_access(company_id)` and targets `TO authenticated`. Mirror
the predicate in application queries (`.eq('company_id', id)`); the design measures 171ms → 9ms.
`AS RESTRICTIVE` narrows by AND-ing with every other policy — use it deliberately, never as the
default (design §1.3).

**Retire `GEO_API_KEY` as an authentication credential here — and only as that.** LIC-T11 must have
already moved share-link signing onto its own secret; deleting the setting outright invalidates every
outstanding client report link.

**Last step: remove the `xfail` markers from LIC-T7 and LIC-T8.** That removal is this task's
acceptance criterion — the markers are `strict=True`, so they fail loudly the moment isolation starts
working, which is exactly when they should stop being expected failures.

---

# Phase L4 — onboarding a real agency

## LIC-T11 — [Blocks LIC-T10] Split the share-link signing secret

**Problem:** `sharing._secret()` returns `settings.GEO_API_KEY` (`sharing.py:56`) and every share
token is HMAC'd with it. The auth credential and the signing key are the same value, so retiring one
silently breaks the other.

**Change:** introduce `SHARE_SIGNING_KEY` in `src/config/settings.py`, seeded from the current
`GEO_API_KEY` value so existing links keep verifying. Verify against the new key, falling back to the
old for a stated deprecation window, then drop the fallback.

**Test:** a token minted before the change verifies after it · a token minted after verifies once the
fallback is removed · an unset `SHARE_SIGNING_KEY` refuses to mint rather than signing with an empty
key, matching current behaviour.

## LIC-T12 — [Depends: LIC-T0, LIC-T6] Resend Auth Hook, DNS, warm-up

Send through the **Auth Hook**, not SMTP. Confirm LIC-T0's raised rate limit is in effect first.
SPF/DKIM/DMARC and domain warm-up per design §3.4–3.5.

## LIC-T13 — [Depends: LIC-T12] Code-only sign-in (no magic link)

**DECIDED 2026-08-07: email OTP only. No clickable magic link, and therefore no interstitial.**
This reverses the design in §3.2–3.3, which specified a scanner-safe interstitial plus an OTP
fallback. The reasoning for that design is still correct and is preserved there — it just no longer
applies once nothing in the email is clickable.

**Why the link was the problem, not the thing being protected.** Both defences in §3.2–3.3 exist
only because of the link. The interstitial exists solely so a prefetching scanner (Defender Safe
Links, Barracuda, Proofpoint, Mimecast) renders static HTML instead of burning a single-use token.
The PKCE same-device trap exists solely because the link carries a browser-bound `code_verifier`, so
"request on laptop, open mail on phone" fails. A six-digit code has neither property: reading an
email does not consume a code, and typing one is device-agnostic by construction. Deleting the link
deletes both failure modes, the interstitial page, and the whole PKCE callback path.

**Mechanics.** The magic-link template carries `{{ .Token }}` and **no `{{ .ConfirmationURL }}`**.
Shipping both is the one way to get this wrong: users then have two routes in, and both original
failure modes return along with the page we just deleted. Sign-in is
`signInWithOtp` → user types the code → `verifyOtp({ type: 'email' })`. Keep `/auth/confirm`
idempotent — stamp `emailVerifiedAt` and treat "already verified" as success — since Supabase does
not support multi-redemption and a double submit is ordinary user behaviour.

**Where this is weaker, and the mitigation.** A 6-digit code is brute-forceable in a way a token
hash is not — a million combinations is not many. So: turn OTP validity down from Supabase's 1-hour
default (§3.1) to ≤10 minutes as part of the LIC-T0 dashboard pass, keep the 60s per-address resend
cooldown, and **confirm Supabase's verify-attempt limiting rather than assuming it** — if there
isn't one, we add our own before launch. This is the single item that must not be skipped; it is the
only respect in which code-only is worse than a link.

Scanner user-agent logging is now moot and is not built — there is nothing in the email for a
scanner to consume.

Unchanged: client report delivery. Those are anonymous token-scoped share links (§3.6), not auth,
and the end client still never logs in.

**Test:** the rendered auth email contains a code and **no absolute `/auth/` URL** — this is the
regression guard against a link creeping back in. A second `/auth/confirm` submit with a consumed
code returns success.

## LIC-T14 — [Depends: LIC-T13, LIC-T4] Provision an agency, bind the invite to a membership

**Problem — nothing else creates the organization.** LIC-T2 adds the columns, LIC-T12/T13 build email
transport, LIC-T19 covers an *existing* owner inviting staff. The first link in the chain is missing.

**Change:** a platform-admin-only path that creates the `organizations` row with a `plan_id` and any
`entitlement_overrides`, then issues an invitation recording `invited_by`. On confirm,
`/auth/confirm` writes `accepted_at` and the `AGENCY_OWNER` membership in the **same transaction** as
the identity is created — a confirmed email with no membership is a user who can log in and see
nothing, which reads as a broken product.

**Test:** end-to-end from platform admin creating the org to the owner landing authenticated with
exactly one `AGENCY_OWNER` membership · a replayed confirm does not create a second membership · a
confirm that fails midway leaves neither an orphan user nor an orphan membership.

## LIC-T15 — [Depends: LIC-T13] Abuse gates, cheapest first

Turnstile, then per-IP and per-domain rate limits, then confirm-gated enqueue — a run is never queued
before the email is verified. Ordered so the expensive check runs least.

## LIC-T16 — [Independent] Queue and status

arq plus a polling status endpoint. `audit_runs` already carries `status`, `completed_calls`,
`total_calls` (`schema_ui.sql:21-23`) — reuse them rather than adding a parallel state machine.

## LIC-T17 — [Depends: LIC-T1] Report tokens as a table, replacing the stateless HMAC

**Departure from the shipped implementation, deliberate.** Design §3.6 explicitly *rejects* stateless
HMAC — revocable only by rotating the secret, which kills every link at once — and chooses a DB token
table for per-link revocation and an access log. What shipped is the rejected option with a
`revoked_share_tokens` deny list bolted on to compensate.

Keep what works — signature, TTL, optional password, per-token revocation surviving deploys — and
move the token to a row carrying `company_id`, `first_viewed_at` and `view_count`. That is what makes
"this client's links stop working when their membership is deactivated" expressible at all; it cannot
be reconciled against a stateless token carrying only `run_id`.

**Name the read path for an unauthenticated visitor.** `/shared/{token}/report` reaches the database
through `runner.get_report` with no JWT, so once LIC-T10 lands policies `TO authenticated` with
`FORCE`, that route returns zero rows unless something is done. The token row **is** the
authorisation: verify it, then read that one report through a service-role call scoped to the single
`run_id` the token names — added to LIC-T7's allowlist with that reason. It must not become a general
service-role read path.

Harden the route per design §3.6: `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`, and
exchange the URL token for an httpOnly cookie on first load so it stops leaking through referrers and
browser history.

**Test:** revoking one link leaves others working across a redeploy · deactivating a company's
membership stops its links · the token does not appear in a subsequent request's `Referer`.

## LIC-T18 — [Depends: LIC-T6, LIC-T1] Bring fact-sheet intake under auth and tenancy

The intake routes "carry no auth of their own — they ride the same `require_api_key` dependency"
(`app.py:1274-1276`). DoD #4 depends on this flow, so it needs migrating under LIC-T6's per-route
flag, and `factsheet_intake_sessions` / `fact_sheets` / `fact_claims` need company scoping and
policies. An agency onboarding its own client is the first real use of this path.

---

# Phase L5 — the agency console, and two gates that outrank it

## LIC-T19 — [Depends: LIC-T4, LIC-T10] Agency console

An `AGENCY_OWNER` adds and removes client companies within the resolved slot band, invites staff as
`AGENCY_MANAGER` or `BILLING_ONLY`, and sees every managed company.

**Access is computed, never copied.** Adding a client is one INSERT with `managing_agency_id` set; no
per-company grants are written and every existing staffer reaches it immediately. Removing a staffer
is one `deactivated_at`.

**Test:** an agency staffer reads a managed company they hold no membership on · reparenting to
`managing_agency_id = null` removes agency reach on the next call while the company's own
`COMPANY_ADMIN` membership keeps working untouched.

## LIC-T20 — [Independent · blocks the first agency-run audit] Verdict-source gate

**Problem:** the prejudge path writes verdicts under the **production cache keyspace**, so a
subscription-judged verdict and an API-judged verdict are indistinguishable downstream.
`verdict_source` appears nowhere in `src/` or `data/` today. The moment an agency triggers a run, the
agency is paying for API-judged output and cannot tell whether it received it.

Tag every verdict `api` | `prejudge` | `opus_dev` at write time. **Hard delivery gate:** a report
containing any non-`api` verdict cannot be rendered for, or shared with, a non-platform organization.
Prejudge and Opus verdicts stay dev-only and never feed calibration or gold labels.

**Test:** a run with one prejudge verdict is refused at render for an agency-owned company, succeeds
for a platform admin, and names the reason.

## LIC-T21 — [Depends: LIC-T11 · blocks the first agency-run audit] Prove no vendor key can leave

The standing rule "never share a raw model-vendor API key with an agency or its clients" has been a
sentence in a doc with nothing enforcing it.

Add a test asserting that no API response body, error payload, log line or export produced under a
non-platform identity contains the value of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`PERPLEXITY_API_KEY`, `GEMINI_API_KEY`, `SERPER_API_KEY`, `SUPABASE_KEY` or `SHARE_SIGNING_KEY`.
Wire it into CI so a future error handler that echoes config fails the build.

---

## Not in this spec, deliberately

White-label theming and logo upload (design §4) · custom domains · Stripe invoicing, usage snapshots
and invoice reconciliation (design §5.1–5.2) · client-viewer logins, since share links come first ·
JWT custom claims, since DB-authoritative RLS is simpler and has no staleness gap · metered usage API.
None is needed for an agency to run audits and deliver them. Specify them when the second agency
arrives, not the first.

---

## Global acceptance

- **Order:** LIC-T0 → LIC-T1 → L1 → L2 → L3 → L4 → L5, with two exceptions an implementer working
  strictly by phase would otherwise hit as a wall: **LIC-T11 is listed under L4 but must be built
  before LIC-T10 in L3**, and LIC-T20 / LIC-T21 may land in any phase but must both be green before
  the first agency-run audit reaches a client.
- **One task per session**, ending green on `mypy src/` → `ruff check src/` → `pytest tests/` (plus
  `npm run typecheck` for web tasks), with one regression test added.
- **The two isolation suites are the one exception.** LIC-T7 and LIC-T8 write tests that *must* fail
  until LIC-T10 lands policies. Mark them `@pytest.mark.xfail(strict=True, reason="isolation not
  enforced until LIC-T10")` so the session still ends green **and** the marker fails loudly the day
  they start passing. LIC-T10 removes the markers as its last step.
- `docs/build-log.md` is append-only, most recent first.
- **Storage stays create-only.** RLS restricts reads; it introduces no deletes.
- **Secrets only via `src/config/settings.py`.** `os.getenv` appears nowhere else; never log a value.
- **Never share a raw model-vendor API key with an agency or its clients.** LIC-T21 enforces it.

## Definition of done

Done when Shay can do all of this without us touching anything:

| # | Outcome | Delivered by |
|---|---|---|
| 1 | Accept an emailed invitation a corporate scanner cannot burn, and land authenticated as `AGENCY_OWNER` of her own organization | LIC-T12, T13, **T14** |
| 2 | Add client companies within her slot band, warned inside the grace band and refused at the API beyond it | LIC-T4, T19 |
| 3 | Invite her own staff, who reach every managed company with no per-company grant written | LIC-T3, T19 |
| 4 | Onboard a client through the fact-sheet intake flow and trigger a run that queues and reports progress | **LIC-T18**, T16 |
| 5 | Deliver through a signed, expiring link her client opens without an account, and revoke that one link without affecting others | **LIC-T11**, T17 |
| 6 | See her own companies and nothing else — proven by tests asserting **zero rows** through the real API | **LIC-T7**, T8, T10 |
| 7 | Never hold a vendor key, and never receive a report containing a non-`api` verdict | **LIC-T21**, T20 |
