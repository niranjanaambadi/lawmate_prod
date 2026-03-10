"use client";

import { AdvocateCauseListRow } from "@/lib/api";

// Matches a Kerala HC case number fragment, e.g. "7749/ 2023", "MACA 1049/ 2025".
// Used to distinguish case-number strings from party-name strings in the DB.
const CASE_NO_RE = /\d{3,}\s*\/\s*\d{4}/;

interface Props {
  rows: AdvocateCauseListRow[];
}

export function AdvocateCauseListTable({ rows }: Props) {
  if (!rows.length) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide w-16">Item No</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Items</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">Court Hall</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Bench</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">List</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">Case No</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Parties</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => {
              // ── Case No ────────────────────────────────────────────────────
              // Old data (pre-fix scraper): case number ended up in judge_name
              // because the old 8-col parser mis-read the 6-col portal HTML.
              // New data (after fix): judge_name is null, case_no is correct.
              const caseNoDisplay =
                row.judge_name && CASE_NO_RE.test(row.judge_name)
                  ? row.judge_name
                  : row.case_no;

              // ── Bench ──────────────────────────────────────────────────────
              // Don't fall back to judge_name when it holds a case number.
              const judgeForBench =
                row.judge_name && !CASE_NO_RE.test(row.judge_name)
                  ? row.judge_name
                  : null;

              // ── Parties ───────────────────────────────────────────────────
              // Three data states:
              // 1. New data (after fix): petitioner = "KUMAR P.R",
              //    respondent = "A.A.ANWAR" — both properly split by backend.
              //    Display as: KUMAR P.R / Vs / A.A.ANWAR (hckinfo style).
              // 2. Legacy combined string: petitioner = "KUMAR P.R Vs A.A.ANWAR",
              //    respondent = "" — show combined without prefix.
              // 3. Old misaligned data: petitioner = "", case_no = parties text
              //    (case_no doesn't match the case-number regex).
              const partiesContent = (() => {
                if (row.petitioner && row.respondent) {
                  // Properly split petitioner + respondent (new data after fix)
                  return (
                    <div className="space-y-0.5">
                      <div className="text-slate-800">{row.petitioner}</div>
                      <div className="text-slate-400 text-[10px] font-medium tracking-wide">Vs</div>
                      <div className="text-slate-800">{row.respondent}</div>
                    </div>
                  );
                }

                if (row.petitioner) {
                  // Combined "KUMAR P.R Vs A.A.ANWAR" string — split for display
                  const vsIdx = row.petitioner.search(/\bVs\b/i);
                  if (vsIdx !== -1) {
                    const pet = row.petitioner.slice(0, vsIdx).trim();
                    const res = row.petitioner.slice(vsIdx + 2).trim();
                    return (
                      <div className="space-y-0.5">
                        <div className="text-slate-800">{pet}</div>
                        <div className="text-slate-400 text-[10px] font-medium tracking-wide">Vs</div>
                        <div className="text-slate-800">{res}</div>
                      </div>
                    );
                  }
                  // No "Vs" separator — show as-is
                  return <span className="text-slate-800">{row.petitioner}</span>;
                }

                // Old misaligned data: parties text stored in case_no
                if (row.case_no && !CASE_NO_RE.test(row.case_no)) {
                  const vsIdx = row.case_no.search(/\bVs\b/i);
                  if (vsIdx !== -1) {
                    const pet = row.case_no.slice(0, vsIdx).trim();
                    const res = row.case_no.slice(vsIdx + 2).trim();
                    return (
                      <div className="space-y-0.5">
                        <div className="text-slate-800">{pet}</div>
                        <div className="text-slate-400 text-[10px] font-medium tracking-wide">Vs</div>
                        <div className="text-slate-800">{res}</div>
                      </div>
                    );
                  }
                  return <span className="text-slate-800">{row.case_no}</span>;
                }

                return <span className="text-slate-400">—</span>;
              })();

              return (
                <tr
                  key={row.id}
                  className={i % 2 === 0 ? "bg-white" : "bg-slate-50/40"}
                >
                  {/* Item No */}
                  <td className="px-4 py-3 text-xs text-center">
                    <span className="font-bold text-slate-800 tabular-nums">
                      {row.item_no ?? i + 1}
                    </span>
                  </td>

                  {/* Items (range) */}
                  <td className="px-4 py-3 text-[11px] text-slate-500 max-w-[180px]">
                    {row.item_no_range
                      ? <span className="leading-relaxed">({row.item_no_range})</span>
                      : <span className="text-slate-300">—</span>
                    }
                  </td>

                  {/* Court Hall */}
                  <td className="px-4 py-3 text-slate-700 whitespace-nowrap text-xs text-center font-medium">
                    {row.court_hall || "—"}
                  </td>

                  {/* Bench */}
                  <td className="px-4 py-3 text-slate-700 text-xs max-w-[220px]">
                    {row.bench || judgeForBench ? (
                      <span className="line-clamp-3">{row.bench || judgeForBench}</span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>

                  {/* List */}
                  <td className="px-4 py-3">
                    {row.list_type ? (
                      <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 whitespace-nowrap">
                        {row.list_type}
                      </span>
                    ) : (
                      <span className="text-slate-400 text-xs">—</span>
                    )}
                  </td>

                  {/* Case No */}
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-900 whitespace-nowrap">
                    {caseNoDisplay || <span className="text-slate-400 font-normal">—</span>}
                  </td>

                  {/* Parties */}
                  <td className="px-4 py-3 text-xs max-w-xs">
                    {partiesContent}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
