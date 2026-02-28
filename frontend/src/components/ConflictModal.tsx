"use client";

/**
 * ConflictModal — LawMate
 * ========================
 * Generic 409 Conflict resolution dialog.
 *
 * Shown whenever a PUT/PATCH to the backend returns HTTP 409 with the
 * structured payload:
 *   { message, current_version, current_record: { ... } }
 *
 * The user can choose one of three actions:
 *   "reload"  — discard their local changes and use the server's version
 *   "keep"    — keep their local version and force-save (bypass the version check)
 *   "cancel"  — dismiss without taking action
 *
 * Usage:
 *   const [conflict, setConflict] = useState<ConflictPayload | null>(null);
 *
 *   // In your save handler:
 *   try {
 *     await saveNote(payload);
 *   } catch (err) {
 *     if (err instanceof ConflictError) setConflict(err.payload);
 *   }
 *
 *   <ConflictModal
 *     conflict={conflict}
 *     onReload={() => { applyServerVersion(conflict!.current_record); setConflict(null); }}
 *     onKeepMine={() => { forceSave(); setConflict(null); }}
 *     onCancel={() => setConflict(null)}
 *   />
 */

import React from "react";

// ── Types (re-exported so callers don't need to import separately) ─────────

export interface ConflictRecord {
  id?: string;
  title?: string;
  content_text?: string | null;
  content_json?: Record<string, unknown> | null;
  version: number;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface ConflictPayload {
  message: string;
  current_version: number;
  current_record: ConflictRecord;
}

// ── Props ─────────────────────────────────────────────────────────────────

interface ConflictModalProps {
  /** Set to the conflict payload to open the modal, null to hide it */
  conflict: ConflictPayload | null;
  /** Called when the user chooses "Reload latest version" */
  onReload: (serverRecord: ConflictRecord) => void;
  /** Called when the user chooses "Keep my version" (force-save) */
  onKeepMine: () => void;
  /** Called when the user dismisses without choosing */
  onCancel: () => void;
  /** Optional label shown in the header (e.g. "note" or "hearing note") */
  entityLabel?: string;
}

// ── Component ─────────────────────────────────────────────────────────────

export function ConflictModal({
  conflict,
  onReload,
  onKeepMine,
  onCancel,
  entityLabel = "document",
}: ConflictModalProps) {
  if (!conflict) return null;

  const serverUpdatedAt = conflict.current_record.updated_at
    ? new Date(conflict.current_record.updated_at).toLocaleString()
    : "unknown time";

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      {/* Panel */}
      <div className="relative w-full max-w-md rounded-xl bg-white shadow-2xl ring-1 ring-black/10 p-0 overflow-hidden">

        {/* Header */}
        <div className="flex items-start gap-3 bg-amber-50 border-b border-amber-200 px-5 py-4">
          <div className="mt-0.5 flex-shrink-0 rounded-full bg-amber-100 p-2">
            {/* Warning icon */}
            <svg
              className="h-5 w-5 text-amber-600"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-amber-800">
              Edit conflict detected
            </p>
            <p className="mt-0.5 text-xs text-amber-700 leading-snug">
              This {entityLabel} was modified in another tab.
            </p>
          </div>

          {/* Close × */}
          <button
            onClick={onCancel}
            className="ml-auto flex-shrink-0 rounded-lg p-1 text-amber-600 hover:bg-amber-200 transition-colors"
            aria-label="Close"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-3">
          <p className="text-sm text-gray-700 leading-relaxed">
            {conflict.message}
          </p>

          {/* Server version info */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-xs text-gray-600 space-y-1">
            <div className="flex justify-between">
              <span className="font-medium text-gray-700">Server version</span>
              <span className="tabular-nums font-mono text-indigo-600">v{conflict.current_version}</span>
            </div>
            <div className="flex justify-between">
              <span>Last saved</span>
              <span>{serverUpdatedAt}</span>
            </div>
            {conflict.current_record.title && (
              <div className="flex justify-between">
                <span>Title</span>
                <span className="truncate max-w-[180px] font-medium text-gray-700">
                  {String(conflict.current_record.title)}
                </span>
              </div>
            )}
          </div>

          <p className="text-xs text-gray-500">
            Choose how to resolve the conflict — you can compare both versions before deciding.
          </p>
        </div>

        {/* Actions */}
        <div className="border-t border-gray-100 px-5 py-3 flex flex-col gap-2 sm:flex-row-reverse">
          {/* Reload latest — primary */}
          <button
            onClick={() => onReload(conflict.current_record)}
            className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white
                       shadow-sm hover:bg-indigo-700 transition-colors focus-visible:outline
                       focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            Reload latest
          </button>

          {/* Keep mine — secondary */}
          <button
            onClick={onKeepMine}
            className="flex-1 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-gray-700
                       ring-1 ring-inset ring-gray-300 hover:bg-gray-50 transition-colors"
          >
            Keep my version
          </button>

          {/* Cancel — ghost */}
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg px-4 py-2 text-sm font-medium text-gray-500
                       hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
