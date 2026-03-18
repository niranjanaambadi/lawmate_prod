"use client";

import React, { useState } from "react";
import { FileText, Trash2, Eye } from "lucide-react";
import type { WorkspaceDocument } from "@/stores/workspaceStore";
import UploadZone from "./UploadZone";

// Doc-type → colour map
const DOC_TYPE_COLORS: Record<string, string> = {
  FIR:                          "bg-red-100 text-red-700",
  ChargeSheet:                  "bg-orange-100 text-orange-700",
  BailOrder:                    "bg-green-100 text-green-700",
  InterimOrder:                 "bg-amber-100 text-amber-700",
  FinalJudgment:                "bg-indigo-100 text-indigo-700",
  HighCourtOrder:               "bg-blue-100 text-blue-700",
  SupremeCourtJudgment:         "bg-purple-100 text-purple-700",
  WritPetition:                 "bg-sky-100 text-sky-700",
  BailApplication:              "bg-teal-100 text-teal-700",
  AnticipatoryBailApplication:  "bg-emerald-100 text-emerald-700",
  CounterAffidavit:             "bg-slate-100 text-slate-700",
  Vakalatnama:                  "bg-gray-100 text-gray-700",
  LegalNotice:                  "bg-yellow-100 text-yellow-700",
};

function docTypeColor(t: string | null) {
  return t ? (DOC_TYPE_COLORS[t] ?? "bg-slate-100 text-slate-600") : "bg-slate-100 text-slate-500";
}

interface Props {
  workspaceId: string;
  documents:   WorkspaceDocument[];
  citedDocIds: string[];
  token:       string;
  onUploaded:  (doc: unknown) => void;
  onDeleted:   (docId: string) => void;
}

export default function DocumentVault({
  workspaceId, documents, citedDocIds, token, onUploaded, onDeleted,
}: Props) {
  const [deleting,  setDeleting]  = useState<string | null>(null);
  const [previewing, setPreviewing] = useState<string | null>(null);

  const handlePreview = async (docId: string) => {
    setPreviewing(docId);
    try {
      const { getDocumentUrl } = await import("@/lib/api");
      const url = await getDocumentUrl(workspaceId, docId, token);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Could not open document");
    } finally {
      setPreviewing(null);
    }
  };

  const totalTokens = documents.reduce((s, d) => s + (d.tokenEstimate ?? 0), 0);
  const tokenLabel  = totalTokens > 1000
    ? `${(totalTokens / 1000).toFixed(0)}k tokens`
    : `${totalTokens} tokens`;

  const handleDelete = async (docId: string) => {
    if (!confirm("Remove this document from the workspace?")) return;
    setDeleting(docId);
    try {
      const { deleteWorkspaceDocument } = await import("@/lib/api");
      await deleteWorkspaceDocument(workspaceId, docId, token);
      onDeleted(docId);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Upload zone */}
      <UploadZone
        workspaceId={workspaceId}
        token={token}
        onUploaded={onUploaded}
      />

      {/* Token budget */}
      <div className="px-3 pb-2 text-[11px] text-slate-400">{tokenLabel}</div>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1 pb-2">
        {documents.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-4 px-2">
            Upload documents to get started
          </p>
        )}
        {documents.map((doc) => {
          const isCited = citedDocIds.includes(doc.id);
          return (
            <div
              key={doc.id}
              className={[
                "flex items-start gap-2 rounded-lg p-2 group border",
                isCited ? "border-indigo-300 bg-indigo-50" : "border-transparent hover:bg-slate-50",
              ].join(" ")}
            >
              <FileText className="h-4 w-4 mt-0.5 shrink-0 text-slate-400" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-slate-700 truncate">{doc.filename}</p>
                <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                  {doc.docType && (
                    <span className={`text-[10px] px-1.5 py-0 rounded-full font-medium ${docTypeColor(doc.docType)}`}>
                      {doc.docType}
                    </span>
                  )}
                  {doc.strategy === "summarized" && (
                    <span className="text-[10px] px-1.5 py-0 rounded-full bg-amber-100 text-amber-700 font-medium">
                      summarised
                    </span>
                  )}
                  {isCited && (
                    <span className="text-[10px] px-1.5 py-0 rounded-full bg-indigo-100 text-indigo-700 font-medium">
                      cited
                    </span>
                  )}
                </div>
              </div>
              <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity shrink-0">
                <button
                  onClick={() => handlePreview(doc.id)}
                  disabled={previewing === doc.id}
                  title="View document"
                  className="text-slate-300 hover:text-indigo-500 disabled:opacity-50 transition-colors"
                >
                  <Eye className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => handleDelete(doc.id)}
                  disabled={deleting === doc.id}
                  title="Remove document"
                  className="text-slate-300 hover:text-red-500 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
