"""Compute every metric the audit deliverable (§1-§6) needs from a stored run.

This is the quantitative backbone for docs/report.md. It pulls the run's
QueryResults + judge verdicts from Supabase and computes, per the deliverable
spec in docs/engine-gap-analysis.md ("The deliverable test"):

  §1  scorecard: A-F grade, share-of-model for client / top competitor /
      category leader, per-engine client mention & citation rate
  §2.2 mention rate, citation rate, and prominence distribution by intent bucket
  §2.3 accuracy flags grouped by type x severity (+ totals)
  §3  leaderboard (visibility + mention + share-of-voice), "closest to winning"
      and "structurally behind" splits of the losing cells
  §4.4 sources behind the category (cited domains, ranked, with engines)
  §6.1 query set with persona/weight
  §6.2 per-query x per-engine capture (client present/prominence/framing/flags,
      competitors present, citation count)

Prints a JSON blob to stdout so the report can be assembled deterministically.

Usage:
    python -m scripts.build_detailed_report <run_id> <query_set.json>
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

from src.pipeline import judge_metrics as jm
from src.pipeline.metrics import domain_of
from src.prompts.query_set import load_query_set
from src.storage import db
from src.storage.models import AnswerJudgment, QueryResult

PROM_ORDER = ["recommended_first", "mid_pack", "buried", "also_ran", "absent"]


def main(run_id: str, query_set_path: str) -> int:
    qs = load_query_set(query_set_path)
    client = qs.client
    competitors = list(qs.competitors)
    brands = [client, *competitors]

    results: list[QueryResult] = db.get_query_results(run_id)
    judgments: list[AnswerJudgment] = db.get_judgments(run_id)

    engines = sorted({r["engine_name"] for r in results})
    intents = ["problem_aware", "category", "comparison", "brand", "adjacent_authority"]

    out: dict[str, object] = {}
    out["meta"] = {
        "run_id": run_id,
        "client": client,
        "category": qs.category,
        "competitors": competitors,
        "query_set_version": qs.version,
        "locked_at": qs.locked_at,
        "n_queries": len(qs.queries),
        "engines": engines,
        "n_results": len(results),
        "n_judgments": len(judgments),
        "intent_counts": dict(Counter(q.intent.value for q in qs.queries)),
    }

    # ---- §1 scorecard ----
    grade = jm.visibility_grade(judgments, client)
    board = jm.leaderboard(judgments, brands)
    top_comp = next((b for b, _, _ in board if b != client), None)
    out["scorecard"] = {
        "grade": grade.letter,
        "raw_visibility": round(grade.raw_score, 3),
        "penalty": round(grade.accuracy_penalty, 3),
        "score": round(grade.score, 3),
        "n_flags": grade.n_flags,
        "client_mention_rate": round(jm.mention_rate(judgments, client), 3),
        "top_competitor": top_comp,
        "category_leader_after_client": top_comp,
    }

    # per-engine client mention & citation rate
    def engine_client_cells(engine: str) -> list[jm.BrandCell]:
        sub = [j for j in judgments if j.engine_name == engine]
        return jm._brand_cells(sub, client)

    per_engine = {}
    cite_cells_by_engine: dict[str, int] = defaultdict(int)
    cells_by_engine: dict[str, int] = defaultdict(int)
    for r in results:
        cells_by_engine[r["engine_name"]] += 1
        if r["citations"]:
            cite_cells_by_engine[r["engine_name"]] += 1
    for e in engines:
        cells = engine_client_cells(e)
        present = sum(1 for c in cells if c.present)
        per_engine[e] = {
            "client_mention_rate": round(present / len(cells), 3) if cells else 0.0,
            "n_cells": len(cells),
            "any_citation_rate": round(cite_cells_by_engine[e] / cells_by_engine[e], 3)
            if cells_by_engine[e]
            else 0.0,
        }
    out["per_engine"] = per_engine

    # ---- §2.2 by intent bucket ----
    by_bucket = {}
    for intent in intents:
        sub = [j for j in judgments if j.intent == intent]
        cells = jm._brand_cells(sub, client)
        prom_dist = Counter(c.prominence for c in cells)
        present = sum(1 for c in cells if c.present)
        # competitor leaderboard within bucket
        comp_board = jm.leaderboard(sub, brands)
        by_bucket[intent] = {
            "n_queries": sum(1 for q in qs.queries if q.intent.value == intent),
            "n_cells": len(cells),
            "client_mention_rate": round(present / len(cells), 3) if cells else 0.0,
            "client_visibility": round(jm.visibility_score(sub, client), 3),
            "prominence_dist": {p: prom_dist.get(p, 0) for p in PROM_ORDER},
            "leaderboard": [
                {"brand": b, "visibility": round(v, 3), "mention": round(m, 3)}
                for b, v, m in comp_board
            ],
        }
    out["by_bucket"] = by_bucket

    # ---- §2.3 accuracy flags by type x severity ----
    flags = jm.collect_accuracy_flags(judgments)
    by_type = Counter(f.type for f in flags)
    by_sev = Counter(f.severity for f in flags)
    type_sev = Counter((f.type, f.severity) for f in flags)
    # total flag *instances* (not deduped) for the "156" headline
    total_flag_instances = sum(len(j.accuracy_flags) for j in judgments if j.assessed)
    out["flags"] = {
        "distinct": len(flags),
        "total_instances": total_flag_instances,
        "by_type": dict(by_type),
        "by_severity": dict(by_sev),
        "by_type_severity": {f"{t}|{s}": n for (t, s), n in sorted(type_sev.items())},
        "all": [
            {"type": f.type, "severity": f.severity, "claim": f.claim, "reality": f.reality}
            for f in flags
        ],
    }

    # ---- §3 leaderboard + share-of-voice + loss splits ----
    # share-of-voice = brand mentions / total brand mentions across all brands
    mention_counts = {}
    for b in brands:
        cells = jm._brand_cells(judgments, b)
        mention_counts[b] = sum(1 for c in cells if c.present)
    total_mentions = sum(mention_counts.values()) or 1
    out["leaderboard"] = [
        {
            "brand": b,
            "visibility": round(v, 3),
            "mention_rate": round(m, 3),
            "mentions": mention_counts[b],
            "share_of_voice": round(mention_counts[b] / total_mentions, 3),
        }
        for b, v, m in board
    ]

    losing = jm.losing_cells(judgments, client, competitors)
    out["losing_cells"] = [
        {"query_id": c.query_id, "engine": c.engine_name, "competitor": c.brand, "intent": c.intent}
        for c in losing
    ]
    # "closest to winning": client present but mid/buried/also_ran while a competitor
    # is recommended_first in the same (query, engine)
    client_cells = {(c.query_id, c.engine_name): c for c in jm._brand_cells(judgments, client)}
    closest = []
    for comp in competitors:
        for c in jm._brand_cells(judgments, comp):
            if c.present and c.prominence == "recommended_first":
                cc = client_cells.get((c.query_id, c.engine_name))
                if cc and cc.present and cc.prominence != "recommended_first":
                    closest.append(
                        {
                            "query_id": c.query_id,
                            "engine": c.engine_name,
                            "competitor": comp,
                            "client_prominence": cc.prominence,
                        }
                    )
    out["closest_to_winning"] = sorted(closest, key=lambda x: (x["query_id"], x["engine"]))

    # ---- §4.4 sources behind the category ----
    # count distinct (query, engine) cells a domain is cited in (matches the CLI report)
    domain_engines: dict[str, set[str]] = defaultdict(set)
    domain_cells: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for r in results:
        for url in r["citations"]:
            d = domain_of(url)
            if not d:
                continue
            domain_cells[d].add((r["query_id"], r["engine_name"]))
            domain_engines[d].add(r["engine_name"])
    out["sources"] = [
        {"domain": d, "cells": len(cells), "engines": sorted(domain_engines[d])}
        for d, cells in sorted(domain_cells.items(), key=lambda kv: len(kv[1]), reverse=True)[:25]
    ]

    # ---- §6.1 query set ----
    out["query_set"] = [
        {
            "query_id": q.query_id,
            "intent": q.intent.value,
            "text": q.text,
            "weight": q.weight,
            "persona": getattr(q, "persona", None),
        }
        for q in qs.queries
    ]

    # ---- §6.2 per-query x per-engine capture (client + which competitor led) ----
    # collapse per (query, engine): client verdict + competitor recommended_first
    cap: dict[tuple[str, str], dict[str, object]] = {}
    for b in brands:
        for c in jm._brand_cells(judgments, b):
            key = (c.query_id, c.engine_name)
            row = cap.setdefault(
                key,
                {
                    "query_id": c.query_id,
                    "engine": c.engine_name,
                    "intent": c.intent,
                    "client_present": False,
                    "client_prominence": "absent",
                    "client_framing": "neutral",
                    "competitors_present": [],
                    "leader": None,
                },
            )
            if b == client:
                row["client_present"] = c.present
                row["client_prominence"] = c.prominence
                row["client_framing"] = c.framing
            elif c.present:
                row["competitors_present"].append(b)  # type: ignore[union-attr]
            if c.present and c.prominence == "recommended_first":
                # prefer client as leader if client is first; else first competitor seen
                if row["leader"] is None or b == client:
                    row["leader"] = b
    # attach flag counts + citation count per cell
    flagcount: dict[tuple[str, str], int] = defaultdict(int)
    for j in judgments:
        if j.assessed and j.accuracy_flags:
            flagcount[(j.query_id, j.engine_name)] += len(j.accuracy_flags)
    citecount: dict[tuple[str, str], int] = defaultdict(int)
    for r in results:
        citecount[(r["query_id"], r["engine_name"])] += len(r["citations"])
    for key, row in cap.items():
        row["client_flags"] = flagcount.get(key, 0)
        row["citations"] = citecount.get(key, 0)
    out["capture"] = sorted(cap.values(), key=lambda x: (x["query_id"], x["engine"]))  # type: ignore[index,arg-type]

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
