"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UploadDropzone } from "@/components/upload-dropzone";
import { PreviewPanels } from "@/components/preview-panels";
import { RecentAudits } from "@/components/recent-audits";
import { createAudit, previewAudit, type ParsePreview } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [files, setFiles] = React.useState<File[]>([]);
  const [preview, setPreview] = React.useState<ParsePreview | null>(null);
  const [previewing, setPreviewing] = React.useState(false);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

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
      const res = await createAudit(files);
      if ("run_id" in res) {
        router.push(`/audits/${res.run_id}`);
      } else {
        setPreview(res.errors);
      }
    } catch {
      setError("Could not start the audit. Is the backend running?");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New audit</h1>
        <p className="mt-1 text-muted-foreground">
          Upload your prompts, fact sheet, and run config as CSV. Review the merged set, then run
          it across the engines.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Upload</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadDropzone
            files={files}
            provenance={preview?.provenance ?? []}
            onAdd={addFiles}
            onRemove={removeFile}
          />
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {previewing && !preview && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Parsing…
        </div>
      )}

      {preview && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Preview &amp; validate</h2>
            <Button onClick={runAudit} disabled={!preview.ok || creating} size="lg">
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Run audit
            </Button>
          </div>
          <PreviewPanels preview={preview} />
        </div>
      )}

      <RecentAudits />
    </div>
  );
}
