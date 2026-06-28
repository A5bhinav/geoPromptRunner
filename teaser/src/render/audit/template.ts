/**
 * AI Visibility Audit template — fills an AuditDraft into a single self-contained,
 * multi-page HTML document in the same "Ledger" editorial design as the teaser
 * (warm cream paper, Newsreader serif, Public Sans body, rust accent). The PDF
 * (render/audit/pdf.ts) prints each § on its own page.
 *
 * Reuses the teaser's STYLE/FONTS + renderProofCard + answerSnippet so the
 * audit is visually continuous with the free teaser (doc §9/§13). Each section is
 * a small pure function so they stay independently testable.
 */

import type {
  AuditDraft,
  AuditEdits,
  DiagnosisCategory,
  EvidenceGroup,
  RoadmapPhase,
} from "../../types/audit.ts";
import type { FlagRow, IntentBucket, LeaderRow, SiteFindingRow, SourceRow } from "../../types/platform.ts";
import { engineLabel } from "../copy.ts";
import { renderProofCard } from "../proofCard.ts";
import { FONTS, STYLE } from "../template.ts";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pct(n: number | null | undefined): number {
  return Math.max(0, Math.min(100, Math.round((n ?? 0) * 100)));
}

function nonEmpty(s: string | undefined): string | null {
  return s && s.trim() ? s : null;
}

const BUCKET_LABEL: Record<IntentBucket, string> = {
  problem_aware: "Problem-aware",
  category: "Category",
  comparison: "Comparison",
  brand: "Brand",
  adjacent_authority: "Adjacent authority",
};

const CATEGORY_LABEL: Record<number, string> = {
  1: "Technical accessibility",
  2: "Content coverage",
  3: "Content structure & extractability",
  4: "Content substance (E-E-A-T)",
  5: "Structured data / schema",
  6: "Off-site authority",
  7: "Baseline measurement",
};

function bucketLabel(b: IntentBucket): string {
  return BUCKET_LABEL[b] ?? b;
}
function categoryLabel(c: number): string {
  return CATEGORY_LABEL[c] ?? `Category ${c}`;
}

