# Packaging the Prompt Runner for Self-Serve + Agency Licensing — Research

**Compiled:** 2026-08-01
**Method:** 5 parallel research agents (~350 sources) + a read of the WagerU schema
**Inputs:** the Josh/Abhi iMessage thread on licensing and packaging; `/Users/abhinavjinka/Documents/WagerU`
**Status:** research only. No code changed.
**Companion:** `docs/audit-packaging-research.md` (what goes *in* the report) and `docs/audit-packaging-spec.md` (how to build it). This file is about *who logs in, what they can see, and who pays for it.*

> **Naming note:** "WagerU" below always means the prediction-market repo being used as an architectural reference. The GEO product is referred to as the prompt runner / the audit tool.

---

## 0. The four things that actually matter

Everything below expands on these.

1. **You do not need an account system to sign a white-label deal.** Deal shape (whose brand, who bills, who owns the client) is a *contract* question. Multi-tenant software is an *execution* question. They can be a quarter apart. This is the single biggest unlock for the meeting — it means "we have no login yet" is not a reason to delay the conversation, only a reason to be precise about what you promise.

2. **Abhi's "agency = N companies" is half-right, and the wrong half is the expensive half.** True: once the object model is right, adding a tenant is an INSERT. False: WagerU's model can be extended into it later. WagerU has `User.schoolId` as a **scalar foreign key** — one user, exactly one tenant, forever. The agency case needs one user across many companies. That's a join table, not a column, and it is not a cheap retrofit. **Cost to do it right now: one extra table. Cost to retrofit later: auth, session, and every permission check.**

3. **Josh's onboarding flow has one part that should be dropped outright** — the emailed temporary password. NIST SP 800-63B Rev. 4 effectively deprecates it, password fields have the worst abandonment rate of any field type (10.5%), and emailing the credential and the report to the same inbox violates the separate-channel principle by construction. The rest of the flow is sound.

4. **Report white-label is cheap and is what agencies actually want. App white-label is expensive and largely isn't asked for.** Every agency complaint found was about the artifact the *client* sees — the PDF cover page, the email sender, the logo. Not one was about the login screen. Build the first, defer the second.

---

## 1. What the thread actually proposes, and the verdict on each piece

| Proposal (from the thread) | Verdict | Why |
|---|---|---|
| "Introduce the software as a whole, then licensing/pricing" (Josh, meeting structure) | **Keep** | Matches how agencies evaluate: capability first, then commercial. |
| "Account system and hierarchy — create businesses, then managers who can register and monitor their companies" (Abhi) | **Right shape, wrong primitive** | The hierarchy is correct (agency → companies). But it must be built on a memberships join table, not WagerU's scalar FK. See §3. |
| "Like WagerU except tiered permissions based on the user" (Abhi) | **Half-transferable** | The tenant-column + middleware + platform-admin-bypass pattern transfers well. `User.role` and `User.schoolId` do not — role must move to the membership row. See §3.3. |
| "Might be pretty big, so focus on that" (Josh) | **Correct instinct** | It is big — but only one piece of it is big *and* urgent. See §7. |
| "Have the licensing be the add-on, we can still pitch the service" (Josh) | **Strongly correct** | This is finding #1. Sell the deal shape now, deliver manually, build behind it. |
| "Ignore licensing/organizational, first package for individual businesses" (Abhi) | **Right for product, dangerous for schema** | Correct sequencing for reports, billing, UI. Wrong if it means shipping a single-tenant identity model. |
| "Once it's done for one, agency packaging only differs in the number of registered companies" (Abhi) | **True only if the membership layer is many-to-many from day one** | This is the load-bearing caveat. Free to add now. |
| "Sign up for initial audit → completed → sent by email with temporary login credential → create a profile" (Josh) | **Change three things** | Drop the temp password; add an instant partial result before the wait; use a hardened magic link. See §4. |
| "It'd just be a search results audit, not a full mention/website audit" (Josh) | **Good scoping** | Keeps the self-serve product cheap to run and fast to deliver. The full audit stays the premium/manual tier. |

---

## 2. The commercial question: what deal to propose

### 2.1 The four shapes, ranked for *this* team

| Shape | Who owns the client | Engineering needed from a no-account-system app | Time to first dollar |
|---|---|---|---|
| **Referral / affiliate** | Ambiguous | Near zero | Days |
| **Reseller (manual delivery behind the scenes)** | Agency | **Near zero** — it's a contract, you keep running it by hand | **Days–weeks** |
| **Reseller (self-serve)** | Agency | High — multi-tenancy, sub-accounts, metering | Months |
| **White-label (self-serve)** | Agency | Highest — all of the above plus branding layer, custom domains | Months+ |
| **True OEM (they run your code)** | Agency | Medium but wrong-shaped — packaging, docs, supporting *their* engineers | Not worth it pre-PMF |

**The insight that collapses the timeline:** rows 2 and 4 differ in *engineering*, not in *commercial terms*. You can sign white-label commercial terms — their brand on the report, they own the client, they invoice — and deliver it as a manually-run service for 60–90 days. The agency gets what they want; you get revenue funding the build instead of speculative engineering.

### 2.2 Proposed term sheet

| Term | Proposal |
|---|---|
| **Structure** | Founding-partner white-label agreement, 90-day paid pilot |
| **Fee** | Flat platform fee covering ~5 client brands. See §5 for the number. |
| **Overage** | Flat per-additional-brand fee |
| **Included** | White-labeled reports (their logo, no vendor branding), the audit run on their behalf, Tier-2 technical support **to the agency** |
| **Explicitly NOT included** | Self-serve login (doesn't exist); sub-2-business-day SLA; direct vendor↔their-client contact; any guarantee of specific visibility outcomes |
| **Term** | 90-day pilot → auto-converts to 12 months unless either side gives 30 days' notice |
| **Exclusivity** | **None.** Offer instead: 90-day right of first refusal in their metro/vertical + founding-partner rate locked 12 months |
| **Non-solicit** | Mutual |
| **Exit** | They keep every report already delivered; 30-day transition window |
| **Support** | Agency = Tier 1 (all client-facing); you = Tier 2 (agency-facing only), 2 business days during pilot |

### 2.3 The traps, ranked

1. **"Just give us exclusivity in our vertical and we're good."** The most dangerous sentence available in the meeting. One founder's public account puts a single blanket exclusivity grant at ~$180K/year in foregone business. If you must concede something: time-boxed, named-competitor-scoped, tied to a volume commitment, paid for with a longer term. Otherwise: ROFR only.
2. **"Can we just talk to your engineers directly whenever?"** The documented reseller failure mode is the vendor getting pulled into every one of the partner's client meetings. Agency is Tier 1, escalation is scheduled, not ad hoc.
3. **"We'll pay once we've resold a few clients."** They're asking to validate demand on your engineering time. Payment up front — even discounted — is the actual signal.
4. **Verbally promising self-serve login "soon."** Put "manual delivery during pilot, self-serve roadmap non-binding" in writing before it becomes an expectation you can't retract.
5. **Letting this become >30% of revenue.** Past ~30% concentration, renewal leverage inverts and the partner starts extracting price concessions because you can't afford to lose them. Keep pursuing direct clients in parallel.
6. **Silence on "this number looks wrong."** Inevitable with LLM-sourced data. Needs a contractual answer *before* the first client escalation. See §6.2.

### 2.4 What to say, and not say, on the call

**Say:**
- "We can run this for your clients under your brand within [X weeks] as a paid pilot — we deliver, you own the client."
- "We're not doing exclusivity today, but we'll lock founding-partner pricing and give you first refusal on other agencies in your space."
- "During the pilot it's white-labeled but manually delivered. Self-serve login is on the roadmap, not a dated promise."
- "It needs to be a real commercial engagement, even a modest one — that's what tells us it's worth building the next version around your workflow."

**Don't commit to:** a ship date for self-serve; any seat/sub-account count; exclusivity even informally; a same-day support SLA; direct access for their clients; revenue share (you can't audit their billing).

