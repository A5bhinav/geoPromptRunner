"use client";

import { SharedReport } from "@/components/shared-report";

/**
 * The clean URL a shared report lives at after the token has been exchanged for
 * an httpOnly cookie (LIC-T17).
 *
 * This route has to EXIST, not merely be a string passed to `replaceState`: the
 * visitor will refresh, bookmark and re-open it, and a rewritten URL with no
 * page behind it turns the security fix into a 404 the first time anyone hits
 * reload. No token in the path — the cookie is the credential now.
 */
export default function SharedReportViewPage() {
  return <SharedReport />;
}
