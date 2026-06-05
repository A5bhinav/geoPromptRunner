"use client";

import { AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { IntentBadge } from "@/components/badges";
import type { ParsePreview } from "@/lib/api";

function Provenance({ file }: { file: string }) {
  return <span className="text-xs text-muted-foreground">from {file}</span>;
}

export function PreviewPanels({ preview }: { preview: ParsePreview }) {
  const cfg = preview.config_resolved;
  return (
    <div className="space-y-4">
      {preview.errors.length > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <div className="mb-2 flex items-center gap-2 font-medium text-destructive">
            <AlertCircle className="h-4 w-4" />
            {preview.errors.length} issue{preview.errors.length === 1 ? "" : "s"} to fix before
            running
          </div>
          <ul className="space-y-1 text-sm text-destructive">
            {preview.errors.map((e, i) => (
              <li key={i}>
                • {e.file ? <span className="font-medium">{e.file}: </span> : null}
                {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Tabs defaultValue="config">
        <TabsList>
          <TabsTrigger value="config">Config</TabsTrigger>
          <TabsTrigger value="facts">Fact sheet ({preview.facts.length})</TabsTrigger>
          <TabsTrigger value="queries">Queries ({preview.queries.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="config">
          <Card>
            <CardContent className="space-y-4 pt-6">
              {cfg ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Client">{cfg.client_name}</Field>
                  <Field label="Category">{cfg.category}</Field>
                  <Field label="Runs per query">{cfg.runs_per_query}</Field>
                  <Field label="Client domains">
                    {cfg.client_domains.length ? cfg.client_domains.join(", ") : "—"}
                  </Field>
                  <Field label="Competitors">
                    <div className="flex flex-wrap gap-1.5">
                      {cfg.competitors.length ? (
                        cfg.competitors.map((c) => (
                          <Badge key={c} variant="secondary">
                            {c}
                          </Badge>
                        ))
                      ) : (
                        <span>—</span>
                      )}
                    </div>
                  </Field>
                  <Field label="Engines">
                    <div className="flex flex-wrap gap-1.5">
                      {cfg.engines.length ? (
                        cfg.engines.map((e) => (
                          <Badge key={e} variant="default">
                            {e}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-muted-foreground">all configured</span>
                      )}
                    </div>
                  </Field>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Config is incomplete — see the issues above.
                </p>
              )}
              <div className="border-t pt-3">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Key</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Source</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.config.map((c, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-medium">{c.key}</TableCell>
                        <TableCell>{c.value}</TableCell>
                        <TableCell>
                          <Provenance file={c.source_file} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="facts">
          <Card>
            <CardContent className="pt-6">
              {preview.facts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No fact sheet provided — the run still works, but accuracy will be{" "}
                  <span className="font-medium">not assessed</span>.
                </p>
              ) : (
                <dl className="space-y-4">
                  {preview.facts.map((f, i) => (
                    <div key={i} className="border-l-2 border-primary/30 pl-3">
                      <dt className="flex items-center gap-2 text-sm font-semibold capitalize">
                        {f.key || "fact"} <Provenance file={f.source_file} />
                      </dt>
                      <dd className="mt-0.5 text-sm text-muted-foreground">{f.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="queries">
          <Card>
            <CardContent className="pt-6">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Intent</TableHead>
                    <TableHead>Persona</TableHead>
                    <TableHead>Query</TableHead>
                    <TableHead>Source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.queries.map((q) => (
                    <TableRow key={q.query_id}>
                      <TableCell className="font-medium">{q.query_id}</TableCell>
                      <TableCell>
                        {q.valid_intent ? (
                          <IntentBadge intent={q.intent} />
                        ) : (
                          <Badge variant="destructive">{q.intent || "missing"}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {q.persona ?? "—"}
                      </TableCell>
                      <TableCell>{q.text}</TableCell>
                      <TableCell>
                        <Provenance file={q.source_file} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}
