/**
 * The client-facing brand, behind one object.
 *
 * Sable's identity is distinctive enough that a white-labelled report cannot
 * simply swap an accent colour: the three plumes, the Garamond wordmark and the
 * navy masthead are all Sable's. When an agency resells, the Sable brand comes
 * OFF the end-client artifact entirely and lives on the methodology page. That
 * means the template needs two skins, and the abstraction has to exist before
 * the second skin does — retrofitting a hardcoded brand later is expensive, and
 * building it now is free.
 *
 * Everything client-facing reads from here: the cover, the masthead, the footer
 * and the chart highlight. Nothing hardcodes "Sable".
 *
 * See docs/audit-packaging-spec.md P0-T4 / P5-T3 and
 * docs/licensing-implementation.md §4.1.
 */

export type BrandConfig = {
  /** Tenant key. `sable` is the default; agencies get their own. */
  id: string;
  /** Displayed in the masthead and the footer. */
  name: string;
  /** Short descriptor under the wordmark. */
  descriptor: string;
  /**
   * The CSS class carrying this tenant's tokens. `sable` is defined in
   * web/styles/sable.css; a white-label tenant ships its own class rather than
   * overriding individual variables, so the two skins can never half-apply.
   */
  themeClass: string;
  /** Render the three-plume mark. False for a neutral tenant. */
  showMark: boolean;
  /** "Measurement by <name>" in the methodology section. Off by agency request. */
  poweredBy: boolean;
  /**
   * The one colour a chart may highlight the client row with. A token name, not
   * a hex value — a tenant that hands us a hex would put a colour outside its
   * own palette into its own report.
   */
  chartHighlightToken: string;
};

export const SABLE: BrandConfig = {
  id: "sable",
  name: "Sable",
  descriptor: "AI SEO",
  themeClass: "sable",
  showMark: true,
  poweredBy: true,
  chartHighlightToken: "--navy",
};

/**
 * A resold report: no Sable mark, no wordmark, no "powered by" on the artifact.
 * Kept here rather than in a tenant database so the second skin is exercised by
 * the type checker and by tests from day one — an abstraction with exactly one
 * implementation is not an abstraction.
 */
export const NEUTRAL: BrandConfig = {
  id: "neutral",
  name: "AI Visibility Report",
  descriptor: "",
  // Its OWN class (web/styles/neutral.css), not Sable's. Pointing this at
  // `sable` is what made the white-label a stub: every "neutral" render shipped
  // Sable's navy, Sable's Cormorant wordmark and Sable's masthead accent under a
  // different name. A tenant ships a whole class rather than overriding
  // individual variables, so the two skins can never half-apply.
  themeClass: "neutral",
  showMark: false,
  poweredBy: false,
  chartHighlightToken: "--navy",
};

export const DEFAULT_BRAND = SABLE;
