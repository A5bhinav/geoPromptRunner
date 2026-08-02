"use client";

import * as React from "react";

/**
 * One flag that drives every print fork in the report (audit-packaging P1-T8).
 *
 * **Print never scrolls the viewport, so `IntersectionObserver` never fires.**
 * That is a spec-level property of paged media, not a Chromium bug, and it means
 * anything below the fold that depends on it silently drops out of the PDF while
 * the live page looks perfect:
 *
 * - `loading="lazy"` images render blank,
 * - `next/dynamic(..., {ssr:false})` sections vanish,
 * - a virtualized table renders only its visible slice, so a 200-row appendix
 *   becomes 20 rows.
 *
 * All three are the same bug and all three are invisible until a client asks
 * where their data went. Hence ONE flag rather than three ad-hoc guards: a fork
 * that forgets to check `mode` is a bug you can grep for.
 *
 * `ResponsiveContainer` gets its own mention because it fails differently — it
 * sizes via `ResizeObserver`, which print layout never triggers, so charts print
 * at whatever the last on-screen size was. In print mode the charts take fixed
 * pixel dimensions matching the `@page` content box instead.
 */
export type RenderMode = "screen" | "print";

type RenderModeValue = {
  mode: RenderMode;
  /** Called by a chart on mount; the returned function marks it laid out. */
  registerChart: () => () => void;
};

const RenderModeContext = React.createContext<RenderModeValue>({
  mode: "screen",
  registerChart: () => () => {},
});

/** The `@page` content box at Letter, 0.6in side margins, at 96dpi.
 *
 * Charts are sized against THIS rather than the viewport, because the viewport
 * is whatever the worker happened to open and the page box is what actually gets
 * printed. Re-measure if the margins in `render-report-pdf.mjs` change — the two
 * are one decision expressed in two places, and there is no way to derive one
 * from the other at runtime. */
export const PRINT_CONTENT_WIDTH_PX = 700;
export const PRINT_CHART_HEIGHT_PX = 220;

export function RenderModeProvider({
  mode,
  children,
}: {
  mode: RenderMode;
  children: React.ReactNode;
}) {
  const pending = React.useRef(0);
  const lastChange = React.useRef(0);

  const registerChart = React.useCallback(() => {
    pending.current += 1;
    lastChange.current = performance.now();
    let settled = false;
    return () => {
      if (settled) return;
      settled = true;
      pending.current -= 1;
      lastChange.current = performance.now();
    };
  }, []);

  // The readiness signal the PDF worker waits on.
  //
  // `networkidle` is NOT enough on its own: it only means HTTP quiesced, while
  // client-rendered SVG finishes on later animation frames. Three conditions,
  // all required:
  //   1. no chart still laying out,
  //   2. fonts settled — font metrics decide axis-label layout, so a chart
  //      measured before they land is measured against the fallback face, and
  //      both Sable faces are metrically unlike system-ui,
  //   3. quiescence: two frames with no new registration, so a chart that
  //      mounts late (next/dynamic resolving its chunk) cannot let the counter
  //      transiently hit zero and declare the page done.
  //
  // Quiescence rather than an expected-chart count on purpose: a count couples
  // this to how many charts the report happens to render today, and would fail
  // silently — as "ready too early" — the first time someone adds one.
  React.useEffect(() => {
    if (mode !== "print") return;
    let raf = 0;
    let cancelled = false;
    let fontsReady = false;
    void document.fonts.ready.then(() => {
      fontsReady = true;
    });

    const tick = () => {
      if (cancelled) return;
      const quiet = performance.now() - lastChange.current > 32; // ~2 frames
      const ready = fontsReady && pending.current === 0 && quiet;
      if (ready) {
        document.body.dataset.reportReady = "true";
      } else {
        delete document.body.dataset.reportReady;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      delete document.body.dataset.reportReady;
    };
  }, [mode]);

  const value = React.useMemo(() => ({ mode, registerChart }), [mode, registerChart]);
  return <RenderModeContext.Provider value={value}>{children}</RenderModeContext.Provider>;
}

export function useRenderMode(): RenderMode {
  return React.useContext(RenderModeContext).mode;
}

export function useIsPrint(): boolean {
  return useRenderMode() === "print";
}

/**
 * Every chart calls this FIRST, unconditionally, before any early return.
 *
 * Unconditional because a chart that bails out on an empty dataset still has to
 * be accounted for — otherwise the readiness signal is computed over a different
 * set of charts than the page actually contains. (React's rules of hooks force
 * this anyway; the point is that it is also correct.)
 */
export function useChartSettled(): void {
  const { registerChart } = React.useContext(RenderModeContext);
  React.useLayoutEffect(() => {
    // useLayoutEffect, not useEffect: it runs after the DOM mutation and before
    // paint, which is exactly "this chart's SVG now exists".
    const settle = registerChart();
    settle();
    return undefined;
  }, [registerChart]);
}

/** Fixed pixel dimensions in print, `undefined` on screen (use the container). */
export function usePrintChartSize(height = PRINT_CHART_HEIGHT_PX): {
  width: number | undefined;
  height: number | undefined;
  isAnimationActive: boolean;
} {
  const isPrint = useIsPrint();
  return isPrint
    ? { width: PRINT_CONTENT_WIDTH_PX, height, isAnimationActive: false }
    : { width: undefined, height: undefined, isAnimationActive: true };
}
