"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronRight, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StateBadge } from "@/components/badges";
import { listAudits, type RunSummary } from "@/lib/api";

export function RecentAudits() {
  const [runs, setRuns] = React.useState<RunSummary[] | null>(null);

  React.useEffect(() => {
    listAudits()
      .then(setRuns)
      .catch(() => setRuns([]));
  }, []);

  if (runs === null) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="h-4 w-4 text-harbour" /> Recent audits
        </CardTitle>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="text-[13px] text-harbour">
            No audits yet — upload a CSV to run your first.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--rule)]">
            {runs.map((r) => (
              <li key={r.run_id}>
                {/* Row hover is a wash, not an opacity fade — fading the text
                    too reads as disabled. */}
                <Link
                  href={`/audits/${r.run_id}`}
                  className="-mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-navy/[0.03]"
                >
                  <span className="text-[13px] font-medium text-navy">{r.client_name}</span>
                  <StateBadge state={r.state} />
                  <span className="text-[13px] text-harbour">
                    {r.n_queries} queries · {r.engines.join(", ") || "no engines"}
                  </span>
                  <span className="ml-auto text-[11px] tabular-nums text-harbour">
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  <ChevronRight className="h-4 w-4 text-harbour" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
