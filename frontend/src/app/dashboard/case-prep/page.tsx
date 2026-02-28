"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import {
  Loader2,
  AlertCircle,
  ArrowRight,
  Hammer,
  ShieldAlert,
  Gavel,
  FileSearch,
  ScrollText,
  BookOpenCheck,
  ChevronDown,
} from "lucide-react";
import { listCases, CaseListItem, CasesPageResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Mode feature cards ────────────────────────────────────────────────────────

const FEATURE_CARDS = [
  {
    icon:        Hammer,
    title:       "Argument Builder",
    description: "Construct the strongest arguments grounded in your case documents.",
    color:       "text-indigo-600",
    bg:          "bg-indigo-50",
    border:      "border-indigo-100",
  },
  {
    icon:        ShieldAlert,
    title:       "Devil's Advocate",
    description: "Expose every weakness before opposing counsel finds it.",
    color:       "text-rose-600",
    bg:          "bg-rose-50",
    border:      "border-rose-100",
  },
  {
    icon:        Gavel,
    title:       "Bench Simulation",
    description: "Face the exact questions the Kerala HC bench will ask.",
    color:       "text-amber-600",
    bg:          "bg-amber-50",
    border:      "border-amber-100",
  },
  {
    icon:        FileSearch,
    title:       "Order Analysis",
    description: "Forensic read of every order — what is the court tracking?",
    color:       "text-teal-600",
    bg:          "bg-teal-50",
    border:      "border-teal-100",
  },
  {
    icon:        ScrollText,
    title:       "Relief Drafting",
    description: "Draft precise prayer clauses and interim relief.",
    color:       "text-violet-600",
    bg:          "bg-violet-50",
    border:      "border-violet-100",
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CasePrepLandingPage() {
  const router         = useRouter();
  const { token }      = useAuth();
  const [cases,        setCases]        = useState<CaseListItem[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState("");
  const [selectedId,   setSelectedId]   = useState("");

  useEffect(() => {
    if (!token) return;
    listCases({ page: 1, perPage: 100 }, token)
      .then((res: CasesPageResponse) => setCases(res.items ?? []))
      .catch(() => setError("Could not load cases."))
      .finally(() => setLoading(false));
  }, [token]);

  const caseLabel = (c: CaseListItem) => {
    const ref = c.case_number || c.efiling_number;
    return `${ref} — ${c.petitioner_name} vs ${c.respondent_name}`;
  };

  const canStart = !!selectedId;

  const handleStart = () => {
    if (canStart) router.push(`/dashboard/case-prep/${selectedId}`);
  };

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-8">
      <div className="mx-auto max-w-3xl">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="mb-8">
          <div className="flex items-center gap-2.5 mb-2">
            <BookOpenCheck className="h-7 w-7 text-indigo-600" />
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Case Prep AI</h1>
          </div>
          <p className="text-lg text-slate-600">
            A sustained, document-grounded hearing preparation workspace powered by Claude.
          </p>
        </div>

        {/* ── Feature cards ──────────────────────────────────────────────── */}
        <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {FEATURE_CARDS.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className={cn(
                  "rounded-xl border p-3.5",
                  f.bg,
                  f.border
                )}
              >
                <Icon className={cn("mb-2 h-5 w-5", f.color)} />
                <p className="text-base font-semibold text-slate-800">{f.title}</p>
                <p className="mt-1 text-sm leading-snug text-slate-600">
                  {f.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* ── Case selector card ─────────────────────────────────────────── */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-xl font-semibold text-slate-800">
            Select a case to begin
          </h2>

          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2.5 text-base text-red-600">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {/* Dropdown */}
          <div className="relative mb-4">
            <label className="mb-1.5 block text-base font-medium text-slate-600">
              Case
            </label>
            {loading ? (
              <div className="flex h-11 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 text-base text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading cases…
              </div>
            ) : (
              <div className="relative">
                <select
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
                  className={cn(
                    "w-full appearance-none rounded-lg border bg-white py-3 pl-3.5 pr-9 text-base text-slate-800 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-indigo-500",
                    selectedId
                      ? "border-slate-300"
                      : "border-slate-200 text-slate-400"
                  )}
                >
                  <option value="">— choose a case —</option>
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {caseLabel(c)}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              </div>
            )}
          </div>

          {/* Selected case summary */}
          {selectedId && (() => {
            const c = cases.find((x) => x.id === selectedId);
            if (!c) return null;
            return (
              <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-base text-slate-700 space-y-1">
                <p><span className="font-medium text-slate-700">Case no.:</span> {c.case_number || c.efiling_number}</p>
                <p><span className="font-medium text-slate-700">Type:</span> {c.case_type} · {c.case_year}</p>
                <p><span className="font-medium text-slate-700">Petitioner:</span> {c.petitioner_name}</p>
                <p><span className="font-medium text-slate-700">Respondent:</span> {c.respondent_name}</p>
                {c.next_hearing_date && (
                  <p><span className="font-medium text-slate-700">Next hearing:</span> {new Date(c.next_hearing_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</p>
                )}
              </div>
            );
          })()}

          {/* CTA */}
          <button
            onClick={handleStart}
            disabled={!canStart}
            className={cn(
              "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-lg font-semibold transition-all",
              canStart
                ? "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm"
                : "cursor-not-allowed bg-slate-100 text-slate-400"
            )}
          >
            Open Prep Workspace
            <ArrowRight className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
