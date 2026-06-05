"use client";

import * as React from "react";
import { UploadCloud, FileText, X, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { templateUrl, type FileProvenance } from "@/lib/api";

interface Props {
  files: File[];
  provenance: FileProvenance[];
  onAdd: (files: File[]) => void;
  onRemove: (name: string) => void;
}

export function UploadDropzone({ files, provenance, onAdd, onRemove }: Props) {
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const handleFiles = (list: FileList | null) => {
    if (!list) return;
    const csvs = Array.from(list).filter(
      (f) => f.name.toLowerCase().endsWith(".csv") || f.type === "text/csv",
    );
    if (csvs.length) onAdd(csvs);
  };

  const summaryFor = (name: string) =>
    provenance.find((p) => p.filename === name)?.summary;

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragging
            ? "border-primary bg-primary/5"
            : "border-border bg-card hover:border-primary/50 hover:bg-secondary/40",
        )}
      >
        <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
          <UploadCloud className="h-6 w-6" />
        </span>
        <p className="text-base font-medium">Drop your audit CSVs</p>
        <p className="mt-1 text-sm text-muted-foreground">
          One combined file, or split config / facts / queries — they merge into one audit.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <div className="flex items-center justify-between">
        <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
          Add file
        </Button>
        <a
          href={templateUrl()}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
        >
          <Download className="h-4 w-4" /> Download template
        </a>
      </div>

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f) => (
            <li
              key={f.name}
              className="flex items-center gap-3 rounded-lg border bg-card px-3 py-2.5"
            >
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="font-medium">{f.name}</span>
              <span className="truncate text-sm text-muted-foreground">
                {summaryFor(f.name) ? `— ${summaryFor(f.name)}` : ""}
              </span>
              <button
                onClick={() => onRemove(f.name)}
                className="ml-auto rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground"
                aria-label={`Remove ${f.name}`}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
