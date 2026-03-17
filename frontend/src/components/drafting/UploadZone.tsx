"use client";

import React, { useCallback, useRef, useState } from "react";
import { Upload, FileText, Loader2 } from "lucide-react";

interface Props {
  workspaceId: string;
  token: string;
  onUploaded: (doc: unknown) => void;
  disabled?: boolean;
}

export default function UploadZone({ workspaceId, token, onUploaded, disabled }: Props) {
  const inputRef       = useRef<HTMLInputElement>(null);
  const [dragging,  setDragging]  = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const upload = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const { uploadWorkspaceDocument } = await import("@/lib/api");
        const doc = await uploadWorkspaceDocument(workspaceId, file, token);
        onUploaded(doc);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [workspaceId, token, onUploaded],
  );

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    upload(files[0]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (!disabled && !uploading) handleFiles(e.dataTransfer.files);
  };

  return (
    <div className="px-3 pb-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => !disabled && !uploading && inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !disabled && !uploading && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          "flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-3 py-4 cursor-pointer transition-colors",
          dragging
            ? "border-indigo-400 bg-indigo-50"
            : "border-slate-200 hover:border-indigo-300 hover:bg-slate-50",
          (disabled || uploading) ? "opacity-60 cursor-not-allowed" : "",
        ].join(" ")}
      >
        {uploading ? (
          <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
        ) : (
          <Upload className="h-5 w-5 text-slate-400" />
        )}
        <span className="text-xs text-slate-500 text-center">
          {uploading ? "Uploading…" : "Drop PDF / DOCX or click to upload"}
        </span>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      {error && (
        <p className="mt-1 text-xs text-red-500">{error}</p>
      )}
    </div>
  );
}
