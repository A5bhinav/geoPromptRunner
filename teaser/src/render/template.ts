/**
 * Teaser one-pager template — fills the TeaserDraft into a single self-contained
 * HTML document, styled to the "Ledger" editorial design (imported from the
 * claude.ai/design project "GEO teaser document revamp"): warm cream paper,
 * Newsreader serif headlines + italic accents, Public Sans body, a rust accent.
 *
 * Self-contained except for the Google Fonts <link> (the design uses Public Sans
 * + Newsreader). Print-clean for PDF export (the PDF is the deliverable).
 */

import type { Finding, TeaserDraft } from "../types/domain.ts";
import type { LeaderRow } from "../types/platform.ts";
import {
  ctaLine,
  engineLabel,
  headlineNumberSentence,
  proofCaption,
} from "./copy.ts";
import { renderProofCard } from "./proofCard.ts";
import { selectWhyGaps } from "../select/selectFindings.ts";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pct(n: number): number {
  return Math.max(0, Math.min(100, Math.round(n * 100)));
}

export const FONTS =
  'https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&display=swap';

export const STYLE = `
  :root {
    --paper:#FBFAF7; --bg:#e7e5df; --ink:#1b1a17; --ink2:#36322c;
    --muted:#54504a; --muted2:#7a756c; --faint:#8a857c; --faintest:#a99a93;
    --rule:#E6E2D9; --rule2:#EFEBE2; --track:#ECE8DF; --neutral:#b3ada2;
    --rust:#B85C3C; --rust-line:rgba(184,92,60,.4);
    --serif:'Newsreader',Georgia,serif; --sans:'Public Sans',-apple-system,Segoe UI,Roboto,sans-serif;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; padding:0; }
  body { background:var(--bg); font-family:var(--sans); color:var(--ink); }
  .wrap { min-height:100vh; padding:40px 24px; display:flex; justify-content:center; }
  .page { width:100%; max-width:760px; background:var(--paper); border-radius:5px; overflow:hidden; box-shadow:0 12px 50px rgba(27,26,23,.16); }
  .serif { font-family:var(--serif); }
  b, strong { font-weight:600; }

  /* ---- Hero ---- */
  .hero { padding:48px 52px 8px; }
  .eyebrow { font-size:11px; letter-spacing:.16em; text-transform:uppercase; font-weight:700; border-bottom:1px solid var(--rule); padding-bottom:16px; display:flex; justify-content:space-between; }
  .eyebrow .date { color:var(--faint); }
  .hero h1 { font-family:var(--serif); font-weight:500; font-size:35px; line-height:1.16; letter-spacing:-.005em; margin:24px 0 14px; }
  .hero .lead { font-size:16px; line-height:1.6; color:var(--muted); margin:0; max-width:62ch; }
  .hero .lead .q { font-style:italic; font-family:var(--serif); color:var(--ink2); }
  .hero .lead .rival { color:var(--rust); font-weight:600; border-bottom:1px solid var(--rust-line); }

  /* ---- Big-number hero stat ---- */
  .hero-stat { margin:24px 52px 0; padding:30px 0; border-top:1px solid var(--ink); border-bottom:1px solid var(--rule); text-align:center; }
  .hero-stat .label { font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:var(--faint); }
  .hero-stat .big { font-family:var(--serif); font-weight:500; font-size:96px; line-height:1; color:var(--rust); margin:8px 0 6px; font-variant-numeric:tabular-nums; }
  .hero-stat .big .of { font-size:30px; color:var(--faintest); }
  .hero-stat .sub { font-size:14.5px; color:var(--muted); }
  .hero-stat .sub b { color:var(--ink); }

  /* ---- Sections ---- */
  .section { padding:0 52px; }
  .section .kicker { font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--faint); font-weight:700; margin:30px 0 14px; }

  /* ---- Proof card ---- */
  .proof { margin:0; border:1px solid var(--rule); border-radius:10px; overflow:hidden; background:#fff; }
  .proof-chrome { display:flex; align-items:center; gap:9px; padding:12px 16px; border-bottom:1px solid var(--rule2); font-size:12px; }
  .proof-avatar { width:20px; height:20px; border-radius:6px; color:#fff; font-weight:800; font-size:11px; display:flex; align-items:center; justify-content:center; }
  .proof-engine { font-weight:700; }
  .proof-live { display:inline-flex; align-items:center; gap:5px; color:#2e8c66; font-weight:600; font-size:11px; }
  .proof-live .dot { width:6px; height:6px; border-radius:50%; background:#2e8c66; }
  .proof-date { margin-left:auto; color:var(--faintest); }
  .proof-body { padding:18px 20px; }
  .proof-q-label { font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin-bottom:7px; }
  .proof-q-text { font-family:var(--serif); font-style:italic; font-size:17px; margin-bottom:14px; }
  .proof-answer { margin:0; padding:0 0 0 16px; border-left:2px solid var(--rule); color:var(--muted); font-size:14.5px; line-height:1.65; }
  mark.competitor { background:transparent; color:var(--rust); font-weight:600; border-bottom:1px solid var(--rust-line); }
  .proof-callout { display:flex; align-items:center; gap:11px; flex-wrap:wrap; margin-top:16px; padding-top:14px; border-top:1px solid var(--rule2); font-size:14px; }
  .proof-callout .x { width:18px; height:18px; border-radius:50%; border:1.5px solid var(--rust); color:var(--rust); font-weight:800; font-size:11px; display:flex; align-items:center; justify-content:center; }
  .proof-callout strong { color:var(--ink); font-weight:600; }
  .proof-callout .rec { margin-left:auto; color:var(--muted2); font-size:12.5px; }
  .proof-sources { margin-top:13px; font-size:12px; color:var(--faintest); }
  .caption { font-size:12.5px; color:var(--muted2); margin:11px 2px 0; }

  /* ---- Pattern table ---- */
  table { width:100%; border-collapse:collapse; font-size:14px; }
  thead th { text-align:left; padding:11px 12px; border-bottom:1px solid var(--ink); font-size:10.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted2); font-weight:700; }
  thead th:first-child { padding-left:0; }
  thead th:last-child { padding-right:0; }
  tbody td { padding:11px 12px; border-bottom:1px solid var(--rule2); }
  tbody td:first-child { padding-left:0; color:var(--muted2); }
  tbody td:last-child { padding-right:0; }
  tbody tr:last-child td { border-bottom:none; }
  td.query { color:var(--ink); }
  td.rec { font-weight:700; color:var(--ink); }
  td.miss { color:var(--rust); font-weight:700; white-space:nowrap; }
  td.miss .dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--rust); margin-right:7px; }

  /* ---- Visibility chart ---- */
  .chart { display:flex; flex-direction:column; gap:11px; }
  .vrow { display:grid; grid-template-columns:130px 1fr 46px; align-items:center; gap:12px; font-size:13px; }
  .vrow .name { font-weight:600; color:var(--muted2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .vrow .track { height:10px; background:var(--track); border-radius:999px; overflow:hidden; }
  .vrow .track > i { display:block; height:100%; background:var(--neutral); border-radius:999px; }
  .vrow .val { text-align:right; font-variant-numeric:tabular-nums; color:var(--muted2); font-weight:600; }
  .vrow.lead-rival .name { color:var(--ink2); }
  .vrow.lead-rival .track > i { background:var(--ink); }
  .vrow.lead-rival .val { color:var(--muted); }
  .vrow.is-client .name { color:var(--rust); font-weight:800; }
  .vrow.is-client .track > i { background:var(--rust); }
  .vrow.is-client .val { color:var(--rust); font-weight:700; }

  /* ---- Why (fixable gaps) ---- */
  .why { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:11px; }
  .why-row { display:flex; align-items:center; gap:11px; font-size:14px; }
  .why-marker { width:6px; height:6px; border-radius:50%; background:var(--rust); flex:none; }
  .why-label { color:var(--ink2); }
  .why-tag { margin-left:auto; font-size:11px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--muted2); white-space:nowrap; }

  /* ---- Stakes ---- */
  .stakes { margin:32px 52px 0; padding:0 0 0 20px; border-left:2px solid var(--rust); }
  .stakes p { margin:0; font-family:var(--serif); font-style:italic; font-size:18px; line-height:1.5; color:var(--ink2); }

  /* ---- CTA ---- */
  .cta { margin:26px 52px 10px; border:1px solid var(--rule); border-radius:10px; padding:22px 24px; display:flex; align-items:center; gap:18px; background:#fff; }
  .cta .txt { font-size:15px; line-height:1.5; color:var(--muted); }
  .cta .txt b { color:var(--ink); }
  .cta .btn { margin-left:auto; background:var(--ink); color:var(--paper); font-weight:700; padding:12px 18px; border-radius:8px; white-space:nowrap; font-size:14px; }

  .foot { padding:14px 52px 32px; font-size:10.5px; color:var(--faintest); line-height:1.6; }

  @media print {
    body { background:#fff; }
    .wrap { padding:0; }
    .page { box-shadow:none; border-radius:0; max-width:none; }
  }
`;

