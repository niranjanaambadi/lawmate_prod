"use client";

import { useAuth } from "@/contexts/AuthContext";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  BellRing,
  CalendarDays,
  Clock3,
  FileText,
  FolderOpen,
  RefreshCw,
} from "lucide-react";
import {
  getPendingCaseStatuses,
  getTrackedCaseStatuses,
  getTodayAtCourt,
  refreshAllPendingStatuses,
  refreshOnePendingStatus,
  type CauseListDayGroup,
  type PendingCaseStatusRow,
  type TrackedCaseStatusRow,
} from "@/lib/api";
import ChatWidget from "@/components/agent/ChatWidget";

type DashboardRosterData = {
  latest?: {
    parsedDate: string | null;
  };
};

type DashboardReminder = {
  event_id: string;
  title: string;
  start_datetime: string;
  all_day: boolean;
};

function formatRosterDate(value: string | null | undefined): string {
  if (!value) return "Latest roster available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Latest roster available";
  return `Roster date: ${date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  })}`;
}

function formatDateShort(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString();
}


export default function DashboardPage() {
  const { user, token } = useAuth();
  const queryClient = useQueryClient();
  const apiBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

  // ── UI-only state ──────────────────────────────────────────────────────────
  const [clockNow, setClockNow] = useState(new Date());
  const [refreshAllSummary, setRefreshAllSummary] = useState<{
    refreshed: number;
    failed: number;
    skipped: number;
  } | null>(null);
  const [newReminderTitle, setNewReminderTitle] = useState("");
  const [newReminderDate, setNewReminderDate] = useState(new Date().toISOString().slice(0, 10));
  const [showReminderForm, setShowReminderForm] = useState(false);

  // Stable date range for reminders (computed once at mount)
  const reminderDateFrom = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const reminderDateTo = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return d.toISOString().slice(0, 10);
  }, []);
  // Clock ticker
  useEffect(() => {
    const timer = setInterval(() => setClockNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // ── Queries ────────────────────────────────────────────────────────────────
  const rosterQuery = useQuery({
    queryKey: ["rosterSummary"],
    queryFn: async () => {
      const res = await fetch("/api/kerala-high-court/roster", { cache: "no-store" });
      return res.json() as Promise<DashboardRosterData>;
    },
    staleTime: 10 * 60 * 1000,
  });

  const todayAtCourtQuery = useQuery({
    queryKey: ["todayAtCourt", token],
    queryFn: () => getTodayAtCourt(token!),
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  const pendingQuery = useQuery({
    queryKey: ["pendingStatuses", token],
    queryFn: () => getPendingCaseStatuses(token!),
    enabled: !!token,
    staleTime: 2 * 60 * 1000,
  });

  const trackedQuery = useQuery({
    queryKey: ["trackedStatuses", token],
    queryFn: () => getTrackedCaseStatuses(token!),
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  const remindersQuery = useQuery({
    queryKey: ["reminders", token, reminderDateFrom, reminderDateTo],
    queryFn: async () => {
      const res = await fetch(
        `${apiBase}/api/v1/calendar/events?date_from=${reminderDateFrom}&date_to=${reminderDateTo}&event_type=reminder`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || "Failed to load reminders");
      }
      const data = (await res.json()) as DashboardReminder[];
      const items = Array.isArray(data) ? data : [];
      return items.sort(
        (a, b) => new Date(a.start_datetime).getTime() - new Date(b.start_datetime).getTime()
      );
    },
    enabled: !!token,
    staleTime: 2 * 60 * 1000,
  });

  // ── Mutations ──────────────────────────────────────────────────────────────
  const addReminderMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${apiBase}/api/v1/calendar/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          title: newReminderTitle.trim(),
          event_type: "reminder",
          start_datetime: `${newReminderDate}T09:00:00`,
          all_day: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || "Could not add reminder");
      }
      return res.json() as Promise<DashboardReminder>;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["reminders", token, reminderDateFrom, reminderDateTo],
      });
      setNewReminderTitle("");
      setShowReminderForm(false);
    },
  });

  const completeReminderMutation = useMutation({
    mutationFn: async (eventId: string) => {
      const res = await fetch(`${apiBase}/api/v1/calendar/events/${eventId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok && res.status !== 204) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || "Could not complete reminder");
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["reminders", token, reminderDateFrom, reminderDateTo],
      });
    },
  });

  const refreshAllMutation = useMutation({
    mutationFn: () => refreshAllPendingStatuses(token!),
    onSuccess: (result) => {
      setRefreshAllSummary({
        refreshed: result.refreshed,
        failed: result.failed,
        skipped: result.skipped,
      });
      void queryClient.invalidateQueries({ queryKey: ["pendingStatuses", token] });
    },
    onError: () => {
      setRefreshAllSummary({ refreshed: 0, failed: pendingRows.length, skipped: 0 });
    },
  });

  const refreshOneRowMutation = useMutation({
    mutationFn: (caseId: string) => refreshOnePendingStatus(token!, caseId),
    onSuccess: (_, caseId) => {
      void queryClient.invalidateQueries({ queryKey: ["pendingStatuses", token] });
      void queryClient.invalidateQueries({ queryKey: ["case", caseId, token] });
    },
  });

  // ── Derived values (variable-named to match original JSX) ──────────────────
  const rosterSubtitle = rosterQuery.isError
    ? "Open latest available roster"
    : rosterQuery.data
    ? formatRosterDate(rosterQuery.data.latest?.parsedDate)
    : "Loading latest roster...";

  const todayAtCourt: CauseListDayGroup | null = todayAtCourtQuery.data?.days?.[0] ?? null;
  const pendingRows: PendingCaseStatusRow[] = pendingQuery.data ?? [];
  const trackedStatusRows: TrackedCaseStatusRow[] = trackedQuery.data ?? [];
  const reminders: DashboardReminder[] = remindersQuery.data ?? [];
  const remindersLoading = remindersQuery.isLoading;

  const refreshAllLoading = refreshAllMutation.isPending;
  const addingReminder = addReminderMutation.isPending;
  const completingReminderId = completeReminderMutation.isPending
    ? (completeReminderMutation.variables as string)
    : null;
  const rowRefreshingId = refreshOneRowMutation.isPending
    ? (refreshOneRowMutation.variables as string)
    : null;

  const remindersError: string | null = (() => {
    const err =
      remindersQuery.error ?? addReminderMutation.error ?? completeReminderMutation.error;
    return err instanceof Error ? err.message : err ? String(err) : null;
  })();

  // ── Handlers ───────────────────────────────────────────────────────────────
  const addReminder = () => {
    if (!token || !newReminderTitle.trim() || !newReminderDate || addingReminder) return;
    addReminderMutation.mutate();
  };

  const completeReminder = (eventId: string) => {
    if (!token || completeReminderMutation.isPending) return;
    completeReminderMutation.mutate(eventId);
  };

  const handleRefreshAll = () => {
    if (!token || refreshAllLoading) return;
    refreshAllMutation.mutate();
  };

  const handleRefreshOneRow = (caseId: string) => {
    if (!token || refreshOneRowMutation.isPending) return;
    refreshOneRowMutation.mutate(caseId);
  };

  return (
    <>
    <div className="space-y-8">
      {/* Welcome banner */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Welcome back, {user?.khc_advocate_name?.split(" ")?.[0] || "Advocate"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {user?.khc_advocate_name}
            {user?.email && ` · ${user.email}`}
            {user?.khc_advocate_id && ` · KHC ID: ${user.khc_advocate_id}`}
          </p>
        </div>
        <Button asChild variant="outline" size="sm" className="hidden sm:flex">
          <Link href="/dashboard/cases">
            View all cases
            <ArrowRight className="ml-2 h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>

      {/* Quick access tiles */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">

        {/* ── Roster ── */}
        <Link href="/dashboard/roster" className="group block focus:outline-none">
          <div className="relative flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 ease-out hover:-translate-y-1.5 hover:border-indigo-200 hover:shadow-xl hover:shadow-indigo-100/60">
            <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-200/60">
              <FileText className="h-5 w-5" />
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-indigo-400">Roster</p>
            <h3 className="mt-0.5 font-semibold text-slate-900">Kerala HC Roster</h3>
            <p className="mt-1.5 flex-1 text-xs text-slate-500 leading-relaxed">{rosterSubtitle}</p>
            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-indigo-600">
              View latest
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </div>
        </Link>

        {/* ── Reminders (interactive content — overlay link + z-index layers) ── */}
        <div className="group relative flex flex-col rounded-2xl border border-slate-200 bg-white shadow-sm transition-all duration-200 ease-out hover:-translate-y-1.5 hover:border-amber-200 hover:shadow-xl hover:shadow-amber-100/60">
          {/* Background nav overlay — sits below interactive elements */}
          <Link href="/dashboard/calendar" className="absolute inset-0 z-0 rounded-2xl" aria-label="Open Reminders" />
          <div className="relative z-10 flex flex-1 flex-col p-5">
            <div className="mb-4 flex items-start justify-between">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-md shadow-amber-200/60">
                <BellRing className="h-5 w-5" />
              </div>
              <button
                type="button"
                className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-base font-medium text-slate-500 shadow-sm transition-colors hover:border-amber-300 hover:text-amber-600"
                onClick={() => setShowReminderForm((prev) => !prev)}
                title={showReminderForm ? "Close" : "Add reminder"}
              >
                {showReminderForm ? "−" : "+"}
              </button>
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-amber-500">Reminders</p>
            <h3 className="mt-0.5 font-semibold text-slate-900">Upcoming Reminders</h3>

            {showReminderForm && (
              <div className="mt-3 space-y-2">
                <input
                  value={newReminderTitle}
                  onChange={(e) => setNewReminderTitle(e.target.value)}
                  placeholder="Add reminder..."
                  className="h-9 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
                <div className="flex gap-2">
                  <input
                    type="date"
                    value={newReminderDate}
                    onChange={(e) => setNewReminderDate(e.target.value)}
                    className="h-9 flex-1 rounded-lg border border-slate-200 px-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                  <Button size="sm" className="h-9 bg-amber-500 hover:bg-amber-600 text-white" onClick={addReminder} disabled={addingReminder || !newReminderTitle.trim()}>
                    {addingReminder ? "…" : "Add"}
                  </Button>
                </div>
              </div>
            )}

            <div className="mt-3 max-h-36 flex-1 overflow-y-auto rounded-xl border border-slate-100 bg-slate-50 p-2">
              {remindersLoading ? (
                <p className="px-1 py-2 text-xs text-slate-400">Loading…</p>
              ) : reminders.length === 0 ? (
                <p className="px-1 py-2 text-xs text-slate-400">No reminders yet.</p>
              ) : (
                <ul className="space-y-1">
                  {reminders.map((item) => (
                    <li key={item.event_id} className="rounded-lg bg-white px-2 py-1.5 shadow-sm">
                      <label className="flex cursor-pointer items-start gap-2">
                        <input
                          type="checkbox"
                          className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300 accent-amber-500"
                          checked={false}
                          onChange={() => completeReminder(item.event_id)}
                          disabled={completingReminderId === item.event_id}
                        />
                        <span className="flex-1">
                          <span className="block text-xs font-medium text-slate-800">{item.title}</span>
                          <span className="block text-[11px] text-slate-400">{formatDateShort(item.start_datetime)}</span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {remindersError && <p className="mt-1 text-xs text-red-500">{remindersError}</p>}

            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-amber-600">
              Open calendar
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </div>
        </div>

        {/* ── Calendar / IST Clock ── */}
        <Link href="/dashboard/calendar" className="group block focus:outline-none">
          <div className="relative flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 ease-out hover:-translate-y-1.5 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-100/60">
            <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-md shadow-emerald-200/60">
              <Clock3 className="h-5 w-5" />
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-emerald-500">Calendar</p>
            <h3 className="mt-0.5 font-semibold text-slate-900">Calendar (IST)</h3>
            <div className="mt-3 flex-1 rounded-xl border border-slate-100 bg-slate-50 px-3.5 py-3">
              <p className="text-xl font-bold tabular-nums text-slate-900">
                {new Intl.DateTimeFormat("en-IN", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                  hour12: true,
                  timeZone: "Asia/Kolkata",
                }).format(clockNow)}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {new Intl.DateTimeFormat("en-IN", {
                  weekday: "long",
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                  timeZone: "Asia/Kolkata",
                }).format(clockNow)}{" "}
                · IST
              </p>
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-emerald-600">
              Open calendar
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </div>
        </Link>

        {/* ── Today at Court ── */}
        <Link href="/dashboard/causelist" className="group block focus:outline-none">
          <div className="relative flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 ease-out hover:-translate-y-1.5 hover:border-sky-200 hover:shadow-xl hover:shadow-sky-100/60">
            <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-md shadow-sky-200/60">
              <CalendarDays className="h-5 w-5" />
            </div>
            <p className="text-[11px] font-semibold uppercase tracking-widest text-sky-500">Cause List</p>
            <h3 className="mt-0.5 font-semibold text-slate-900">Today at Court</h3>
            <p className="mt-1 text-xs text-slate-500">
              {todayAtCourt?.items?.length
                ? `${todayAtCourt.items.length} relevant entr${todayAtCourt.items.length > 1 ? "ies" : "y"} today`
                : "No matched cases from today's cause list"}
            </p>
            <div className="mt-3 flex-1 space-y-1.5">
              {todayAtCourt?.items?.slice(0, 3).map((item) => (
                <div
                  key={`${item.case_id}-${item.source}-${item.listing_date}`}
                  className="rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-2"
                >
                  <p className="text-xs font-semibold text-slate-800">{item.case_number || item.efiling_number}</p>
                  <p className="text-[11px] text-slate-400">{item.case_type} · {item.source}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-sky-600">
              Open cause list
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
            </div>
          </div>
        </Link>

      </div>

      {/* Status Updates — pending cases with latest hearing history */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle>Status Updates</CardTitle>
              <CardDescription>
                {pendingRows.length > 0
                  ? `${pendingRows.length} pending case${pendingRows.length !== 1 ? "s" : ""} — latest hearing details from court`
                  : "Pending cases with latest hearing details from court"}
              </CardDescription>
              {refreshAllSummary && (
                <p className="mt-1.5 text-xs text-slate-500">
                  Last sync: {refreshAllSummary.refreshed} updated
                  {refreshAllSummary.failed > 0 && `, ${refreshAllSummary.failed} failed`}
                  {refreshAllSummary.skipped > 0 && `, ${refreshAllSummary.skipped} skipped`}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRefreshAll}
                disabled={refreshAllLoading || pendingRows.length === 0}
                title="Sync all pending cases from KHC portal"
              >
                <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${refreshAllLoading ? "animate-spin" : ""}`} />
                {refreshAllLoading ? "Syncing…" : "Refresh All"}
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link href="/dashboard/cases?status=pending">
                  View all
                  <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {pendingRows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <Clock3 className="mb-2 h-8 w-8 text-slate-200" />
              <p className="text-sm text-slate-500">
                No pending cases found. Add cases with status &quot;pending&quot; or use the case detail page to sync from the court portal.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Case Number</th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Business Date</th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Tentative Date</th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Purpose of Hearing</th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Order</th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Hon&apos; Judge</th>
                    <th className="pb-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Sync</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {pendingRows.map((row) => {
                    const isRowRefreshing = rowRefreshingId === row.id;
                    const neverSynced = !row.last_synced_at;
                    return (
                      <tr key={row.id} className="group transition-colors hover:bg-slate-50">
                        <td className="py-3 pr-4">
                          <Link
                            href={`/dashboard/cases/${row.id}`}
                            className="font-medium text-indigo-600 hover:underline"
                          >
                            {row.case_number}
                          </Link>
                          {neverSynced && (
                            <span className="ml-2 inline-block rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                              Not synced
                            </span>
                          )}
                        </td>
                        <td className="py-3 pr-4 text-slate-600">{row.business_date || "-"}</td>
                        <td className="py-3 pr-4 text-slate-600">{row.tentative_date || "-"}</td>
                        <td className="py-3 pr-4 text-slate-600">{row.purpose_of_hearing || "-"}</td>
                        <td className="py-3 pr-4 max-w-[14rem] text-slate-600">
                          <span className="line-clamp-2">{row.order_text || "-"}</span>
                        </td>
                        <td className="py-3 pr-4 text-slate-600">{row.judge_name || "-"}</td>
                        <td className="py-3">
                          <button
                            onClick={() => handleRefreshOneRow(row.id)}
                            disabled={!!rowRefreshingId || refreshAllLoading}
                            title={`Refresh ${row.case_number} from KHC portal`}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-indigo-600 disabled:opacity-40 transition-colors"
                          >
                            <RefreshCw className={`h-3.5 w-3.5 ${isRowRefreshing ? "animate-spin text-indigo-600" : ""}`} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tracked Cases */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle>Tracked Cases</CardTitle>
          <CardDescription>Cases you manually track (stored in tracked_cases)</CardDescription>
        </CardHeader>
        <CardContent>
          {trackedStatusRows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <FolderOpen className="mb-2 h-8 w-8 text-slate-200" />
              <p className="text-sm text-slate-500">No tracked cases added yet.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Case Number
                    </th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Status
                    </th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Stage
                    </th>
                    <th className="pb-3 pr-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Next Hearing
                    </th>
                    <th className="pb-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Updated
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {trackedStatusRows.slice(0, 10).map((row) => (
                    <tr key={row.id} className="transition-colors hover:bg-slate-50">
                      <td className="py-3 pr-4 font-medium text-slate-800">{row.case_number}</td>
                      <td className="py-3 pr-4 text-slate-600">{row.status_text || "-"}</td>
                      <td className="py-3 pr-4 text-slate-600">{row.stage || "-"}</td>
                      <td className="py-3 pr-4 text-slate-600">
                        {row.next_hearing_date ? formatDateShort(row.next_hearing_date) : "-"}
                      </td>
                      <td className="py-3 text-xs text-slate-400">
                        {new Date(row.updated_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
    <ChatWidget page="global" />
  </>
  );
}
