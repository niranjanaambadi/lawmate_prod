"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { searchCases, type CaseOption } from "@/lib/api";
import { ArrowRight, CheckCircle2, Gavel, Loader2, Search, X } from "lucide-react";
import ChatWidget from "@/components/agent/ChatWidget";

const DEBOUNCE_MS = 300;

export default function HearingDayPage() {
  const { token } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CaseOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CaseOption | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const runSearch = useCallback(
    async (q: string) => {
      if (!q.trim() || !token) {
        setResults([]);
        setDropdownOpen(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const { cases: list } = await searchCases(q.trim(), 20, token);
        const arr = Array.isArray(list) ? list : [];
        setResults(arr);
        setDropdownOpen(arr.length > 0);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
        setResults([]);
        setDropdownOpen(false);
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  const onQueryChange = (value: string) => {
    setQuery(value);
    setSelected(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim()) {
      setResults([]);
      setLoading(false);
      setDropdownOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => runSearch(value), DEBOUNCE_MS);
  };

  const onSelect = (c: CaseOption) => {
    setSelected(c);
    setQuery("");
    setResults([]);
    setDropdownOpen(false);
  };

  const onClear = () => {
    setSelected(null);
    setQuery("");
    setResults([]);
    setDropdownOpen(false);
    inputRef.current?.focus();
  };

  const onProceed = () => {
    if (selected?.id) router.push(`/dashboard/hearing-day/${selected.id}`);
  };

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-50">

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="flex-none bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 shadow-sm">
            <Gavel className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Hearing Day</h1>
            <p className="text-sm text-slate-500">
              Search and select a case to open the case bundle workspace on your hearing day.
            </p>
          </div>
        </div>
      </div>

      {/* ── Main content ───────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-xl mx-auto px-6 py-8">

          {/* Search card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
            <p className="text-sm font-semibold text-slate-700">Find your case</p>

            {/* Search input + floating dropdown */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                placeholder="Case number, e-filing number, or party name…"
                value={query}
                onChange={(e) => onQueryChange(e.target.value)}
                onFocus={() => results.length > 0 && setDropdownOpen(true)}
                onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                className="w-full pl-9 pr-10 py-2.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
              />
              {loading && (
                <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-slate-400" />
              )}

              {/* Floating results dropdown */}
              {dropdownOpen && results.length > 0 && (
                <ul className="absolute left-0 right-0 top-full mt-1.5 z-20 max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
                  {results.map((c) => (
                    <li key={c.id} className="border-b border-slate-50 last:border-0">
                      <button
                        type="button"
                        onMouseDown={() => onSelect(c)}
                        className="w-full px-4 py-3 text-left hover:bg-indigo-50 transition-colors"
                      >
                        <p className="text-sm font-medium text-slate-800">
                          {c.case_number || c.efiling_number}
                          {c.case_type && (
                            <span className="ml-2 text-xs font-normal text-slate-500">{c.case_type}</span>
                          )}
                        </p>
                        {c.petitioner_name && (
                          <p className="text-xs text-slate-500 mt-0.5">{c.petitioner_name}</p>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Error */}
            {error && <p className="text-sm text-red-600">{error}</p>}

            {/* No results hint */}
            {!loading && !dropdownOpen && query.trim() && results.length === 0 && !selected && (
              <p className="text-sm text-slate-500">No cases found. Try a different search term.</p>
            )}

            {/* Selected case chip */}
            {selected && (
              <div className="flex items-start gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
                <CheckCircle2 className="h-4 w-4 text-indigo-500 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-indigo-900">
                    {selected.case_number || selected.efiling_number}
                    {selected.case_type && (
                      <span className="ml-2 text-xs font-normal text-indigo-600">{selected.case_type}</span>
                    )}
                  </p>
                  {selected.petitioner_name && (
                    <p className="text-xs text-indigo-700 mt-0.5">{selected.petitioner_name}</p>
                  )}
                </div>
                <button
                  onClick={onClear}
                  className="shrink-0 text-indigo-400 hover:text-indigo-600 transition-colors"
                  title="Clear selection"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* CTA */}
            <button
              onClick={onProceed}
              disabled={!selected}
              className="w-full flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors shadow-sm"
            >
              Open Case Bundle
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

        </div>
      </div>

      <ChatWidget page="hearing_day" />
    </div>
  );
}
