"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { getSubscriptionUsage, purchaseTopup, type UsageStats } from "@/lib/api";

// Lazy-load the chart component with SSR disabled — chart.js requires browser canvas
const DoughnutChart = dynamic(
  () =>
    import("chart.js").then(({ Chart, ArcElement, Tooltip, Legend }) => {
      Chart.register(ArcElement, Tooltip, Legend);
      return import("react-chartjs-2").then((mod) => mod.Doughnut);
    }),
  { ssr: false, loading: () => <div className="h-[200px] w-full animate-pulse rounded-lg bg-slate-100" /> }
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns the colour theme for a given utilisation ratio (0–1). */
function themeFor(ratio: number): { bar: string; bg: string; text: string; ring: string } {
  if (ratio >= 1)    return { bar: "#ef4444", bg: "#fef2f2", text: "#b91c1c", ring: "#ef4444" };
  if (ratio >= 0.8)  return { bar: "#f59e0b", bg: "#fffbeb", text: "#b45309", ring: "#f59e0b" };
  return               { bar: "#4f46e5", bg: "#eef2ff", text: "#3730a3", ring: "#4f46e5" };
}

function pct(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(used / limit, 1);
}

function formatGb(gb: number): string {
  const n = Number(gb);
  if (isNaN(n) || n < 0.01) return "< 0.01 GB";
  return `${n.toFixed(2)} GB`;
}

function resetDate(periodEnd: string): string {
  try {
    const d = new Date(periodEnd);
    // advance to 1st of next month
    const next = new Date(d.getFullYear(), d.getMonth() + 1, 1);
    return next.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// Fallback limits when API hasn't loaded yet (professional/base plan)
// ---------------------------------------------------------------------------
const FALLBACK_LIMITS = { cases: 20, documents: 60, storageGb: 30, aiAnalyses: 100 };

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type ResourceRowProps = {
  label: string;
  icon: string;
  used: number;
  limit: number;
  formatValue?: (v: number) => string;
  formatLimit?: (v: number) => string;
};

function ResourceRow({ label, icon, used, limit, formatValue, formatLimit }: ResourceRowProps) {
  const ratio = pct(used, limit);
  const theme = themeFor(ratio);
  const displayUsed  = formatValue ? formatValue(used)  : used.toLocaleString();
  const displayLimit = formatLimit ? formatLimit(limit) : limit.toLocaleString();

  return (
    <li className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 font-medium text-slate-700">
          <span>{icon}</span>
          {label}
        </span>
        <span className="tabular-nums" style={{ color: theme.text }}>
          {displayUsed} / {displayLimit}
        </span>
      </div>
      {/* Progress bar */}
      <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
        <div
          className="h-2 rounded-full transition-all duration-500"
          style={{ width: `${Math.round(ratio * 100)}%`, backgroundColor: theme.bar }}
        />
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SettingsUsagePage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [topupLoading, setTopupLoading] = useState(false);
  const [topupMessage, setTopupMessage] = useState<string | null>(null);

  function loadUsage() {
    if (!token) return;
    setLoading(true);
    getSubscriptionUsage(token)
      .then((data) => setStats(data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadUsage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const limits = stats?.limits ?? FALLBACK_LIMITS;

  // Weighted units: cases×1 + docs×2 + AI×3  (storage excluded — hard to weight fairly)
  const totalAllotted = useMemo(
    () => limits.cases * 1 + limits.documents * 2 + limits.aiAnalyses * 3,
    [limits]
  );
  const totalUsed = useMemo(() => {
    if (!stats) return 0;
    return (
      stats.casesCount * 1 +
      stats.documentsCount * 2 +
      stats.aiAnalysesUsed * 3
    );
  }, [stats]);

  const overallRatio = pct(totalUsed, totalAllotted);
  const overallPct   = Math.round(overallRatio * 100);
  const overallTheme = themeFor(overallRatio);

  const aiRatio    = stats ? pct(stats.aiAnalysesUsed, limits.aiAnalyses) : 0;
  const aiLimitHit = aiRatio >= 1;
  const aiWarning  = aiRatio >= 0.8 && !aiLimitHit;

  const chartData = useMemo(() => ({
    labels: ["Used", "Remaining"],
    datasets: [
      {
        data: [totalUsed, Math.max(0, totalAllotted - totalUsed)],
        backgroundColor: [overallTheme.ring, "#e2e8f0"],
        borderColor:     [overallTheme.ring, "#cbd5e1"],
        borderWidth: 1,
        hoverBackgroundColor: [overallTheme.ring, "#f1f5f9"],
      },
    ],
  }), [totalUsed, totalAllotted, overallTheme]);

  const centerTextPlugin = useMemo(() => ({
    id: "centerText",
    beforeDraw(chart: { ctx: CanvasRenderingContext2D; width: number; height: number }) {
      const { ctx, width, height } = chart;
      ctx.save();
      if (!ctx) return;
      const fontSize = Math.max(12, Math.round(height / 9));
      ctx.font = `bold ${fontSize}px sans-serif`;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      ctx.fillStyle = overallTheme.text;
      ctx.fillText(`${overallPct}%`, width / 2, height / 2);
      ctx.restore();
    },
  }), [overallPct, overallTheme]);

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: true,
    cutout: "72%",
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item: { label?: string; raw?: unknown }) => {
            const total = totalUsed + Math.max(0, totalAllotted - totalUsed);
            const p = total > 0 ? (((item.raw as number) / total) * 100).toFixed(1) : "0";
            return `${item.label}: ${(item.raw as number).toLocaleString()} units (${p}%)`;
          },
        },
      },
    },
  }), [totalUsed, totalAllotted]);

  async function handleTopup() {
    if (!token) return;
    setTopupLoading(true);
    setTopupMessage(null);
    try {
      const result = await purchaseTopup(token);
      setTopupMessage(`+${result.aiAnalysesAdded} AI analyses added for this month.`);
      loadUsage(); // refresh
    } catch {
      setTopupMessage("Top-up failed. Please try again.");
    } finally {
      setTopupLoading(false);
    }
  }

  const planLabel = stats?.plan
    ? stats.plan.charAt(0).toUpperCase() + stats.plan.slice(1)
    : "—";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Usage Tracker</CardTitle>
        <CardDescription>
          {stats
            ? `${planLabel} plan · Resets on ${resetDate(stats.periodEnd)}`
            : "Your usage this billing period"}
        </CardDescription>
      </CardHeader>

      <CardContent>
        {loading ? (
          <p className="text-sm text-slate-500">Loading usage…</p>
        ) : (
          <div className="grid gap-6 md:grid-cols-[220px,1fr]">

            {/* ── Doughnut ──────────────────────────────────────────────── */}
            <div
              className="flex flex-col items-center justify-center rounded-xl border p-6"
              style={{ borderColor: overallTheme.ring + "44", backgroundColor: overallTheme.bg }}
            >
              <div className="relative h-[200px] w-full max-w-[200px]">
                <DoughnutChart data={chartData} options={chartOptions} plugins={[centerTextPlugin]} />
              </div>
              <p className="mt-3 text-center text-xs text-slate-500">
                {totalUsed.toLocaleString()} / {totalAllotted.toLocaleString()} weighted units
              </p>
              {overallRatio >= 0.8 && (
                <p
                  className="mt-1 text-center text-xs font-medium"
                  style={{ color: overallTheme.text }}
                >
                  {overallRatio >= 1 ? "Limit reached" : "Approaching limit"}
                </p>
              )}
            </div>

            {/* ── Per-resource breakdown ─────────────────────────────────── */}
            <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-5">
              <h3 className="text-sm font-semibold text-slate-900">Resource breakdown</h3>

              <ul className="space-y-4">
                <ResourceRow
                  label="Cases"
                  icon="📁"
                  used={stats?.casesCount ?? 0}
                  limit={limits.cases}
                />
                <ResourceRow
                  label="Documents"
                  icon="📄"
                  used={stats?.documentsCount ?? 0}
                  limit={limits.documents}
                />
                <ResourceRow
                  label="AI Analyses"
                  icon="🤖"
                  used={stats?.aiAnalysesUsed ?? 0}
                  limit={limits.aiAnalyses}
                />
                <ResourceRow
                  label="Storage"
                  icon="💾"
                  used={Number(stats?.storageUsedGb ?? 0)}
                  limit={limits.storageGb}
                  formatValue={formatGb}
                  formatLimit={(v) => `${v} GB`}
                />
              </ul>

              {/* Top-up banner (shown when AI is at/near limit) */}
              {(aiLimitHit || aiWarning) && (
                <div
                  className="rounded-lg border p-4 space-y-3"
                  style={{
                    borderColor: aiLimitHit ? "#fca5a5" : "#fde68a",
                    backgroundColor: aiLimitHit ? "#fef2f2" : "#fffbeb",
                  }}
                >
                  <p
                    className="text-sm font-medium"
                    style={{ color: aiLimitHit ? "#b91c1c" : "#92400e" }}
                  >
                    {aiLimitHit
                      ? "AI analysis limit reached for this month."
                      : `${Math.round(aiRatio * 100)}% of AI analyses used — running low.`}
                  </p>
                  {stats?.topupsAiAdded ? (
                    <p className="text-xs text-slate-500">
                      Includes {stats.topupsAiAdded} analyses from top-ups this month.
                    </p>
                  ) : null}
                  <button
                    onClick={handleTopup}
                    disabled={topupLoading}
                    className="inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold text-white transition-opacity disabled:opacity-60"
                    style={{ backgroundColor: aiLimitHit ? "#ef4444" : "#f59e0b" }}
                  >
                    {topupLoading ? "Processing…" : "Buy top-up · ₹200 → +20 analyses"}
                  </button>
                  {topupMessage && (
                    <p className="text-xs font-medium text-slate-700">{topupMessage}</p>
                  )}
                </div>
              )}

              {/* Success message after topup when not in warning state */}
              {topupMessage && !aiLimitHit && !aiWarning && (
                <p className="text-xs font-medium text-indigo-700 bg-indigo-50 rounded-md px-3 py-2">
                  {topupMessage}
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
