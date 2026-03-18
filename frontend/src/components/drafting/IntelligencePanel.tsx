"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, RefreshCw, AlertCircle, CheckSquare, Square, CheckCircle2 } from "lucide-react";
import type { CaseContext } from "@/stores/workspaceStore";

interface Props {
  caseContext:   CaseContext | null;
  hasDocuments:  boolean;
  onRefresh:     () => Promise<"ok" | "empty" | "error">;
  isRefreshing:  boolean;
}

export default function IntelligencePanel({ caseContext, hasDocuments, onRefresh, isRefreshing }: Props) {
  const [expanded,        setExpanded]        = useState(true);
  const [checked,         setChecked]         = useState<Record<number, boolean>>({});
  const [refreshResult,   setRefreshResult]   = useState<"ok" | "empty" | "error" | null>(null);

  const handleRefresh = async () => {
    setRefreshResult(null);
    const result = await onRefresh();
    setRefreshResult(result);
    // Auto-clear the result indicator after 4 seconds
    setTimeout(() => setRefreshResult(null), 4000);
  };

  const refreshLabel = isRefreshing
    ? "Extracting…"
    : refreshResult === "ok"    ? "Extracted ✓"
    : refreshResult === "empty" ? "Nothing found"
    : refreshResult === "error" ? "Failed — retry"
    : "Extract Context";

  const refreshColor = isRefreshing
    ? "text-indigo-500"
    : refreshResult === "ok"    ? "text-green-600"
    : refreshResult === "empty" ? "text-amber-600"
    : refreshResult === "error" ? "text-red-500"
    : "text-indigo-600 hover:text-indigo-700";

  if (!caseContext || Object.keys(caseContext).length === 0) {
    const tipText = hasDocuments
      ? "💡 Documents uploaded. Click \"Extract Context\" to analyse them."
      : "💡 Upload documents first, then click \"Extract Context\" to let AI read your case.";

    return (
      <div className="px-3 py-2 border-b border-amber-100 bg-amber-50 text-xs flex items-center justify-between gap-2">
        <span className="text-amber-700 font-medium">{tipText}</span>
        {hasDocuments && (
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className={`flex items-center gap-1 font-medium disabled:opacity-50 shrink-0 whitespace-nowrap transition-colors ${refreshColor}`}
            title="Run AI extraction over all uploaded documents to populate the case intelligence panel"
          >
            <RefreshCw className={`h-3 w-3 ${isRefreshing ? "animate-spin" : ""}`} />
            {refreshLabel}
          </button>
        )}
      </div>
    );
  }

  const ctx = caseContext;
  const parties = ctx.parties;

  return (
    <div className="border-b border-slate-200 bg-white">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer select-none"
        onClick={() => setExpanded((e) => !e)}
      >
        <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
          Case Intelligence
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); handleRefresh(); }}
            disabled={isRefreshing}
            title="Re-run AI extraction over all uploaded documents"
            className={`flex items-center gap-1 text-[11px] font-medium disabled:opacity-50 transition-colors ${refreshColor}`}
          >
            {refreshResult === "ok"
              ? <CheckCircle2 className="h-3.5 w-3.5" />
              : <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            }
            {refreshLabel}
          </button>
          {expanded ? <ChevronUp className="h-3.5 w-3.5 text-slate-400" /> : <ChevronDown className="h-3.5 w-3.5 text-slate-400" />}
        </div>
      </div>

      {expanded && (
        <div className="px-3 pb-3 space-y-3 text-xs">
          {/* Parties */}
          {parties && (
            <div className="flex gap-2 flex-wrap">
              {parties.petitioner && (
                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
                  Pet: {parties.petitioner}
                </span>
              )}
              {parties.respondent && (
                <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full">
                  Resp: {parties.respondent}
                </span>
              )}
            </div>
          )}

          {/* Case metadata row */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-slate-600">
            {ctx.caseNumber   && <span><b>Case:</b> {ctx.caseNumber}</span>}
            {ctx.caseType     && <span><b>Type:</b> {ctx.caseType}</span>}
            {ctx.nextHearing  && <span><b>Next Hearing:</b> {ctx.nextHearing}</span>}
            {ctx.judge        && <span><b>Judge:</b> {ctx.judge}</span>}
          </div>

          {/* Status */}
          {ctx.status && (
            <p className="text-slate-600">{ctx.status}</p>
          )}

          {/* Sections invoked */}
          {ctx.sectionsInvoked && ctx.sectionsInvoked.length > 0 && (
            <div className="flex gap-1 flex-wrap">
              {ctx.sectionsInvoked.map((s, i) => (
                <span key={i} className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-[10px]">
                  {s}
                </span>
              ))}
            </div>
          )}

          {/* Recommended actions */}
          {ctx.recommendedActions && ctx.recommendedActions.length > 0 && (
            <div>
              <p className="font-semibold text-slate-700 mb-1">Recommended Actions</p>
              <ol className="space-y-0.5">
                {ctx.recommendedActions.map((action, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-1.5 cursor-pointer"
                    onClick={() => setChecked((c) => ({ ...c, [i]: !c[i] }))}
                  >
                    {checked[i]
                      ? <CheckSquare className="h-3.5 w-3.5 text-indigo-500 shrink-0 mt-0.5" />
                      : <Square className="h-3.5 w-3.5 text-slate-300 shrink-0 mt-0.5" />
                    }
                    <span className={checked[i] ? "line-through text-slate-400" : "text-slate-600"}>
                      {action}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Missing documents */}
          {ctx.missingDocuments && ctx.missingDocuments.length > 0 && (
            <div>
              <p className="font-semibold text-red-600 mb-1 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" /> Missing Documents
              </p>
              <ul className="space-y-0.5">
                {ctx.missingDocuments.map((m, i) => (
                  <li key={i} className="text-red-600 flex items-start gap-1">
                    <span className="text-red-400">•</span> {m}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
