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

export function buildMatcher(name: string, aliases: string[] = []): (text: string) => boolean {
  const variants = [name, ...aliases].map((v) => v.trim()).filter(Boolean);
  if (variants.length === 0) return () => false;
  const pattern = new RegExp(
    `\\b(${variants.map(escapeRegExp).join("|")})\\b`,
    "i",
  );
  return (text: string) => pattern.test(text);
}
