"""The fact-sheet intake API.

Lives in its own module because ``app.py`` is already 42 KB and the fact-sheet
block was the last coherent thing in it. The router carries no auth of its own —
it is mounted on the same ``APIRouter(dependencies=[Depends(require_api_key)])``
every other route uses.

THE RULE THIS WHOLE MODULE SERVES. ``FactSheet.verification_tier`` is a MINIMUM
across the sheet's claims, so one leftover ``public_source_only`` claim caps the
entire sheet at LOW/MED and nullifies the intake. Therefore, at approval, every
claim in the outgoing sheet is either ``client_confirmed`` or it is dropped.
There is no third option and no silent pass-through: :func:`approve` refuses with
a 409 naming the claims, and the review screen is expected to have resolved them
before the button is enabled. The API is the backstop, not the only gate.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException

from src.audit.factsheet.intake import (
    Answer,
    IntakeQuestion,
    assertions_for,
    build_plan,
    claims_from_answers,
    question,
    run_inputs_from_answers,
    unfalsifiable_terms,
)
from src.audit.factsheet.models import (
    BusinessKind,
    FactSheet,
    Verification,
    assigned_claims,
)
from src.prompts.assemble import DEFAULT_LOCAL_ENGINES, assemble_run_csv
from src.prompts.generate import generate_query_set
from src.prompts.intent import LOCAL_BUCKET_ALLOCATION
from src.prompts.lint import lint_query_set
from src.prompts.local_templates import TRADES
from src.storage import db

logger = logging.getLogger(__name__)

router = APIRouter()

__all__ = ["router"]

#: How many questions a generated set carries. Thirty is the working default:
#: the local assembler emits 29, and matching it keeps the cost estimate on the
#: review screen comparable between the two paths.
DEFAULT_QUERY_COUNT = 30


def _today() -> str:
    """The ``as_of`` stamp. The ONE clock in the intake stack.

    Everything under `src/audit/factsheet/intake/` takes `as_of` as a parameter
    precisely so it can be tested without one; this is where the real date
    enters, at the edge, once.
    """
    return datetime.now(UTC).date().isoformat()


# --- serialisation ------------------------------------------------------------


def _question_json(q: IntakeQuestion, prefill: dict[str, Any]) -> dict[str, Any]:
    """One card, as the UI consumes it.

    The UI never hardcodes a question — this is the whole contract. A card that
    exists in the frontend but not in the registry is a card whose answer has
    nowhere to go.
    """
    return {
        "id": q.id,
        "kind": q.kind.value,
        "section": q.section.value if q.section else None,
        "keys": list(q.keys),
        "prompt": q.prompt,
        "why": q.why,
        "helper": q.helper,
        "placeholder": q.placeholder,
        "options": [{"value": o.value, "label": o.label} for o in q.options],
        "skippable": q.skippable,
        "negativeFirst": q.negative_first,
        "producesClaims": q.produces_claims,
        "showIf": ({"questionId": q.show_if[0], "equals": q.show_if[1]} if q.show_if else None),
        # Only the keys this card can actually fill, so the UI does not have to
        # know the shape of the whole prefill map to render one confirm.
        "prefill": {k: prefill[k] for k in q.keys if k in prefill},
    }


def _dict_of(row: dict[str, Any], key: str) -> dict[str, Any]:
    """A jsonb column as a dict.

    Every jsonb column here arrives typed `object` from PostgREST, and a `None`
    from a row written before the column existed is indistinguishable from an
    empty one until you index it. One narrowing helper, used everywhere, so the
    guard cannot be forgotten at one of the nine call sites.
    """
    value = row.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _answers_from_row(row: dict[str, Any]) -> list[Answer]:
    stored = _dict_of(row, "answers")
    out: list[Answer] = []
    for qid, payload in stored.items():
        data = payload if isinstance(payload, dict) else {}
        out.append(
            Answer(
                question_id=str(qid),
                value=data.get("value"),
                raw=str(data.get("raw", "")),
                skipped=bool(data.get("skipped", False)),
            )
        )
    return out


def _session_row(session_id: str) -> dict[str, Any]:
    row = db.get_intake_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"intake session {session_id} not found")
    return dict(row)


def _kind_of(row: dict[str, Any]) -> BusinessKind:
    try:
        return BusinessKind(str(row.get("business_kind") or BusinessKind.LOCAL_SERVICE.value))
    except ValueError:
        return BusinessKind.LOCAL_SERVICE


def _plan_for(row: dict[str, Any]) -> list[IntakeQuestion]:
    """The plan, recomputed from the stored answers on every request.

    Recomputed rather than stored: Q-ID-01 routes the whole tree, so a session
    that answers it differently on a Back-and-change has a different plan, and a
    stored plan would be the OLD one. It is a pure function of cheap inputs.
    """
    answers = {a.question_id: a.value for a in _answers_from_row(row)}
    kind = _kind_of(row)
    # The owner's own answer wins over whatever the crawl guessed.
    chosen = str(answers.get("Q-ID-01") or "")
    if chosen in {k.value for k in BusinessKind}:
        kind = BusinessKind(chosen)
    prefill = _dict_of(row, "prefill")
    return build_plan(business_kind=kind, prefill=prefill, answers=answers)


def _next_question(row: dict[str, Any]) -> IntakeQuestion | None:
    answered = {a.question_id for a in _answers_from_row(row)}
    for q in _plan_for(row):
        if q.id not in answered:
            return q
    return None


def _progress(row: dict[str, Any]) -> dict[str, Any]:
    plan = _plan_for(row)
    answers = _answers_from_row(row)
    by_id = {a.question_id: a for a in answers}
    marks = []
    current = _next_question(row)
    for q in plan:
        a = by_id.get(q.id)
        if a is None:
            marks.append("current" if current and q.id == current.id else "todo")
        elif a.skipped:
            # ADDRESSED, never "answered" and never "pending". That distinction
            # is what makes skipping safe to offer.
            marks.append("skipped")
        else:
            marks.append("done")
    confirmed = sum(1 for a in answers if not a.is_blank)
    return {
        "marks": marks,
        "total": len(plan),
        "answered": len(by_id),
        "confirmed": confirmed,
        "done": current is None,
    }


def _session_json(row: dict[str, Any]) -> dict[str, Any]:
    prefill = _dict_of(row, "prefill")
    plan = _plan_for(row)
    nxt = _next_question(row)
    return {
        "session_id": str(row.get("id", "")),
        "domain": str(row.get("domain", "")),
        # The name the prompts address the owner by. Resolved server-side so the
        # UI never has to guess it from the domain — "blackpropeller.com is a
        # local business people call or visit" is not a sentence anyone signs.
        "business_name": _business_name(row),
        "business_kind": str(row.get("business_kind", "")),
        "state": str(row.get("state", "")),
        "fact_sheet_id": row.get("fact_sheet_id"),
        "approved_fact_sheet_id": row.get("approved_fact_sheet_id"),
        "plan": [_question_json(q, prefill) for q in plan],
        "answers": _dict_of(row, "answers"),
        "prefill": prefill,
        "run_inputs": _dict_of(row, "run_inputs"),
        "next": _question_json(nxt, prefill) if nxt else None,
        "progress": _progress(row),
    }


def _business_name(row: dict[str, Any]) -> str:
    inputs = _dict_of(row, "run_inputs")
    if inputs.get("business"):
        return str(inputs["business"])
    sheet_id = row.get("fact_sheet_id")
    if sheet_id:
        sheet = db.get_fact_sheet(str(sheet_id))
        if sheet is not None:
            return sheet.business_name
    return str(row.get("domain", ""))


# --- create / resume ----------------------------------------------------------


@router.post("/fact-sheets/{sheet_id}/intake")
def start_intake(sheet_id: str) -> dict[str, Any]:
    """Create a session for a draft sheet, or hand back the live one.

    Resume rather than refuse: two people opening the same sheet in the same
    minute is ordinary, and a second session would silently diverge from the
    first. ``uq_intake_sessions_live`` is what decides, not a read-then-write
    check here.
    """
    sheet = db.get_fact_sheet(sheet_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail=f"fact sheet {sheet_id} not found")

    existing = db.live_intake_session(sheet.domain)
    if existing is not None:
        return _session_json(dict(existing))

    # Prefill: what the crawl already found, so a card is a one-tap confirm
    # instead of a blank field.
    prefill: dict[str, Any] = {
        c.key: {
            "value": c.value,
            "source_url": c.source_url,
            "source_kind": c.source_kind.value,
            "confidence": c.confidence.value,
        }
        for c in sheet.claims
    }
    session_id = db.create_intake_session(
        domain=sheet.domain,
        business_kind=sheet.business_kind.value,
        fact_sheet_id=sheet_id,
        prefill=prefill,
    )
    if session_id is None:
        # Lost the insert race. The winner's session is the right answer.
        existing = db.live_intake_session(sheet.domain)
        if existing is None:
            raise HTTPException(
                status_code=503, detail="could not open an intake session for this domain"
            )
        return _session_json(dict(existing))
    return _session_json(_session_row(session_id))


@router.post("/fact-sheets/{sheet_id}/edit")
def edit_sheet(sheet_id: str) -> dict[str, Any]:
    """A new session pre-filled from an ACTIVE sheet.

    Editing an approved sheet is a new intake, never an in-place mutation:
    storage is create-only for sheets, past reports keep the version they were
    run against, and approving this session writes v(N+1).
    """
    return start_intake(sheet_id)


@router.get("/intake/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    """Full state, for a resume after a refresh."""
    return _session_json(_session_row(session_id))


# --- answering ----------------------------------------------------------------


@router.post("/intake/{session_id}/answer")
def answer(session_id: str, payload: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Record one answer. IDEMPOTENT PER QUESTION ID — re-answering overwrites.

    That is what makes Back, the launcher's "Answer this one", and the review
    screen's inline edits free: they all just set the answer again.
    """
    row = _session_row(session_id)
    if row.get("state") == "approved":
        raise HTTPException(
            status_code=409,
            detail="this intake is already approved; start an edit to change the sheet",
        )

    question_id = str(payload.get("question_id") or "")
    try:
        q = question(question_id)
    except KeyError:
        raise HTTPException(
            status_code=422, detail=f"unknown question id {question_id!r}"
        ) from None

    skipped = bool(payload.get("skipped", False))
    if skipped and not q.skippable:
        raise HTTPException(
            status_code=422,
            detail=f"{q.id} cannot be skipped — the rest of the plan is built from it",
        )

    answers = dict(row.get("answers") or {})
    answers[q.id] = {
        "value": payload.get("value"),
        "raw": str(payload.get("raw", "")),
        "skipped": skipped,
        "answered_at": datetime.now(UTC).isoformat(),
    }

    db.update_intake_session(
        session_id,
        {"answers": answers, "current_question_id": q.id, "state": "in_progress"},
    )
    fresh = _session_row(session_id)
    return {
        "next": _session_json(fresh)["next"],
        "progress": _progress(fresh),
        # What the owner is now on the record as saying. The UI has already
        # previewed this; returning it means the preview can never be a
        # different sentence from the stored one.
        "assertions": [
            {"key": a.key, "value": a.value, "polarity": a.polarity.value}
            for a in assertions_for(
                q,
                Answer(
                    question_id=q.id,
                    value=payload.get("value"),
                    raw=str(payload.get("raw", "")),
                    skipped=skipped,
                ),
                as_of=_today(),
                business_name=_business_name(fresh),
            )
        ],
        "nudge": list(unfalsifiable_terms(str(payload.get("raw") or ""))),
    }


