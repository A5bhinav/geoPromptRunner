/** Shared form-control class strings.
 *
 * Before this file, app/teaser/page.tsx defined a local `inputCls` while
 * app/page.tsx, app/audit/page.tsx and components/upload-dropzone.tsx each
 * inlined their own <select> classes — and they already disagreed about border
 * radius. One export, four call sites, so they cannot drift again.
 */

/** Every text input and select in the app. */
export const INPUT_CLS =
  "h-9 w-full rounded-md border border-[var(--rule)] bg-white px-3 text-[13px] text-navy " +
  "placeholder:text-mist focus:border-blue focus:outline-none focus:ring-1 focus:ring-blue";

/** The field label above an input. Sentence case, Franklin, never Cormorant. */
export const FIELD_LABEL_CLS = "text-[13px] font-medium text-navy";

/** The helper line under an input. */
export const FIELD_HINT_CLS = "text-[11px] leading-relaxed text-harbour";
