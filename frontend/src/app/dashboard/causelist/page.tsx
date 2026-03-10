"use client";

import { AdvocateCauseListTable } from "@/components/causelist/AdvocateCauseListTable";
import { useAuth } from "@/contexts/AuthContext";
import { useCauseList } from "@/hooks/useCauseList";
import { refreshAdvocateCauseList, getFullCauseListPdfUrl } from "@/lib/api";
import { AlertCircle, Building2, CalendarDays, ExternalLink, Gavel, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import ChatWidget from "@/components/agent/ChatWidget";

function toIsoDate(value: Date): string {
  const yyyy = value.getFullYear();
  const mm = String(value.getMonth() + 1).padStart(2, "0");
  const dd = String(value.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function formatLongDate(d: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(d);
}

function CauseListSkeleton() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm animate-pulse">
      <div className="mb-5 h-5 w-56 rounded bg-slate-200" />
      <div className="mb-4 h-4 w-72 rounded bg-slate-100" />
      <div className="overflow-hidden rounded-xl border border-slate-200">
        <div className="grid grid-cols-7 gap-2 bg-slate-50 px-4 py-3">
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="h-3 rounded bg-slate-200" />
          ))}
        </div>
        {[1, 2, 3].map((row) => (
          <div key={row} className="grid grid-cols-7 gap-2 border-t border-slate-100 px-4 py-4">
            {[1, 2, 3, 4, 5, 6, 7].map((i) => (
              <div key={i} className="h-3 rounded bg-slate-100" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CauseListPage() {
  // Default to today in IST
  const [selectedDate, setSelectedDate] = useState(
    () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })
  );

  // Tomorrow in IST — max selectable date
  const maxDate = useMemo(() => {
    const todayIST = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    const [y, m, d] = todayIST.split("-").map(Number);
    return toIsoDate(new Date(y, m - 1, d + 1));
  }, []);

  const { user, token } = useAuth();
  const { data, loading, error, refetch, setData } = useCauseList(selectedDate);

  const [runningJob, setRunningJob] = useState(false);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);

  const [fullListLoading, setFullListLoading] = useState(false);
  const [fullListError, setFullListError] = useState<string | null>(null);

  const selectedDateObj = useMemo(() => {
    const [y, m, d] = selectedDate.split("-").map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
  }, [selectedDate]);

  const totalListings = data?.total ?? 0;
  const isEmpty = !loading && !error && totalListings === 0;
  const hasContent = !loading && !error && totalListings > 0;

  // Refresh: live-fetch from hckinfo via Oracle VM, then update data directly.
  // No polling needed — the endpoint is synchronous (waits for the scraper).
  const runJob = async () => {
    if (!token) return;
    setRunningJob(true);
    setJobMessage(null);
    setJobError(null);
    try {
      const res = await refreshAdvocateCauseList(token, selectedDate);
      setData(res);
      setJobMessage(
        res.total > 0
          ? `Fetched ${res.total} listing${res.total === 1 ? "" : "s"} from hckinfo.`
          : "No listings found for this date on hckinfo."
      );
    } catch (err) {
      setJobError(err instanceof Error ? err.message : "Failed to refresh cause list.");
    } finally {
      setRunningJob(false);
    }
  };

  // Full list: fetch PDF URL from hckinfo via backend → open in new tab
  const openFullList = async () => {
    if (!token) return;
    setFullListLoading(true);
    setFullListError(null);
    try {
      const res = await getFullCauseListPdfUrl(token, selectedDate);
      window.open(res.pdf_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setFullListError(
        err instanceof Error ? err.message : "Could not fetch full cause list link."
      );
    } finally {
      setFullListLoading(false);
    }
  };

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Cause List</h1>
              <p className="mt-1 text-sm text-slate-600">{formatLongDate(selectedDateObj)}</p>
              <p className="mt-1 text-xs text-slate-500">
                {user?.khc_advocate_name
                  ? `Showing listings for ${user.khc_advocate_name}`
                  : "Showing your listings"}
              </p>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                <span className="inline-flex items-center gap-1">
                  <CalendarDays className="h-3.5 w-3.5" /> Date
                </span>
                <input
                  type="date"
                  value={selectedDate}
                  max={maxDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none"
                />
              </label>

              <button
                type="button"
                onClick={runJob}
                disabled={runningJob}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <RefreshCcw className={`h-4 w-4 ${runningJob ? "animate-spin" : ""}`} />
                {runningJob ? "Fetching..." : "Refresh"}
              </button>

              <button
                type="button"
                onClick={openFullList}
                disabled={fullListLoading}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <ExternalLink className={`h-4 w-4 ${fullListLoading ? "animate-pulse" : ""}`} />
                {fullListLoading ? "Opening..." : "Latest Full Cause List"}
              </button>
            </div>
          </div>

          {fullListError && (
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              {fullListError}
            </div>
          )}

          {(jobMessage || jobError) && (
            <div
              className={`mt-4 rounded-lg border px-3 py-2 text-sm ${
                jobError
                  ? "border-rose-200 bg-rose-50 text-rose-700"
                  : "border-emerald-200 bg-emerald-50 text-emerald-700"
              }`}
            >
              {jobError || jobMessage}
            </div>
          )}
        </section>

        {/* Listing count badge */}
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          {!loading && !error && totalListings > 0 ? (
            <div className="flex items-center gap-2 text-sm text-slate-700">
              <Building2 className="h-4 w-4 text-slate-500" />
              <span>
                {totalListings} listing{totalListings === 1 ? "" : "s"}
              </span>
            </div>
          ) : (
            <p className="text-sm text-slate-600">No listings for this date</p>
          )}
        </section>

        {/* Loading */}
        {loading && <CauseListSkeleton />}

        {/* Error */}
        {!loading && error && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 text-rose-600" />
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-rose-900">Could not load cause list</h2>
                <p className="mt-1 text-sm text-rose-700">{error}</p>
                <button
                  type="button"
                  onClick={() => void refetch()}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium text-white hover:bg-rose-800"
                >
                  <RefreshCcw className="h-4 w-4" />
                  Retry
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Empty */}
        {isEmpty && (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <div className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-600">
              <Gavel className="h-7 w-7" />
            </div>
            <h2 className="text-lg font-semibold text-slate-900">No listings found</h2>
            <p className="mt-2 text-sm text-slate-600">
              No cases found for this date. Click <strong>Refresh</strong> to fetch live data from hckinfo.
            </p>
          </div>
        )}

        {/* Results table */}
        {hasContent && data?.rows && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm overflow-hidden">
            <AdvocateCauseListTable rows={data.rows} />
          </div>
        )}
      </div>

      <ChatWidget page="global" />
    </>
  );
}
