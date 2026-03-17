"use client";

import React, { useRef, useState } from "react";
import { Plus, X, ChevronDown } from "lucide-react";
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
    <div className="flex items-center overflow-x-auto border-b border-slate-200 bg-white shrink-0 h-10">
      {/* New workspace button */}
      <button
        onClick={onCreate}
        title="New workspace"
        className="flex items-center gap-1 px-3 h-full text-slate-500 hover:text-indigo-600 hover:bg-slate-50 border-r border-slate-200 shrink-0 text-sm"
      >
        <Plus className="h-4 w-4" />
      </button>

      {/* Tab pills */}
      {workspaces.map((ws) => {
        const isActive = ws.id === activeId;
        return (
          <div
            key={ws.id}
            onClick={() => onSwitch(ws.id)}
            className={[
              "flex items-center gap-1.5 px-3 h-full cursor-pointer border-r border-slate-200 shrink-0 max-w-[160px] group",
              isActive
                ? "bg-white border-b-2 border-b-indigo-500 text-slate-800"
                : "text-slate-500 hover:bg-slate-50 hover:text-slate-700",
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
                className="w-24 text-xs outline-none border-b border-indigo-400 bg-transparent"
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
              className="ml-auto opacity-0 group-hover:opacity-100 hover:text-red-500 transition-opacity"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}

      {/* Mobile fallback — hidden on md+ */}
      <div className="md:hidden ml-auto pr-2">
        <select
          value={activeId ?? ""}
          onChange={(e) => onSwitch(e.target.value)}
          className="text-xs border border-slate-200 rounded px-1 py-0.5"
        >
          {workspaces.map((ws) => (
            <option key={ws.id} value={ws.id}>{ws.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
