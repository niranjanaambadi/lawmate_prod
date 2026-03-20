"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type RosterEntry = {
  label: string;
  pdfUrl: string;
  sourcePage: string;
  parsedDate: string | null;
};

type RosterApiResponse = {
  ok: boolean;
  fetchedAt?: string;
  sourcePages: string[];
  latest?: RosterEntry;
  entries: RosterEntry[];
  error?: string;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-IN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

const SYNC_SETTLE_MS = 20_000;

export default function RosterPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncCountdown, setSyncCountdown] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RosterApiResponse | null>(null);
  const [selectedUrl, setSelectedUrl] = useState<string>("");

  const loadRoster = async (forceRefresh = false) => {
    if (!forceRefresh) setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/kerala-high-court/roster${forceRefresh ? "?refresh=1" : ""}`,
        { cache: "no-store" },
      );
      const body = (await res.json()) as RosterApiResponse;
      if (!res.ok || !body.ok) throw new Error(body.error || "Unable to load roster");
      setData(body);
      setSelectedUrl(body.latest?.pdfUrl || body.entries[0]?.pdfUrl || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load roster");
      setData(null);
      setSelectedUrl("");
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    await loadRoster(true);
    const steps = SYNC_SETTLE_MS / 1000;
    for (let i = steps; i > 0; i--) {
      setSyncCountdown(i);
      await new Promise((r) => setTimeout(r, 1000));
    }
    setSyncCountdown(null);
    await loadRoster();
    setRefreshing(false);
  };

  useEffect(() => { void loadRoster(); }, []);

  const selectedRoster = useMemo(
    () => data?.entries.find((e) => e.pdfUrl === selectedUrl) ?? data?.latest ?? null,
    [data, selectedUrl],
  );

  const effectiveDate = formatDate(selectedRoster?.parsedDate);
  const checkedDate = data?.fetchedAt
    ? new Date(data.fetchedAt).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
    : null;

  return (
    <div className="flex h-[calc(100vh-80px)] flex-col gap-5">

      {/* ── Page header ── */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">
              Kerala High Court Roster
            </h1>
            <p className="text-sm text-slate-500">
              {effectiveDate ? `Effective ${effectiveDate}` : "Current bench assignments"}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button variant="ghost" size="sm" asChild className="text-slate-500 hover:text-slate-700">
            <Link href="/dashboard">
              <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
              Dashboard
            </Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleRefresh()}
            disabled={refreshing || loading}
            className="gap-1.5"
          >
            <RefreshCcw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            {syncCountdown !== null
              ? `Syncing… ${syncCountdown}s`
              : refreshing
                ? "Syncing…"
                : "Refresh"}
          </Button>
        </div>
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="flex items-center gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── PDF viewer panel ── */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">

        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/70 px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2 text-sm">
            {loading ? (
              <span className="text-slate-400">Loading…</span>
            ) : selectedRoster ? (
              <>
                <span className="truncate font-medium text-slate-800">
                  {selectedRoster.label}
                </span>
                {checkedDate && (
                  <>
                    <span className="shrink-0 text-slate-300">·</span>
                    <span className="shrink-0 text-slate-400">Checked {checkedDate}</span>
                  </>
                )}
              </>
            ) : (
              <span className="text-slate-400">No roster loaded</span>
            )}
          </div>

          {selectedRoster && (
            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                asChild
                className="h-7 gap-1 px-2.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <a href={selectedRoster.sourcePage} target="_blank" rel="noopener noreferrer">
                  KHC website
                  <ExternalLink className="h-3 w-3" />
                </a>
              </Button>
            </div>
          )}
        </div>

        {/* Viewer body */}
        <div className="min-h-0 flex-1">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-2.5 text-sm text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading roster…
            </div>
          ) : selectedUrl ? (
            <iframe
              src={selectedUrl}
              className="h-full w-full border-0"
              title="Kerala High Court Roster"
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <FileText className="h-12 w-12 text-slate-300" />
              <div className="text-center">
                <p className="text-sm font-medium text-slate-600">Roster not yet available</p>
                <p className="mt-1 text-xs text-slate-400">
                  Click Refresh to fetch the latest roster from the High Court website.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