---

## 3. The architecture question: what to actually build

### 3.1 What WagerU does, precisely

Read from the schema and middleware:

- `School` is the tenant. Every domain model carries `schoolId`.
- **`User.schoolId` is a scalar FK** — a user belongs to exactly one school.
- Three flat roles on the user row: `USER` / `OPERATOR` / `PLATFORM_ADMIN`.
- Tenant resolved per-request from subdomain or `X-School-Slug` header → `req.context.schoolId`; mismatches rejected; `PLATFORM_ADMIN` bypasses isolation.
- A hardcoded bypass-prefix list for auth routes that self-determine their school.
- No database-level RLS — isolation is enforced by application code remembering `where: { schoolId }` every time (which is exactly why `CLAUDE.md` has to state it as a hard rule).

**What transfers:** the tenant-column pattern, middleware-resolved context, the platform-admin bypass, the bypass-prefix concept.
**What doesn't:** `User.schoolId` as a scalar, and `role` living on the user row.

### 3.2 Why the scalar FK is the whole problem

An agency analyst works across 12 client companies. A person can be an agency manager on 5 companies and a viewer on a 6th. Under `User.schoolId`, both are structurally impossible — not hard, impossible.

The industry-standard shape is universal across WorkOS, Auth0, Clerk, and the multi-tenant data-modeling literature: **User (global identity) ↔ Membership (carries the role) ↔ Tenant.** Auth0 documents it as a decision made *at the start* — "users isolated by organization" vs "users shared between organizations" — and retrofitting means bolting on a second model, not tweaking the first.

**Cheap vs expensive in a retrofit:**

| Cheap (hours) | Expensive (days–weeks, and risky) |
|---|---|
| Adding tenant rows | `User.orgId` scalar → `Membership` table (touches every `req.user.orgId`) |
| Adding columns | Every query's scope: "the user's one org" → "the user's *selected* org" |
| Copying a UI screen | Session/JWT redesign: identity vs **active org** as separate state |
| A second Stripe customer | Every permission check that reads role off `User` instead of `Membership` |
| | Emailed report links and bookmarks that encoded org implicitly |
| | Zero-downtime expand/backfill/contract migration on live customer data |

> **The cheap insurance policy, in one sentence:** put the org id on a `memberships` table from day one even if every user has exactly one membership in v1. It costs one table and one join in the auth middleware now. It is the single change that makes "agency = N companies" a true statement instead of a false one.

Everything else in Abhi's plan — reports, scoring, PDF, billing scoped to one company — is correct sequencing and should proceed exactly as he proposed.

### 3.3 Recommended data model

Serves one standalone company on day one (no `organizations` row exists — the agency layer is simply unused) and an agency later with **zero schema change**.

```sql
create table organizations (            -- an AGENCY. Absent for solo companies.
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  created_at timestamptz default now()
);

create table companies (                -- the audited brand; the paying tenant
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  managing_agency_id uuid references organizations(id),  -- NULLABLE + reassignable
  created_at timestamptz default now()
);

create table users (                    -- global identity; id = supabase auth.users.id
  id uuid primary key,
  email text unique not null,
  is_platform_admin boolean not null default false,   -- the two founders
  created_at timestamptz default now()
);

create table memberships (              -- THE table that makes "agency = N companies" true
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id),
  organization_id uuid references organizations(id),
  company_id uuid references companies(id),
  role text not null,
  invited_by uuid references users(id),
  invited_at timestamptz,
  accepted_at timestamptz,
  check ((organization_id is not null and company_id is null)
      or (organization_id is null and company_id is not null)),
  unique (user_id, organization_id),
  unique (user_id, company_id)
);

create table report_shares (            -- build this BEFORE client logins
  id uuid primary key default gen_random_uuid(),
  report_id uuid not null references reports(id),
  token text unique not null,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_by uuid references users(id)
);
```

Domain tables carry `company_id`, never `organization_id` — a report is always about a specific company, agency-managed or not.

**One access function, both paths:**

```sql
create or replace function has_company_access(target_company_id uuid)
returns boolean language sql security definer as $$
  select exists (
    select 1 from memberships m
    where m.user_id = (select auth.uid())
      and ( m.company_id = target_company_id
         or m.organization_id = (select managing_agency_id
                                 from companies where id = target_company_id) )
  );
$$;
```

**Note `managing_agency_id` is nullable and reassignable, not an ownership hierarchy.** This matters commercially: when a client leaves the agency and wants to go direct, it's one UPDATE plus a membership grant. AgencyAnalytics — the market leader — apparently can't do this; their own docs say transferring a client between accounts requires manually recreating dashboards, reports and users because they "cannot be exported." Getting this right costs nothing now and is a genuine differentiator later.

### 3.4 Role matrix

Role lives on `memberships.role`, scoped per relationship. Flat roles-on-user do not survive two levels of hierarchy — "OPERATOR of *what*?" becomes ambiguous the moment a second membership exists.

