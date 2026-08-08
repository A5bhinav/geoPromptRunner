# How to Build Accounts, Tenancy and Licensing — Implementation Guide

**Compiled:** 2026-08-01 · **Method:** 4 research agents (~180 sources) on implementation technique
**Scope:** the *how* for the model decided in `docs/licensing-and-packaging-research.md` — self-serve onboarding, the agency→company hierarchy, white-label, share links, billing.
**Priority:** secondary to `audit-packaging-implementation.md`. Don't start this until Phase 1–2 of the packaging work is real, with one exception in §0.

---

## 0. The one thing to do before anything else

**Create the `memberships` join table now, even though every user will have exactly one membership in v1.**

This is the entire insurance policy from the licensing research: `User.schoolId` as a scalar FK (the WagerU pattern) makes "one user, many companies" structurally impossible, and retrofitting it later touches auth, session, and every permission check. One extra table today.

Everything else in this document can wait. That table can't — it costs nothing now and everything later.

---

## 1. Schema and RLS

### 1.1 Core DDL

```sql
create extension if not exists pgcrypto;

create type public.membership_role as enum (
  'AGENCY_OWNER','AGENCY_MANAGER','COMPANY_ADMIN','COMPANY_VIEWER','BILLING_ONLY'
);

create table public.users (               -- mirrors auth.users
  id                uuid primary key references auth.users(id) on delete cascade,
  email             text not null,
  is_platform_admin boolean not null default false,   -- the founders
  created_at        timestamptz not null default now(),
  deactivated_at    timestamptz                        -- soft delete; storage is create-only
);

create table public.organizations (       -- agencies; absent for solo companies
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now(),
  deactivated_at timestamptz
);

create table public.companies (           -- the audited brand; the paying tenant
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  managing_agency_id uuid references public.organizations(id),  -- NULLABLE, reassignable
  created_at timestamptz not null default now()
);

create table public.memberships (         -- ← the load-bearing table
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users(id),
  organization_id uuid references public.organizations(id),
  company_id      uuid references public.companies(id),
  role            public.membership_role not null,
  invited_by      uuid references public.users(id),
  accepted_at     timestamptz,
  deactivated_at  timestamptz,
  check ((organization_id is not null and company_id is null)
      or (organization_id is null and company_id is not null)),
  unique (user_id, organization_id),
  unique (user_id, company_id)
);
```

Domain tables carry `company_id`, never `organization_id` — a report is always about a company, agency-managed or not.

**`managing_agency_id` is nullable and reassignable, not ownership.** When a client leaves the agency and goes direct, it's one UPDATE plus a membership grant. AgencyAnalytics — the market leader — can't do this; their docs say transferring a client requires manually recreating dashboards, reports, and users because they "cannot be exported."

### 1.2 The access function

Every business-table policy calls this. It must cover platform-admin bypass, direct company membership, *and* the agency-managed path.

```sql
create schema if not exists private;

create or replace function private.has_company_access(target_company_id uuid)
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select
    private.is_platform_admin()
    or exists (                              -- direct company membership
      select 1 from public.memberships m
      where m.user_id = (select auth.uid())
        and m.company_id = target_company_id
        and m.deactivated_at is null
    )
    or exists (                              -- agency-managed path
      select 1 from public.memberships m
      join public.companies c on c.managing_agency_id = m.organization_id
      where m.user_id = (select auth.uid())
        and c.id = target_company_id
        and m.deactivated_at is null
    );
$$;

grant execute on function private.has_company_access(uuid) to authenticated;
```

**Why `security definer` specifically matters:** without it, a policy on `audits` that joins `memberships` triggers RLS evaluation *on `memberships` itself* for every row of `audits`, compounding per-row. `security definer` runs the internal query once, plain and indexed, with no recursive policy evaluation.

### 1.3 RLS performance — the numbers are dramatic

From Supabase's own [troubleshooting doc](https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv):

| Technique | Improvement |
|---|---|
| Index the columns used in policies | >100× |
| Wrap `auth.uid()` as `(select auth.uid())` | 179ms → 9ms |
| `security definer` function for join-table checks | **178,000ms → 12ms** |
| `TO authenticated` role targeting | 170ms → <0.1ms for excluded roles |
| Mirror the RLS filter in the app query (`.eq('company_id', id)`) | 171ms → 9ms |
| Reverse the join direction (start from `user_id`, not `company_id`) | 9,000ms → 20ms |

