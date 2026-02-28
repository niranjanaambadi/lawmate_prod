// export default function CalendarPage() {
//   return (
//     <div className="container mx-auto py-8">
//       <h1 className="text-3xl font-bold">Calendar</h1>
//       <p className="mt-1 text-slate-600">Hearing calendar will be implemented here.</p>
//     </div>
//   );
// }

"use client";

/**
 * src/app/dashboard/calendar/page.tsx
 *
 * LawMate Calendar — monthly view with event management and Google Calendar sync.
 *
 * Features:
 *  - Month grid view with event dots
 *  - Day detail panel (click any date)
 *  - Create / delete events
 *  - Google Calendar connect / sync
 *  - Event type colour coding
 *  - ChatWidget for AI scheduling assistance
 */

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/contexts/AuthContext";

// ── Types ────────────────────────────────────────────────────────────────────

interface CalendarEvent {
  event_id:       string;
  title:          string;
  event_type:     string;
  source:         string;
  start_datetime: string;
  end_datetime:   string | null;
  all_day:        boolean;
  location:       string | null;
  description:    string | null;
  case_id:        string | null;
  google_synced:  boolean;
}

interface GoogleStatus {
  connected:       boolean;
  calendar_id?:    string;
  last_synced_at?: string;
  last_sync_error?: string;
}