| Role | Scoped to | Can |
|---|---|---|
| `PLATFORM_ADMIN` | Global flag on the user row (genuinely cross-tenant, same as WagerU) | Everything, all tenants, support/impersonation |
| `AGENCY_OWNER` | Agency | Billing, add/remove staff, add/remove/reparent companies, all client data |
| `AGENCY_MANAGER` | Agency | Run audits, manage assigned companies, invite client viewers. No billing, no staff removal |
| `COMPANY_ADMIN` | Company | Full control of that one company, manage its users, see all its reports |
| `COMPANY_VIEWER` | Company | Read-only report access |
| `BILLING_ONLY` | Either | Invoices only, no product data — for when the payer isn't the user |

Access to a company *via* an agency membership is **computed at query time**, not stored as duplicate membership rows — so reparenting a company doesn't require rewriting derived grants.

### 3.5 RBAC vs anything fancier

Plain RBAC on the membership table. Full stop. The tipping points into relationship-based access (ReBAC / OpenFGA / Zanzibar) are: creating roles faster than you hire people, access depending on runtime attributes rather than job function, or shipping user-driven ad-hoc sharing. Only the third is near you — "share this one report with this one external email" — and that's better solved with the expiring signed links in `report_shares` than by adopting an authorization engine. A two-person team does not need Zanzibar.

### 3.6 Auth: build vs buy

The decisive finding: **none of the identity vendors give you the two-level agency→client hierarchy.** Clerk, WorkOS, Auth0, PropelAuth and Stytch all provide *one* flat Organization primitive at best. You model agency→company yourself regardless of who you pay. That reduces the choice to identity plumbing — password reset, sessions, invitations — not hierarchy.

**Recommendation: stay on Supabase Auth + your own tables + Postgres RLS.** You're already on Supabase; the paid alternatives don't solve the hard part; and RLS gives you a data-layer backstop that a session-claims-only vendor doesn't.

**Revisit when:** a large agency's IT department demands SAML SSO or SCIM. At that point evaluate WorkOS specifically — its per-connection pricing means you pay ~$0 until that day, unlike MAU-priced alternatives that meter from day one.

### 3.7 Isolation: add RLS, don't repeat WagerU's approach

WagerU enforces isolation purely in application code — every Prisma call must remember `where: { schoolId }`. It works, but it has no backstop, which is why it needs a hard rule in `CLAUDE.md` and constant vigilance (including against AI coding assistants that forget it).

The literature is consistent that the #1 real-world multi-tenant bug is a missing tenant filter in ordinary application code — "most incidents stem from developers adding endpoints without `tenant_id` validation, not attackers." Since you're building from scratch:

1. **Postgres RLS as the hard backstop** — a forgotten `WHERE` cannot leak data.
2. A query wrapper that always injects the tenant filter (defense in depth).
3. CI tests asserting user A cannot see org B's rows, **per table**.

Two Supabase-specific gotchas: wrap `auth.uid()` as `(select auth.uid())` inside policies or you get per-row re-evaluation and a performance cliff at real data volume; and **RLS denies by returning zero rows, not an error** — so tests must assert emptiness, not exceptions, or a broken policy looks like "no results" and passes manual testing.

### 3.8 URL structure

Use **path prefix** (`/company/{slug}/reports/...`), not subdomains.

- Cheapest to add to the existing Next.js app; no wildcard DNS/SSL work.
- Critically: emailed report links become **self-describing**. A link to `/company/acme-co/reports/2026-07` identifies its tenant unambiguously, so it survives a user having multiple memberships, opening an old link in a different session, or forwarding it to a colleague. Session-only "active org" breaks all three.
- Never read the active org from a client-supplied header or cookie on protected routes — it must come from a signed JWT claim or server-side session, or a client can forge which org they're acting as.

Reserve subdomains for later white-label portals — that's a different ask, not tenant routing.

---

## 4. The self-serve onboarding flow

### 4.1 Recommended flow

1. **Request page** — brand name, website, work email. Auto-derive competitors and category from the site; let the user edit. **No password, no account.**
2. **Instant micro-audit (seconds)** — 1 engine × 3–4 prompts, run synchronously, shown on-page as a real number. *"ChatGPT mentioned you in 2 of 4 answers; a competitor appeared in all 4."*
3. **Confirmation** — "Your full audit is running, you'll have it by email in ~X." Release them; don't hold them on a blocking progress page.
4. **Single opt-in email verification** — fires here, *before* the expensive multi-engine run is queued. This is the abuse gate.
5. **Human review** of the first audit — which doubles as the approval queue; no separate one needed.
6. **Delivery email** from a dedicated transactional subdomain: the report via a signed expiring link (**no login required to view it**), plus a "save this and track future audits" CTA.
7. **Account created lazily** at that first claim-click — password or passkey set then, never emailed.
8. **Portal v1** — list of past audits (login-gated) + the same viewer. Nothing more.

### 4.2 The three changes to Josh's proposal

**Drop the emailed temporary password.** NIST SP 800-63B Rev. 4 requires separate-channel delivery, single use, minutes-to-hours expiry, and mandatory rotation on consumption — emailing the credential and the report to the same inbox violates the first requirement structurally. Password fields have the highest abandonment of any field type (10.5%). Real 2026 breaches trace to unrotated onboarding temp passwords.

**Add an instant partial result before the wait.** Form conversion falls steeply with perceived risk and field count (3 fields ≈ 23%, 5 ≈ 17%, 7 ≈ 11%, 10+ ≈ 7%). A form with *zero* payoff until an email arrives later is an act of faith. Every adjacent instant-audit tool (HubSpot Grader, UpGuard, SEOptimer) leads with a same-second number and gates only the *detail*. One engine × 3 prompts costs pennies and seconds.

**Harden the magic link against corporate email scanners.** This is a real and underappreciated failure mode: Microsoft Defender, Proofpoint and Mimecast **prefetch links inside emails before the human clicks**, silently burning single-use tokens. The user then sees "invalid or expired" with no explanation. Your audience — marketing and brand teams at real companies — sits behind exactly these gateways, so this is a probable first-week support ticket, not an edge case. Mitigations, in order:

1. Put the token in the URL **fragment** (`#token=...`), not the query string — fragments are never sent to the server, so a prefetching scanner can't consume them. Land on an intermediate page and require an explicit button click to redeem.
2. Allow **multiple redemption attempts** within the expiry window rather than single-use-then-dead.
3. Ignore `HEAD` requests and known scanner user-agents server-side; set `Referrer-Policy: no-referrer`.
4. Offer a **"resend as a 6-digit code"** fallback on the same page — an OTP can't be consumed by a prefetch bot because a human has to type it.

Expiry: 10–15 minutes for login; 24 hours is fine for a report-claim link (lower security stakes, fewer scanner false-negatives).

### 4.3 Form fields

Three required, one optional. Every field beyond the minimum is measurably expensive.