/** Audit-specific CSS layered on top of the shared Ledger STYLE. */
const AUDIT_STYLE = `
  .page { max-width:820px; }
  .audit-section { padding:0 52px; }
  .audit-section + .audit-section { margin-top:8px; }
  .sec-head { margin:34px 0 16px; border-bottom:1px solid var(--ink); padding-bottom:10px; }
  .sec-num { font-size:11px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; color:var(--rust); }
  .sec-title { font-family:var(--serif); font-weight:500; font-size:24px; line-height:1.2; margin:6px 0 0; letter-spacing:-.005em; }
  .sec-sub { font-size:13.5px; color:var(--muted); margin:6px 0 0; line-height:1.55; }

  /* §1 cover */
  .cover-hero h1 { font-family:var(--serif); font-weight:500; font-size:33px; line-height:1.18; letter-spacing:-.006em; margin:22px 0 16px; }
  .cover-hero h1 .you { color:var(--rust); }
  .grade-card { display:flex; align-items:center; gap:26px; margin:22px 0; padding:22px 26px; border:1px solid var(--rule); border-radius:12px; background:#fff; }
  .grade-now { font-family:var(--serif); font-weight:500; font-size:64px; line-height:1; color:var(--rust); font-variant-numeric:tabular-nums; }
  .grade-arrow { font-size:30px; color:var(--faintest); }
  .grade-goal { font-family:var(--serif); font-weight:500; font-size:48px; line-height:1; color:var(--ink2); }
  .grade-labels { display:flex; flex-direction:column; gap:2px; font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); }
  .grade-col { text-align:center; }
  .grade-col .cap { font-size:10.5px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); margin-top:7px; }
  .grade-rationale { font-size:13px; color:var(--muted); margin:0; max-width:46ch; line-height:1.55; }
  .verdict { font-family:var(--serif); font-style:italic; font-size:18px; line-height:1.5; color:var(--ink2); margin:18px 0 18px; padding-left:18px; border-left:2px solid var(--rust); }
  .what-inside { font-size:12.5px; color:var(--muted2); border-top:1px solid var(--rule); padding-top:14px; }
  .what-inside b { color:var(--ink); font-weight:600; }

  /* §2 per-bucket table reuses table styles; small caption */
  .bucket-grid { width:100%; border-collapse:collapse; font-size:13.5px; margin-top:6px; }

  /* §4 accuracy */
  .acc { display:flex; flex-direction:column; gap:12px; }
  .acc-item { border:1px solid var(--rule); border-radius:10px; padding:14px 16px; background:#fff; }
  .acc-top { display:flex; align-items:center; gap:10px; margin-bottom:9px; }
  .sev { font-size:10px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; padding:2px 8px; border-radius:999px; }
  .sev.high { background:#f7e2da; color:#9c3a1c; }
  .sev.med { background:#f3ecdd; color:#8a6d2a; }
  .sev.low { background:#eceae3; color:var(--muted); }
  .acc-type { font-size:11px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:var(--muted2); }
  .acc-claim { font-size:14px; color:var(--ink2); margin:0 0 6px; }
  .acc-claim .k { font-weight:700; color:var(--rust); }
  .acc-reality { font-size:14px; color:var(--muted); margin:0; }
  .acc-reality .k { font-weight:700; color:#2e8c66; }

  /* §5 gap map + cited sources */
  .gapmap { width:100%; border-collapse:collapse; font-size:13.5px; }
  .gapmap th { text-align:left; padding:9px 10px; border-bottom:1px solid var(--ink); font-size:10.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted2); font-weight:700; }
  .gapmap td { padding:9px 10px; border-bottom:1px solid var(--rule2); }
  .yes { color:#2e8c66; font-weight:700; }
  .no { color:var(--rust); font-weight:700; }
  .sources { display:flex; flex-wrap:wrap; gap:7px; margin-top:12px; }
  .src-chip { font-size:12px; border:1px solid var(--rule); border-radius:999px; padding:4px 11px; color:var(--muted); background:#fff; }
  .src-chip b { color:var(--ink); font-weight:600; }

  /* §6 diagnosis */
  .diag-cat { border:1px solid var(--rule); border-radius:10px; margin-bottom:11px; overflow:hidden; background:#fff; }
  .diag-head { display:flex; align-items:center; gap:10px; padding:11px 15px; border-bottom:1px solid var(--rule2); }
  .diag-head .name { font-weight:700; font-size:13.5px; color:var(--ink); }
  .diag-verdict { margin-left:auto; font-size:10px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; padding:2px 9px; border-radius:999px; }
  .diag-verdict.fail { background:#f7e2da; color:#9c3a1c; }
  .diag-verdict.partial { background:#f3ecdd; color:#8a6d2a; }
  .diag-verdict.pass { background:#e3efe7; color:#2e7d57; }
  .diag-checks { list-style:none; margin:0; padding:6px 15px 12px; }
  .diag-check { display:flex; gap:10px; padding:6px 0; font-size:13px; border-bottom:1px solid var(--rule2); }
  .diag-check:last-child { border-bottom:none; }
  .diag-status { flex:none; width:54px; font-size:10px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; padding-top:1px; }
  .diag-status.fail { color:#9c3a1c; }
  .diag-status.partial { color:#8a6d2a; }
  .diag-status.pass { color:#2e7d57; }
  .diag-status.ungradeable { color:var(--faintest); }
  .diag-detail { color:var(--muted); line-height:1.5; }
  .diag-detail .ck { color:var(--ink2); font-weight:600; }

  /* §7 roadmap */
  .phase { margin-bottom:16px; }
  .phase-title { font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--ink); margin:0 0 8px; }
  .road { width:100%; border-collapse:collapse; font-size:13px; }
  .road td { padding:9px 10px; border-bottom:1px solid var(--rule2); vertical-align:top; }
  .road td:first-child { padding-left:0; }
  .road .badge { font-size:10px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; padding:2px 8px; border-radius:999px; white-space:nowrap; }
  .road .impact.High { background:#f7e2da; color:#9c3a1c; }
  .road .impact.Medium { background:#f3ecdd; color:#8a6d2a; }
  .road .impact.Low { background:#eceae3; color:var(--muted); }
  .road .effort { color:var(--muted2); font-size:12px; }

  /* §8 engagement */
  .engage p { font-size:14.5px; line-height:1.6; color:var(--muted); margin:0 0 14px; max-width:64ch; }
  .engage .lab { font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--faint); display:block; margin-bottom:5px; }

  @media print {
    .audit-section { break-inside:avoid; }
    .sec-break { break-before:page; }
    .grade-card, .acc-item, .diag-cat, .proof { break-inside:avoid; }
  }
`;

