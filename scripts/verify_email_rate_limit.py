"""Verify Supabase's auth email rate limit is ACTUALLY raised (LIC-T0 / LIC-T12).

**Why this exists.** Supabase's built-in mailer is capped at 2 emails/hour, and
that cap is the one thing that stops magic-link onboarding from launching. The
cap becomes editable only once custom SMTP is configured — but a dashboard field
reading "30" is not evidence that 30 emails get sent. The two ways it silently
stays broken:

  * The SMTP settings saved, the rate-limit field moved, and GoTrue still
    refuses past the old ceiling.
  * GoTrue accepts every request, and Resend bounces or drops them — a
    Supabase-side 200 and a Resend-side failure look identical from here.

So this measures the FIRST of those by sending real requests and reporting where
the limit actually bites. It cannot see the second: check Resend's own dashboard
for the matching sends, which is why `--to` must be a mailbox you can open.

**It sends real email.** Default is a dry run that prints the plan and sends
nothing; `--confirm` is required to send. Every address is a `+tag` on ONE
mailbox you control, because sending to invented addresses bounces, and bounces
are what destroy a new sending domain's reputation before it has one.

Usage:
    python scripts/verify_email_rate_limit.py --to you@yourdomain.com
    python scripts/verify_email_rate_limit.py --to you@yourdomain.com --confirm
    python scripts/verify_email_rate_limit.py --to you@yourdomain.com --confirm --count 8
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from dataclasses import dataclass

import httpx

from src.config import settings

#: GoTrue's error code when the email rate limit refuses a send. Matched on the
#: code rather than the human message, which is not a stable interface.
RATE_LIMITED_CODE = "over_email_send_rate_limit"

#: The tag every probe address carries, so cleanup can find exactly these users
#: and nothing else.
PROBE_TAG = "geo-ratelimit-probe"


@dataclass(frozen=True)
class Attempt:
    """One send attempt and what Supabase said about it."""

    index: int
    email: str
    status: int
    rate_limited: bool
    detail: str


def _auth_key() -> tuple[str, str]:
    """The key to call the auth API with, and which one it is.

    Prefers the ANON key: that is the credential a real sign-up flow presents, so
    a probe using it exercises the path the product actually takes. Falls back to
    the service-role key ONLY so this script still runs before
    `SUPABASE_ANON_KEY` has been set — which is itself a current blocker, and is
    reported rather than papered over. Neither value is ever printed.
    """
    if settings.SUPABASE_ANON_KEY:
        return settings.SUPABASE_ANON_KEY, "anon"
    if settings.SUPABASE_KEY:
        return settings.SUPABASE_KEY, "service-role"
    raise SystemExit(
        "No Supabase key configured. Set SUPABASE_ANON_KEY (preferred) or "
        "SUPABASE_KEY in .env — see .env.example."
    )


def _probe_address(base: str, index: int, run_id: str) -> str:
    """A `+tag` address on the caller's own mailbox.

    Unique per run, so a second run does not collide with users the first one
    created and get a misleading "already registered" instead of a real send.
    """
    local, _, domain = base.partition("@")
    return f"{local}+{PROBE_TAG}-{run_id}-{index}@{domain}"


def _attempt(client: httpx.Client, url: str, key: str, email: str, index: int) -> Attempt:
    """One signup request. Never raises — a transport failure is a result too."""
    try:
        response = client.post(
            f"{url}/auth/v1/signup",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"email": email, "password": uuid.uuid4().hex},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        # Log the TYPE, not the exception: an httpx message can echo the URL with
        # credentials attached.
        return Attempt(index, email, 0, False, f"transport error ({type(exc).__name__})")

    body: dict[str, object] = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            body = parsed
    except ValueError:
        pass

    code = str(body.get("error_code") or body.get("code") or "")
    limited = response.status_code == 429 or code == RATE_LIMITED_CODE
    detail = str(body.get("msg") or body.get("message") or body.get("error") or "").strip()
    return Attempt(index, email, response.status_code, limited, detail or "ok")


def _cleanup(run_id: str) -> int:
    """Delete the auth users this run created. Returns how many went.

    Probe users are real rows in `auth.users`, and leaving them behind would
    pollute the very table LIC-T5 wants to stay a clean, founders-only set. Scoped
    to this run's tag so it can never touch a real account.
    """
    if not settings.SUPABASE_DB_URL:
        print("  ! SUPABASE_DB_URL unset — probe users left behind; delete them by hand")
        return 0
    try:
        import psycopg
    except ImportError:
        print("  ! psycopg not installed — probe users left behind (pip install 'psycopg[binary]')")
        return 0
    pattern = f"%+{PROBE_TAG}-{run_id}-%"
    with psycopg.connect(settings.SUPABASE_DB_URL) as conn, conn.cursor() as cur:
        # public.users mirrors auth.users via a trigger; delete the mirror first
        # so the FK from memberships/invitations can never dangle.
        cur.execute("delete from public.users where email like %s", (pattern,))
        cur.execute("delete from auth.users where email like %s", (pattern,))
        return cur.rowcount


def _report(attempts: list[Attempt], requested: int) -> int:
    """Print the verdict. Returns the process exit code."""
    sent = [a for a in attempts if not a.rate_limited and 200 <= a.status < 300]
    limited = [a for a in attempts if a.rate_limited]
    other = [a for a in attempts if a not in sent and a not in limited]

    print("\n--- result ---")
    for a in attempts:
        mark = "RATE LIMITED" if a.rate_limited else ("sent" if a in sent else "failed")
        print(f"  {a.index:>2}. {mark:<12} HTTP {a.status:<3} {a.detail[:60]}")

    print(f"\n  accepted: {len(sent)} / {requested}")
    if other:
        print(f"  failed for other reasons: {len(other)} — read the detail column above")

    if not limited:
        print(
            f"\n  No rate limit hit in {requested} sends.\n"
            "  The cap is above that. If you asked for more than 2, the 2/hour\n"
            "  built-in ceiling is genuinely raised — LIC-T0's blocker is cleared."
        )
        print(
            "\n  STILL UNVERIFIED, and this script cannot see it: whether the mail\n"
            "  was DELIVERED. Open Resend's dashboard and confirm the matching\n"
            "  sends, then open the mailbox. A Supabase 200 with a Resend bounce\n"
            "  looks exactly like success from here."
        )
        return 0

    first = min(a.index for a in limited)
    print(
        f"\n  Rate limited on attempt {first}, so the effective cap is {first - 1}/hour.\n"
    )
    if first - 1 <= 2:
        print(
            "  That is the BUILT-IN 2/hour ceiling — custom SMTP is not in effect.\n"
            "  Supabase → Project Settings → Authentication → SMTP Settings, then\n"
            "  raise Authentication → Rate Limits → 'Rate limit for sending emails'.\n"
            "  Magic-link onboarding (LIC-T12) cannot launch until this changes."
        )
    else:
        print(
            "  Custom SMTP is in effect but the limit is lower than you asked for.\n"
            "  Raise it under Authentication → Rate Limits, keeping your sending\n"
            "  domain's warm-up schedule in mind (day 1 is ~150/day, not 2,000)."
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--to", required=True, help="a mailbox YOU control; probes are +tags on it")
    parser.add_argument(
        "--count", type=int, default=6, help="how many sends to attempt (default 6)"
    )
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between sends")
    parser.add_argument("--confirm", action="store_true", help="actually send (default: dry run)")
    parser.add_argument("--keep", action="store_true", help="do not delete the probe users")
    args = parser.parse_args(argv)

    if "@" not in args.to:
        raise SystemExit("--to must be an email address")
    if args.count < 1:
        raise SystemExit("--count must be at least 1")
    if not settings.SUPABASE_URL:
        raise SystemExit("SUPABASE_URL is not set — see .env.example")

    key, kind = _auth_key()
    url = settings.SUPABASE_URL.rstrip("/")
    run_id = uuid.uuid4().hex[:6]

    print(f"project:  {url}")
    print(f"auth key: {kind}")
    if kind == "service-role":
        print("  ! SUPABASE_ANON_KEY is unset. Using the service-role key so this can run,")
        print("    but the anon key is what a real sign-up presents — and it is required")
        print("    before any route can move to per-user auth. Set it.")
    print(f"sending:  {args.count} signups to +{PROBE_TAG}-{run_id}-N tags on {args.to}")

    if not args.confirm:
        print(
            "\nDRY RUN — nothing sent. Re-run with --confirm to send for real.\n"
            "Note this burns Resend quota and counts toward your domain's warm-up."
        )
        return 0

    attempts: list[Attempt] = []
    with httpx.Client() as client:
        for i in range(1, args.count + 1):
            email = _probe_address(args.to, i, run_id)
            attempt = _attempt(client, url, key, email, i)
            attempts.append(attempt)
            flag = " (rate limited)" if attempt.rate_limited else ""
            print(f"  {i:>2}. HTTP {attempt.status}{flag}")
            if attempt.rate_limited:
                # Stop at the first refusal: the limit is now known, and every
                # further request is a send we do not need against a domain whose
                # reputation we are trying to build.
                break
            if i < args.count:
                time.sleep(args.interval)

    exit_code = _report(attempts, args.count)

    if not args.keep:
        removed = _cleanup(run_id)
        print(f"\n  cleaned up {removed} probe user(s)")
    else:
        print(f"\n  probe users kept (tag: {PROBE_TAG}-{run_id})")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