function visibilityChart(leaderboard: LeaderRow[], topCompetitor: string | null): string {
  const rows = [...leaderboard].sort((a, b) => b.mention_rate - a.mention_rate).slice(0, 6);
  return `<div class="chart">${rows
    .map((r) => {
      const cls = r.is_client ? "is-client" : r.brand === topCompetitor ? "lead-rival" : "";
      const width = pct(r.mention_rate);
      return `
      <div class="vrow ${cls}">
        <span class="name">${escapeHtml(r.brand)}${r.is_client ? " (you)" : ""}</span>
        <span class="track"><i style="width:${width}%"></i></span>
        <span class="val">${width}%</span>
      </div>`;
    })
    .join("")}</div>`;
}

function patternRow(f: Finding, companyName: string): string {
  return `
    <tr>
      <td>${escapeHtml(engineLabel(f.engineName))}</td>
      <td class="query">${escapeHtml(f.verbatimQuery)}</td>
      <td class="rec">${escapeHtml(f.competitor)}</td>
      <td class="miss"><span class="dot"></span>absent</td>
    </tr>`;
}

/**
 * Reviewer copy overrides for the printable one-pager. Each field, when present,
 * replaces the draft's generated copy at render time — this is how human edits
 * made in the review UI actually reach the downloaded PDF/HTML. Mirrors the
 * `edited_fields` columns (TeaserEditedFields in web/lib/api.ts).
 */