// --- sections -------------------------------------------------------------------

function renderVerdict(d: AuditDraft, edits: AuditEdits): string {
  const headline = nonEmpty(edits.headline) ?? d.headline;
  const verdict = nonEmpty(edits.verdictSentence) ?? d.verdictSentence;
  const achievable = nonEmpty(edits.achievableGrade) ?? d.achievableGrade;
  const enginesLine = d.engines.map(engineLabel).filter((v, i, a) => a.indexOf(v) === i).join(" · ");

  // Bold the client name inside the gap-led headline (it leads with the SoV gap).
  const heroHtml = escapeHtml(headline).replace(
    escapeHtml(d.clientName),
    `<span class="you">${escapeHtml(d.clientName)}</span>`,
  );

  const gradeCard = d.grade
    ? `
      <div class="grade-card">
        <div class="grade-col">
          <div class="grade-now">${escapeHtml(d.grade.letter)}</div>
          <div class="cap">Today</div>
        </div>
        ${
          achievable
            ? `<div class="grade-arrow">→</div>
        <div class="grade-col">
          <div class="grade-goal">${escapeHtml(achievable)}</div>
          <div class="cap">Achievable · 90 days</div>
        </div>`
            : ""
        }
        <p class="grade-rationale">${escapeHtml(d.grade.rationale)}</p>
      </div>`
    : `<p class="sec-sub">Grade uncalibrated — internal only.</p>`;

  return `
  <header class="hero">
    <div class="eyebrow"><span>AI Visibility Audit</span><span class="date">${escapeHtml(d.runDate)}</span></div>
    <div class="cover-hero">
      <h1>${heroHtml}</h1>
    </div>
  </header>
  <section class="audit-section">
    ${gradeCard}
    <p class="verdict">${escapeHtml(verdict)}</p>
    <p class="what-inside"><b>Inside:</b> where you stand · the evidence · what AI gets wrong · who's winning &amp; why · the full diagnosis · a prioritized 90-day roadmap.</p>
    <p class="sec-sub">${escapeHtml(d.clientName)} · ${escapeHtml(d.category)} · ${escapeHtml(enginesLine)}</p>
  </section>`;
}

function leaderRow(r: LeaderRow, topCompetitor: string | null): string {
  const cls = r.is_client ? "is-client" : r.brand === topCompetitor ? "lead-rival" : "";
  const width = pct(r.mention_rate);
  return `
    <div class="vrow ${cls}">
      <span class="name">${escapeHtml(r.brand)}${r.is_client ? " (you)" : ""}</span>
      <span class="track"><i style="width:${width}%"></i></span>
      <span class="val">${width}%</span>
    </div>`;
}