1. Work email (required — account key + delivery address)
2. Company/brand name (required)
3. Website URL (required — auto-derive competitors, category, starting prompt set from this)
4. Competitors (optional, pre-filled from #3, editable)

**Don't ask for:** phone (37% abandonment if not marked optional), company size, job title, industry dropdown, "how did you hear about us." Collect those progressively once they're back for audit #2.

### 4.4 Email deliverability — existential for this product

The entire product fails silently if one email lands in spam.

- Google and Microsoft moved from soft deferrals to **permanent 550-level hard rejections** for DMARC failures in November 2025. DMARCbis (RFC 9989) was published May 2026, making DMARC a Proposed Standard.
- Compliant senders average **89% inbox placement vs 22–34% for non-compliant** — a 3–7× penalty.
- You're under the 5,000/day bulk threshold so the hard-block rules don't bind you, but placement still depends on SPF/DKIM/DMARC correctness, and it costs nothing to do right on day one.
- **Send from a dedicated transactional subdomain** (`reports@mail.yourdomain.com`) with its own auth records, never a shared marketing sender.
- Keep the delivery email low-signal — plain transactional template, no urgency language, minimal links — since high-entropy token links raise spam scores.

**Provider: Resend.** Free tier 3,000/mo (100/day) likely covers you for a long time; $20/mo Pro at 50K. Best DX for a two-person team with no infra person. Postmark has the strongest deliverability reputation and is the fallback if placement problems show up in testing, but its 100/mo free tier isn't usable pre-launch. SES is cheapest at scale and the wrong choice here (sandbox approval, manual DKIM, no real support).

### 4.5 Abuse and qualification

Each full audit costs real LLM money, so the gate must sit *before* the spend.

- **Single opt-in email verification** before queueing the multi-engine run. Enough friction to stop bots, far cheaper in conversion than blocking free-email domains.
- **Per-domain rate limiting** (e.g. one free audit per company domain per 30 days).
- **Don't hard-gate on work email.** ~55% of B2B professionals use personal email on lead forms, rising sharply at small companies and among senior people who do it deliberately. A hard `@company.com` rule bounces real buyers.
- The founder review of every first audit already *is* the approval queue. Don't build a second one.

### 4.6 The uncomfortable question the login has to answer

If the report is emailed anyway, **why would anyone log in again?**

The honest answer is that they wouldn't — until there's a second audit. The account only earns its keep when it offers something a PDF in an inbox can't: trend over time, diff vs last cycle, competitor movement, raw per-prompt transcripts, re-running on demand. That is exactly what `docs/audit-packaging-research.md` says the recurring product should be.

**So: don't build the account system to gate report #1. Build it to make report #2 better than another PDF.** If that "reason to come back" isn't real yet, the login layer is premature — which is an argument for doing the recurring-report work (that spec's Phase 2) either before or alongside the account system, not after it.

---

## 5. Pricing

### 5.1 Real comparables

| Vendor | Structure | Price |
|---|---|---|
| **Peec AI** (agency plans) | Client projects, credit-based | **$10,000/yr** (3 projects) / **$25,000/yr** (10) / **$65,000/yr** (25) |
| **Profound** (agency) | Base + per client workspace | **$99/mo + $399/mo per full client workspace**; $199/mo trial workspaces |
| **Pierview** (white-label) | Flat + per additional org | **$999/mo covering 10 client orgs, +$99/mo each beyond** |
| **Otterly** | Tiers + agency partner allowances | $29 / $189 / $489 per month |
| **AthenaHQ** | Self-serve | $95/mo annual, $295/mo monthly |
| **GoHighLevel** | Flat platform fee, unlimited sub-accounts | $97 / $297 / $497 per month |
| **DashThis** | Flat by dashboard count, white-label free at every tier | $44 → $429/mo |
| **Databox** | Solutions Partner | 30% recurring commission; white-label $14/mo add-on, free at $399+ tiers |
| **Ayzeo** | White-label as an add-on | $299/mo add-on on the $149/mo Pro plan |

**The pattern:** nobody sells pure per-seat or flat-unlimited to agencies. Everyone bundles a client/project count into a tier with a ceiling, then charges overage. GEO-specific tools cluster tightly around *flat platform fee bundling N client slots + ~$99–400 per additional client*.

### 5.2 What the agency charges *their* client — your ceiling

| Source | Tier | Price |
|---|---|---|
| RevvGrowth | Basic / Growth / Enterprise GEO | $3–6k / $6–12k / $12–25k+ per month |
| AI Advantage Agency | Starter / Mid / Enterprise | $2.5–4.5k / $5–10k / $15–25k+ per month |
| AI Advantage Agency | Standalone audit | $5–15k one-time |

Back-solving from the comps: tools consume roughly **5–20% of the retainer**. Since this product delivers a periodic audit rather than continuous daily monitoring, price in the **lower half — 5–12%**. If the agency charges $2,000/month per client, **~$200/client/month is your realistic ceiling.**

### 5.3 Recommended structure and the margin math

**Tiered platform fee bundling client slots, each slot including one audit/month, with paid overage per additional audit.** Not per-seat (meaningless — the value metric is clients audited, not logins). Not revenue share (you cannot audit their billing). Not raw credits (exposes your unit cost as a negotiating target, and becomes an incomprehensible exchange-rate matrix as features grow).

| Tier | Price | Included | Overage |
|---|---|---|---|
| **Pilot** | $750/mo | 5 client slots, 1 audit each | $150/extra audit |
| **Growth** | $1,800/mo | 15 slots | $125/extra audit |
| **Scale** | $4,000/mo | 40 slots | $100/extra audit |

Against a COGS of ~$19/audit *(this was an estimate for a 100-query run; the measured figure is $0.0736/call → $5.52 per 25-query run at K=3, ~$22 at 100 queries — see `audit-packaging-implementation.md` §3.0. Margins below hold, and improve at the smaller config)*:

- Pilot: 5 × $19 = $95 → **87% gross margin**
- Growth: 15 × $19 = $285 → **84%**
- Scale: 40 × $19 = $760 → **81%**
- **Overage: $100–150 against $19 COGS → 84–87% on marginal usage too.** This is the number that matters most; it's where AI products get killed.

On the apparent conflict with "AI-native SaaS runs 50–60% gross margin": that benchmark describes products where inference dominates price (a $20/mo coding tool burning $15 in tokens). At $19 COGS against a $120–200 effective per-client price, this is structurally a data/analytics product with an AI backend. Use the headroom to cover the **manual labor** of running and QA-ing audits, which the API-only COGS figure doesn't capture.

### 5.4 Commitments and the under-onboarding problem

The classic failure: they sign for 10 clients and onboard 2.

Fix it with a **floor payment, not a seat commitment**: "Grows to Growth tier by month 4, minimum floor $1,200/mo regardless of slots used, true-up quarterly against actual client count; bill the higher of floor or actual." They pay either way, you never chase unused-seat overage, and upside is preserved. Add 10–15% for annual prepay.

### 5.5 What the AI pricing failures teach

- **Cursor** sold flat "unlimited-ish" $20/mo against real variable COGS, then introduced usage overage in June 2025 with no warning — $10–20/day surprise bills, one team burning a $7,000 annual plan in a day, repeated backlash through late 2025.
- **Replit** triggered the same backlash with effort-based agent pricing.
- **Perplexity** reportedly cut Pro usage caps in a January 2026 ToS update, drawing "bait and switch" complaints.

**Rule: never sell unlimited against a real variable cost, and never introduce metering after training users to expect flat-rate.** Put the allowance and overage in the contract from day one.

### 5.6 Billing

**Stripe Invoicing, manual, net 30.** One agency customer at $750–4,000/month does not need automated billing infrastructure. Move to Stripe Billing at 3+ agency accounts. Consider a merchant-of-record (Paddle) only when cross-border VAT actually appears — i.e. a UK/EU agency. Agencies expect an invoice with net terms, not card-on-file.

---

## 6. Contract

> Not legal advice. Have a real attorney review before signing.

### 6.1 Standard clauses — push vs concede

| Clause | Push for | Concede |
|---|---|---|
| **License grant** | Non-exclusive, non-sublicensable, field-of-use limited to brand-visibility reporting | They present output under their own brand to their clients |
| **IP ownership** | You retain 100% of platform, prompt sets, judge methodology, software | They own their client relationships and their own report templates |
| **Trademark / white-label** | Approval right over any use of your name/logo | Full white-label of the client-facing PDF |
| **Term** | 12 months, auto-renew, 60-day non-renewal notice | Month-to-month after year one |
| **Termination** | 30-day cure for their breach; convenience exit only after initial term with 90 days' notice | A convenience out after year one |
| **Payment** | Net 15–30, 1.5%/mo late fee, auto-suspend at 30 days past due | Net 30 — standard, don't fight it |
| **Liability cap** | 12 months' fees paid; exclude consequential damages entirely | A modest super-cap ($50–100k) for security incidents |
| **Indemnification** | You indemnify only for your own IP infringement in the core software | Mutual IP-infringement indemnity is normal |
| **Insurance** | Resist an enterprise stack early; stage into Tech E&O/cyber as revenue allows | Proof of general liability + E&O once affordable |

### 6.2 The AI-specific clauses no template has

These are the ones that actually matter here, and a boilerplate reseller agreement will not contain them.

1. **Disclaim third-party model output.** State that scores, comparisons and error catalogues come from querying third-party LLMs whose outputs are non-deterministic, may be wrong, and are outside your control. No warranty of accuracy, completeness, or reproducibility run-to-run.

2. **No guarantee of marketing results.** The FTC has explicitly signaled scrutiny of exaggerated AI performance claims and brought enforcement (Workado) over unsubstantiated AI-accuracy claims. So: (a) no guarantee any client sees visibility improvement; and (b) **prohibit the agency from making performance claims about your tool that you haven't substantiated** — push that burden onto them, because they're the ones talking to end clients.

> **⚠️ Corrected 2026-08-02 (spec task P0-T0).** The Anthropic claim in item 3 below was a misread of
> the underlying story and is **not** a threat to this model. The Feb-2026 change restricted **consumer
> Claude Pro/Max OAuth tokens** — shutting down tools piggybacking third-party traffic onto a personal
> flat-rate subscription — and left standard pay-per-token API-key usage untouched. Anthropic's
> Commercial Terms **§A.1 expressly permit** using the Services "to power products and services
> Customer makes available to its own customers and end users"; §D.4 bars reselling *the Services*
> (raw API access), which is a different thing. OpenAI's Services Agreement §2.2 grants the same
> right. **The only line not to cross is sharing raw API credentials with the agency or its clients.**
> No BYOK and no reseller agreement is needed for the derived-report product. Full audit:
> `gtm-legal-readiness.md` → "Data-source & API-surface audit".

3. **Right to substitute engines.** Reserve the right to substitute, reduce, or discontinue any underlying LLM engine with 30–60 days' notice without that being a breach. This is live risk — Anthropic reportedly tightened API terms in 2026 to bar serving external paying customers on a shared company key, pushing wrapper companies toward BYOK or formal reseller deals; OpenAI and Google have comparable redistribution restrictions. **Verify all four vendors' current commercial terms directly — this is fast-moving and this specific claim comes from a single secondary source.**

4. **Liability for an error the tool surfaces.** The sharpest edge in the deal: your product's whole value is *cataloguing* the models' factual errors, so what happens when your tool mis-classifies one and the agency forwards it to their client? Language: outputs are a **diagnostic aid**, not warranted as complete or currently accurate at time of the agency's use; the agency indemnifies you for how *it* edits, uses or forwards your reports; no liability for decisions clients make on agency-forwarded reports; consequential and reputational damages excluded.

### 6.3 Data protection, proportionate to two people

- **Chain:** end client = controller, agency = processor (or joint controller), **you = subprocessor**. The agency must have authorization from its clients to engage you, with equivalent protections flowed down.
- **Reduced exposure worth noting:** you mostly process brand names, competitor names and LLM outputs — not end-consumer PII. That materially shrinks the GDPR/CCPA surface versus a typical SaaS. Confirm with the agency before allocating risk as if it were larger.
- **Deliver:** a standard DPA naming you as subprocessor, a published subprocessor list (OpenAI / Anthropic / Google / Perplexity), 72-hour breach notification, and honest answers on encryption, access control, retention and deletion.
- **SOC 2: don't chase it.** A security questionnaire is normal and sufficient at this stage. Revisit only when it's a hard blocker on a deal you'd otherwise win.

---

## 7. What agencies actually demand from the product

### 7.1 Report white-label vs app white-label — the clear answer

**They want the artifact branded. They don't ask for the app branded.**

Every complaint found in G2/Capterra reviews and practitioner writing is about the *deliverable*: the PDF cover page, the email sender, the logo, the color. Not one was about the login screen or the favicon. One practitioner puts the need exactly: *"Can I put my agency's branding on the reports and send them directly to a client? Or am I screenshotting dashboards into Google Slides like it's 2015?"*

Pierview draws the line explicitly in their own marketing: *"The client experience is yours. The data infrastructure is Pierview's."*

The cost asymmetry is real: report white-label is templating. App white-label is infrastructure — custom domains, SSL provisioning, per-tenant email sending domains with DKIM/SPF. Entire companies (Approximated, VanityCert) exist solely to solve "custom domain + SSL for your SaaS," which tells you it isn't a checkbox.

### 7.2 Feature checklist, ranked by demand

**Before the first agency deal:**

1. Agency logo + brand color on the PDF
2. All vendor branding removed from PDF and client-facing email
3. Custom "From" name on report emails (display name matters more than the sending domain at first)
4. Scheduled/automated report delivery — table stakes across every competitor; don't make them manually export and forward
5. A fast, no-login "run this for one brand" flow producing a clean shareable one-pager — see §7.4, this is how agencies win the client in the first place
6. Pricing that doesn't punish adding client #6 (per-client/per-seat penalty pricing is the top scaling complaint; retrofitting a pricing model is painful)

**Within 3 months:**

7. Custom domain for report links (`reports.agencyname.com`) — accept the SSL lift once revenue justifies it
8. **Clone/duplicate a client config** — both AgencyAnalytics ("Clone a Client") and GoHighLevel ("Snapshots") independently built this, which is strong evidence of real demand
9. Client switcher — *"Can I manage 30+ brands from one workspace without logging in and out of separate accounts? This sounds basic. Most tools still don't do it well."*
10. Cross-client rollup view — the difference between "a tool per client" and "a tool for my agency"
11. **Editable/annotatable reports** — let the agency add their own commentary before it goes out. AgencyAnalytics markets "Custom Comments" as a durable named feature
12. Real DKIM/SPF-authenticated custom sending domain

**Later:**

13. Read-only client-viewer dashboard, gated and curated — as an optional upsell, per client
14. Bulk operations, portfolio-wide alerting, API export
15. Multiple white-label brand profiles (only for agencies running sub-brands)
16. PowerPoint/Slides export — **searching turned up essentially no demand signal**; don't prioritize it
17. Full custom login page / app re-skin — no evidence it's ever asked for independent of custom domain

### 7.3 Do agencies even want their clients logged in?

Evidence leans toward **PDF-to-client as the default, dashboard access as a selective upsell.** "No-login client access" exists as a distinctly *marketed feature* in this category, which implies real demand for keeping clients out of the live tool. GoHighLevel's feature-request board shows agencies actively asking to hide or gate what clients see on shared dashboards, and to insert their own messaging into the client view — agencies curate the client-facing surface, they don't hand over raw data.

**Implication:** build the expiring signed share link first (`report_shares` in §3.3). It requires no invite flow, no client account management, and covers the workflow you're actually replacing. Add `COMPANY_VIEWER` logins when a client asks to check back repeatedly — the schema is already ready for it.

*(Caveat: the strongest version of the "agencies won't share raw data because it's their secret sauce" claim couldn't be verified with a first-person source — Reddit was inaccessible to the research agent, which is likely where that sentiment lives most candidly. Treat it as well-supported by adjacent evidence but not directly quoted.)*

### 7.4 How agencies actually sell GEO in 2026 — and why it changes the roadmap

Consistent across multiple independent sources, agencies package this as a ladder:

1. **Free/fast audit as a sales weapon** — a shareable visibility score used to open prospect conversations, explicitly modeled on HubSpot's Website Grader. *"A specific score on the prospect's site is more persuasive than any pitch deck."*
2. **Paid diagnostic audit** — $500–$5,000 one-time, converting prospects or upselling existing SEO clients via a competitive gap report.
3. **Monitoring retainer** — $500–$5,000/mo.
4. **Growth/execution retainer** — $1,500–$25,000+/mo: content rewrites, schema, digital PR, monthly reporting.

Two go-to-market models both in active use: **"Layer"** (bolt onto an existing SEO retainer, ~20–30% uplift) and **"Standalone."** Neither dominates.

**What this means for the build:** the tool must serve *both* the sales-weapon use case (fast, single-brand, presentable, no login friction) and the recurring-delivery use case (scheduled, white-labeled, portfolio-wide). These are different UX modes of one product, and agencies expect to move a client from the first into the second.

**And the sales-weapon mode is the cheaper one to build — and it's the same flow as the self-serve funnel in §4.** The instant micro-audit that earns an email from a direct prospect is the same artifact an agency uses to win a client. Build it once, it serves both go-to-market motions. That is the single highest-leverage thing in this entire document.

### 7.5 What kills agency deals

Ranked from a 29-agency survey plus review-site patterns:

1. Slow or absent support — the #1 stated reason to leave a reseller partnership
2. Features that don't work as promised
3. No demonstrable ROI
4. One-sided vendor relationship (vendor only cares about volume)
5. Stagnant product, unaddressed bugs
6. Pricing that doesn't scale with the agency's growth
7. Vendor going direct to the agency's clients *(evidenced from the structurally identical MSP/IT channel, not GEO-specific)*
8. Rigid or shallow white-label — logo-only, ugly fixed templates, no color control

### 7.6 The objections a two-person vendor will face

| Objection | Answer |
|---|---|
| **"Will you two still exist in a year?"** | Don't hide your size — be transparent. Offer a pilot bounded to one client so their risk isn't a portfolio migration. Make speed and responsiveness the differentiator against slower incumbents. |
| **"How do I justify this against a client retainer?"** | Do the math out loud: they charge $2–4k/mo, the tool is ~5–12% of that, and it produces the client deliverable. |
| **"Can I trial with one client first?"** | Yes — this is the default agency evaluation pattern. Make single-client trial trivially cheap; it's how you'll get every first deal. |
| **"Will it fit our reporting cadence?"** | Scheduled delivery + white-label from day one is the minimum to not disrupt their existing monthly cycle. |
| **"What if you get acquired, or go direct to our clients?"** | Mutual non-solicit in writing, plus the data-portability commitment from §2.2. Cheap to give, disproportionately reassuring. |

---

## 8. Sequencing

### Do first — costs almost nothing, prevents the expensive mistake
1. **Memberships join table** instead of a scalar `company_id` on users. One table. This is the whole insurance policy.
2. **RLS from day one**, with `(select auth.uid())` wrapping and empty-result assertions in tests.
3. **Path-prefix URLs** (`/company/{slug}/...`) so links are self-describing.
4. `managing_agency_id` **nullable and reassignable**, not an ownership hierarchy.

### Then — the self-serve funnel (also the agency's sales weapon)
5. Request form: 3 fields, auto-derive the rest.
6. Instant micro-audit — 1 engine × 3 prompts, synchronous, real number on screen.
7. Email verification gate before the expensive run.
8. Resend + dedicated transactional subdomain + SPF/DKIM/DMARC.
9. Delivery email: report behind a signed expiring link, claim-CTA behind a hardened magic link.
10. Lazy account creation at first claim-click. **Never an emailed password.**
11. Portal v1: list + viewer. Nothing more.

### Then — what makes the account worth having
12. The recurring-report work in `docs/audit-packaging-spec.md` Phase 2 (lifecycle, week-over-week, what-changed). Without this, there is no reason to log in twice.

### Then — the agency layer
13. Report-level white-label: logo, color, no vendor branding, custom From name.
14. Scheduled delivery.
15. Client switcher + clone-a-client.
16. Cross-client rollup.
17. Editable commentary before send.
18. Custom domain + authenticated sending domain.

### Not yet
Client-viewer logins (share links first) · bulk ops · portfolio alerting · API export · multiple brand profiles · PPT export · app-level white-label / custom login page.

---

## 9. Open questions

1. **Which API surface do the engines actually hit?** Still unanswered from the last research round (`docs/audit-packaging-spec.md` P0-T0). It matters more now — a licensing agreement makes you a commercial redistributor of model outputs, which raises the stakes on every vendor's terms.
2. **Is the agency buying a delivery system or a sales weapon?** §7.4 says both, but which they lead with changes what to demo Monday.
3. **How many clients do they realistically onboard in 90 days?** Determines whether the Pilot or Growth tier is the right starting point, and sizes the floor payment.
4. **Does the agency want their clients logged in at all?** Ask directly. It's the difference between shipping share links (days) and a client portal (weeks).
5. **Do you have a product name yet?** White-labeling means removing your brand from the client-facing artifact — but you still need one for the agency-facing relationship, the contract, and the methodology page.

---

## 10. Source index

**Licensing & deal structure** — [GoHighLevel white-label economics](https://ghlcrm.me/go-high-level-crm-white-label/) · [SaaS mode markup math](https://rocketlauncher.ai/saas-mode) · [Vendasta Partners](https://www.vendasta.com/partners/) · [Databox Solutions Partner](https://help.databox.com/databox-solutions-partner-program) · [DashThis pricing](https://dashthis.com/pricing/) · [Semrush Enterprise Partner Program](https://enterprise.semrush.com/partner-program) · [GrackerAI agencies](https://gracker.ai/agencies) · [Ayzeo for SEO agencies](https://ayzeo.com/use-cases/seo-agencies) · [GeoScout partners](https://geoscout.pro/en/partners) · [Pierview — how agencies monetize AI search](https://www.pierview.ai/guides/how-agencies-can-monetize-ai-search) · [Pierview — white-label AEO/GEO](https://www.pierview.ai/guides/white-label-aeo-geo) · [ToS Lawyer — SaaS white-label reseller agreement](https://toslawyer.com/saas-white-label-reseller-agreement/) · [Sprintlaw — reseller agreement mistakes](https://www.sprintlaw.com/articles/common-software-reseller-agreement-mistakes-that-create-customer-risk/) · [Aaron Hall — IP clauses in white-label reseller agreements](https://aaronhall.com/ip-clauses-in-white-label-software-reseller-agreements/) · [RBL Associates — the challenge with resellers](https://www.rblassociates.com/insights/the-challenge-with-resellers-part-1/) · [PartnerStack — why agencies stop reselling](https://blog.partnerstack.com/post/why-agencies-stop-reselling) · [IT Glue — vendors poaching clients](https://www.itglue.com/blog/vendors-poaching-clients/)

**Exclusivity, pilots, design partners** — [Suster — when to allow exclusivity](https://medium.com/both-sides-of-the-table/when-should-you-allow-exclusivity-in-deals-15b37534cfba) · [Erik Olson — the problem with exclusivity requests](https://medium.com/@iamerikjolson/the-problem-with-exclusivity-requests-and-how-i-finally-solved-it-5d30d99b4ac9) · [Pitching Angels — avoid exclusivity agreements](https://pitchingangels.com/2025/12/14/avoid-exclusivity-agreements/) · [SaaStr — design partner incentives](https://www.saastr.com/dear-saastr-what-incentives-are-given-to-design-partners-and-other-super-early-customers) · [Do What Matter — design partners for startups](https://dowhatmatter.com/guides/design-partner-for-startups) · [Above A — structuring a paid pilot](https://abovea.tech/insights-strategies/how-to-structure-paid-pilot-startup/) · [Startup Busboy — "if you sell it then I'll build it"](https://startupbusboy.substack.com/p/if-you-sell-it-then-ill-build-it) · [SaaStr — vendor viability](https://www.saastr.com/vendor-viability/) · [Beancount — customer concentration risk](https://beancount.io/blog/2026/05/11/customer-concentration-risk-10-percent-revenue-threshold-business-valuation-loan-capacity-negotiating-leverage-guide)

**Multi-tenancy & RBAC** — [WorkOS — developer's guide to SaaS multi-tenant architecture](https://workos.com/blog/developers-guide-saas-multi-tenant-architecture) · [WorkOS — multi-tenant session management](https://workos.com/blog/multi-tenant-session-management) · [WorkOS vs Auth0 vs Clerk 2026](https://workos.com/blog/workos-vs-auth0-vs-clerk-the-best-auth-platform-for-b2b-saas-in-2026) · [Ravion — multi-tenant SaaS data modeling](https://www.ravion.com/blog/ultimate-guide-to-multi-tenant-saas-data-modeling) · [Auth0 — multiple organization architecture](https://auth0.com/docs/get-started/architecture-scenarios/multiple-organization-architecture) · [Clerk — organizations](https://clerk.com/docs/guides/organizations/overview) · [PropelAuth pricing](https://www.propelauth.com/pricing) · [Makerkit — Supabase RLS best practices](https://makerkit.dev/blog/tutorials/supabase-rls-best-practices) · [Supabase — RLS performance](https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv) · [The `auth.uid()` init-plan trap](https://dev.to/arvavit/76-rls-policies-rewritten-in-one-migration-the-authuid-init-plan-trap-in-supabase-4hg) · [RBAC vs ABAC vs ReBAC vs PBAC](https://guptadeepak.com/guides/rbac-abac-rebac-pbac/) · [Expand/contract zero-downtime migrations](https://dev.to/jp_fontenele4321/the-expand-and-contract-pattern-for-zero-downtime-migrations-445m) · [Path vs subdomain vs DB routing](https://hafiz.dev/blog/laravel-multi-tenancy-database-vs-subdomain-vs-path-routing-strategies) · [Multi-tenancy on day 2 (anecdotal)](https://chandlernguyen.com/blog/2025/11/18/i-knew-what-agencies-needed-so-i-built-multi-tenancy-on-day-2/)

**Agency tooling patterns** — [AgencyAnalytics — white-label overview](https://help.agencyanalytics.com/en/articles/2728635-white-label-overview) · [Clone a client](https://help.agencyanalytics.com/en/articles/7321472-clone-a-client) · [Transfer a client between accounts](https://help.agencyanalytics.com/en/articles/4141840-transfer-a-client-between-accounts) · [Roll-up tables](https://agencyanalytics.com/feature/rollup-table) · [Custom comments](https://agencyanalytics.com/feature/custom-comments) · [Linked accounts](https://help.agencyanalytics.com/en/articles/2851383-linked-accounts-overview) · [GoHighLevel Company vs Location ID](https://auto-respond.com/blog/gohighlevel-company-id-vs-location-id/) · [GHL snapshots](https://www.gohighlevel.com/post/clone-client-setups-snapshots) · [GHL ideas board — agency messaging on client dashboards](https://ideas.gohighlevel.com/dashboard/p/add-agency-own-marketing-messages-to-dashboard) · [Semrush user management](https://www.semrush.com/kb/1409-user-management) · [Alex Birkett — GEO tools for agencies](https://alexbirkett.com/geo-tools-for-agencies/) · [G2 — Whatagraph reviews](https://www.g2.com/products/whatagraph/reviews) · [Capterra — AgencyAnalytics reviews](https://www.capterra.com/p/158746/Agency-Analytics/reviews)

**Onboarding, auth UX, deliverability** — [Form conversion benchmarks 2026](https://www.digitalapplied.com/blog/form-conversion-rate-benchmarks-2026-data-points) · [Form abandonment statistics](https://formstory.io/learn/form-abandonment-statistics/) · [Lazy registration pattern](https://ui-patterns.com/patterns/LazyRegistration) · [better-auth — magic links consumed by scanners](https://github.com/better-auth/better-auth/discussions/6985) · [Supabase — same issue](https://github.com/orgs/supabase/discussions/41618) · [Security Boulevard — are magic links secure](https://securityboulevard.com/2026/05/are-magic-links-secure-a-technical-deep-dive-into-email-based-authentication/) · [Scalekit — OTP vs magic links](https://www.scalekit.com/blog/otp-vs-magic-links-passwordless-authentication) · [NIST 800-63B Rev.4 temp password practice](https://credentialgovernance.avatier.com/en/blog/temporary-password-best-practices-2026) · [The Hacker News — onboarding password mistake](https://thehackernews.com/2026/06/the-onboarding-password-mistake-that.html) · [Standard Beagle — B2B login causes churn](https://standardbeagle.com/b2b-login-customer-churn/) · [PowerDMARC — 2026 bulk sender requirements](https://powerdmarc.com/bulk-email-sender-requirements/) · [Resend pricing](https://resend.com/pricing) · [Email provider pricing comparison](https://blog.vibecoder.me/email-service-pricing-resend-sendgrid-postmark) · [MarketingSherpa — business vs personal email on B2B forms](https://marketingsherpa.com/article/chart/lead-gen-business-vs-personal-email) · [Freemius — AI API cost protection](https://freemius.com/blog/ai-api-cost-protection/) · [LogRocket — async workflow UI patterns](https://blog.logrocket.com/ux-design/ui-patterns-for-async-workflows-background-jobs-and-data-pipelines/)

**Pricing & GEO market rates** — [Peec AI agency pricing](https://peec.ai/pricing-agencies) · [Profound pricing breakdown](https://thatmarketingbuddy.com/pricing/profound) · [Otterly pricing](https://otterly.ai/pricing) · [AthenaHQ review](https://pikaseo.com/articles/athena-hq-review) · [Vendasta pricing](https://www.vendasta.com/pricing/) · [GoHighLevel pricing 2026](https://deliveredsocial.com/gohighlevel-pricing-2026-in-depth-complete-power-user-guide/) · [RevvGrowth — GEO agency pricing](https://www.revvgrowth.com/geo/geo-agency-pricing) · [AI Advantage — AEO agency pricing](https://aiadvantageagency.com/aeo-agency-pricing/) · [Bessemer — AI pricing & monetization playbook](https://bvp.com/atlas/the-ai-pricing-and-monetization-playbook) · [Six fatal flaws of credit pricing for AI](https://softwarepricing.com/blog/credit-based-pricing-ai/) · [AI startup gross margin benchmark 2026](https://avanteventures.com/en/library/ai-startup-gross-margin-benchmark-2026) · [Cursor's pricing disaster timeline](https://www.wearefounders.uk/cursors-pricing-disaster-the-full-timeline-of-how-an-ai-coding-darling-burned-its-most-loyal-users/) · [Replit pricing backlash](https://www.infoworld.com/article/4059876/replit-update-sparks-developers-dissatisfaction-over-pricing.html) · [Ramp deals](https://dealhub.io/glossary/ramp-deal/) · [Minimum commitments](https://contractcorridor.com/contractsexplained/minimum-commitment/) · [Stripe vs Paddle vs Lemon Squeezy for B2B](https://fintechspecs.com/blog/stripe-vs-paddle-vs-lemon-squeezy-vs-polar-merchant-of-record-b2b-saas/)

**Legal & compliance** — [FTC on deceptive AI claims](https://www.hklaw.com/en/insights/publications/2025/06/ftc-evaluating-deceptive-artificial-intelligence-claims) · [Law Insider — no-warranty-of-accuracy clauses](https://www.lawinsider.com/clause/no-warranty-of-accuracy-disclaimer) · [Anthropic API terms and the wrapper era](https://www.sitepoint.com/end-wrapper-era-anthropic-api-terms-saas/) · [Controller vs processor](https://complydog.com/blog/controller-vs-processor) · [DPAs for SaaS](https://secureprivacy.ai/blog/data-processing-agreements-dpas-for-saas) · [SOC 2 vs security questionnaires](https://secureframe.com/blog/soc-2-vs-security-questionnaires) · [Negotiating liability caps with little leverage](https://www.legaldive.com/news/negotiating-limitations-of-liability-when-you-have-little-leverage-alnajafi-nguyen-lexion/714477/) · [Insuring a SaaS startup](https://www.vouch.us/insurance101/how-to-properly-insure-your-saas-startup-to-win-deals-and-protect-your-company)

---

*Compiled 2026-08-01. Five research agents: agency licensing structures, multi-tenant hierarchy/RBAC, audit-first onboarding, agency white-label requirements, licensing pricing and contracts. WagerU schema read directly. Findings flagged verified vs inferred where the underlying agent distinguished them. Not legal advice.*
