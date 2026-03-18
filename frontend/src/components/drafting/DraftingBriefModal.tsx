"use client";

import React, { useState } from "react";
import { X, Loader2, FileText, Info } from "lucide-react";
import type { CaseContext } from "@/stores/workspaceStore";

// ── Document type registry — keys must match backend DRAFTING_PROMPTS exactly ──

interface DocTypeOption {
  value: string;
  label: string;
  tier:  1 | 2;
}

interface DocTypeGroup {
  group:   string;
  emoji:   string;
  options: DocTypeOption[];
}

const DOC_TYPE_GROUPS: DocTypeGroup[] = [
  {
    group: "Criminal",
    emoji: "🔴",
    options: [
      { value: "BailApplication_Regular",        label: "Bail Application (Regular)",          tier: 1 },
      { value: "BailApplication_Anticipatory",   label: "Anticipatory Bail Application",       tier: 1 },
      { value: "CriminalAppeal",                 label: "Criminal Appeal",                     tier: 1 },
      { value: "CriminalAppeal_Victim",          label: "Criminal Appeal (by Victim)",         tier: 1 },
      { value: "CriminalRevisionPetition",       label: "Criminal Revision Petition",          tier: 1 },
      { value: "CriminalMiscCase",               label: "Criminal Misc. Case",                 tier: 1 },
      { value: "CriminalLeavePetition",          label: "Criminal Leave Petition",             tier: 1 },
      { value: "CompoundingPetition",            label: "Compounding Petition",                tier: 1 },
      { value: "CriminalMiscApplication",        label: "Criminal Misc. Application",          tier: 2 },
      { value: "RevisionPetition_JuvenileJustice", label: "Revision Petition (Juvenile Justice)", tier: 2 },
    ],
  },
  {
    group: "Constitutional / Writ",
    emoji: "🔵",
    options: [
      { value: "WritPetition_Civil",             label: "Writ Petition (Civil)",               tier: 1 },
      { value: "WritPetition_Criminal",          label: "Writ Petition (Criminal)",            tier: 1 },
      { value: "WritAppeal",                     label: "Writ Appeal",                         tier: 1 },
      { value: "ContemptPetition_Civil",         label: "Contempt Petition",                   tier: 1 },
      { value: "OriginalPetition_Civil",         label: "Original Petition (Civil)",           tier: 1 },
      { value: "OriginalPetition_Criminal",      label: "O.P. (Criminal)",                     tier: 2 },
      { value: "OriginalPetition_CAT",           label: "O.P. (CAT)",                          tier: 2 },
      { value: "OriginalPetition_KAT",           label: "O.P. (KAT)",                          tier: 2 },
      { value: "OriginalPetition_DRT",           label: "O.P. (DRT)",                          tier: 2 },
      { value: "OriginalPetition_LabourCourt",   label: "O.P. (Labour Court)",                 tier: 2 },
      { value: "OriginalPetition_RentControl",   label: "O.P. (Rent Control)",                 tier: 2 },
      { value: "OriginalPetition_Tax",           label: "O.P. (Tax)",                          tier: 2 },
      { value: "OriginalPetition_Wakf",          label: "O.P. (Wakf)",                         tier: 2 },
    ],
  },
  {
    group: "Civil",
    emoji: "🟢",
    options: [
      { value: "RegularFirstAppeal",             label: "Regular First Appeal",                tier: 1 },
      { value: "RegularSecondAppeal",            label: "Regular Second Appeal",               tier: 1 },
      { value: "CivilRevisionPetition",          label: "Civil Revision Petition",             tier: 1 },
      { value: "TransferPetition_Civil",         label: "Transfer Petition (Civil)",           tier: 1 },
      { value: "TransferPetition_Criminal",      label: "Transfer Petition (Criminal)",        tier: 1 },
      { value: "ReviewPetition",                 label: "Review Petition",                     tier: 1 },
      { value: "CivilMiscApplication",           label: "Civil Misc. Application",             tier: 1 },
      { value: "InterlocutoryApplication",       label: "Interlocutory Application",           tier: 1 },
      { value: "Caveat",                         label: "Caveat",                              tier: 1 },
      { value: "FirstAppeal_Order",              label: "First Appeal against Order",          tier: 2 },
      { value: "ExecutionFirstAppeal",           label: "Execution First Appeal",              tier: 2 },
      { value: "CrossObjection",                 label: "Cross Objection",                     tier: 2 },
      { value: "LandAcquisitionAppeal",          label: "Land Acquisition Appeal",             tier: 2 },
      { value: "CommercialAppeal",               label: "Commercial Appeal",                   tier: 2 },
      { value: "RentControlRevision",            label: "Rent Control Revision",               tier: 2 },
    ],
  },
  {
    group: "Family / Matrimonial",
    emoji: "🟣",
    options: [
      { value: "MatrimonialAppeal",              label: "Matrimonial Appeal",                  tier: 1 },
      { value: "MatrimonialAppeal_Execution",    label: "Matrimonial Appeal (Execution)",      tier: 1 },
      { value: "RevisionPetition_FamilyCourt",   label: "Revision Petition (Family Court)",    tier: 1 },
      { value: "OriginalPetition_FamilyCourt",   label: "O.P. (Family Court)",                 tier: 2 },
    ],
  },
  {
    group: "Motor Accidents",
    emoji: "🟠",
    options: [
      { value: "MotorAccidentClaimsAppeal",      label: "Motor Accident Claims Appeal",        tier: 1 },
      { value: "OriginalPetition_MAC",           label: "O.P. (MAC)",                          tier: 2 },
    ],
  },
  {
    group: "Arbitration",
    emoji: "🟡",
    options: [
      { value: "ArbitrationRequest",             label: "Arbitration Request",                 tier: 1 },
      { value: "ArbitrationAppeal",              label: "Arbitration Appeal",                  tier: 1 },
      { value: "OriginalPetition_ICA",           label: "O.P. (ICA)",                          tier: 2 },
      { value: "ExecutionPetition_ICA",          label: "Execution Petition (ICA)",            tier: 2 },
      { value: "OriginalPetition_ArbitrationTimeExtension", label: "O.P. (Arbitration Time Extension)", tier: 2 },
    ],
  },
  {
    group: "General",
    emoji: "⚪",
    options: [
      { value: "Vakalatnama",                    label: "Vakalatnama",                         tier: 1 },
      { value: "SupremeCourtLeavePetition",      label: "Supreme Court Leave Petition",        tier: 2 },
    ],
  },
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  workspaceId:   string;
  caseContext:   CaseContext | null;
  prefillText?:  string;
  token:         string;
  onGenerated:   (draft: unknown) => void;
  onClose:       () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DraftingBriefModal({
  workspaceId, caseContext, prefillText, token, onGenerated, onClose,
}: Props) {
  const [docType,    setDocType]    = useState(DOC_TYPE_GROUPS[0].options[0].value);
  const [brief,      setBrief]      = useState(prefillText ?? "");
  const [generating, setGenerating] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const handleGenerate = async () => {
    setError(null);
    setGenerating(true);
    try {
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

  // Selected option metadata
  const selectedOption = DOC_TYPE_GROUPS
    .flatMap((g) => g.options)
    .find((o) => o.value === docType);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-indigo-600" />
            <h2 className="font-semibold text-slate-800">Generate Draft</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

          {/* Case context — read-only summary */}
          {caseContext && Object.keys(caseContext).length > 0 ? (
            <div className="rounded-xl bg-indigo-50 border border-indigo-100 px-3 py-2.5 space-y-1">
              <p className="text-[10px] font-semibold text-indigo-500 uppercase tracking-wide">
                Case Context (auto-extracted)
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-700">
                {caseContext.parties?.petitioner && (
                  <span><span className="text-slate-400">Pet:</span> {caseContext.parties.petitioner}</span>
                )}
                {caseContext.parties?.respondent && (
                  <span><span className="text-slate-400">Resp:</span> {caseContext.parties.respondent}</span>
                )}
                {caseContext.caseNumber && (
                  <span><span className="text-slate-400">Case:</span> {caseContext.caseNumber}</span>
                )}
                {caseContext.caseType && (
                  <span><span className="text-slate-400">Type:</span> {caseContext.caseType}</span>
                )}
              </div>
              {caseContext.sectionsInvoked && caseContext.sectionsInvoked.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-0.5">
                  {caseContext.sectionsInvoked.map((s, i) => (
                    <span key={i} className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-[10px]">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2.5 flex items-start gap-2">
              <Info className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700">
                No case context extracted yet. Upload documents and refresh before generating
                for best results. You can still generate using instructions below.
              </p>
            </div>
          )}

          {/* Document type */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Document Type
            </label>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
            >
              {DOC_TYPE_GROUPS.map((group) => (
                <optgroup key={group.group} label={`${group.emoji} ${group.group}`}>
                  {group.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {selectedOption?.tier === 2 && (
              <p className="text-[11px] text-slate-400 mt-1">
                Generic structure — uses standard KHC format with correct court fee & limitation.
              </p>
            )}
          </div>

          {/* Additional instructions */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Additional Instructions
              <span className="font-normal text-slate-400 ml-1">(optional)</span>
            </label>
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              rows={5}
              placeholder={
                `e.g. "Emphasise medical grounds — accused is diabetic and hypertensive."\n` +
                `     "Include parity argument — co-accused Suresh released on bail 12 Feb."\n` +
                `     "Do not include any interim prayer."`
              }
              className="w-full text-sm border border-slate-300 rounded-lg px-3 py-2.5 resize-none text-slate-800 placeholder:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            {prefillText && (
              <p className="text-[11px] text-indigo-500 mt-1">
                ✦ Pre-filled from your chat analysis — edit as needed.
              </p>
            )}
          </div>

          {error && (
            <p className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="px-5 py-4 border-t border-slate-200 flex justify-end gap-2 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating
              ? <><Loader2 className="h-4 w-4 animate-spin" /> Generating…</>
              : <>Generate Draft</>
            }
          </button>
        </div>

      </div>
    </div>
  );
}
