"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * The canvas: every fact the owner has put on the record, as a point.
 *
 * WHY IT IS NEVER EMPTY. A blank area while someone answers the first question
 * reads as "nothing is happening" — the worst possible signal in a flow whose
 * whole job is to feel like a conversation. So the surface always carries an
 * IDLE constellation: seven ghost nodes and seven ghost edges, tracing on a long
 * loop. They are decoration and they are honest about it — they sit at 8–18%
 * opacity and carry no label, and the line at the top says in as many words that
 * nothing is on the record yet.
 *
 * WHY IT IS NOT INFORMATION. Nothing here is readable as data: you cannot tell
 * which fact is which node, and you are not meant to. It is a progress signal
 * with the emotional register of accumulation. Every fact it represents is
 * listed, in words, one toggle away in Details — which is the view a person uses
 * to actually check their sheet. Turn animation off and the Details list is
 * still complete; that is the reduced-motion contract holding.
 */

const HUB = { x: 310, y: 260 };

/** Golden-angle spiral: 137.5° per step never repeats an angle, so points spread
 * evenly however many there are, and the y-scale tilts the plane so it reads as
 * a web rather than a dartboard. */
function slot(k: number): { x: number; y: number } {
  const angle = (k * 137.5 * Math.PI) / 180;
  const radius = Math.min(210, 92 + k * 15);
  return {
    x: HUB.x + Math.cos(angle) * radius,
    y: HUB.y + Math.sin(angle) * radius * 0.58,
  };
}

const GHOST_NODES = Array.from({ length: 7 }, (_, k) => {
  const p = slot(k + 2);
  return { x: Math.round(p.x), y: Math.round(p.y), delay: `${k * 260}ms` };
});

const GHOST_EDGES = GHOST_NODES.map((n, k) => {
  const m = GHOST_NODES[(k + 3) % GHOST_NODES.length];
  return {
    x1: n.x,
    y1: n.y,
    x2: m.x,
    y2: m.y,
    len: Math.round(Math.hypot(m.x - n.x, m.y - n.y)),
    delay: `${k * 620}ms`,
  };
});

export function Constellation({
  count,
  className,
}: {
  count: number;
  className?: string;
}) {
  const nodes = React.useMemo(
    () =>
      Array.from({ length: count }, (_, k) => {
        const p = slot(k);
        return {
          x: p.x,
          y: p.y,
          r: k === 0 ? 4.5 : 3.5,
          // Later facts sit slightly stronger, so the shape reads as building.
          op: 0.35 + Math.min(0.5, k * 0.06),
        };
      }),
    [count],
  );

  const edges = React.useMemo(() => {
    const out: { x1: number; y1: number; x2: number; y2: number; op: number; len: number }[] = [];
    const mk = (x1: number, y1: number, x2: number, y2: number, op: number) => ({
      x1,
      y1,
      x2,
      y2,
      op,
      len: Math.round(Math.hypot(x2 - x1, y2 - y1)),
    });
    for (let k = 1; k < nodes.length; k += 1) {
      out.push(mk(HUB.x, HUB.y, nodes[k].x, nodes[k].y, 0.16));
      out.push(mk(nodes[k - 1].x, nodes[k - 1].y, nodes[k].x, nodes[k].y, 0.1));
    }
    return out;
  }, [nodes]);

  return (
    // The caller BOUNDS this and fades its lower edge. Left at `inset-0` the
    // edges drew straight through the chat bubbles and the composer labels,
    // which is most of what made the screen feel busy — a graph crossing a
    // sentence reads as noise no matter how faint it is.
    <div
      className={cn(
        "pointer-events-none absolute inset-0 flex items-center justify-center",
        className,
      )}
      style={{
        // Fades out before it reaches anything with words in it.
        maskImage: "linear-gradient(to bottom, #000 55%, transparent 100%)",
        WebkitMaskImage: "linear-gradient(to bottom, #000 55%, transparent 100%)",
      }}
    >
      <svg
        width="620"
        height="520"
        viewBox="0 0 620 520"
        role="img"
        aria-label={
          count === 0
            ? "No facts confirmed yet."
            : `${count} confirmed fact${count === 1 ? "" : "s"}, connected.`
        }
      >
        <g className="anim-web-spin" style={{ transformOrigin: "310px 260px" }}>
          {edges.map((e, i) => (
            <line
              key={`e${i}`}
              x1={e.x1}
              y1={e.y1}
              x2={e.x2}
              y2={e.y2}
              stroke="#0e2340"
              strokeOpacity={e.op}
              strokeWidth="1"
              // The dash is exactly one segment long, so the offset draws the
              // line end to end rather than marching a pattern along it.
              strokeDasharray={e.len}
              className="anim-edge-draw"
            />
          ))}
          {GHOST_EDGES.map((e, i) => (
            <line
              key={`ge${i}`}
              x1={e.x1}
              y1={e.y1}
              x2={e.x2}
              y2={e.y2}
              stroke="#0e2340"
              strokeOpacity="0.08"
              strokeWidth="1"
              strokeDasharray={e.len}
              className="anim-edge-trace"
              style={{ animationDelay: e.delay }}
            />
          ))}
          {GHOST_NODES.map((n, i) => (
            <circle
              key={`gn${i}`}
              cx={n.x}
              cy={n.y}
              r="2.5"
              fill="#0e2340"
              fillOpacity="0.18"
              className="anim-ghost-pulse"
              style={{ animationDelay: n.delay }}
            />
          ))}
          {nodes.map((n, i) => (
            <circle
              key={`n${i}`}
              cx={n.x}
              cy={n.y}
              r={n.r}
              fill="#0e2340"
              fillOpacity={n.op}
              className="anim-node-pop"
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