The last one is why `has_company_access` filters on `user_id = (select auth.uid())` first — small, index-friendly result set — rather than starting from `company_id`.

**Three footguns to check off:**

1. **Table owners bypass RLS by default.** `ENABLE ROW LEVEL SECURITY` doesn't apply to the owner. If migrations run as `postgres` and your app connects as the same role, RLS is silently a no-op. Fix: `ALTER TABLE ... FORCE ROW LEVEL SECURITY` on every tenant table, and never run application traffic as the table owner.
2. **Multiple permissive policies OR together.** Adding a second permissive policy to "add an exception" silently widens access on all existing rows. Use `AS RESTRICTIVE` to narrow.
3. **Non-`LEAKPROOF` functions in policy predicates** can disable pushdown and force per-row evaluation. Keep predicates simple and `STABLE`.

Run `supabase db advisors` in CI — lints 0007/0008/0013 catch "RLS enabled, no policy," "policy exists, RLS disabled," and "RLS disabled in public."

### 1.4 The FastAPI service-role problem — get this exactly right

A backend using the service-role key **bypasses RLS entirely**. Pass the user's JWT through to Postgres instead, and the mechanism has a real cross-tenant leak vector:

- `set_config(name, value, is_local)`: `is_local = true` scopes to the **current transaction** and reverts at COMMIT. `is_local = false` sets it for the **entire session** — the lifetime of the physical connection.
- **Always use `is_local = true`, wrapped in an explicit transaction.** With session-level config on a pooled connection, User A's claims persist on that backend after their request. Under transaction-mode pooling (Supavisor/PgBouncer), the *next* request — possibly a different tenant — can be handed that same physical connection and inherit A's claims.

The severity is in how it fails: *"only manifests under production load when backends are recycled rapidly… tests pass in development with a single connection."*

Also: `SET`/`set_config` for RLS **does not work at all under PgBouncer statement-mode pooling** — you get rows for the wrong user, surfacing only under concurrency.

Treat pooler reset-on-return (`server_reset_query`, `DISCARD ALL`) as a *secondary* safety net, not the primary mechanism. There's an active Postgres mailing-list report that `set_config(..., true)` behavior can change after first use in a session and `RESET ALL`/`DISCARD ALL` don't fully restore it.

### 1.5 JWT claims vs table lookups

Putting `org_id`/role into the JWT via a Supabase custom access token hook avoids a per-query lookup, but introduces **staleness**: a revoked membership still lives in an unexpired JWT.

There is **no first-party Supabase mechanism to force-refresh a specific user's claims mid-session.** Design around it: keep RLS DB-authoritative (the policies above hit `memberships` live, so revocation is immediate at the data layer regardless of what the token says), and call `admin.signOut(userId, 'global')` on revocation. Re-check Supabase's changelog before shipping — this may have moved.

### 1.6 Testing isolation

Two layers, because they catch different bugs:

