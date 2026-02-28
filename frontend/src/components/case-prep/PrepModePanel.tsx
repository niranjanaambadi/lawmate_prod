"use client";

import { PrepMode, PREP_MODE_LABELS } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Hammer,
  ShieldAlert,
  Gavel,
  FileSearch,
  ScrollText,
  Scale,
} from "lucide-react";

// ── Mode metadata ─────────────────────────────────────────────────────────────

interface ModeInfo {
  id:           PrepMode;
  label:        string;
  description:  string;
  icon:         React.ElementType;
  activeColor:  string;
  activeBg:     string;
  dot:          string;
  noDocsNeeded?: boolean;
}

const MODES: ModeInfo[] = [
  {
    id:          "argument_builder",
    label:       PREP_MODE_LABELS.argument_builder,
    description: "Strongest case for your client",
    icon:        Hammer,
    activeColor: "text-indigo-700",
    activeBg:    "bg-indigo-50 border-indigo-200",
    dot:         "bg-indigo-500",
  },
  {
    id:          "devils_advocate",
    label:       PREP_MODE_LABELS.devils_advocate,
    description: "Find every weakness first",
    icon:        ShieldAlert,
    activeColor: "text-rose-700",
    activeBg:    "bg-rose-50 border-rose-200",
    dot:         "bg-rose-500",
  },
  {
    id:          "bench_simulation",
    label:       PREP_MODE_LABELS.bench_simulation,
    description: "Face the bench's questions",
    icon:        Gavel,
    activeColor: "text-amber-700",
    activeBg:    "bg-amber-50 border-amber-200",
    dot:         "bg-amber-500",
  },
  {
    id:          "order_analysis",
    label:       PREP_MODE_LABELS.order_analysis,
    description: "What is the court tracking?",
    icon:        FileSearch,
    activeColor: "text-teal-700",
    activeBg:    "bg-teal-50 border-teal-200",
    dot:         "bg-teal-500",
  },
  {
    id:          "relief_drafting",
    label:       PREP_MODE_LABELS.relief_drafting,
    description: "Precise prayer clauses",
    icon:        ScrollText,
    activeColor: "text-violet-700",
    activeBg:    "bg-violet-50 border-violet-200",
    dot:         "bg-violet-500",
  },
  {
    id:           "precedent_finder",
    label:        PREP_MODE_LABELS.precedent_finder,
    description:  "Search IndianKanoon case law",
    icon:         Scale,
    activeColor:  "text-cyan-700",
    activeBg:     "bg-cyan-50 border-cyan-200",
    dot:          "bg-cyan-500",
    noDocsNeeded: true,
  },
];

/** Returns true if the given mode requires at least one document to start. */
export function modeRequiresDocs(mode: PrepMode): boolean {
  return !MODES.find((m) => m.id === mode)?.noDocsNeeded;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface PrepModePanelProps {
  activeMode:   PrepMode;
  onModeChange: (mode: PrepMode) => void;
  disabled?:    boolean;
}

export function PrepModePanel({
  activeMode,
  onModeChange,
  disabled = false,
}: PrepModePanelProps) {
  return (
    <div className="flex flex-col gap-1 p-3">
      <p className="mb-1 px-1 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Prep Mode
      </p>
      {MODES.map((mode) => {
        const Icon     = mode.icon;
        const isActive = mode.id === activeMode;
        return (
          <button
            key={mode.id}
            onClick={() => !disabled && onModeChange(mode.id)}
            disabled={disabled}
            className={cn(
              "group flex w-full items-start gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-all",
              isActive
                ? `${mode.activeBg} ${mode.activeColor}`
                : "border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-700",
              disabled && "cursor-not-allowed opacity-50"
            )}
          >
            {/* Colour dot */}
            <span
              className={cn(
                "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                isActive ? mode.dot : "bg-slate-300"
              )}
            />

            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-[13px] font-medium leading-tight">
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {mode.label}
              </p>
              <p className="mt-0.5 text-[11px] leading-snug text-slate-400">
                {mode.description}
              </p>
              {mode.noDocsNeeded && (
                <p className="mt-0.5 text-[10px] font-medium text-cyan-500">
                  No docs needed
                </p>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
