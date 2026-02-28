"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  FolderOpen,
  ScanLine,
  Brain,
  Calendar,
  Gavel,
  FileText,
  ListChecks,
  Clock3,
  Trash2,
  NotebookPen,
  Settings,
  Scale,
  Languages,
  BookOpen,
  BookOpenCheck,
  GitCompare,
  HelpCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const hearingDayEnabled =
  typeof process.env.NEXT_PUBLIC_HEARING_DAY_ENABLED !== "string" ||
  process.env.NEXT_PUBLIC_HEARING_DAY_ENABLED === "true";

const baseNav = [
  { name: "Cases", href: "/dashboard/cases", icon: FolderOpen },
  { name: "OCR", href: "/dashboard/ocr", icon: ScanLine },
  { name: "AI Insights", href: "/dashboard/ai-insights", icon: Brain },
  { name: "Roster", href: "/dashboard/roster", icon: FileText },
  { name: "Cause List", href: "/dashboard/causelist", icon: ListChecks },
  { name: "Case Status", href: "/dashboard/case-status-check", icon: Clock3 },
  { name: "Case Notebooks", href: "/dashboard/notebooks", icon: NotebookPen },
  { name: "Legal Translator AI", href: "/dashboard/translate", icon: Languages },
  { name: "Judgement Analyzer AI", href: "/dashboard/legal-insight", icon: BookOpen },
  { name: "Case Prep AI", href: "/dashboard/case-prep", icon: BookOpenCheck },
  { name: "Doc Comparison AI", href: "/dashboard/doc-compare", icon: GitCompare },
];
const hearingDayNav = hearingDayEnabled
  ? [{ name: "Hearing Day", href: "/dashboard/hearing-day", icon: Gavel }]
  : [];
const navigation = [
  ...baseNav,
  ...hearingDayNav,
  { name: "Calendar", href: "/dashboard/calendar", icon: Calendar },
];
const bottomNavigation = [
  { name: "Help Center", href: "/dashboard/help-center", icon: HelpCircle },
  { name: "Settings", href: "/dashboard/settings/profile", icon: Settings },
  { name: "Recycle Bin", href: "/dashboard/recycle-bin", icon: Trash2 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 w-64 bg-slate-900">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <Link
          href="/dashboard"
          className="flex h-16 items-center gap-3 border-b border-slate-800 px-5 transition-opacity hover:opacity-80"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 shadow-sm">
            <Scale className="h-4 w-4 text-white" />
          </div>
          <span className="text-base font-bold tracking-tight text-white">
            LawMate
          </span>
        </Link>

        {/* Main navigation */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
          {navigation.map((item) => {
            const Icon = item.icon;
            const current = pathname.startsWith(item.href);
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                  current
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Bottom navigation */}
        <div className="border-t border-slate-800 px-3 py-3">
          <nav className="space-y-0.5">
            {bottomNavigation.map((item) => {
              const Icon = item.icon;
              const current = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                    current
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-300 hover:bg-slate-800 hover:text-white"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </aside>
  );
}
