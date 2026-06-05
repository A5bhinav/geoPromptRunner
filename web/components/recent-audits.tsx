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
          <Clock className="h-4 w-4 text-muted-foreground" /> Recent audits
        </CardTitle>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No audits yet — upload a CSV to run your first.
          </p>
        ) : (
          <ul className="divide-y">
            {runs.map((r) => (
              <li key={r.run_id}>
                <Link
                  href={`/audits/${r.run_id}`}
                  className="flex items-center gap-3 py-2.5 hover:opacity-80"
                >
                  <span className="font-medium">{r.client_name}</span>
                  <StateBadge state={r.state} />
                  <span className="text-sm text-muted-foreground">
                    {r.n_queries} queries · {r.engines.join(", ") || "no engines"}
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
