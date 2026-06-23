/**
 * Proof card — a branded re-render of the verbatim engine answer (BUILD_PLAN.md
 * §4d), styled to the "Ledger" editorial design: a clean engine-chrome header,
 * the buyer's question set in italic serif, the verbatim answer with the
 * competitor underlined in rust, and a quiet-but-pointed "absent" callout.
 *
 * All layout CSS lives in template.ts; this returns semantic markup (plus the
 * one per-engine avatar color, which is data-driven). MVP BrandedCardRenderer.
 */

import type { Finding } from "../types/domain.ts";
import { engineColor, engineLabel } from "./copy.ts";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Underline each occurrence of `competitor` in rust (HTML-safe). */
function highlightCompetitor(answerHtml: string, competitor: string): string {
  if (!competitor) return answerHtml;
  const re = new RegExp(`(${escapeRegExp(escapeHtml(competitor))})`, "gi");
  return answerHtml.replace(re, '<mark class="competitor">$1</mark>');
}

export function renderProofCard(companyName: string, finding: Finding, runDate: string): string {
  const safeAnswer = highlightCompetitor(escapeHtml(finding.verbatimAnswer), finding.competitor);
  const citations = finding.citations
    .map((u) => {
      try {
        return new URL(u).hostname.replace(/^www\./, "");
      } catch {
        return u;
      }
    })
    .filter((v, i, a) => a.indexOf(v) === i);

  const initial = engineLabel(finding.engineName).charAt(0).toUpperCase();

  return `
  <figure class="proof">
    <div class="proof-chrome">
      <span class="proof-avatar" style="background:${engineColor(finding.engineName)}">${escapeHtml(initial)}</span>
      <span class="proof-engine">${escapeHtml(engineLabel(finding.engineName))}</span>
      <span class="proof-live"><span class="dot"></span>live answer</span>
      <span class="proof-date">${escapeHtml(runDate)}</span>
    </div>
    <div class="proof-body">
      <div class="proof-q-label">Buyer asks</div>
      <div class="proof-q-text">“${escapeHtml(finding.verbatimQuery)}”</div>
      <blockquote class="proof-answer">${safeAnswer}</blockquote>
      <div class="proof-callout">
        <span class="x">✕</span>
        <strong>${escapeHtml(companyName)} appears nowhere in this answer.</strong>
        <span class="rec">${escapeHtml(finding.competitor)} recommended instead</span>
      </div>
      ${
        citations.length
          ? `<div class="proof-sources">Sources cited: ${citations.map(escapeHtml).join(" · ")}</div>`
          : ""
      }
    </div>
  </figure>`;
}