interface CreateEventForm {
  title:          string;
  event_type:     string;
  start_datetime: string;
  all_day:        boolean;
  location:       string;
  description:    string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DAYS    = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS  = ["January","February","March","April","May","June",
                 "July","August","September","October","November","December"];

const EVENT_COLORS: Record<string, string> = {
  hearing:  "#b45309",   // amber-700
  deadline: "#dc2626",   // red-600
  filing:   "#7c3aed",   // violet-600
  reminder: "#0369a1",   // sky-700
  meeting:  "#047857",   // emerald-700
  other:    "#64748b",   // slate-500
};

const EVENT_LABELS: Record<string, string> = {
  hearing:  "Hearing",
  deadline: "Deadline",
  filing:   "Filing",
  reminder: "Reminder",
  meeting:  "Meeting",
  other:    "Other",
};

const EMPTY_FORM: CreateEventForm = {
  title:          "",
  event_type:     "hearing",
  start_datetime: "",
  all_day:        true,
  location:       "",
  description:    "",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

function formatDisplay(dt: string, allDay: boolean) {
  if (allDay) {
    const d = new Date(dt + "T00:00:00");
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  }
  const d = new Date(dt);
  return d.toLocaleString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

function groupByDate(events: CalendarEvent[]): Record<string, CalendarEvent[]> {
  const map: Record<string, CalendarEvent[]> = {};
  for (const e of events) {
    const key = e.start_datetime.slice(0, 10);
    if (!map[key]) map[key] = [];
    map[key].push(e);
  }
  return map;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CalendarPage() {
  const { token } = useAuth();

  const today = new Date();
  const [year,  setYear]  = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());

  const [events,        setEvents]        = useState<CalendarEvent[]>([]);
  const [eventsByDate,  setEventsByDate]  = useState<Record<string, CalendarEvent[]>>({});
  const [selectedDate,  setSelectedDate]  = useState<string>(isoDate(today));
  const [googleStatus,  setGoogleStatus]  = useState<GoogleStatus>({ connected: false });
  const [loading,       setLoading]       = useState(true);
  const [syncing,       setSyncing]       = useState(false);
  const [showForm,      setShowForm]      = useState(false);
  const [form,          setForm]          = useState<CreateEventForm>(EMPTY_FORM);
  const [saving,        setSaving]        = useState(false);
  const [error,         setError]         = useState<string | null>(null);
  const apiBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

  // ── API helpers ─────────────────────────────────────────────────────────────

  const apiFetch = useCallback(async (path: string, options: RequestInit = {}) => {
    const res = await fetch(`${apiBase}/api/v1${path}`, {
      ...options,
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${token}`,
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const errJson = await res.json().catch(() => ({}));
        const detail = (errJson as { detail?: string }).detail;
        throw new Error(detail || `Request failed: ${res.status}`);
      }
      throw new Error(`Request failed: ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json();
  }, [apiBase, token]);

  // ── Load events for current month ──────────────────────────────────────────

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const firstDay = new Date(year, month, 1);
      const lastDay  = new Date(year, month + 1, 0);
      const data: CalendarEvent[] = await apiFetch(
        `/calendar/events?date_from=${isoDate(firstDay)}&date_to=${isoDate(lastDay)}`
      );
      setEvents(data);
      setEventsByDate(groupByDate(data));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [year, month, apiFetch]);

  // ── Load Google status ──────────────────────────────────────────────────────

  const loadGoogleStatus = useCallback(async () => {
    try {
      const data: GoogleStatus = await apiFetch("/calendar/google/status");
      setGoogleStatus(data);
    } catch { /* non-critical */ }
  }, [apiFetch]);

  useEffect(() => { loadEvents(); },       [loadEvents]);
  useEffect(() => { loadGoogleStatus(); }, [loadGoogleStatus]);

  // ── Calendar grid ───────────────────────────────────────────────────────────

  const firstDayOfMonth = new Date(year, month, 1).getDay();
  const daysInMonth     = new Date(year, month + 1, 0).getDate();
  const prevMonthDays   = new Date(year, month, 0).getDate();

  const cells: { date: string; isCurrentMonth: boolean; isToday: boolean }[] = [];

  // Leading days from previous month
  for (let i = firstDayOfMonth - 1; i >= 0; i--) {
    const d = new Date(year, month - 1, prevMonthDays - i);
    cells.push({ date: isoDate(d), isCurrentMonth: false, isToday: false });
  }
  // Current month days
  for (let d = 1; d <= daysInMonth; d++) {
    const dt = new Date(year, month, d);
    cells.push({
      date:           isoDate(dt),
      isCurrentMonth: true,
      isToday:        isoDate(dt) === isoDate(today),
    });
  }
  // Trailing days to complete grid (6 rows × 7 = 42)
  const trailing = 42 - cells.length;
  for (let d = 1; d <= trailing; d++) {
    const dt = new Date(year, month + 1, d);
    cells.push({ date: isoDate(dt), isCurrentMonth: false, isToday: false });
  }

  // ── Navigation ──────────────────────────────────────────────────────────────

  const prevMonth = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  };
  const goToday = () => {
    setYear(today.getFullYear());
    setMonth(today.getMonth());
    setSelectedDate(isoDate(today));
  };

  // ── Selected day events ─────────────────────────────────────────────────────

  const selectedEvents = eventsByDate[selectedDate] || [];

  // ── Create event ────────────────────────────────────────────────────────────

  const openCreateForm = () => {
    setForm({
      ...EMPTY_FORM,
      start_datetime: selectedDate,
    });
    setShowForm(true);
  };

  const handleCreate = async () => {
    if (!form.title || !form.start_datetime) return;
    setSaving(true);
    try {
      await apiFetch("/calendar/events", {
        method: "POST",
        body:   JSON.stringify({
          title:          form.title,
          event_type:     form.event_type,
          start_datetime: form.all_day
            ? `${form.start_datetime}T00:00:00`
            : form.start_datetime,
          all_day:        form.all_day,
          location:       form.location || null,
          description:    form.description || null,
        }),
      });
      setShowForm(false);
      setForm(EMPTY_FORM);
      await loadEvents();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Delete event ────────────────────────────────────────────────────────────

  const handleDelete = async (eventId: string) => {
    if (!confirm("Remove this event?")) return;
    try {
      await apiFetch(`/calendar/events/${eventId}`, { method: "DELETE" });
      await loadEvents();
    } catch (e: any) {
      setError(e.message);
    }
  };

  // ── Google sync ─────────────────────────────────────────────────────────────

  const handleGoogleConnect = async () => {
    try {
      const data = await apiFetch("/calendar/google/auth-url");
      window.location.href = data.auth_url;
    } catch (e: any) {
      if (e instanceof TypeError && e.message === "Failed to fetch") {
        setError("Cannot reach the server — make sure the backend is running.");
      } else {
        setError(e.message);
      }
    }
  };

  const handleGoogleSync = async () => {
    setSyncing(true);
    try {
      await apiFetch("/calendar/google/sync", { method: "POST" });
      await loadEvents();
      await loadGoogleStatus();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSyncing(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=DM+Sans:wght@300;400;500&display=swap');

        .cal-root {
          font-family: 'DM Sans', sans-serif;
          background: #faf9f6;
          min-height: 100vh;
          color: #1e293b;
        }
        .cal-header-title {
          font-family: 'Playfair Display', Georgia, serif;
          font-weight: 600;
          letter-spacing: -0.02em;
        }
        .cal-month-label {
          font-family: 'Playfair Display', Georgia, serif;
          font-weight: 400;
        }
        .cal-grid-cell {
          border: 1px solid #e8e4dc;
          min-height: 88px;
          cursor: pointer;
          transition: background 0.12s;
          position: relative;
          padding: 6px 8px;
        }
        .cal-grid-cell:hover { background: #f1ede6; }
        .cal-grid-cell.selected { background: #fef3c7; border-color: #b45309; }
        .cal-grid-cell.today .day-num {
          background: #1e293b;
          color: #fff;
          border-radius: 50%;
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 500;
        }
        .cal-grid-cell.dimmed { background: #f5f3ef; }
        .cal-grid-cell.dimmed .day-num { color: #c4b89a; }
        .day-num {
          font-size: 12px;
          font-weight: 500;
          color: #475569;
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .event-pill {
          font-size: 10px;
          font-weight: 500;
          padding: 1px 6px;
          border-radius: 3px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 100%;
          margin-top: 2px;
          color: #fff;
          line-height: 1.6;
        }
        .event-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          display: inline-block;
          margin-right: 3px;
          flex-shrink: 0;
        }
        .side-event-row {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 12px 0;
          border-bottom: 1px solid #e8e4dc;
        }
        .side-event-row:last-child { border-bottom: none; }
        .btn-primary {
          background: #1e293b;
          color: #fff;
          border: none;
          padding: 8px 18px;
          border-radius: 6px;
          font-size: 13px;
          font-family: 'DM Sans', sans-serif;
          font-weight: 500;
          cursor: pointer;
          transition: background 0.12s;
        }
        .btn-primary:hover { background: #334155; }
        .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-ghost {
          background: transparent;
          border: 1px solid #e2d9cc;
          padding: 7px 14px;
          border-radius: 6px;
          font-size: 13px;
          font-family: 'DM Sans', sans-serif;
          color: #475569;
          cursor: pointer;
          transition: all 0.12s;
        }
        .btn-ghost:hover { background: #f1ede6; border-color: #c4b89a; }
        .input-field {
          width: 100%;
          border: 1px solid #e2d9cc;
          border-radius: 6px;
          padding: 8px 12px;
          font-size: 13px;
          font-family: 'DM Sans', sans-serif;
          background: #fff;
          color: #1e293b;
          outline: none;
          transition: border 0.12s;
        }
        .input-field:focus { border-color: #b45309; }
        .google-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          padding: 4px 10px;
          border-radius: 20px;
          font-weight: 500;
        }
        .google-badge.connected {
          background: #dcfce7;
          color: #166534;
        }
        .google-badge.disconnected {
          background: #fef9ec;
          color: #92400e;
          border: 1px solid #fde68a;
        }
        .modal-overlay {
          position: fixed; inset: 0;
          background: rgba(15, 20, 35, 0.4);
          backdrop-filter: blur(4px);
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .modal-box {
          background: #fff;
          border-radius: 12px;
          padding: 28px;
          width: 440px;
          max-width: 95vw;
          box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        }
        .legend-dot {
          width: 8px; height: 8px;
          border-radius: 50%;
          display: inline-block;
          margin-right: 5px;
        }
      `}</style>

      <div className="cal-root">
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 24px" }}>

          {/* ── Page Header ── */}
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 28 }}>
            <div>
              <p style={{ fontSize: 11, fontWeight: 500, letterSpacing: "0.1em", color: "#b45309", textTransform: "uppercase", marginBottom: 4 }}>
                Kerala High Court
              </p>
              <h1 className="cal-header-title" style={{ fontSize: 28, color: "#1e293b", margin: 0 }}>
                My Calendar
              </h1>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {/* Google status */}
              {googleStatus.connected ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="google-badge connected">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    Google Calendar
                  </span>
                  <button className="btn-ghost" onClick={handleGoogleSync} disabled={syncing} style={{ fontSize: 12, padding: "5px 12px" }}>
                    {syncing ? "Syncing…" : "↻ Sync"}
                  </button>
                </div>
              ) : (
                <button className="btn-ghost" onClick={handleGoogleConnect} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
                  Connect Google Calendar
                </button>
              )}
              <button className="btn-primary" onClick={openCreateForm}>+ New Event</button>
            </div>
          </div>

          {error && (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#dc2626", borderRadius: 8, padding: "10px 14px", fontSize: 13, marginBottom: 16 }}>
              {error}
              <button onClick={() => setError(null)} style={{ marginLeft: 8, fontWeight: 700, cursor: "pointer", background: "none", border: "none", color: "#dc2626" }}>✕</button>
            </div>
          )}

          {/* ── Main Layout: Calendar + Side Panel ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 24, alignItems: "start" }}>

            {/* ── Calendar Grid ── */}
            <div style={{ background: "#fff", borderRadius: 12, border: "1px solid #e8e4dc", overflow: "hidden", boxShadow: "0 1px 8px rgba(0,0,0,0.04)" }}>

              {/* Month navigation */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: "1px solid #e8e4dc", background: "#faf9f6" }}>
                <button className="btn-ghost" onClick={prevMonth} style={{ padding: "6px 12px" }}>←</button>
                <div style={{ textAlign: "center" }}>
                  <span className="cal-month-label" style={{ fontSize: 20, color: "#1e293b" }}>
                    {MONTHS[month]} {year}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn-ghost" onClick={goToday} style={{ padding: "6px 12px", fontSize: 12 }}>Today</button>
                  <button className="btn-ghost" onClick={nextMonth} style={{ padding: "6px 12px" }}>→</button>
                </div>
              </div>

              {/* Day headers */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", background: "#f5f3ef" }}>
                {DAYS.map(d => (
                  <div key={d} style={{ padding: "8px 0", textAlign: "center", fontSize: 11, fontWeight: 600, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    {d}
                  </div>
                ))}
              </div>

              {/* Date cells */}
              {loading ? (
                <div style={{ padding: 48, textAlign: "center", color: "#94a3b8", fontSize: 14 }}>Loading calendar…</div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)" }}>
                  {cells.map((cell) => {
                    const dayEvents = eventsByDate[cell.date] || [];
                    const isSelected = cell.date === selectedDate;
                    return (
                      <div
                        key={cell.date}
                        className={`cal-grid-cell ${!cell.isCurrentMonth ? "dimmed" : ""} ${cell.isToday ? "today" : ""} ${isSelected ? "selected" : ""}`}
                        onClick={() => setSelectedDate(cell.date)}
                      >
                        <div className="day-num">
                          {parseInt(cell.date.slice(8))}
                        </div>
                        {/* Show up to 2 event pills, rest as count */}
                        {dayEvents.slice(0, 2).map(e => (
                          <div
                            key={e.event_id}
                            className="event-pill"
                            style={{ background: EVENT_COLORS[e.event_type] || EVENT_COLORS.other }}
                            title={e.title}
                          >
                            {e.title}
                          </div>
                        ))}
                        {dayEvents.length > 2 && (
                          <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2, paddingLeft: 2 }}>
                            +{dayEvents.length - 2} more
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Legend */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", padding: "12px 16px", borderTop: "1px solid #e8e4dc", background: "#faf9f6" }}>
                {Object.entries(EVENT_LABELS).map(([type, label]) => (
                  <span key={type} style={{ display: "flex", alignItems: "center", fontSize: 11, color: "#64748b" }}>
                    <span className="legend-dot" style={{ background: EVENT_COLORS[type] }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>

            {/* ── Side Panel: Selected Day ── */}
            <div style={{ background: "#fff", borderRadius: 12, border: "1px solid #e8e4dc", boxShadow: "0 1px 8px rgba(0,0,0,0.04)", overflow: "hidden" }}>

              {/* Side header */}
              <div style={{ padding: "16px 18px", borderBottom: "1px solid #e8e4dc", background: "#faf9f6" }}>
                <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", color: "#b45309", textTransform: "uppercase", margin: 0 }}>
                  {new Date(selectedDate + "T12:00:00").toLocaleDateString("en-IN", { weekday: "long" })}
                </p>
                <p className="cal-month-label" style={{ fontSize: 22, color: "#1e293b", margin: "2px 0 0" }}>
                  {new Date(selectedDate + "T12:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
                </p>
              </div>

              {/* Events for selected day */}
              <div style={{ padding: "4px 18px 12px", maxHeight: 420, overflowY: "auto" }}>
                {selectedEvents.length === 0 ? (
                  <div style={{ padding: "24px 0", textAlign: "center" }}>
                    <div style={{ fontSize: 28, marginBottom: 8 }}>📅</div>
                    <p style={{ fontSize: 13, color: "#94a3b8", margin: 0 }}>No events</p>
                    <button
                      className="btn-ghost"
                      onClick={openCreateForm}
                      style={{ fontSize: 12, marginTop: 12, padding: "6px 14px" }}
                    >
                      + Add event
                    </button>
                  </div>
                ) : (
                  selectedEvents.map(event => (
                    <div key={event.event_id} className="side-event-row">
                      <div style={{
                        width: 3, borderRadius: 2, alignSelf: "stretch", flexShrink: 0,
                        background: EVENT_COLORS[event.event_type] || EVENT_COLORS.other,
                        marginTop: 2,
                      }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                          <p style={{ fontSize: 13, fontWeight: 500, color: "#1e293b", margin: 0, lineHeight: 1.4 }}>
                            {event.title}
                          </p>
                          <button
                            onClick={() => handleDelete(event.event_id)}
                            style={{ background: "none", border: "none", color: "#cbd5e1", cursor: "pointer", fontSize: 14, padding: "0 2px", flexShrink: 0 }}
                            title="Delete event"
                          >
                            ✕
                          </button>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                          <span style={{
                            fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
                            padding: "2px 7px", borderRadius: 3, textTransform: "uppercase",
                            background: EVENT_COLORS[event.event_type] + "22",
                            color: EVENT_COLORS[event.event_type],
                          }}>
                            {EVENT_LABELS[event.event_type] || event.event_type}
                          </span>
                          {event.google_synced && (
                            <span style={{ fontSize: 10, color: "#16a34a" }}>✓ Google</span>
                          )}
                          {event.source === "agent" && (
                            <span style={{ fontSize: 10, color: "#0369a1" }}>⚖️ Agent</span>
                          )}
                          {event.source === "court_sync" && (
                            <span style={{ fontSize: 10, color: "#7c3aed" }}>🏛 Court</span>
                          )}
                        </div>
                        {!event.all_day && (
                          <p style={{ fontSize: 11, color: "#94a3b8", margin: "4px 0 0" }}>
                            {formatDisplay(event.start_datetime, false)}
                          </p>
                        )}
                        {event.location && (
                          <p style={{ fontSize: 11, color: "#94a3b8", margin: "2px 0 0" }}>
                            📍 {event.location}
                          </p>
                        )}
                        {event.description && (
                          <p style={{ fontSize: 11, color: "#64748b", margin: "4px 0 0", lineHeight: 1.5 }}>
                            {event.description}
                          </p>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {selectedEvents.length > 0 && (
                <div style={{ padding: "0 18px 16px" }}>
                  <button className="btn-ghost" onClick={openCreateForm} style={{ width: "100%", fontSize: 12 }}>
                    + Add event on this day
                  </button>
                </div>
              )}

              {/* Google sync info */}
              {googleStatus.connected && googleStatus.last_synced_at && (
                <div style={{ padding: "10px 18px", borderTop: "1px solid #e8e4dc", background: "#faf9f6" }}>
                  <p style={{ fontSize: 10, color: "#94a3b8", margin: 0 }}>
                    Last synced: {new Date(googleStatus.last_synced_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  </p>
                  {googleStatus.last_sync_error && (
                    <p style={{ fontSize: 10, color: "#dc2626", margin: "2px 0 0" }}>
                      ⚠ {googleStatus.last_sync_error}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Create Event Modal ── */}
      {showForm && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowForm(false); }}>
          <div className="modal-box">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <h2 className="cal-header-title" style={{ fontSize: 20, margin: 0 }}>New Event</h2>
              <button onClick={() => setShowForm(false)} style={{ background: "none", border: "none", fontSize: 18, color: "#94a3b8", cursor: "pointer" }}>✕</button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "#475569", display: "block", marginBottom: 5 }}>Title *</label>
                <input
                  className="input-field"
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  placeholder="e.g. Hearing — WP(C) 1234/2024"
                  autoFocus
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "#475569", display: "block", marginBottom: 5 }}>Type</label>
                <select
                  className="input-field"
                  value={form.event_type}
                  onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}
                >
                  {Object.entries(EVENT_LABELS).map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "#475569", display: "block", marginBottom: 5 }}>Date *</label>
                <input
                  className="input-field"
                  type={form.all_day ? "date" : "datetime-local"}
                  value={form.start_datetime}
                  onChange={e => setForm(f => ({ ...f, start_datetime: e.target.value }))}
                />
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  id="all_day"
                  checked={form.all_day}
                  onChange={e => setForm(f => ({ ...f, all_day: e.target.checked, start_datetime: selectedDate }))}
                  style={{ width: 15, height: 15, accentColor: "#b45309" }}
                />
                <label htmlFor="all_day" style={{ fontSize: 13, color: "#475569", cursor: "pointer" }}>All-day event</label>
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "#475569", display: "block", marginBottom: 5 }}>Location</label>
                <input
                  className="input-field"
                  value={form.location}
                  onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
                  placeholder="e.g. Court Hall 5, Kerala High Court"
                />
              </div>

              <div>
                <label style={{ fontSize: 12, fontWeight: 500, color: "#475569", display: "block", marginBottom: 5 }}>Notes</label>
                <textarea
                  className="input-field"
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="Optional notes…"
                  rows={2}
                  style={{ resize: "vertical" }}
                />
              </div>

              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 }}>
                <button className="btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
                <button
                  className="btn-primary"
                  onClick={handleCreate}
                  disabled={saving || !form.title || !form.start_datetime}
                >
                  {saving ? "Saving…" : "Create Event"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
