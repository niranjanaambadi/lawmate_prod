"use client";

import React, { useState } from "react";
import { X, Plus, Trash2, Loader2, FileText } from "lucide-react";
import type { CaseContext } from "@/stores/workspaceStore";

const DOC_TYPES = [
  "BailApplication",
  "AnticipatoryBailApplication",
  "WritPetition",
  "RevisionPetition",
  "Vakalatnama",
  "MemoParies",
  "CounterAffidavit",
  "InterimApplication",
  "Custom",
];

interface Props {
  workspaceId:   string;
  caseContext:   CaseContext | null;
  prefillText?:  string;
  token:         string;
  onGenerated:   (draft: unknown) => void;
  onClose:       () => void;
}

export default function DraftingBriefModal({
  workspaceId, caseContext, prefillText, token, onGenerated, onClose,
}: Props) {
  const [docType,    setDocType]    = useState(DOC_TYPES[0]);
  const [grounds,    setGrounds]    = useState<string[]>([""]);
  const [prayers,    setPrayers]    = useState<string[]>([""]);
  const [addlFacts,  setAddlFacts]  = useState(prefillText ?? "");
  const [generating, setGenerating] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const addGround  = () => setGrounds((g) => [...g, ""]);
  const addPrayer  = () => setPrayers((p) => [...p, ""]);

  const updateGround = (i: number, v: string) =>
    setGrounds((g) => g.map((x, idx) => (idx === i ? v : x)));
  const updatePrayer = (i: number, v: string) =>
    setPrayers((p) => p.map((x, idx) => (idx === i ? v : x)));

  const removeGround = (i: number) => setGrounds((g) => g.filter((_, idx) => idx !== i));
  const removePrayer = (i: number) => setPrayers((p) => p.filter((_, idx) => idx !== i));

  const handleGenerate = async () => {
    setError(null);
    setGenerating(true);
    try {
      const brief = [
        grounds.filter(Boolean).length
          ? `Grounds:\n${grounds.filter(Boolean).map((g, i) => `${i + 1}. ${g}`).join("\n")}`
          : "",
        prayers.filter(Boolean).length
          ? `Prayers:\n${prayers.filter(Boolean).map((p, i) => `${i + 1}. ${p}`).join("\n")}`
          : "",
        addlFacts ? `Additional facts / context:\n${addlFacts}` : "",
      ]
        .filter(Boolean)
        .join("\n\n");

      const { generateDraft } = await import("@/lib/api");
      const draft = await generateDraft(workspaceId, docType, brief, token);
      onGenerated(draft);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-indigo-600" />
            <h2 className="font-semibold text-slate-800">Generate Draft</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* DocType */}
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Document Type</label>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          {/* Grounds */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-600">Grounds</label>
              <button onClick={addGround} className="text-xs text-indigo-600 flex items-center gap-0.5 hover:text-indigo-700">
                <Plus className="h-3 w-3" /> Add
              </button>
            </div>
            <div className="space-y-1.5">
              {grounds.map((g, i) => (
                <div key={i} className="flex gap-1.5">
                  <input
                    value={g}
                    onChange={(e) => updateGround(i, e.target.value)}
                    placeholder={`Ground ${i + 1}`}
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                  {grounds.length > 1 && (
                    <button onClick={() => removeGround(i)} className="text-slate-300 hover:text-red-500">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Prayers */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-600">Prayers</label>
              <button onClick={addPrayer} className="text-xs text-indigo-600 flex items-center gap-0.5 hover:text-indigo-700">
                <Plus className="h-3 w-3" /> Add
              </button>
            </div>
            <div className="space-y-1.5">
              {prayers.map((p, i) => (
                <div key={i} className="flex gap-1.5">
                  <input
                    value={p}
                    onChange={(e) => updatePrayer(i, e.target.value)}
                    placeholder={`Prayer ${i + 1}`}
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                  {prayers.length > 1 && (
                    <button onClick={() => removePrayer(i)} className="text-slate-300 hover:text-red-500">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Additional facts */}
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Additional facts / context
            </label>
            <textarea
              value={addlFacts}
              onChange={(e) => setAddlFacts(e.target.value)}
              rows={4}
              placeholder="Any additional facts, specific instructions, or context for the AI…"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-1.5 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {generating && <Loader2 className="h-4 w-4 animate-spin" />}
            Generate Draft
          </button>
        </div>
      </div>
    </div>
  );
}
