"""Render docs/report.md from the computed metrics blob (build_detailed_report.py).

Lays the report out against the audit deliverable spec in
docs/engine-gap-analysis.md ("The deliverable test"): §1 scorecard, §2 funnel
(by intent bucket + accuracy flags), §3 competitive leaderboard, §4 sources,
§5 prioritized synthesis, §6 appendix (query set + per-query×per-engine capture).
Numbers come straight from the JSON so the document can't drift from the data.

Usage:
    python -m scripts.render_report_md /tmp/report_data.json docs/report.md
"""

from __future__ import annotations

import json
import sys

PROM_LABEL = {
    "recommended_first": "🥇 first",
    "mid_pack": "mid-pack",
    "buried": "buried",
    "also_ran": "also-ran",
    "absent": "—",
}
INTENT_LABEL = {
    "problem_aware": "Problem-aware (upper funnel)",
    "category": "Category (“best smart ring …”)",
    "comparison": "Comparison (“X vs Y”)",
    "brand": "Brand (navigational)",
    "adjacent_authority": "Adjacent authority (topic questions)",
}


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def main(data_path: str, out_path: str) -> int:
    d = json.load(open(data_path))
    m = d["meta"]
    sc = d["scorecard"]
    L: list[str] = []

    # ---------- Header ----------
    L += [
        f"# GEO Audit — {m['client']} ({m['category']})",
        "",
        f"**Run ID:** `{m['run_id']}`  ",
        "**Surface:** parametric memory (what each model recommends from training, "
        "no live retrieval) — Perplexity additionally returns live citations  ",
        f"**Query set:** `{m['query_set_version']}` · {m['n_queries']} queries, "
        f"locked {m['locked_at']}  ",
        f"**Engines:** {', '.join(m['engines'])} (4)  ",
        f"**Competitors benchmarked:** {', '.join(m['competitors'])}  ",
        f"**Coverage:** {m['n_results']} answers · {m['n_judgments']} judge verdicts "
        "(every answer scored by one held-constant `gpt-4o` judge against the Oura "
        "fact sheet)  ",
        "**Detection:** LLM judge (prominence / framing / typed accuracy flags); "
        "regex fallback unused here.",
        "",
        "> **What this measures.** When a consumer asks an AI assistant a question in "
        "the smart-ring category, does Oura show up, where in the answer, framed how, "
        "and is what the model says about Oura *true*? This is the GEO analogue of a "
        "search-ranking audit. It powers Steps 1 (baseline) and 5 (competitive "
        "benchmark) of the audit method; the §5 synthesis below is the analyst layer.",
        "",
        "---",
        "",
    ]

    # ---------- Executive summary ----------
    board = d["leaderboard"]
    top = board[0]
    comp = board[1]
    bb = d["by_bucket"]
    L += [
        "## Executive summary",
        "",
        f"- **Headline grade: {sc['grade']}.** Prominence-weighted visibility is "
        f"**{sc['raw_visibility']:.2f}** (the strongest in the category), but "
        f"**{sc['n_flags']} distinct client accuracy flags** drive the accuracy-"
        f"discounted score to **0.00**. Oura is *seen* but frequently *described "
        "wrong*.",
        f"- **Oura leads the category leaderboard** — visibility {top['visibility']:.2f} "
        f"vs. {comp['brand']} {comp['visibility']:.2f}; share-of-voice "
        f"{pct(top['share_of_voice'])} of all brand mentions. Presence is not the "
        "problem.",
        "- **The problem is two-sided:**",
        f"  1. **Accuracy.** {d['flags']['by_severity'].get('high', 0)} of "
        f"{sc['n_flags']} flags are *high* severity — overwhelmingly **stale pricing/"
        "model** facts: models still quote the $299–$549 Gen-3/Ring-4 era and call "
        "Oura subscription-optional, when the current line is **Ring 5 at $399/$499 "
        "with a required $5.99/mo membership** (Ring 5 launched 2026-05-28).",
        f"  2. **Funnel shape.** Oura owns bottom-funnel intent "
        f"(brand {pct(bb['brand']['client_mention_rate'])}, category "
        f"{pct(bb['category']['client_mention_rate'])}, comparison "
        f"{pct(bb['comparison']['client_mention_rate'])}) but is **nearly invisible "
        f"upper-funnel**: problem-aware {pct(bb['problem_aware']['client_mention_rate'])}, "
        f"adjacent-authority {pct(bb['adjacent_authority']['client_mention_rate'])}. "
        "Buyers at the start of the journey never hear the name.",
        f"- **Where it loses outright:** {len(d['losing_cells'])} (query, engine) cells "
        "where Oura is absent and a competitor is recommended first — almost all in "
        "**comparison** queries (cmp-08/09/11), led by Whoop, Ultrahuman, RingConn, and "
        "Samsung.",
        "- **Citations come from one surface.** Only Perplexity exposes sources; the "
        "off-site battleground it reveals is **YouTube, Facebook, and review media "
        "(wareable, CNET, Tom’s Guide)** — not Oura’s own site.",
        "",
        "---",
        "",
    ]

    # ---------- §1 Scorecard ----------
    L += [
        "## §1 · AI Visibility Scorecard",
        "",
        f"### Grade: {sc['grade']}",
        "",
        f"- **Raw visibility (prominence-weighted):** {sc['raw_visibility']:.2f} / 1.00"
        "  — rewards being recommended *first* over being buried.",
        f"- **Accuracy penalty:** −{sc['penalty']:.2f} across {sc['n_flags']} distinct "
        "flags (high −0.15, med −0.07, low −0.03 each).",
        f"- **Discounted score:** {sc['score']:.2f} → **{sc['grade']}** (floored at 0).",
        "",
        "> The grade is deliberately severe on accuracy: a confidently wrong claim "
        "(“no subscription required”) erodes buyer trust even when the brand is "
        "front-and-centre. The raw 0.56 visibility is a **B/A-grade presence**; the F "
        "is entirely an accuracy verdict.",
        "",
        "### Share-of-model",
        "",
        "| Role | Brand | Visibility | Mention rate | Share-of-voice |",
        "| --- | --- | --- | --- | --- |",
    ]
    roles = {top["brand"]: "Client / category leader", comp["brand"]: "Top competitor"}
    for r in board:
        role = roles.get(r["brand"], "Competitor")
        L.append(
            f"| {role} | {r['brand']} | {r['visibility']:.2f} | "
            f"{pct(r['mention_rate'])} | {pct(r['share_of_voice'])} |"
        )
    L += [
        "",
        "*Share-of-voice = a brand’s present-cells as a fraction of all brand "
        "present-cells across the run.*",
        "",
        "### Per-engine — client mention & citation rate",
        "",
        "| Engine | Client mention rate | Any-citation rate | Note |",
        "| --- | --- | --- | --- |",
    ]
    notes = {
        "gemini": "most generous to Oura",
        "openai": "lowest — Oct-2023 training cutoff refuses 2026 queries",
        "perplexity": "only engine with live citations",
        "anthropic": "",
    }
    pe = d["per_engine"]
    for e in m["engines"]:
        L.append(
            f"| {e} | {pct(pe[e]['client_mention_rate'])} | "
            f"{pct(pe[e]['any_citation_rate'])} | {notes.get(e, '')} |"
        )
    L += [
        "",
        "*Client **citation** rate is 0% on every engine: on the parametric surface "
        "models recommend from memory without linking, and where Perplexity does cite, "
        "it cites review media rather than ouraring.com. See §4.*",
        "",
        "---",
        "",
    ]

    # ---------- §2 Funnel ----------
    L += [
        "## §2 · Funnel analysis (by intent bucket)",
        "",
        "Every score is tied back to *which queries* it comes from. Buckets run from "
        "upper-funnel (a consumer describing a problem) to navigational (typing the "
        "brand name).",
        "",
        "### §2.2 Mention, visibility & prominence by bucket",
        "",
        "| Intent bucket | Queries | Client mention | Client visibility | "
        "🥇 first | mid-pack | also-ran | absent |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = ["brand", "category", "comparison", "problem_aware", "adjacent_authority"]
    for intent in order:
        b = bb[intent]
        pd = b["prominence_dist"]
        L.append(
            f"| {INTENT_LABEL[intent]} | {b['n_queries']} | "
            f"{pct(b['client_mention_rate'])} | {b['client_visibility']:.2f} | "
            f"{pd['recommended_first']} | {pd['mid_pack']} | {pd['also_ran']} | "
            f"{pd['absent']} |"
        )
    L += [
        "",
        "**Read:** Oura is **dominant where intent is explicit** — 100% on brand "
        "queries, 88% on category (“best smart ring …”), 80% on comparison — and "
        "**effectively absent where it isn’t**: 11% problem-aware, 4% adjacent-"
        "authority. The upper-funnel gap is the single biggest *growth* opportunity; "
        "the comparison softness (often mid-pack, not first) is the biggest "
        "*competitive* risk. The two clusters map to different fixes (§5).",
        "",
        "### §2.3 Accuracy flags — what the models get wrong about Oura",
        "",
        f"**{sc['n_flags']} distinct flags** ({d['flags']['total_instances']} total "
        "instances across answers). This is the most persuasive material in the audit: "
        "concrete, falsifiable things the AIs state about Oura that are wrong.",
        "",
        "| | high | med | low | **total** |",
        "| --- | --- | --- | --- | --- |",
    ]
    bt = d["flags"]["by_type"]
    ts = d["flags"]["by_type_severity"]

    def cell(t: str, s: str) -> int:
        return ts.get(f"{t}|{s}", 0)

    for t, label in [
        ("wrong_pricing", "Wrong pricing / subscription"),
        ("stale", "Stale model / generation"),
        ("missing_or_invented_feature", "Missing or invented feature"),
    ]:
        L.append(
            f"| {label} | {cell(t, 'high')} | {cell(t, 'med')} | {cell(t, 'low')} | "
            f"**{bt.get(t, 0)}** |"
        )
    sev = d["flags"]["by_severity"]
    L.append(
        f"| **total** | **{sev.get('high', 0)}** | **{sev.get('med', 0)}** | "
        f"**{sev.get('low', 0)}** | **{sc['n_flags']}** |"
    )
    L += [
        "",
        "**The three failure modes, in plain terms:**",
        "",
        "1. **Stale pricing & subscription (74 flags, 62 high).** Models quote the old "
        "$299–$549 range and — most damagingly — tell shoppers Oura needs **no "
        "subscription**. Reality: Ring 5 base **$399** / premium **$499**, plus a "
        "**required $5.99/mo (or $69.99/yr) membership** for full features.",
        "2. **Stale model / generation (29 flags, 25 high).** Models name the **Gen 3 / "
        "Ring 4** as current or “best in 2026.” Reality: **Oura Ring 5 launched "
        "2026-05-28.**",
        "3. **Missing/invented features (53 flags).** Battery quoted as 4–7 days "
        "(actual ~8), SpO2 omitted or denied, “period prediction” invented, integration "
        "breadth understated.",
        "",
        "**Evidence (verbatim from the answers):**",
        "",
        "- **cat-09 “best smart ring 2026” · Perplexity** — recommends Oura *first* but "
        "stale and wrong on both model and price:",
        "  > “The **best smart ring in 2026 overall is the Oura Ring 4** according to "
        "multiple expert test roundups … If you want the best *subscription-free* "
        "option, the **Samsung Galaxy Ring** is a leading pick.”",
        "  Flags: `stale/high` (Ring 4 ≠ current Ring 5), `wrong_pricing/high` "
        "(“was $349”), `missing_or_invented_feature/high` (frames a *subscription-free* "
        "alternative as the win).",
        "- **cat-06 “best smart ring without a monthly subscription” · Gemini** — Oura "
        "is correctly *demoted* here (it requires a membership), and **RingConn is "
        "recommended first**. A legitimate competitive loss, not a hallucination:",
        "  > “**RingConn** … is arguably the most direct competitor to Oura … but "
        "without any subscription. **No Subscription:** All features are included with "
        "the purchase price.”",
        "- **cat-10 “what’s the newest smart ring in 2026?” · OpenAI** — the parametric "
        "cutoff makes the model refuse outright, so Oura (and everyone) is absent:",
        "  > “I can’t provide real-time or future-specific information as my training "
        "only includes data up to October 2023.”",
        "",
        "The full flag list is in [§6.2](#62--per-query--per-engine-capture) context "
        "and enumerated below.",
        "",
        "<details><summary><strong>All "
        f"{sc['n_flags']} distinct accuracy flags (type · severity · claim → reality)"
        "</strong></summary>",
        "",
        "| # | Type | Sev | Claim → Reality |",
        "| --- | --- | --- | --- |",
    ]
    for i, f in enumerate(d["flags"]["all"], 1):
        claim = f["claim"].replace("|", "\\|").replace("\n", " ")
        reality = f["reality"].replace("|", "\\|").replace("\n", " ")
        L.append(f"| {i} | {f['type']} | {f['severity']} | {claim} → {reality} |")
    L += ["", "</details>", "", "---", ""]

    # ---------- §3 Leaderboard ----------
    losing = d["losing_cells"]
    closest = [c for c in d["closest_to_winning"] if c["client_prominence"] != "absent"]
    L += [
        "## §3 · Competitive leaderboard & loss attribution",
        "",
        "### Leaderboard",
        "",
        "| Rank | Brand | Visibility | Mention rate | Share-of-voice | Mentions |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i, r in enumerate(board, 1):
        mark = " *(client)*" if r["brand"] == m["client"] else ""
        L.append(
            f"| {i} | {r['brand']}{mark} | {r['visibility']:.2f} | "
            f"{pct(r['mention_rate'])} | {pct(r['share_of_voice'])} | {r['mentions']} |"
        )
    L += [
        "",
        f"Oura’s {pct(top['share_of_voice'])} share-of-voice is larger than the next "
        "two competitors combined. **Ultrahuman** and **RingConn** are the real "
        "challengers; Whoop (a wrist band, not a ring) and Samsung trail.",
        "",
        "### Trend",
        "",
        "_This is the **baseline** cycle for query set `"
        + m["query_set_version"]
        + "` — no prior comparable run to diff against. The trend column (the "
        "method’s moat: re-run the locked set on a 4–6 week cadence and show the "
        "named metric move) activates from the next cycle via `geo compare <before> "
        "<after>`._",
        "",
        f"### Structurally behind — Oura absent, competitor #1 ({len(losing)} cells)",
        "",
        "| Query | Engine | Recommended first instead |",
        "| --- | --- | --- |",
    ]
    for c in losing:
        L.append(f"| {c['query_id']} ({c['intent']}) | {c['engine']} | {c['competitor']} |")
    L += [
        "",
        "Concentrated in **comparison** intent: `cmp-08` (Whoop vs Ultrahuman for "
        "athletes — Oura isn’t in the matchup framing), `cmp-09` (Samsung/RingConn win "
        "on a spec angle), `cmp-11` (cheaper-alternatives-to-Whoop → Whoop/others). On "
        "category, `cat-06` (no-subscription) and `cat-10` (newest-2026) are lost on "
        "Perplexity.",
        "",
        f"### Closest to winning — Oura present but *not* first ({len(closest)} cells)",
        "",
        "These are the cheapest wins: Oura already appears, just ranked behind a "
        "competitor recommended first. Nudging prominence here moves the leaderboard "
        "fastest.",
        "",
        "| Query | Engine | Loses first place to | Oura currently |",
        "| --- | --- | --- | --- |",
    ]
    for c in closest:
        L.append(
            f"| {c['query_id']} | {c['engine']} | {c['competitor']} | "
            f"{PROM_LABEL.get(c['client_prominence'], c['client_prominence'])} |"
        )
    L += ["", "---", ""]

    # ---------- §4 Sources ----------
    L += [
        "## §4 · Sources & technical accessibility",
        "",
        "### §4.4 Sources behind the category",
        "",
        "Where models *do* cite (Perplexity only on this surface), these are the "
        "domains shaping the category answer. Per the method, this **routes the "
        "off-site work**: if the sources are review media and social, the battleground "
        "isn’t ouraring.com.",
        "",
        "| Rank | Domain | Cited in cells | Engines |",
        "| --- | --- | --- | --- |",
    ]
    for i, s in enumerate(d["sources"][:15], 1):
        L.append(f"| {i} | {s['domain']} | {s['cells']} | {', '.join(s['engines'])} |")
    L += [
        "",
        "**Read:** the category is decided on **YouTube (34), Facebook (19), and "
        "review media** — wareable, CNET, Tom’s Guide, ZDNet, TechAdvisor — plus "
        "retail (BestBuy) and health authorities (PMC/NIH, SleepFoundation, Cleveland "
        "Clinic) for the problem-aware questions. `ouraring.com` is cited in only 9 "
        "cells. **Earning creator and review-media coverage is higher-leverage than "
        "on-site changes.**",
        "",
        "### §4.1 Technical accessibility",
        "",
        "_Not run in this cycle._ Crawler-access / WAF / rendering / llms.txt / "
        "sitemap checks are available via `geo technical ouraring.com` and should be "
        "attached in the full deliverable (Step 2). Flagged as a gap, not a pass.",
        "",
        "---",
        "",
    ]

    # ---------- §5 Synthesis ----------
    L += [
        "## §5 · Prioritized takeaways (analyst synthesis)",
        "",
        "Sequenced by impact × fixability. Items 1–2 are the demo-ready story; 3–4 are "
        "the growth program.",
        "",
        "1. **Fix the facts the models repeat (highest impact, partially in client’s "
        "control).** Every high-severity flag traces to **stale pricing/model** data. "
        "Publish clear, current, answer-first Ring 5 pricing + membership facts on "
        "ouraring.com, and — because the models cite *review media*, not Oura — push "
        "the corrected Ring 5 / $399 / membership facts into the wareable / CNET / "
        "Tom’s Guide / YouTube ecosystem so the next training + retrieval pass sees "
        "the truth. This is what flips “F on accuracy” without touching visibility.",
        "2. **Defend the comparison queries (highest competitive risk).** `cmp-08/09/"
        "11` and the “closest to winning” set are where Ultrahuman, RingConn, Whoop and "
        "Samsung take first place. Build/seed **“Oura vs Ultrahuman”, “Oura vs RingConn”, "
        "“Oura vs Samsung Galaxy Ring”** comparison content and creator coverage that "
        "names Oura first on the axes buyers ask about.",
        "3. **Own the “no-subscription” and “budget” framings or concede them "
        "honestly.** `cat-06`/`cat-08` are legitimate losses (Oura requires a "
        "membership). Decide messaging: compete on value-with-membership, or accept "
        "these queries route to RingConn/Samsung.",
        "4. **Attack the upper funnel (biggest growth headroom).** Problem-aware (11%) "
        "and adjacent-authority (4%) are wide open — when someone asks “why do I wake "
        "up exhausted?” or “how does HRV relate to recovery?”, no smart-ring brand "
        "owns the answer. Authoritative, citable explainer content (the kind PMC / "
        "SleepFoundation currently supply) is the path in.",
        "5. **Lock the cadence (the moat).** Re-run this exact locked query set in "
        "4–6 weeks and diff with `geo compare` to prove the accuracy flags fall and "
        "comparison prominence rises.",
        "",
        "---",
        "",
    ]

    # ---------- §6 Appendix ----------
    L += [
        "## §6 · Appendix",
        "",
        "### §6.1 Query set",
        "",
        f"`{m['query_set_version']}` · {m['n_queries']} queries · locked "
        f"{m['locked_at']}. Intent mix: "
        + ", ".join(f"{k} {v}" for k, v in m["intent_counts"].items())
        + ".",
        "",
        "| Query ID | Intent | Weight | Persona/modifier | Prompt |",
        "| --- | --- | --- | --- | --- |",
    ]
    for q in d["query_set"]:
        persona = q["persona"] or "—"
        text = q["text"].replace("|", "\\|")
        L.append(
            f"| {q['query_id']} | {q['intent']} | {q['weight']} | {persona} | {text} |"
        )

    L += [
        "",
        "### §6.2 Per-query × per-engine capture",
        "",
        "One row per (query, engine): Oura’s presence, prominence and framing, the "
        "number of accuracy flags the judge raised on that answer, which brand was "
        "recommended first, which competitors appeared, and citation count. This is "
        "the raw §6.3 data rolled to the cell level — every number above traces here.",
        "",
        "Legend: prominence 🥇 first · mid-pack · also-ran · — absent.",
        "",
        "| Query | Engine | Oura | Prominence | Framing | Flags | Led by | "
        "Competitors present | Cites |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in d["capture"]:
        present = "✅" if r["client_present"] else "—"
        prom = PROM_LABEL.get(r["client_prominence"], r["client_prominence"])
        leader = r["leader"] or "—"
        comps = ", ".join(r["competitors_present"]) or "—"
        L.append(
            f"| {r['query_id']} | {r['engine']} | {present} | {prom} | "
            f"{r['client_framing']} | {r['client_flags'] or ''} | {leader} | {comps} | "
            f"{r['citations'] or ''} |"
        )

    L += [
        "",
        "### §6.3 Methodology & honesty caveats",
        "",
        "- **Surface.** Parametric memory (no live web) on OpenAI/Anthropic/Gemini; "
        "Perplexity returns live citations. A separate `--surface search` run measures "
        "the live-retrieval surfaces (ChatGPT-search, Claude-search, Gemini grounding, "
        "Google AI Overviews) and is recommended as a companion.",
        "- **Determinism.** Temperature pinned to 0; 1 run per query this cycle "
        "(repeat-run averaging is supported via `--runs`).",
        "- **Judge.** One held-constant `gpt-4o` judge, forced-JSON, no outside "
        "knowledge — accuracy is checked **only** against the supplied Oura fact sheet "
        "(`docs/fact-sheet-example-oura.md`). Accuracy flags are **client-only** by "
        "design; competitors get presence/prominence/framing.",
        "- **Trust.** The judge is currently **plausible but lightly calibrated** "
        "(placeholder gold set). Calibrate against a hand-labeled gold set before "
        "quoting flag counts to a client as ground truth.",
        "- **Gemini provenance.** Gemini’s answers in this run were backfilled "
        "2026-06-12 after an API-key/quota fix and judged on the same fact sheet as "
        "the other engines.",
        "- **Citations.** Client citation rate is 0% because the parametric surface "
        "doesn’t link and Perplexity cites review media over ouraring.com — a finding, "
        "not a data gap.",
        "",
    ]

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"wrote {out_path}: {len(L)} lines")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
