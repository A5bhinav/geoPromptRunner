"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { LeaderRow } from "@/lib/api";

export function LeaderboardChart({ rows }: { rows: LeaderRow[] }) {
  const data = rows.map((r) => ({
    brand: r.brand,
    share: Math.round(r.share_of_model * 100),
    isClient: r.is_client,
  }));
  const height = Math.max(120, data.length * 44);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
      >
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis
          type="category"
          dataKey="brand"
          width={120}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 13, fill: "hsl(var(--foreground))" }}
        />
        <Bar dataKey="share" radius={[4, 4, 4, 4]} barSize={22}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={d.isClient ? "hsl(var(--primary))" : "hsl(215 20% 65%)"}
            />
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
