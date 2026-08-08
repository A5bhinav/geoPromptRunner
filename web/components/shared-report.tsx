"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";
import { ReportView } from "@/components/report-view";
import { RenderModeProvider } from "@/lib/render-mode";
import { getSharedReport, type ReportPayload } from "@/lib/api";

/**
 * A report behind a signed link (P3-T4, hardened by LIC-T17).
 *
 * **No API key, no login.** A login wall is what kills forwardability, and
 * forwardability is the one thing a PDF has over a dashboard — a CMO forwards
 * this to a founder who has no account, and if it asks them to sign in the
 * report stops travelling.
 *
 * Read-only by construction, not by permission: it renders `ReportView` with no
 * `runId`, so the Judge / re-judge / export controls never mount. There is no
 * privileged action reachable from this page to guard.
 *
 * **The token leaves the URL on first load.** `/shared/{token}` presents the
 * token once; the API sets it as an httpOnly cookie and this component rewrites
 * the address bar to `/shared/view`, which reads through the cookie. While the
 * token sits in the URL it is a working credential that leaks into browser
 * history, screenshots, and the `Referer` of anything the page loads.
 */
export function SharedReport({ token }: { token?: string }) {
  const [report, setReport] = React.useState<ReportPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [needsPassword, setNeedsPassword] = React.useState(false);
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(true);

  // Kept in a ref rather than state so flipping it never re-runs `load` and
  // re-fetches the report.
  const exchanged = React.useRef(!token);

  const load = React.useCallback(
    (pw: string) => {
      setLoading(true);
      setError(null);
      getSharedReport(exchanged.current ? "" : (token ?? ""), pw)
        .then((payload) => {
          setReport(payload);
          setNeedsPassword(false);
          if (!exchanged.current) {
            exchanged.current = true;
            // `replaceState`, not `push` — a back button that restored the token
            // would undo the whole point.
            window.history.replaceState(null, "", "/shared/view");
          }
        })
        .catch((err: Error) => {
          // The API returns 403 with the reason in the body for EVERY failure —
          // expired, revoked, wrong password, forged — so a visitor cannot tell
          // which run ids exist from the status code. Surface the reason it gave
          // rather than inventing a friendlier one that might be wrong.
          const message = err.message || "This link is not valid.";
          setError(message);
          setNeedsPassword(message.toLowerCase().includes("password"));
        })
        .finally(() => setLoading(false));
    },
    [token],
  );

  React.useEffect(() => load(""), [load]);

  if (loading && !report) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  if (needsPassword) {
    return (
      <form
        className="mx-auto max-w-sm space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          load(password);
        }}
      >
        <p className="text-sm">This report is password-protected.</p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border px-2 py-1.5 text-sm"
          style={{ borderColor: "var(--rule)" }}
          placeholder="Password"
          autoFocus
        />
        <button
          type="submit"
          className="rounded px-3 py-1.5 text-sm"
          style={{ backgroundColor: "var(--navy)", color: "#fff" }}
        >
          Open report
        </button>
        {error && !error.toLowerCase().includes("needs a password") && (
          <p className="text-sm">{error}</p>
        )}
      </form>
    );
  }

  if (error || !report) {
    return (
      <div className="mx-auto max-w-md space-y-2 text-sm">
        <p>{error ?? "This link is not valid."}</p>
        <p style={{ color: "var(--harbour)" }}>
          Links expire, and the person who sent it can withdraw it. Ask them for a new one.
        </p>
      </div>
    );
  }

  return (
    <RenderModeProvider mode="screen">
      {/* No runId: the Judge, re-judge and export controls are gated on it, so a
          shared viewer gets the report and nothing that spends money. */}
      <ReportView report={report} />
    </RenderModeProvider>
  );
}
