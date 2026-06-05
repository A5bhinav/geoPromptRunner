"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BucketRow, LeaderRow, SourceRow } from "@/lib/api";

const INTENT_LABELS: Record<string, string> = {
  problem_aware: "Problem-aware",
  category: "Category",
  comparison: "Comparison",
  brand: "Brand",
  adjacent_authority: "Adjacent",
};

// A categorical palette for non-client brands / sources (client stays primary).
const PALETTE = [
  "hsl(243 75% 59%)", // indigo (primary)
  "hsl(199 89% 48%)", // sky
  "hsl(160 84% 39%)", // emerald
  "hsl(38 92% 50%)", // amber
  "hsl(280 65% 60%)", // violet
  "hsl(340 75% 55%)", // rose
  "hsl(215 20% 65%)", // slate
];

const AXIS_TICK = { fontSize: 12, fill: "hsl(var(--muted-foreground))" };

const tooltipStyle = {
  contentStyle: {
    borderRadius: 8,
    border: "1px solid hsl(var(--border))",
    fontSize: 12,
    background: "hsl(var(--card))",
  },
};

/** Horizontal share-of-model bars (client highlighted). */
export function LeaderboardChart({ rows }: { rows: LeaderRow[] }) {
  const data = rows.map((r) => ({
    brand: r.brand,
    share: Math.round(r.share_of_model * 100),
    isClient: r.is_client,
  }));
  const height = Math.max(120, data.length * 46);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 44, bottom: 4, left: 8 }}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis
          type="category"
          dataKey="brand"
          width={120}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 13, fill: "hsl(var(--foreground))" }}
        />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v}%`, "Share of model"]} />
        <Bar dataKey="share" radius={[4, 4, 4, 4]} barSize={22}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.isClient ? "hsl(var(--primary))" : "hsl(215 20% 70%)"} />
          ))}
          <LabelList
            dataKey="share"
            position="right"
            formatter={(v: number) => `${v}%`}
            style={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Donut of share-of-model across all brands. */
export function ShareDonut({ rows }: { rows: LeaderRow[] }) {
  const data = rows
    .map((r) => ({ name: r.brand, value: Math.round(r.share_of_model * 100), isClient: r.is_client }))
    .filter((d) => d.value > 0);

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No share to show.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={88}
          paddingAngle={2}
          strokeWidth={0}
        >
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={d.isClient ? "hsl(var(--primary))" : PALETTE[(i % (PALETTE.length - 1)) + 1]}
            />
          ))}
        </Pie>
        <Tooltip {...tooltipStyle} formatter={(v: number, n: string) => [`${v}%`, n]} />
        <Legend
          verticalAlign="middle"
          align="right"
          layout="vertical"
          iconType="circle"
          wrapperStyle={{ fontSize: 12 }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

/** Grouped bars of mention (and citation, when present) per intent bucket. */
export function BucketChart({ rows }: { rows: BucketRow[] }) {
  const hasCitation = rows.some((r) => r.citation_rate !== null);
  const data = rows.map((r) => ({
    bucket: INTENT_LABELS[r.bucket] ?? r.bucket,
    mention: Math.round(r.mention_rate * 100),
    citation: r.citation_rate === null ? 0 : Math.round(r.citation_rate * 100),
  }));

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No data.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
        <XAxis dataKey="bucket" tickLine={false} axisLine={false} tick={AXIS_TICK} interval={0} />
        <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={AXIS_TICK} unit="%" />
        <Tooltip {...tooltipStyle} formatter={(v: number) => `${v}%`} cursor={{ fill: "hsl(var(--secondary))" }} />
        {hasCitation && <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />}
        <Bar dataKey="mention" name="Mention" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} barSize={hasCitation ? 16 : 28} />
        {hasCitation && (
          <Bar dataKey="citation" name="Citation" fill="hsl(199 89% 48%)" radius={[4, 4, 0, 0]} barSize={16} />
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars of the most-cited domains. */
export function SourcesChart({ rows }: { rows: SourceRow[] }) {
  const data = rows.slice(0, 8).map((r) => ({ domain: r.domain, count: r.count }));
  if (data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No citations captured for this run.
      </p>
    );
  }
  const height = Math.max(120, data.length * 38);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 32, bottom: 4, left: 8 }}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="domain"
          width={140}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 12, fill: "hsl(var(--foreground))" }}
        />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [v, "cells"]} cursor={{ fill: "hsl(var(--secondary))" }} />
        <Bar dataKey="count" radius={[4, 4, 4, 4]} barSize={18}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            style={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