- **pgTAP** at the DB level — fast, CI-friendly, tests policies directly.
- **Integration tests** at the app level — authenticate as user A, assert zero rows from tenant B. Catches FastAPI-layer regressions (a forgotten `set_config`, a service-role path that shouldn't be) the DB layer can't see.

**The subtlety that makes tests lie: RLS denies by returning zero rows, not an error.** A broken policy looks like "no results found," which passes a naive test and passes manual clicking. **Assert emptiness explicitly**, never just "didn't throw."

---

## 2. Migration from no-auth to multi-tenant

Expand → migrate → contract, adapted to a founders-only starting point. Each step independently verifiable and reversible.

**Phase 0 — Expand (schema only, zero behavior change)**
1. Ship §1.1 DDL as new empty tables. Nothing existing is touched.
2. Add `company_id uuid references companies(id)` **nullable, no default** to every tenant-owned table. Nullable is required — existing rows have no tenant, and adding NOT NULL with a function default forces a full table scan.
3. **Model the founders as `is_platform_admin`, not a fake "founders agency" org.** A placeholder tenant pollutes agency-level UI and reports later and you'd have to migrate away from it.
4. Backfill `company_id` only if existing rows are genuinely customer data. If it's fixture/seed data, treat it as such.

**Phase 1 — Auth without enforcement**
5. Enable Supabase Auth. Add the `handle_new_user` trigger. Create accounts for the founders; backfill `users` + `memberships`.
6. **Do not enable RLS yet.** The schema supports tenancy but nothing enforces it, so the current founder-operated workflow keeps working unchanged.
7. Update the backend to require a JWT on new/updated endpoints, **feature-flagged per route**, threading claims per §1.4 — with RLS still off. This is where you find every "assumed there's one tenant" bug *before* RLS makes them fail silently in front of users.

**Phase 2 — Contract**
8. Backfill 100%; verify `count(*) where company_id is null = 0` per table.
9. `SET NOT NULL` — on a large table via `CHECK (... IS NOT NULL) NOT VALID` then `VALIDATE CONSTRAINT` separately, to avoid a long lock.
10. Write and pgTAP-test policies against the real schema in a Supabase branch **before** `ENABLE ROW LEVEL SECURITY`.
11. Enable RLS + `FORCE ROW LEVEL SECURITY` table by table, verifying after each.

---

## 3. Onboarding

### 3.1 Two Supabase limits that will silently block launch

- **Supabase's built-in email service is capped at 2 emails/hour.** Hard limit. This alone forces custom SMTP or the Auth Hook before you can launch, independent of Resend.
- **Custom SMTP does not remove Supabase-side throttling** — it raises the default to **30/hour**, still dashboard-configurable. Teams assume SMTP removes all limits. It doesn't.

Other current defaults: OTP validity 1 hour · resend cooldown 60s per address · 360 OTP requests/hour.

### 3.2 The scanner-safe magic link

> **SUPERSEDED 2026-08-07 — see LIC-T13.** We ship **email OTP only**: no clickable link, and so no
> interstitial and no PKCE callback. Both defences below exist only to protect a *link* — the
> interstitial from prefetch consumption, §3.3 from the browser-bound `code_verifier`. Neither
> failure mode survives removing the link, so neither is built.
>
> §3.2–3.3 are kept as the reasoning record, not the plan. Read them before proposing a magic link
> again: they are why the link is expensive, and they become live again the moment one is added.
> What still applies from here: `/auth/confirm` idempotency (Supabase does not support
> multi-redemption), and the email-change token-swap gotcha in §3.4.

Corporate scanners (**Microsoft Defender Safe Links**, **Barracuda** are named in the Supabase issues; Proofpoint/Mimecast run the same class of defense) prefetch emailed URLs and burn single-use tokens. The user then sees "invalid or expired" with no explanation.

**Supabase's official position** ([auth#1214](https://github.com/supabase/auth/issues/1214)): they won't fix `/verify`; build your own flow with `{{ .TokenHash }}` + a custom confirm page + `verifyOtp()`. Their own [email template docs](https://supabase.com/docs/guides/auth/auth-email-templates) recommend "a page where they can click a button to confirm the action."

**PKCE does not fix this.** PKCE protects against third-party code interception; a scanner prefetching the email link *is* the first requester. The fix is architectural.

The email links to **your own page**, which does nothing on load:

```html
<a href="{{ .SiteURL }}/auth/verify-interstitial?token_hash={{ .TokenHash }}&type={{ .Type }}&next=/report/claim">
  Confirm email
</a>
```

```tsx
// app/auth/verify-interstitial/page.tsx — no useEffect, no auto-redirect
export default function VerifyInterstitial({ searchParams }: {
  searchParams: { token_hash?: string; type?: string; next?: string }
}) {
  const { token_hash, type, next } = searchParams;
  if (!token_hash || !type) return <p>This link is invalid or has already been used.</p>;
  return (
    <form action="/auth/confirm" method="GET">
      <input type="hidden" name="token_hash" value={token_hash} />
      <input type="hidden" name="type" value={type} />
      <input type="hidden" name="next" value={next ?? '/'} />
      <button type="submit">Confirm email address</button>
    </form>
  );
}
```

A scanner hitting the interstitial just renders static HTML — Supabase is never called, nothing is consumed. `/auth/confirm` (which does call `verifyOtp`) is only ever reached by a real click.

> **No `useEffect` that auto-submits.** That just moves the problem into JS — which dumb scanners skip but headless-browser scanners execute.

Add scanner-UA logging (`Microsoft Defender`, `SafeLinks`, `Barracuda`, `Mimecast`, `proofpoint`, `GoogleImageProxy`) as **detection only**, never as a gate — UA strings are trivially spoofed.

**Supabase does not support multi-redemption** of a `token_hash`. Make your *own* confirm route idempotent instead: stamp `emailVerifiedAt` on success and treat "already verified" as success even if a second click hits a consumed token.

### 3.3 The PKCE same-device trap

The PKCE code is valid 5 minutes, single-use, and **must be exchanged on the same browser that started the flow** (the `code_verifier` lives in that browser's storage). Request on laptop, open email on phone → exchange fails.

**Always ship a visible "or enter the 6-digit code instead" fallback.** An OTP typed by a human is device-agnostic *and* immune to prefetch consumption.

### 3.4 Resend: use the Auth Hook, not SMTP

| | Custom SMTP | Send Email Auth Hook |
|---|---|---|
| Setup | 5 min, dashboard only | Deploy an edge function |
| Templates | Stuck with Supabase's Go templates | Full control — React Email, conditionals, attachments |
| Supabase throttle | Still applies (30/hr default) | Bypassed for transport |

Use the hook. The original argument — the flow *requires* a custom interstitial link — died with LIC-T13, but the conclusion did not: branded report emails still need full template control, and the throttle bypass is the reason launch isn't capped at 30/hr. Resend's own docs steer Supabase users this way.

```ts
// supabase/functions/send-email/index.ts
import { Webhook } from 'https://esm.sh/standardwebhooks@1.0.0';
import { Resend } from 'npm:resend';

const resend = new Resend(Deno.env.get('RESEND_API_KEY'));
const hookSecret = Deno.env.get('SEND_EMAIL_HOOK_SECRET')!.replace('v1,whsec_', '');

Deno.serve(async (req) => {
  const payload = await req.text();
  const wh = new Webhook(hookSecret);
  try {
    const { user, email_data } = wh.verify(payload, Object.fromEntries(req.headers)) as any;
    // LIC-T13: send the CODE, never a link. `email_data.token` is the 6-digit OTP;
    // `token_hash` is the link half and must not be turned into a URL here.
    await resend.emails.send({ from: '…', to: [user.email], subject: 'Your sign-in code',
                               react: SignInCode({ code: email_data.token }) });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), { status: 401 });
  }
  return new Response('{}', { status: 200 });
});
```

Deploy with `--no-verify-jwt`, wire in Dashboard → Auth → Hooks.

> **Email-change edge case:** with Secure Email Change on, the *current* address gets `token` + `token_hash_new` and the *new* address gets `token_new` + `token_hash`. The fields are swapped for backward compatibility. Copy-pasting a naive template sends each address the other's token.

Note the Auth Hook bypasses SMTP throttling but **not** the upstream `/auth/v1/otp` limits (60s cooldown, 360/hr) — those fire before your hook runs.

### 3.5 DNS

Dedicated subdomain (`mail.yourdomain.com`) so a reputation hit never touches your primary domain's mail.

| Type | Host | Purpose |
|---|---|---|
| TXT (SPF) | `mail.yourdomain.com` | Authorizes Resend's IPs |
| **MX** | same host | Routes bounce/complaint feedback back to Resend — **required**, not optional |
| TXT (DKIM) | `resend._domainkey.mail.…` | 1024-bit (Resend's choice; RFC 8301-compliant, accepted everywhere) |
| TXT (DMARC) | `_dmarc.…` | `v=DMARC1; p=none; rua=mailto:…` |

Rollout: `p=none` → verify `dmarc=pass` across all senders → `p=quarantine` → `p=reject`.

Keep this subdomain's SPF **Resend-only** — each `include:` is a DNS lookup and SPF fails closed past 10.

**Warm-up** (Resend's published schedule): day 1: 150 · day 2: 250 · day 3: 400 · day 4: 700 (50/hr) · day 5: 1,000 (75/hr) · day 6: 1,500 (100/hr) · day 7: 2,000 (150/hr). Keep bounces <4%, complaints <0.08%. At 2–3 emails per prospect this is generous.

Bulk-sender rules (>5,000/day to Gmail) don't bind you yet, but SPF/DKIM/DMARC correctness still drives placement — compliant senders average **89% inbox placement vs 22–34%** for non-compliant. Test with mail-tester before real reports.

### 3.6 Report links: DB token table

| Option | Revocable? | Notes |
|---|---|---|
| Supabase Storage `createSignedUrl` | **No** — "contact Supabase support" | Fine for the file, bad as the access-control primitive |
| Stateless HMAC | Only by rotating the secret (kills all links) | Cheap, but no per-link kill switch |
| Short-lived JWT | Needs a denylist anyway → reduces to a token table | No advantage |
| **DB token table** | **Yes** — flip `revoked_at` | Queryable audit trail of who viewed what, when |

For an audit product, the token table is the only option that gives an actual access log and per-link revocation.

```sql
create table report_access_tokens (
  id            uuid primary key default gen_random_uuid(),
  token         text unique not null,          -- randomBytes(32).toString('base64url')
  report_id     uuid not null references reports(id),
  company_id    uuid not null references companies(id),
  expires_at    timestamptz not null,
  revoked_at    timestamptz,
  first_viewed_at timestamptz,
  view_count    int not null default 0
);
```

Security details that matter for a confidential report:
- **Referrer leakage** — set `Referrer-Policy: no-referrer` on the report route and avoid third-party embeds. Otherwise the token goes to any CDN/analytics origin in the `Referer` header.
- **Browser history** — exchange the URL token for an httpOnly cookie on first load, then `history.replaceState()` to a clean URL, so the URL alone stops being a working credential.
- **Indexing** — `X-Robots-Tag: noindex, nofollow, noarchive` header *and* a `<meta name="robots">` tag (different crawlers respect different ones), plus `Disallow:` in robots.txt as courtesy.
- **Forwarding** — accepted behavior within the window; that's the point of no-login access. Bound the blast radius with a 7–14 day expiry and a revoke button once they claim an account.

### 3.7 Abuse gates, ordered cheapest-first

1. **Cloudflare Turnstile** on the form. Managed/invisible mode, doesn't require routing traffic through Cloudflare's CDN, and doesn't harvest for ad retargeting the way reCAPTCHA does. Verify server-side before touching the DB.
2. **Per-IP + per-domain rate limit** (Upstash Redis sliding window) before the cheap micro-audit — it still costs tokens.
3. **Disposable-domain hard block; free-consumer-email soft flag.** Nobody legitimately signs up from `tempmail.com`, but ~55% of B2B professionals use personal email on lead forms. Blocking gmail.com bounces real buyers.
4. **The expensive audit is enqueued only from the server-side email-confirmation success handler** — never from a client-triggered call. Then even a client bypassing every UI check can't cause spend without proving inbox control.

### 3.8 Queue and status

**Queue: `arq`.** Asyncio-native (same `async def` mental model as FastAPI, no Celery context-switch), automatic retries, ~700 LOC — both founders can read the whole library in an afternoon. It needs Redis, which you already have from §3.7 rate limiting.

> Gotcha: arq needs a real TCP Redis connection (`redis://`), while Upstash's serverless-flagship is the HTTP REST API. Confirm your plan exposes a TCP endpoint before assuming one instance serves both.

If you'd rather avoid Redis entirely, `pgmq` + `pg_cron` on Supabase Postgres is legitimate — budget more of your own worker/monitoring code.

**Status: plain polling**, 3–5s. It's the only option that needs zero extra infrastructure, works for unauthenticated visitors by construction, and is trivially resumable from an emailed link. Supabase Realtime requires an authorization carve-out for anonymous subscribers; SSE fights serverless execution limits; WebSockets are a full infrastructure commitment for one-directional "is it done yet."

Notification on completion is fire-and-forget — never fail the job because an email bounced.

---

## 4. White-label

### 4.1 Theming: server-rendered CSS variables

```tsx
// app/layout.tsx — server component, no FOUC, no hydration race
const tenant = await getTenantByHost((await headers()).get('host')!);
return (
  <html style={{ '--brand': tenant.accentHsl,
                 '--brand-foreground': tenant.fgHsl } as React.CSSProperties}>
```

Tailwind references the variable, holding only the H/S/L triplet so the alpha modifier still works:

```js
colors: { brand: { DEFAULT: 'hsl(var(--brand) / <alpha-value>)' } }
```

Then `bg-brand`, `bg-brand/10`, `text-brand-foreground` all work with a runtime tenant color and no rebuild.

> **Don't inject tenant branding via `useEffect` + `setProperty`.** It works on the live site but introduces a client-JS timing race in the PDF path — one more async signal the capture has to wait on. Server-render it into the first HTML Chromium parses.

Cache the hostname→tenant lookup (Edge Config or short-TTL) — don't hit the DB per request.

### 4.2 Accessible color from one hex

Don't threshold luminance at 0.5 — that can pick the *lower*-contrast option near the boundary. Compute both ratios and take the winner:

```ts
export function pickForeground(brandHex: string): string {
  const bg = relLuminance(hexToRgb(brandHex));
  return contrastRatio(bg, 1.0) >= contrastRatio(bg, 0.0) ? '#ffffff' : '#0a0a0a';
}
```

WCAG AA is 4.5:1 normal text, 3:1 large text/UI. **Check contrast at onboarding, when the agency enters their hex** — warn or auto-adjust rather than trusting the input.

For a brand color unusable as a background (pale yellow, near-white): use the raw hex for small accents only, and generate a darkened variant for large surfaces by mixing toward black **in OKLCH** until it clears 4.5:1. OKLCH gives perceptually even ramps; RGB/HSL mixing produces muddy mid-tones. `culori` ships `wcagLuminance`, `wcagContrast`, `interpolate` and `samples`.

### 4.3 Logo upload

**An uploaded SVG is XML and can carry `<script>`, `on*` handlers, `<foreignObject>`, or external `xlink:href` references.** If rendered inline, it executes in your origin. Two independent mitigations, use both:

1. **Sanitize server-side** with DOMPurify + jsdom, `USE_PROFILES: { svg: true, svgFilters: true }`, forbidding `script`/`foreignObject`.
2. **Serve via `<img src>`, never inline** — browsers don't execute script in image-context SVG, so this survives a sanitizer gap. Serve from a cookieless subdomain/CDN path.

Normalize on ingest, not at render: bound raster logos to a max box with `sharp` (`fit: 'inside'`, preserve transparency, strip EXIF), reject aspect ratios outside ~1:4–4:1, enforce size/MIME at the bucket level too.

Store **two variants** (`logo_light`, `logo_dark`). A black-on-transparent PNG disappears on a dark header. If only one exists, render it in a white rounded chip on backgrounds that would kill contrast. **Fallback with no logo at all: a generated initials badge** using the §4.2 contrast logic — no upload needed, never a broken-image icon in a client-facing PDF.

### 4.4 Custom domains

For one agency partner, **use Vercel's Domains API directly** — free within your plan, no new vendor.

```ts
await projectsAddProjectDomain(vercel, {
  idOrName: PROJECT, teamId: TEAM, requestBody: { name: 'reports.agency.com' },
});
```

**DNS instructions for the agency:** CNAME `reports.agency.com` → `cname.vercel-dns.com`. If the domain was ever attached to another Vercel project, a TXT at `_vercel.reports.agency.com` proves ownership. SSL auto-provisions in **5–10 minutes** after DNS resolves; worst-case global propagation 24–48 hours. Failure modes: CAA records blocking Let's Encrypt, stale TXT from a previous attempt.

Skip wildcards (they require moving nameservers to Vercel). Approximated ($0.20/domain/mo, $20 minimum) and Cloudflare for SaaS are the escalation paths if you outgrow Vercel's domain UX — not justified for one partner.

Middleware rewrites hostname → tenant path; resolve via cached lookup, not a raw DB hit per request.

---

## 5. Billing

### 5.1 Stripe Invoicing, not Billing

For 1–3 B2B accounts at $750–4,000/mo with net-30, manually-triggered or lightly-scripted invoices beat subscription machinery.

```ts
const invoice = await stripe.invoices.create({
  customer: customerId,
  collection_method: 'send_invoice',   // NOT charge_automatically
  days_until_due: 30,
});
await stripe.invoiceItems.create({ customer: customerId, invoice: invoice.id,
  description: `Platform fee — includes ${slots} client slots`,
  price: process.env.STRIPE_PRICE_PLATFORM_FEE });
if (overage > 0) {
  await stripe.invoiceItems.create({ customer: customerId, invoice: invoice.id,
    description: `Overage — ${overage} additional client slot(s)`,
    quantity: overage, price: process.env.STRIPE_PRICE_OVERAGE_SLOT });
}
await stripe.invoices.finalizeInvoice(invoice.id);
await stripe.invoices.sendInvoice(invoice.id);
```

A monthly cron reading slot counts from your own table and calling this is less code and more auditable than wiring subscription items + metered prices for one customer.

**Don't automate metered overage yet.** Computing it yourself and adding a line item is less work than integrating the meter-events pipeline end to end.

**Stripe's usage API changed:** `subscriptionItems.createUsageRecord` is legacy; current is **Billing Meters** (`/v1/billing/meter_events`). Events process asynchronously, timestamps must be within 35 days past / 5 minutes future. Stripe now recommends Metronome for new high-volume metering — all irrelevant at your scale, but know the old API is the wrong one if you copy an older tutorial.

**Tax:** don't enable collection. Most US states' economic nexus thresholds are ~$100k or 200 transactions per state per year, and B2B SaaS is often not taxable at all. Do enable Stripe Tax's free **threshold monitoring** as an early warning. Consult an advisor before multi-state.

### 5.2 Usage snapshots

Snapshot slot counts at invoice time — don't rely on live counts later for what you already billed.

```sql
create table usage_snapshots (
  agency_id      uuid not null,
  period_start   date not null,
  included_slots int not null,
  active_slots   int not null,
  overage_slots  int generated always as (greatest(active_slots - included_slots, 0)) stored,
  invoice_id     text,
  unique (agency_id, period_start)
);
```

This row *is* the reconciliation record. "We were told 10 slots but got billed for 13" is answered by querying it, not by re-deriving from a live table that has since changed.

**Enforcement: soft warning, not hard block.** Blocking slot creation risks blocking your customer's business — and your revenue — over a billing technicality. Show a banner, reconcile at invoice time.

### 5.3 Entitlements

**Anti-pattern:** `if (agency.plan === 'pro')` scattered through handlers. Adding a plan, renaming one, or giving one agency a custom limit ("just for them, 15 slots") means hunting every check.

```ts
export const PLAN_ENTITLEMENTS: Record<string, Entitlements> = {
  agency:    { clientSlots: 10, customDomain: true,  whiteLabelLogo: true,  apiAccess: false },
  agencyPro: { clientSlots: 25, customDomain: true,  whiteLabelLogo: true,  apiAccess: true  },
};

export function resolveEntitlements(planId: string, overrides: Partial<Entitlements> = {}) {
  return { ...PLAN_ENTITLEMENTS[planId], ...overrides };
}
```

Store `plan_id` + a nullable `entitlement_overrides jsonb` on the account row — that's how you handle a negotiated deal without inventing a plan name. Check by *capability*, never by plan name. The frontend gate is UX only; the API-boundary check is the security boundary.

---

## 6. Build order

**Now (with the packaging work, not after it)**
1. `memberships` join table. §0. One table, whole insurance policy.

**When self-serve becomes real**
2. Schema + RLS with `security definer` + `(select auth.uid())` + `FORCE ROW LEVEL SECURITY` (§1)
3. pgTAP + integration isolation tests that **assert emptiness** (§1.6)
4. Migration Phases 0→2, RLS enabled last (§2)
5. Resend Auth Hook + DNS + warm-up (§3.4–3.5) — **and raise the Supabase rate limit off 30/hr**
6. Code-only sign-in — OTP, no link, no interstitial (LIC-T13; supersedes §3.2–3.3)
7. Turnstile + rate limits + confirm-gated enqueue (§3.7)
8. arq + polling status (§3.8)
9. Report token table with revocation (§3.6)

**When the agency deal is real**
10. Server-rendered CSS-variable theming + contrast checking (§4.1–4.2)
11. Logo upload with SVG sanitization (§4.3)
12. Stripe Invoicing + usage snapshots + entitlements map (§5)
13. Custom domain via Vercel API (§4.4)

**Not yet:** client-viewer logins (share links first) · JWT custom claims (DB-authoritative RLS is simpler and has no staleness gap) · Stripe Billing subscriptions · metered usage API · Cloudflare for SaaS.

---

## 7. Things to re-verify before shipping

Fast-moving, and the research flagged each explicitly:

- **Asymmetric JWT signing keys** (2025 rollout) changed backend verification from `getUser()` to `getClaims()`. Confirm your project migrated before building the FastAPI verification path.
- **`@supabase/auth-helpers-nextjs` is deprecated** relative to `@supabase/ssr`. Check for stale imports.
- **No first-party way to force-refresh JWT claims mid-session** — re-check the changelog.
- **Vercel's apex A-record IP** — read it from the dashboard, don't hardcode from a blog.
- **Supabase Storage bucket-level `file_size_limit`/`allowed_mime_types` parameter names** in the current JS SDK.
- **US state economic-nexus thresholds** — vary by state and change. Advisor, not a blog post.

---

## 8. Sources

**Supabase & RLS** — [RLS performance and best practices](https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv) · [Database advisors](https://supabase.com/docs/guides/database/database-advisors?lint=0013_rls_disabled_in_public) · [Makerkit RLS best practices](https://makerkit.dev/blog/tutorials/supabase-rls-best-practices) · [The auth.uid() init-plan trap](https://dev.to/arvavit/76-rls-policies-rewritten-in-one-migration-the-authuid-init-plan-trap-in-supabase-4hg) · [Postgres RLS footguns](https://www.bytebase.com/blog/postgres-row-level-security-footguns/) · [PgBouncer transaction pooling for multi-tenant SaaS](https://multi-tenant-saas.com/tenant-aware-data-routing-query-scoping/connection-pooling-in-multi-tenant-systems/pgbouncer-transaction-pooling-for-multi-tenant-saas/) · [Expand and contract pattern](https://www.prisma.io/dataguide/types/relational/expand-and-contract-pattern) · [WorkOS multi-tenant architecture](https://workos.com/blog/developers-guide-saas-multi-tenant-architecture) · [WorkOS session management](https://workos.com/blog/multi-tenant-session-management)

**Auth & onboarding** — [Passwordless email logins](https://supabase.com/docs/guides/auth/auth-email-passwordless) · [Email templates](https://supabase.com/docs/guides/auth/auth-email-templates) · [PKCE flow](https://supabase.com/docs/guides/auth/sessions/pkce-flow) · [Server-side auth for Next.js](https://supabase.com/docs/guides/auth/server-side/nextjs) · [Production checklist](https://supabase.com/docs/guides/deployment/going-into-prod) · [Custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp) · [Send Email Auth Hook](https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook) · [Magic links invalidated by scanners](https://github.com/supabase/auth/issues/1214) · [Same issue, discussion](https://github.com/orgs/supabase/discussions/41618) · [Nhost: protect magic links from email clients](https://nhost.io/blog/protect-magic-links-from-email-clients) · [Resend + Supabase](https://resend.com/docs/knowledge-base/getting-started-with-resend-and-supabase.md) · [Resend DMARC](https://resend.com/docs/dashboard/domains/dmarc.md) · [Resend warm-up](https://resend.com/docs/knowledge-base/warming-up.md) · [Google bulk sender guidelines](https://support.google.com/mail/answer/81126) · [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/) · [arq](https://arq-docs.helpmanual.io/) · [pgmq](https://github.com/tembo-io/pgmq) · [Supabase Realtime broadcast](https://supabase.com/docs/guides/realtime/broadcast)

**White-label** — [Vercel multi-tenant reference](https://vercel.com/docs/platforms/multi-tenant-platforms/reference) · [Vercel multi-tenant concepts](https://vercel.com/docs/platforms/multi-tenant-platforms/concepts) · [Next.js multi-tenant guide](https://nextjs.org/docs/app/guides/multi-tenant) · [WCAG G18 contrast formula](https://www.w3.org/TR/WCAG20-TECHS/G18.html) · [culori API](https://culorijs.org/api/) · [DOMPurify](https://github.com/cure53/dompurify) · [SVG upload XSS advisory](https://github.com/shopware/shopware/security/advisories/GHSA-xvhc-gm7j-mhmc) · [Supabase Storage access control](https://supabase.com/docs/guides/storage/security/access-control) · [Approximated](https://www.approximated.app/) · [Cloudflare for SaaS](https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/)

**Billing** — [Stripe invoicing integration](https://docs.stripe.com/invoicing/integration) · [Subscription prorations](https://docs.stripe.com/billing/subscriptions/prorations) · [Usage recording API (Billing Meters)](https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage-api) · [Stripe Tax](https://docs.stripe.com/tax) · [Customer portal](https://docs.stripe.com/customer-management)

---

*Compiled 2026-08-01 from 4 implementation-research agents. Not legal or tax advice. Vendor APIs and limits move — re-verify §7 before shipping.*
