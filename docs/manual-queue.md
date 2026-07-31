# Manual queue — what needs a human

Everything currently waiting on a person, ordered by how much it unblocks per minute
spent. Written 2026-07-31. Each item says what it is, why it is blocked on you
specifically, and roughly how long it takes.

Delete an item when it is done. This is a working list, not a record — `build-log.md`
is the record.

---

## Do these first — minutes each, and they unblock whole systems

### 1 · The `leads_reader` password → `LEADS_DB_URL` · ~2 min

The fact-sheet worker is written, tested and **cannot run**. It reads the leads queue
over the SELECT-only `leads_reader` role, and that role's password is not the one
`leads-visibility.sql` shipped (`CHANGE_ME_BEFORE_USE` is rejected — tested), so
somebody set a real one.

Add to `.env`:

    LEADS_DB_URL=postgresql://leads_reader:<password>@db.satjbyfjzrwocwwonsxz.supabase.co:5432/postgres?sslmode=require

Then `python -m src.cli factsheet-worker` runs. It currently exits 1 with a specific
reason, which is the intended clean failure rather than a silent no-op.

*If nobody has that password any more, say so — it can be rotated through the
superuser DSN commented in `.env`, but not blind: something else may authenticate as
that role.*

### 2 · One phone call to Albert Nahman · ~15 min

Three open questions on `docs/fact-sheet-albert-nahman.md` are all answerable in one
call, and they gate the accuracy half of the local gold set:

1. **What are the real service hours?** The site publishes none anywhere — it
   advertises "24/7 Live Answering", which is answering, not dispatch. Until this is
   answered no hours claim may be added, and an answer stating specific opening hours
   grades as *unverifiable*, not *wrong*.
2. **Is (510) 295-0534 live?** It appears on some service pages; the homepage,
   contact page and footer all publish (510) 408-7879. Recorded as a disagreement,
   deliberately not chosen (§4.3).
3. **What is the real dispatch radius?** The service-area page lists towns well beyond
   Berkeley and Hayward. `wrong_service_area` cannot be graded until this is settled.

Answering 1 and 2 also promotes those claims toward `client_confirmed`, which is what
§8 requires before a high-severity flag may appear in anything sent to a prospect.

### 3 · Verify a Resend domain · ~30 min, mostly waiting on DNS

Lead alerts already work — 4 of 5 sends returned 200, the key is in the leads
project's Supabase Vault, `pg_net`/`pg_cron` are installed and the `lead_arrived`
trigger is live. The one failure is the constraint you already know about:

> `403` — *"You can only send testing emails to your own email address
> (abhinavjinka@gmail.com). To send emails to other recipients, please verify a domain
> at resend.com/domains, and change the `from` address."*

So: verify a domain, then change the hardcoded sender at
`geoWebsite/scripts/lead-email-alerts.sql:112`
(`AI visibility alerts <onboarding@resend.dev>`) and re-apply the file. Until then no
report can reach anyone but Abhi.

---

## The real work

### 4 · Label the local gold set · 1–2 hours

`docs/local-labeling-sheet.md` — 40 answers about Albert Nahman Plumbing, grouped by
question so the four engines' answers to one query sit together. Each item carries the
vocabulary inline and a mention-evidence block (literal match count and how far into
the answer the first one falls).

    python -m scripts.parse_labeling_sheet docs/local-labeling-sheet.md data/local_gold.json          # validate
    python -m scripts.parse_labeling_sheet docs/local-labeling-sheet.md data/local_gold.json --write  # apply

Validate as often as you like; it writes nothing without `--write` and refuses to
write at all if anything fails validation.

**A model must never label this set** — independence is the entire point of measuring
the judge against it. `present` is deliberately left defaulted to `no` rather than
pre-filled from the name match, because a pre-filled answer gets rubber-stamped and a
disavowal ("there is no such plumber") names the brand while meaning the opposite.

**Watch the flag density.** The consumer calibration (below) showed flag precision is
unmeasurable when a set carries only 3 flag-bearing items. If this set ends up with
very few `expected_flags`, it will have the same problem — so label the flags
attentively, and if the corpus genuinely contains almost no client errors, that is
itself the finding and the set needs more items rather than a shrug.

---

## Decisions only you and Josh can make

### 5 · A4 — does the competitor set join the fact sheet?

`docs/audit-packaging-research.md` §9.5 binds the fact sheet and the competitor set
into one governance artifact; the fact-sheet plan has no competitor-set plan at all.
It changes what the F4 review screen gates.

F4 is built gating the **sheet only**, structured so a second artifact is additive
rather than a rewrite — so this is not blocking anything today. It does need deciding
before the screen goes in front of a client.

### 6 · Two `.docx` files are now tracked in git

`docs/Client Call Prep - Objections and Close Path.docx` and
`docs/Technical Founder Call Prep.docx` were untracked; "commit everything" swept them
in. Binary blobs in a source repo are a choice — `git rm --cached` if you would rather
they stayed out.

---

## Infrastructure, when you want it

### 7 · Schedule the worker

`geo factsheet-worker` is one pass per invocation by design — a daemon that owns its
own clock is harder to stop, and this reads a queue of real prospects. Scheduling
lives outside it. A cron entry is a one-liner once item 1 is done.

### 8 · Host the API

Everything currently runs with your laptop open. `run-api.sh` is localhost, which is
also why the fact-sheet worker had to be a polling bridge rather than a `pg_net` call
from the leads trigger. Hosting removes that constraint and lets the worker and any
schedule run without you.

---

## Not blocked on you, recorded so it is not lost

- **F2 (half done).** `buildAuditCsv` emits fact rows; what is missing is threading the
  sheet's verification tier onto the run so `fact_sheet_verification` stops being null.
  Until then F3 returns `[]` and the teaser output is unchanged.
- **A renderer for accuracy findings**, plus copy following the audit-packaging voice
  rules — that is what actually changes what a prospect sees.
- **A2** — JSON-LD coverage across ~10 real trade sites. One data point exists:
  albertnahmanplumbing.com is at **0%** (its only JSON-LD block has no `@type`, and
  there is no `<footer>` element), which is evidence for L1's centre of gravity being
  `tel:` links and prose rather than schema.