@router.post("/intake/{session_id}/preview")
def preview(
    session_id: str, payload: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    """The sentence a candidate answer WOULD produce. Stores nothing.

    THE POINT OF THE INTAKE SCREEN. The owner must see the exact line they will
    be quoted on before the card commits — "No after-hours or emergency
    service.", not their tap ("No"). That sentence has to come from the same
    builder that will actually write the claim, or the preview is a promise the
    stored claim does not keep.

    Which is why this is a round trip rather than a copy of the sentence logic in
    TypeScript. The registry and its phrasing live in one place; a second
    implementation in the client would drift the first time someone reworded a
    card, and the owner would be shown one sentence and quoted on another.
    """
    row = _session_row(session_id)
    question_id = str(payload.get("question_id") or "")
    try:
        q = question(question_id)
    except KeyError:
        raise HTTPException(
            status_code=422, detail=f"unknown question id {question_id!r}"
        ) from None

    built = assertions_for(
        q,
        Answer(
            question_id=q.id,
            value=payload.get("value"),
            raw=str(payload.get("raw", "")),
            skipped=bool(payload.get("skipped", False)),
        ),
        as_of=_today(),
        business_name=_business_name(row),
    )
    return {
        "assertions": [
            {"key": a.key, "value": a.value, "polarity": a.polarity.value} for a in built
        ],
        "nudge": list(unfalsifiable_terms(str(payload.get("raw") or ""))),
    }


@router.post("/intake/{session_id}/back")
def back(session_id: str) -> dict[str, Any]:
    """Step back one card. THE ANSWER STAYS and stays editable.

    Deleting it would be the destructive reading of "back" — the owner wants to
    change what they said, not to unsay it, and an answer that vanishes on a
    mis-tap is the thing that makes people distrust a form.
    """
    row = _session_row(session_id)
    plan = _plan_for(row)
    answered = [a.question_id for a in _answers_from_row(row)]
    if not answered:
        return _session_json(row)
    order = [q.id for q in plan]
    last = max((qid for qid in answered if qid in order), key=order.index, default=None)
    if last is not None:
        db.update_intake_session(session_id, {"current_question_id": last})
    return _session_json(_session_row(session_id))


# --- complete: build the sheet, the query set and the CSV ---------------------


def _build_claims(row: dict[str, Any]) -> tuple[list[Any], list[str]]:
    """(claims, unconfirmed keys). The tier rule's raw material.

    Crawl claims the owner confirmed are UPGRADED and keep their `source_kind`;
    crawl claims nobody touched stay `public_source_only` and are reported so
    the review screen can force a confirm-or-drop.
    """
    as_of = _today()
    business = _business_name(row)
    session_id = str(row.get("id", ""))
    answers = _answers_from_row(row)

    intake_claims = claims_from_answers(
        answers, session_id=session_id, as_of=as_of, business_name=business
    )
    confirmed_keys = {c.key for c in intake_claims}

    # Keys the owner explicitly left alone are NOT dropped silently — they are
    # returned as unconfirmed so the reviewer decides. Dropping quietly would be
    # the tier rule enforcing itself by deleting the client's data.
    dropped_keys: list[str] = []
    sheet_id = row.get("fact_sheet_id")
    if sheet_id:
        sheet = db.get_fact_sheet(str(sheet_id))
        if sheet is not None:
            for claim in sheet.claims:
                if claim.key in confirmed_keys:
                    continue
                dropped_keys.append(claim.key)
    return intake_claims, dropped_keys


def _query_set_for(row: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[Any]]:
    """(csv_text, query rows, lint items).

    Local trades with a hand-written template use ``assemble_run_csv``, which is
    already exactly what this needs — config plus query rows and NO FACT BLOCK,
    because the sheet travels by ``fact_sheet_id`` and a run carrying both is
    refused. Everything else falls back to the bucket-generic generator, and the
    review screen says which path produced the set.
    """
    inputs = _dict_of(row, "run_inputs")
    business = str(inputs.get("business") or _business_name(row))
    website = str(inputs.get("website") or row.get("domain") or "")
    trade = str(inputs.get("trade") or "")
    city = str(inputs.get("city") or "")
    region = str(inputs.get("region") or "")
    category = str(inputs.get("category") or trade or "")
    competitors = [str(c) for c in (inputs.get("competitors") or [])]
    local = _kind_of(row) is BusinessKind.LOCAL_SERVICE

    if local and trade in TRADES and city and region:
        csv_text = assemble_run_csv(
            business=business,
            website=website,
            trade=trade,
            city=city,
            region=region,
            competitors=competitors,
            category=category or None,
        )
        rows = _query_rows_from_csv(csv_text)
        return csv_text, rows, []

    generated = generate_query_set(
        client=business,
        category=category,
        competitors=competitors,
        slots={"city": city, "region": region, "year": _today()[:4]},
        n=DEFAULT_QUERY_COUNT,
        local=local,
        allocation=LOCAL_BUCKET_ALLOCATION if local else None,
    )
    csv_text = _csv_from_generated(
        generated, business=business, category=category, competitors=competitors
    )
    lint = lint_query_set(
        generated,
        csv_text=csv_text,
        client=business,
        category=category,
        competitors=competitors,
        engines=list(DEFAULT_LOCAL_ENGINES),
        region=region,
    )
    rows = [
        {
            "query_id": q.query_id,
            "text": q.text,
            "intent": q.intent.value,
            "persona": q.persona,
            "provenance": q.provenance,
        }
        for q in generated.queries
    ]
    return csv_text, rows, lint


def _csv_from_generated(
    generated: Any, *, business: str, category: str, competitors: list[str]
) -> str:
    """Config block plus query rows. NO FACT BLOCK, deliberately.

    The sheet reaches the run by ``fact_sheet_id``; a run carrying both a sheet
    and fact rows is refused, and the id is also what carries
    ``fact_sheet_verification`` into ``build_report``, which is what makes any
    accuracy finding sendable at all.
    """
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(("block", "key", "value", "intent", "persona"))
    writer.writerow(("config", "client_name", business, "", ""))
    writer.writerow(("config", "category", category, "", ""))
    if competitors:
        writer.writerow(("config", "competitors", ";".join(competitors), "", ""))
    writer.writerow(("config", "engines", ";".join(DEFAULT_LOCAL_ENGINES), "", ""))
    writer.writerow(("config", "runs_per_query", "3", "", ""))
    for q in generated.queries:
        writer.writerow(("query", q.query_id, q.text, q.intent.value, q.persona))
    return buffer.getvalue()


def _query_rows_from_csv(csv_text: str) -> list[dict[str, Any]]:
    """Read back the assembler's own output, so both paths return one shape."""
    import csv
    import io

    rows: list[dict[str, Any]] = []
    for record in csv.DictReader(io.StringIO(csv_text)):
        if (record.get("block") or "").strip() != "query":
            continue
        rows.append(
            {
                "query_id": (record.get("key") or "").strip(),
                "text": (record.get("value") or "").strip(),
                "intent": (record.get("intent") or "").strip(),
                "persona": (record.get("persona") or "").strip(),
                "provenance": "near_verbatim",
            }
        )
    return rows


@router.post("/intake/{session_id}/complete")
def complete(session_id: str) -> dict[str, Any]:
    """Build the claims, the query set and the CSV, then move to review."""
    row = _session_row(session_id)
    answers = _answers_from_row(row)
    run_inputs = run_inputs_from_answers(
        answers,
        fallback_business=_business_name(row),
        fallback_website=str(row.get("domain") or ""),
    )
    db.update_intake_session(session_id, {"run_inputs": asdict(run_inputs)})

    row = _session_row(session_id)
    csv_text, query_rows, lint = _query_set_for(row)
    db.update_intake_session(
        session_id,
        {
            "state": "awaiting_review",
            "query_set": {"queries": query_rows},
            "csv_text": csv_text,
            "lint": [asdict(item) for item in lint],
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )
    return review(session_id)


# --- review + approve ---------------------------------------------------------


@router.get("/intake/{session_id}/review")
def review(session_id: str) -> dict[str, Any]:
    """Everything the approve gate needs, and the reason it is or is not open."""
    row = _session_row(session_id)
    claims, unconfirmed = _build_claims(row)
    lint = row.get("lint") or []
    blocked = [i for i in lint if isinstance(i, dict) and i.get("level") == "block"]
    stored_set = row.get("query_set")
    queries = stored_set.get("queries", []) if isinstance(stored_set, dict) else []

    return {
        "session_id": session_id,
        "state": str(row.get("state", "")),
        "claims": [
            {
                "claim_id": c.claim_id,
                "section": c.section.value,
                "key": c.key,
                "value": c.value,
                "quote": c.verbatim_quote,
                "polarity": c.polarity.value,
                "as_of": c.as_of,
                "verification": c.verification.value,
            }
            for c in assigned_claims(claims)
        ],
        # Named, not counted. "3 facts nobody has confirmed" with no way to see
        # WHICH is a dead end, and this is the list the meter's button opens.
        "unconfirmed": unconfirmed,
        "query_set": queries,
        "csv": row.get("csv_text") or "",
        "lint": lint,
        "tier": (
            Verification.CLIENT_CONFIRMED.value
            if claims and not unconfirmed
            else Verification.PUBLIC_SOURCE_ONLY.value
        ),
        "can_approve": bool(claims) and not unconfirmed and not blocked,
        "run_inputs": _dict_of(row, "run_inputs"),
    }


@router.patch("/intake/{session_id}/review")
def patch_review(
    session_id: str, payload: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    """Edit the queries or the run config, then revalidate.

    Claims are edited by RE-ANSWERING the card that produced them, not by
    editing the claim: the sentence the owner is quoted on has to keep coming
    from an answer they gave, or the provenance trail stops being true.
    """
    row = _session_row(session_id)
    patch: dict[str, Any] = {}

    if "run_inputs" in payload and isinstance(payload["run_inputs"], dict):
        merged = _dict_of(row, "run_inputs")
        merged.update(payload["run_inputs"])
        patch["run_inputs"] = merged

    if patch:
        db.update_intake_session(session_id, patch)
        row = _session_row(session_id)
        csv_text, query_rows, lint = _query_set_for(row)
        db.update_intake_session(
            session_id,
            {
                "query_set": {"queries": query_rows},
                "csv_text": csv_text,
                "lint": [asdict(item) for item in lint],
            },
        )
    return review(session_id)


@router.post("/intake/{session_id}/approve")
def approve(session_id: str) -> dict[str, Any]:
    """Write v(N+1), activate it, and record what the session produced.

    Steps 3 and 4 are two calls because PostgREST has no cross-table
    transaction. The ordering is demote-then-promote, and it must not be
    flipped: the existing failure window is "this domain has NO active sheet",
    never "two active sheets". A run that finds nothing uses no fact sheet and
    makes no accuracy claim; a run that finds two has no defined reference at
    all.
    """
    row = _session_row(session_id)
    claims, unconfirmed = _build_claims(row)

    if not claims:
        raise HTTPException(
            status_code=409,
            detail="nothing was confirmed — an empty sheet cannot flag anything",
        )
    if unconfirmed:
        # THE TIER RULE. One public_source_only claim caps the whole sheet at
        # LOW/MED and hides every serious finding, so this is a refusal and not
        # a warning.
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"{len(unconfirmed)} claim(s) are not client-confirmed. Confirm or drop "
                    "each one — until they are handled this sheet can only flag low and "
                    "medium issues, and the serious ones stay hidden."
                ),
                "unconfirmed": unconfirmed,
            },
        )

    lint = row.get("lint") or []
    blocked = [i for i in lint if isinstance(i, dict) and i.get("level") == "block"]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "the generated question set does not pass its checks",
                "lint": blocked,
            },
        )

    domain = str(row.get("domain", ""))
    sheet = FactSheet(
        domain=domain,
        business_name=_business_name(row),
        business_kind=_kind_of(row),
        claims=list(claims),
        generated_at=_today(),
    )
    try:
        sheet_id, version = db.save_fact_sheet_next_version(sheet)
        db.activate_fact_sheet(sheet_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.update_intake_session(
        session_id,
        {"state": "approved", "approved_fact_sheet_id": sheet_id},
    )
    # Per-client, not global: `fact_sheet` is an input to the verdict cache key,
    # so a new version re-keys every cached verdict for THIS client. Nothing here
    # touches `_PROMPT_LAYOUT`, so the judge's parity tests are unaffected and
    # re-warming is free through the prejudge flow.
    logger.info(
        "intake approved: domain=%s version=%s claims=%s (cached verdicts for this "
        "client are now cold)",
        domain,
        version,
        len(claims),
    )
    return {"fact_sheet_id": sheet_id, "version": version, "claims": len(claims)}


@router.get("/fact-sheets/{sheet_id}/query-set")
def sheet_query_set(sheet_id: str) -> dict[str, Any]:
    """The stored set and CSV for a sheet an intake approved.

    Read off the SESSION that approved the sheet rather than stored twice: two
    representations of the same question set is how they drift.
    """
    sheet = db.get_fact_sheet(sheet_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail=f"fact sheet {sheet_id} not found")
    for row in db.list_intake_sessions(domain=sheet.domain):
        if str(row.get("approved_fact_sheet_id") or "") == sheet_id:
            payload = row.get("query_set")
            return {
                "fact_sheet_id": sheet_id,
                "queries": payload.get("queries", []) if isinstance(payload, dict) else [],
                "csv": row.get("csv_text") or "",
            }
    return {"fact_sheet_id": sheet_id, "queries": [], "csv": ""}