export interface TeaserEdits {
  headline?: string;
  leadSentence?: string;
  stakesLine?: string;
  cta?: string;
}

function nonEmpty(s: string | undefined): string | null {
  return s && s.trim() ? s : null;
}

export function renderTeaserHtml(t: TeaserDraft, edits: TeaserEdits = {}): string {
  const h = t.headlineNumber;

  const headline = nonEmpty(edits.headline) ?? t.headline;
  const stakesLine = nonEmpty(edits.stakesLine) ?? t.stakesLine;
  const ctaText = nonEmpty(edits.cta) ?? nonEmpty(t.cta) ?? ctaLine(t.companyName);

  // A reviewer-edited lead sentence is rendered verbatim (escaped); otherwise we
  // build the default rich hero lead from the lead finding.
  const editedLead = nonEmpty(edits.leadSentence) ?? nonEmpty(t.leadSentence);
  const heroLead = editedLead
    ? escapeHtml(editedLead)
    : `Ask ${escapeHtml(engineLabel(t.lead.engineName))} ` +
      `<span class="q">“${escapeHtml(t.lead.verbatimQuery)}”</span> and it recommends ` +
      `<span class="rival">${escapeHtml(t.lead.competitor)}</span> — ` +
      `${escapeHtml(t.companyName)} is nowhere in the answer.`;

  const tableRows = [t.lead, ...t.table].map((f) => patternRow(f, t.companyName)).join("");

  // "Why AI skips you" — the top fixable on/off-site gaps behind the loss, from
  // the site-audit roadmap. Omitted when no site audit ran.
  const whyGaps = selectWhyGaps(t.report.site_audit);
  const whySection = whyGaps.length
    ? `
      <section class="section">
        <div class="kicker">Why AI leaves ${escapeHtml(t.companyName)} out</div>
        <ul class="why">
          ${whyGaps
            .map(
              (g) => `
          <li class="why-row">
            <span class="why-marker"></span>
            <span class="why-label">${escapeHtml(g.label)}</span>
            <span class="why-tag">${g.status === "fail" ? "missing" : "partial"} · ${escapeHtml(g.impact)} impact</span>
          </li>`,
            )
            .join("")}
        </ul>
        <p class="caption">The on-site &amp; off-site signals AI uses to decide who to recommend — the fixable gaps behind the pattern above.</p>
      </section>`
    : "";

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(t.companyName)} — AI visibility teaser</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="${FONTS}" rel="stylesheet" />
  <style>${STYLE}</style>
</head>
<body>
  <div class="wrap">
    <main class="page">
      <header class="hero">
        <div class="eyebrow"><span>AI Answer Audit</span><span class="date">${escapeHtml(t.runDate)}</span></div>
        <h1>${escapeHtml(headline)}</h1>
        <p class="lead">${heroLead}</p>
      </header>

      <section class="hero-stat">
        <div class="label">${escapeHtml(t.companyName)} appears in</div>
        <div class="big">${h.companyAppears} <span class="of">of ${h.n}</span></div>
        <div class="sub">high-intent buyer queries — <b>${escapeHtml(h.competitorName)} appears in ${h.competitorAppears}</b>.</div>
      </section>

      <section class="section">
        <div class="kicker">See it for yourself</div>
        ${renderProofCard(t.companyName, t.lead, t.runDate)}
        <p class="caption">${escapeHtml(proofCaption(t.companyName, t.lead))}</p>
      </section>

      <section class="section">
        <div class="kicker">Not a one-off — the same pattern repeats</div>
        <table>
          <thead>
            <tr><th>Engine</th><th>Buyer query</th><th>AI recommends</th><th>${escapeHtml(t.companyName)}</th></tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </section>

      <section class="section">
        <div class="kicker">Who AI recommends in your category</div>
        ${visibilityChart(t.report.leaderboard, t.report.scorecard.top_competitor)}
        <p class="caption">${escapeHtml(headlineNumberSentence(t.companyName, h))}</p>
      </section>
      ${whySection}

      <div class="stakes"><p>${escapeHtml(stakesLine)}</p></div>

      <div class="cta">
        <div class="txt">${escapeHtml(ctaText)}</div>
        <div class="btn">Book 15 min →</div>
      </div>

      <div class="foot">
        Findings derived from live AI-engine answers · hero engine: ${escapeHtml(engineLabel(t.heroEngine))} ·
        query set ${escapeHtml(t.report.query_set_version)} ·
        <strong>Draft — human review required before sending.</strong>
      </div>
    </main>
  </div>
</body>
</html>`;
}