function renderBaseline(d: AuditDraft): string {
  const rows = [...d.leaderboard].sort((a, b) => b.mention_rate - a.mention_rate).slice(0, 8);
  const chart = `<div class="chart">${rows.map((r) => leaderRow(r, d.topCompetitor)).join("")}</div>`;
  const bucketRows = d.byBucket
    .map(
      (b) => `
      <tr>
        <td class="query">${escapeHtml(bucketLabel(b.bucket as IntentBucket))}</td>
        <td class="rec">${pct(b.mention_rate)}%</td>
        <td>${b.citation_rate == null ? "—" : pct(b.citation_rate) + "%"}</td>
      </tr>`,
    )
    .join("");
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§2 · Where you stand</div><h2 class="sec-title">Your share of the AI answer</h2></div>
    ${chart}
    <p class="caption">Mention rate across all engines, you vs your competitors.</p>
    <table class="bucket-grid">
      <thead><tr><th>Buyer-journey stage</th><th>You mentioned</th><th>You cited</th></tr></thead>
      <tbody>${bucketRows || `<tr><td colspan="3">No per-stage data.</td></tr>`}</tbody>
    </table>
  </section>`;
}

function renderEvidence(d: AuditDraft): string {
  if (!d.evidence.length) return "";
  const groups = d.evidence
    .map(
      (g: EvidenceGroup) => `
      <div class="kicker">${escapeHtml(bucketLabel(g.bucket))} queries</div>
      ${g.findings.map((f) => renderProofCard(d.clientName, f, d.runDate)).join("")}`,
    )
    .join("");
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§3 · See it for yourself</div><h2 class="sec-title">The answers buyers actually get</h2>
      <p class="sec-sub">Verbatim AI answers where ${escapeHtml(d.clientName)} is left out, grouped by where the buyer is in their journey — a pattern, not a one-off.</p></div>
    ${groups}
  </section>`;
}

function flagItem(f: FlagRow): string {
  const sev = f.severity === "high" ? "high" : f.severity === "med" ? "med" : "low";
  const typeLabel = f.type.replace(/_/g, " ");
  return `
    <div class="acc-item">
      <div class="acc-top"><span class="sev ${sev}">${escapeHtml(f.severity)}</span><span class="acc-type">${escapeHtml(typeLabel)}</span></div>
      <p class="acc-claim"><span class="k">AI says:</span> ${escapeHtml(f.claim)}</p>
      <p class="acc-reality"><span class="k">Reality:</span> ${escapeHtml(f.reality)}</p>
    </div>`;
}

function renderAccuracy(d: AuditDraft): string {
  if (!d.accuracy.assessed || d.accuracy.flags.length === 0) return "";
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§4 · What AI gets wrong</div><h2 class="sec-title">Facts AI states about you that aren't true</h2>
      <p class="sec-sub">Every claim below is what an engine asserted about ${escapeHtml(d.clientName)}, checked against your own fact sheet.</p></div>
    <div class="acc">${d.accuracy.flags.map(flagItem).join("")}</div>
  </section>`;
}

function renderCompetitive(d: AuditDraft): string {
  const offsite = d.competitiveGap.offsite;
  const sources = d.competitiveGap.citedSources;
  if (!offsite.length && !sources.length) return "";
  const gapRows = offsite
    .map(
      (o: SiteFindingRow) => `
      <tr>
        <td>${escapeHtml(o.finding_type.replace(/_/g, " "))}</td>
        <td>${escapeHtml(o.title)}</td>
        <td>${escapeHtml(o.confidence)}</td>
      </tr>`,
    )
    .join("");
  const gapTable = offsite.length
    ? `<table class="gapmap"><thead><tr><th>Off-site signal</th><th>What we found</th><th>Confidence</th></tr></thead><tbody>${gapRows}</tbody></table>`
    : "";
  const srcChips = sources
    .map((s: SourceRow) => `<span class="src-chip"><b>${escapeHtml(s.domain)}</b> · ${s.count}</span>`)
    .join("");
  const srcBlock = sources.length
    ? `<p class="caption" style="margin-top:18px">Where AI is getting its answers (most-cited domains):</p><div class="sources">${srcChips}</div>`
    : "";
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§5 · Who's winning &amp; why</div><h2 class="sec-title">The off-site authority gap</h2>
      <p class="sec-sub">AI recommends brands it sees endorsed across the web — Reddit, the app stores, review platforms, listicles, press.</p></div>
    ${gapTable}
    ${srcBlock}
  </section>`;
}

