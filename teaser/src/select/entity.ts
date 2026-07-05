/**
 * Minimal entity matcher for the headline count only.
 *
 * NOTE: the authoritative presence/absence for printed FINDINGS comes from the
 * platform's judge (the losing_queries list). This matcher is used solely to
 * compute the "appears in X of N" headline number from the verbatim answers, and
 * is deliberately conservative (word-boundary, case-insensitive, alias-aware).
 */

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Brand names that are also everyday English words. For these, a
 * case-INSENSITIVE `\bmint\b` fires on the herb/color "mint", the verb "loop",
 * "cash", etc. — false presence that corrupts the headline count. We match these
 * CASE-SENSITIVELY (brands are capitalized mid-sentence: "Mint", "Notion"),
 * which keeps the brand mention while dropping the common-word noise. Lowercased
 * for the lookup; a name qualifies if its lowercased form is in this set.
 */
const AMBIGUOUS_COMMON_WORDS: ReadonlySet<string> = new Set([
  "mint",
  "notion",
  "monday",
  "loop",
  "cash",
  "current",
  "simple",
  "oura",
  "whoop",
]);

/** Split a variant on comma/semicolon so a comma-joined competitor string
 * ("Whoop, Fitbit") becomes real alternatives instead of one literal that never
 * matches (the `\b(Whoop, Fitbit)\b` pattern can't fire inside prose). */
function splitVariant(v: string): string[] {
  return v
    .split(/[,;]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function buildMatcher(name: string, aliases: string[] = []): (text: string) => boolean {
  const variants = [name, ...aliases]
    .flatMap(splitVariant)
    .map((v) => v.trim())
    .filter(Boolean);
  if (variants.length === 0) return () => false;

  // Ambiguous common-word variants match case-sensitively (no `i` flag); the
  // rest stay case-insensitive. Two patterns so one ambiguous alias doesn't
  // force the whole matcher case-sensitive (which would miss "YNAB" as "ynab").
  const strict: string[] = [];
  const loose: string[] = [];
  for (const v of variants) {
    (AMBIGUOUS_COMMON_WORDS.has(v.toLowerCase()) ? strict : loose).push(v);
  }
  const matchers: RegExp[] = [];
  if (loose.length) matchers.push(new RegExp(`\\b(${loose.map(escapeRegExp).join("|")})\\b`, "i"));
  if (strict.length) matchers.push(new RegExp(`\\b(${strict.map(escapeRegExp).join("|")})\\b`));
  return (text: string) => matchers.some((re) => re.test(text));
}
