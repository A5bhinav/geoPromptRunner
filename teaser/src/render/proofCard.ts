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

/**
 * Engine answers come back as Markdown (bold, headings, tables, [1] citation
 * markers). The proof card is a quote, not a document, so we strip the Markdown
 * to clean prose and trim to a focused excerpt — otherwise raw `**`, `###`, and
 * `|` symbols bleed into the card and it reads as broken.
 */
export function cleanAnswerText(raw: string, maxChars = 420): string {
  let t = raw
    .replace(/```[\s\S]*?```/g, " ") // fenced code blocks
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ") // images
    .replace(/\[(\d+)\]/g, "") // [1] citation markers (sources shown separately)
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // [text](url) -> text
    .replace(/^\s{0,3}#{1,6}\s+/gm, "") // ### headings -> drop the marker
    .replace(/^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$/gm, "") // table separator rows |---|
    .replace(/^\s*\|(.+)\|\s*$/gm, (_m, c: string) =>
      c
        .split("|")
        .map((s) => s.trim())
        .filter(Boolean)
        .join(" — "),
    ) // table content rows -> " — " joined
    .replace(/\*\*([^*]+)\*\*/g, "$1") // **bold**
    .replace(/__([^_]+)__/g, "$1") // __bold__
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1$2") // *italic*
    .replace(/^\s*[-*+]\s+/gm, "") // bullet markers
    .replace(/^\s*\d+\.\s+/gm, "") // numbered-list markers
    .replace(/[ \t]+/g, " ")
    .replace(/\s*\n\s*/g, " ") // collapse to a single clean paragraph
    .replace(/\s{2,}/g, " ")
    .trim();
  if (t.length > maxChars) {
    const cut = t.slice(0, maxChars);
    const stop = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("! "), cut.lastIndexOf("? "));
    t = (stop > maxChars * 0.5 ? cut.slice(0, stop + 1) : cut.trimEnd()) + " …";
  }
  return t;
}

/** Underline each occurrence of `competitor` in rust (HTML-safe). */
function highlightCompetitor(answerHtml: string, competitor: string): string {
  if (!competitor) return answerHtml;
  const re = new RegExp(`(${escapeRegExp(escapeHtml(competitor))})`, "gi");
  return answerHtml.replace(re, '<mark class="competitor">$1</mark>');
}

export function renderProofCard(companyName: string, finding: Finding, runDate: string): string {
  const safeAnswer = highlightCompetitor(
    escapeHtml(cleanAnswerText(finding.verbatimAnswer)),
    finding.competitor,
  );
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