function diagCategory(c: DiagnosisCategory): string {
  const failing = c.checks.filter((ck) => ck.status === "fail" || ck.status === "partial");
  const shown = failing.length ? failing : c.checks.slice(0, 3);
  const checks = shown
    .map(
      (ck) => `
      <li class="diag-check">
        <span class="diag-status ${ck.status}">${escapeHtml(ck.status)}</span>
        <span class="diag-detail"><span class="ck">${escapeHtml(ck.check_key.replace(/_/g, " "))}</span> — ${escapeHtml(ck.detail)}</span>
      </li>`,
    )
    .join("");
  return `
    <div class="diag-cat">
      <div class="diag-head"><span class="name">${escapeHtml(categoryLabel(c.category))}</span><span class="diag-verdict ${c.verdict}">${escapeHtml(c.verdict)}</span></div>
      <ul class="diag-checks">${checks || `<li class="diag-check"><span class="diag-detail">All checks pass.</span></li>`}</ul>
    </div>`;
}

function renderDiagnosis(d: AuditDraft): string {
  if (!d.diagnosis.present || !d.diagnosis.categories.length) return "";
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§6 · Why AI skips you</div><h2 class="sec-title">The full diagnosis</h2>
      <p class="sec-sub">${d.diagnosis.pagesCrawled} pages crawled · the 7-category technique checklist AI uses to decide who to recommend.</p></div>
    ${d.diagnosis.categories.map(diagCategory).join("")}
  </section>`;
}

function phaseTitle(phase: number): string {
  const m: Record<number, string> = {
    1: "Phase 1 · Accessibility",
    2: "Phase 2 · Content",
    3: "Phase 3 · Structured data",
    4: "Phase 4 · Off-site",
  };
  return m[phase] ?? `Phase ${phase}`;
}

function renderRoadmap(d: AuditDraft): string {
  if (!d.roadmap.present || !d.roadmap.phases.length) return "";
  const phases = d.roadmap.phases
    .map(
      (p: RoadmapPhase) => `
      <div class="phase">
        <p class="phase-title">${escapeHtml(phaseTitle(p.phase))}</p>
        <table class="road"><tbody>${p.rows
          .map(
            (r) => `
          <tr>
            <td>${escapeHtml(r.check_name)}</td>
            <td><span class="badge impact ${escapeHtml(r.impact_label)}">${escapeHtml(r.impact_label)} impact</span></td>
            <td class="effort">${escapeHtml(r.effort)} effort</td>
          </tr>`,
          )
          .join("")}</tbody></table>
      </div>`,
    )
    .join("");
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§7 · The roadmap</div><h2 class="sec-title">What we'd do — in order</h2>
      <p class="sec-sub">Sequenced so the highest-leverage, lowest-effort fixes land first.</p></div>
    ${phases}
  </section>`;
}

function renderEngagement(d: AuditDraft, edits: AuditEdits): string {
  const impact = nonEmpty(edits.projectedImpact) ?? d.engagement.projectedImpact;
  const next = nonEmpty(edits.nextSteps) ?? d.engagement.nextSteps;
  return `
  <section class="audit-section sec-break">
    <div class="sec-head"><div class="sec-num">§8 · What this unlocks</div><h2 class="sec-title">Projected impact &amp; next steps</h2></div>
    <div class="engage">
      <span class="lab">Projected impact</span>
      <p>${escapeHtml(impact)}</p>
      <span class="lab">Engagement</span>
      <p>${escapeHtml(next)}</p>
    </div>
    <div class="foot" style="padding:0">
      Findings derived from live AI-engine answers · engines: ${escapeHtml(d.engines.map(engineLabel).join(", "))} ·
      query set ${escapeHtml(d.report.query_set_version)} ·
      <strong>Draft — human review required before sending.</strong>
    </div>
  </section>`;
}

export function renderAuditHtml(d: AuditDraft, edits: AuditEdits = {}): string {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(d.clientName)} — AI Visibility Audit</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="${FONTS}" rel="stylesheet" />
  <style>${STYLE}${AUDIT_STYLE}</style>
</head>
<body>
  <div class="wrap">
    <main class="page">
      ${renderVerdict(d, edits)}
      ${renderBaseline(d)}
      ${renderEvidence(d)}
      ${renderAccuracy(d)}
      ${renderCompetitive(d)}
      ${renderDiagnosis(d)}
      ${renderRoadmap(d)}
      ${renderEngagement(d, edits)}
    </main>
  </div>
</body>
</html>`;
}
