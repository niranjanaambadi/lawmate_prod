"use client";

import { AdvocateCauseListRow } from "@/lib/api";

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
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide w-12">#</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">Court Hall</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Bench / Judge</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">List Type</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">Case No</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Parties</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => (
              <tr
                key={row.id}
                className={i % 2 === 0 ? "bg-white" : "bg-slate-50/40"}
              >
                {/* # */}
                <td className="px-4 py-3 text-slate-400 tabular-nums text-xs">
                  {row.item_no ?? i + 1}
                </td>

                {/* Court Hall */}
                <td className="px-4 py-3 text-slate-700 whitespace-nowrap text-xs">
                  {row.court_hall || "—"}
                </td>

                {/* Bench / Judge */}
                <td className="px-4 py-3 text-slate-700 text-xs max-w-[200px]">
                  {row.bench || row.judge_name ? (
                    <span className="line-clamp-3">{row.bench || row.judge_name}</span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>

                {/* List Type */}
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
                <td className="px-4 py-3 font-mono text-xs text-slate-900 whitespace-nowrap">
                  {row.case_no || <span className="text-slate-400">—</span>}
                </td>

                {/* Parties */}
                <td className="px-4 py-3 text-xs text-slate-700 max-w-xs">
                  {row.petitioner && (
                    <div>
                      <span className="text-slate-400">Pet: </span>
                      {row.petitioner}
                    </div>
                  )}
                  {row.respondent && (
                    <div className={row.petitioner ? "mt-0.5" : ""}>
                      <span className="text-slate-400">Res: </span>
                      {row.respondent}
                    </div>
                  )}
                  {!row.petitioner && !row.respondent && (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
