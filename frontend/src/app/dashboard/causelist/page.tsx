"use client";

import { CauseListContent } from "@/components/causelist/CauseListContent";
import { useAuth } from "@/contexts/AuthContext";
import { useCauseList } from "@/hooks/useCauseList";
import { runCauseListJobForDate } from "@/lib/api";
import { AlertCircle, Building2, CalendarDays, CheckCircle2, Gavel, Loader2, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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
        <div className="grid grid-cols-6 gap-2 bg-slate-50 px-4 py-3">
          <div className="h-3 rounded bg-slate-200" />
          <div className="h-3 rounded bg-slate-200" />
          <div className="h-3 rounded bg-slate-200" />
          <div className="h-3 rounded bg-slate-200" />
          <div className="h-3 rounded bg-slate-200" />
          <div className="h-3 rounded bg-slate-200" />
        </div>
        {[1, 2, 3].map((row) => (
          <div key={row} className="grid grid-cols-6 gap-2 border-t border-slate-100 px-4 py-4">
            <div className="h-3 rounded bg-slate-100" />
            <div className="h-3 rounded bg-slate-100" />
            <div className="h-3 rounded bg-slate-100" />
            <div className="h-3 rounded bg-slate-100" />
            <div className="h-3 rounded bg-slate-100" />
            <div className="h-3 rounded bg-slate-100" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CauseListPage() {
  const today = useMemo(() => new Date(), []);
  const [selectedDate, setSelectedDate] = useState(toIsoDate(today));
  const { user, token } = useAuth();
  const { data, loading, error, refetch } = useCauseList(selectedDate);
  const [runningJob, setRunningJob] = useState(false);
  const [jobMessage, setJobMessage] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [pollSeconds, setPollSeconds] = useState(0);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);
  const POLL_INTERVAL_MS = 5000;
  const MAX_POLLS = 36; // 3 minutes

  const selectedDateObj = useMemo(() => {
    const [y, m, d] = selectedDate.split("-").map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
  }, [selectedDate]);

  const totalListings = data?.total_listings ?? 0;
  const isEmpty = !loading && !error && totalListings === 0;
  const hasContent = !loading && !error && totalListings > 0 && Boolean(data?.html);

  // Stop polling when data arrives or component unmounts
  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    pollCountRef.current = 0;
    setPollSeconds(0);
  };

  useEffect(() => {
    if (totalListings > 0 && pollIntervalRef.current) {
      stopPolling();
      setRunningJob(false);
      setJobMessage("Cause list loaded successfully.");
    }
  }, [totalListings]);

  useEffect(() => () => stopPolling(), []);

  const runJob = async () => {
    if (!token) return;
    setRunningJob(true);
    setJobMessage(null);
    setJobError(null);
    stopPolling();
    pollCountRef.current = 0;

    try {
      await runCauseListJobForDate(selectedDate, token);
      setJobMessage("Job started in background — results will appear automatically.");

      // Poll refetch every 5 s for up to 3 minutes
      let elapsed = 0;
      pollIntervalRef.current = setInterval(async () => {
        pollCountRef.current += 1;
        elapsed += POLL_INTERVAL_MS / 1000;
        setPollSeconds(elapsed);

        await refetch();

        if (pollCountRef.current >= MAX_POLLS) {
          stopPolling();
          setRunningJob(false);
          setJobMessage(
            "Job is still running in the background — refresh the page in a few minutes."
          );
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setRunningJob(false);
      setJobError(err instanceof Error ? err.message : "Failed to start daily cause list job.");
    }
  };

  return (<>
    <div className="space-y-6">
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
              <span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" /> Date</span>
              <input
                type="date"
                value={selectedDate}
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
              {runningJob ? "Running..." : "Run Daily Job"}
            </button>
          </div>
        </div>

        {(jobMessage || jobError) && (
          <div className={`mt-4 rounded-lg border px-3 py-2 text-sm ${jobError ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
            {jobError || jobMessage}
          </div>
        )}
      </section>

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

      {loading && <CauseListSkeleton />}

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

      {isEmpty && (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
          <div className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-600">
            <Gavel className="h-7 w-7" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900">No listings today</h2>
          <p className="mt-2 text-sm text-slate-600">You have no cases listed for this date. Check back tomorrow.</p>
        </div>
      )}

      {hasContent && data?.html && <CauseListContent html={data.html} />}
    </div>
    <ChatWidget page="global" /> 
    </>
  );
}
