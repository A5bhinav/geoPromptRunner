"use client";

import * as React from "react";
import { FileText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Plume } from "@/components/plume";
import { cn } from "@/lib/utils";
import type { FileProvenance } from "@/lib/api";

// Mirror of the backend MAX_UPLOAD_BYTES (5 MB) for a fast client-side reject.
// The server enforces the real cap; this is just UX.
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

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
      (f) =>
        (f.name.toLowerCase().endsWith(".csv") || f.type === "text/csv") &&
        f.size <= MAX_UPLOAD_BYTES,
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
          // A 2px dash at navy reads as a hard box; the guide's own clearspace
          // diagram uses a 1px dash.
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 text-center transition-colors",
          dragging
            ? "border-blue bg-navy/[0.04]"
            : "border-navy/25 bg-white hover:border-navy/40 hover:bg-navy/[0.02]",
        )}
      >
        {/* The empty state is the single best place in the app to show the mark
            at size — and it replaces a stock cloud icon with something ours. */}
        <span className="mb-3 flex items-center justify-center">
          <Plume size={34} tone="paper" />
        </span>
        <p className="text-base font-medium text-navy">Drop your audit CSVs</p>
        <p className="mt-1 text-[13px] text-harbour">
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

      <div className="flex items-center">
        <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
          Add file
        </Button>
      </div>

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f) => (
            <li
              key={f.name}
              className="flex items-center gap-3 rounded-md border border-[var(--rule)] bg-white px-3 py-2.5"
            >
              <FileText className="h-4 w-4 shrink-0 text-harbour" />
              <span className="text-[13px] font-medium text-navy">{f.name}</span>
              <span className="truncate text-[13px] text-harbour">
                {summaryFor(f.name) ? `— ${summaryFor(f.name)}` : ""}
              </span>
              <button
                onClick={() => onRemove(f.name)}
                className="ml-auto rounded-md p-1 text-harbour hover:bg-navy/[0.04] hover:text-navy"
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
