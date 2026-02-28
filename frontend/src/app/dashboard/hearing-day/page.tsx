"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { searchCases, type CaseOption } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Gavel, Loader2, Search } from "lucide-react";
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
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(
    async (q: string) => {
      if (!q.trim() || !token) {
        setResults([]);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const { cases: list } = await searchCases(q.trim(), 20, token);
        setResults(Array.isArray(list) ? list : []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
        setResults([]);
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
      return;
    }
    debounceRef.current = setTimeout(() => runSearch(value), DEBOUNCE_MS);
  };

  const onProceed = () => {
    if (selected?.id) router.push(`/dashboard/hearing-day/${selected.id}`);
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold">
          <Gavel className="h-8 w-8" />
          Hearing Day
        </h1>
        <p className="mt-1 text-slate-600">Search and select a case to open the case bundle workspace.</p>
      </div>

      <div className="max-w-xl space-y-4">
        <Label htmlFor="case-search">Search case</Label>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            id="case-search"
            type="text"
            placeholder="Case number, e-filing number, or party name..."
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            className="pl-9"
          />
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Searching…
          </div>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && query.trim() && results.length === 0 && (
          <p className="text-sm text-slate-500">No cases found. Try a different search.</p>
        )}

        {!loading && results.length > 0 && (
          <ul className="max-h-64 overflow-auto rounded-lg border bg-white">
            {results.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelected(c)}
                  className={`w-full px-4 py-3 text-left text-sm hover:bg-slate-50 ${
                    selected?.id === c.id ? "bg-primary/10 font-medium" : ""
                  }`}
                >
                  <span className="text-slate-700">{c.case_number || c.efiling_number} - {c.case_type ?? "Case"}</span>
                  {c.petitioner_name && <span className="ml-2 text-slate-500">{c.petitioner_name}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}

        <Button onClick={onProceed} disabled={!selected} className="mt-4">
          View Case Bundle
        </Button>
      </div>

      <ChatWidget page="hearing_day" />
    </div>
  );
}
