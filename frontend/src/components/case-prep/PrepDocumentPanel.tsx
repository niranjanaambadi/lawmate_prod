"use client";

import { FileText, CheckSquare, Square, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { DocumentListItem } from "@/lib/api";

// ── Component ─────────────────────────────────────────────────────────────────

interface PrepDocumentPanelProps {
  documents:         DocumentListItem[];
  selectedIds:       string[];
  onSelectionChange: (ids: string[]) => void;
  loading?:          boolean;
  disabled?:         boolean;
}

export function PrepDocumentPanel({
  documents,
  selectedIds,
  onSelectionChange,
  loading  = false,
  disabled = false,
}: PrepDocumentPanelProps) {
  const toggle = (id: string) => {
    if (disabled) return;
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((d) => d !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  const toggleAll = () => {
    if (disabled) return;
    if (selectedIds.length === documents.length) {
      onSelectionChange([]);
    } else {
      onSelectionChange(documents.map((d) => d.id));
    }
  };

  const allSelected = documents.length > 0 && selectedIds.length === documents.length;

  return (
    <div className="flex flex-col gap-1 p-3">
      {/* Header */}
      <div className="mb-1 flex items-center justify-between px-1">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Documents ({selectedIds.length}/{documents.length})
        </p>
        {documents.length > 1 && (
          <button
            onClick={toggleAll}
            disabled={disabled || loading}
            className="text-[11px] text-indigo-600 hover:text-indigo-800 disabled:opacity-40"
          >
            {allSelected ? "Deselect all" : "Select all"}
          </button>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5 text-sm text-slate-400">
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          Loading…
        </div>
      )}

      {/* Empty */}
      {!loading && documents.length === 0 && (
        <p className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-3 text-[12px] text-slate-400">
          No documents found for this case.
        </p>
      )}

      {/* Document list */}
      {!loading && documents.map((doc) => {
        const isSelected = selectedIds.includes(doc.id);
        return (
          <button
            key={doc.id}
            onClick={() => toggle(doc.id)}
            disabled={disabled}
            className={cn(
              "group flex w-full items-start gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-all",
              isSelected
                ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                : "border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-700",
              disabled && "cursor-not-allowed opacity-50"
            )}
          >
            {/* Checkbox */}
            <span className="mt-0.5 shrink-0">
              {isSelected ? (
                <CheckSquare className="h-3.5 w-3.5 text-indigo-500" />
              ) : (
                <Square className="h-3.5 w-3.5 text-slate-300" />
              )}
            </span>

            <div className="min-w-0">
              <p className="flex items-center gap-1 truncate text-[13px] font-medium leading-tight">
                <FileText className="h-3 w-3 shrink-0" />
                <span className="truncate">{doc.title}</span>
              </p>
              {doc.category && (
                <p className="mt-0.5 text-[11px] capitalize text-slate-400">
                  {doc.category.replace(/_/g, " ")}
                </p>
              )}
            </div>
          </button>
        );
      })}

      {/* Hint */}
      {!loading && documents.length > 0 && selectedIds.length === 0 && (
        <p className="mt-1 px-1 text-[11px] text-slate-400">
          Select at least one document to start.
        </p>
      )}
    </div>
  );
}
