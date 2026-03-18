"use client";

import React, { useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import type { Workspace } from "@/stores/workspaceStore";

interface Props {
  workspaces:  Workspace[];
  activeId:    string | null;
  onSwitch:    (id: string) => void;
  onClose:     (id: string) => void;
  onCreate:    () => void;
  onRename:    (id: string, label: string) => void;
}

export default function WorkspaceTabs({
  workspaces, activeId, onSwitch, onClose, onCreate, onRename,
}: Props) {
  const [editingId,    setEditingId]    = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = (ws: Workspace) => {
    setEditingId(ws.id);
    setEditingLabel(ws.label);
    setTimeout(() => inputRef.current?.focus(), 30);
  };

  const commitEdit = () => {
    if (editingId && editingLabel.trim()) {
      onRename(editingId, editingLabel.trim());
    }
    setEditingId(null);
  };

  return (
    <div className="flex items-center overflow-x-auto border-b-2 border-indigo-100 bg-slate-50 shrink-0 h-10">

      {/* Tab pills — rendered first so + appears to their right */}
      {workspaces.map((ws) => {
        const isActive = ws.id === activeId;
        return (
          <div
            key={ws.id}
            onClick={() => onSwitch(ws.id)}
            className={[
              "flex items-center gap-1.5 px-4 h-full cursor-pointer border-r border-slate-200 shrink-0 max-w-[180px] group select-none transition-colors",
              isActive
                ? "bg-white border-b-2 border-b-indigo-600 text-indigo-700 font-semibold shadow-sm"
                : "text-slate-500 hover:bg-white hover:text-slateigo-700",
            ].join(" ")}
          >
            {editingId === ws.id ? (
              <input
                ref={inputRef}
                value={editingLabel}
                onChange={(e) => setEditingLabel(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit();
                  if (e.key === "Escape") setEditingId(null);
                }}
                onClick={(e) => e.stopPropagation()}
                className="w-28 text-xs outline-none border-b-2 border-indigo-500 bg-transparent"
              />
            ) : (
              <span
                className="text-xs truncate"
                onDoubleClick={(e) => { e.stopPropagation(); startEdit(ws); }}
              >
                {ws.label}
              </span>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onClose(ws.id); }}
              className="ml-auto opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-opacity rounded"
              title="Close workspace"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}

      {/* ── New workspace button — sits immediately after the last tab ── */}
      <button
        onClick={onCreate}
        title="New workspace"
        className="flex items-center justify-center w-8 h-7 mx-1.5 rounded-md shrink-0 bg-indigo-600 text-white hover:bg-indigo-700 active:bg-indigo-800 shadow-sm transition-colors"
      >
        <Plus className="h-4 w-4" />
      </button>

      {/* Spacer fills the rest of the bar */}
      <div className="flex-1" />

      {/* Mobile fallback — hidden on md+ */}
      <div className="md:hidden pr-2">
        <select
          value={activeId ?? ""}
          onChange={(e) => onSwitch(e.target.value)}
          className="text-xs border border-slate-300 rounded px-1 py-0.5"
        >
          {workspaces.map((ws) => (
            <option key={ws.id} value={ws.id}>{ws.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
