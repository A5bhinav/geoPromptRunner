"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Notice } from "@/components/notice";
import { INPUT_CLS, FIELD_LABEL_CLS, FIELD_HINT_CLS } from "@/lib/ui";
import { cn } from "@/lib/utils";
import { UploadDropzone } from "@/components/upload-dropzone";
import { AssembleFromLead } from "@/components/assemble-from-lead";
import { PreviewPanels } from "@/components/preview-panels";
import { RecentAudits } from "@/components/recent-audits";
import {
  createAudit,
  previewAudit,
  listFactSheets,
  type ParsePreview,
  type FactSheetSummary,
} from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [files, setFiles] = React.useState<File[]>([]);
  const [preview, setPreview] = React.useState<ParsePreview | null>(null);
  const [previewing, setPreviewing] = React.useState(false);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Approved sheets only. A draft is not ground truth — approval is the gate —
  // and the API refuses one anyway, so offering it here would only produce a 422.
  const [sheets, setSheets] = React.useState<FactSheetSummary[]>([]);
  const [factSheetId, setFactSheetId] = React.useState<string | null>(null);

  React.useEffect(() => {
    listFactSheets("active")
      .then(setSheets)
      .catch(() => setSheets([]));
  }, []);

  React.useEffect(() => {
    if (files.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewing(true);
    setError(null);
    previewAudit(files)
      .then((p) => !cancelled && setPreview(p))
      .catch(() => !cancelled && setError("Could not reach the API. Is the backend running?"))
      .finally(() => !cancelled && setPreviewing(false));
    return () => {
      cancelled = true;
    };
  }, [files]);

  const addFiles = (incoming: File[]) =>
    setFiles((prev) => {
      const byName = new Map(prev.map((f) => [f.name, f]));
      for (const f of incoming) byName.set(f.name, f);
      return Array.from(byName.values());
    });

  const removeFile = (name: string) =>
    setFiles((prev) => prev.filter((f) => f.name !== name));

  const runAudit = async () => {
    setCreating(true);
    setError(null);
    try {
      const res = await createAudit(files, factSheetId);
      if ("run_id" in res) {
        router.push(`/audits/${res.run_id}`);
      } else if ("refused" in res) {
        // The CSV parsed; the SHEET was rejected. Say so as a sentence rather
        // than rendering it as a parse error over the upload.
        setError(res.refused);
      } else {
        setPreview(res.errors);
      }
    } catch {
      setError("Could not start the audit. Is the backend running?");
    } finally {
      setCreating(false);
    }
  };

  const sheetPicker =
    sheets.length > 0 ? (
      <div className="rounded-lg border border-[var(--rule)] bg-white p-4">
        <p className={FIELD_LABEL_CLS}>Fact sheet</p>
        <p className={cn(FIELD_HINT_CLS, "mt-1")}>
          Judge this run&apos;s accuracy against an approved sheet instead of{" "}
          <code>fact</code> rows in the CSV. Only approved sheets appear here, and a
          run cannot use both.
        </p>
        <select
          className={cn(INPUT_CLS, "mt-3")}
          value={factSheetId ?? ""}
          onChange={(e) => setFactSheetId(e.target.value || null)}
        >
          <option value="">No fact sheet (use the CSV&apos;s fact rows)</option>
          {sheets.map((s) => (
            <option key={s.id} value={s.id}>
              {s.business_name || s.domain} — v{s.version} · {s.domain}
            </option>
          ))}
        </select>
      </div>
    ) : null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="label">Run</p>
        <h1 className="display text-[34px] leading-tight">Upload your prompts</h1>
        <p className="max-w-xl text-[13px] leading-relaxed text-[color:var(--ink-secondary)]">
          Upload your prompts, fact sheet, and run config as CSV. Review the merged set, then run
          it across the engines.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* The assembled CSV enters as a normal file, so it goes through the
              same preview and validation a hand-made one does. */}
          <AssembleFromLead
            onAssembled={(file) => addFiles([file])}
            onSheetChosen={setFactSheetId}
          />
          <UploadDropzone
            files={files}
            provenance={preview?.provenance ?? []}
            onAdd={addFiles}
            onRemove={removeFile}
          />
        </CardContent>
      </Card>

      {error && <Notice tone="problem">{error}</Notice>}

      {previewing && !preview && (
        <div className="flex items-center gap-2 text-[13px] text-[color:var(--ink-secondary)]">
          <Loader2 className="h-4 w-4 animate-spin" /> Parsing…
        </div>
      )}

      {preview && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium">Preview &amp; validate</h2>
            <Button onClick={runAudit} disabled={!preview.ok || creating} variant="hero" size="lg">
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Run audit
            </Button>
          </div>
          {sheetPicker}
          <PreviewPanels preview={preview} />
        </div>
      )}

      <RecentAudits />
    </div>
  );
}
