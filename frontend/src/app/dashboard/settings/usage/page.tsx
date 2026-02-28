"use client";

import { useMemo, useState } from "react";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Doughnut } from "react-chartjs-2";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { getSubscriptionUsage } from "@/lib/api";
import { useEffect } from "react";

ChartJS.register(ArcElement, Tooltip, Legend);

type ChartContext = { ctx: CanvasRenderingContext2D; width: number; height: number };

// Feature usage: name, units used, color. percentageOfTotal derived.
type FeatureUsage = {
  name: string;
  used: number;
  color: string;
  percentageOfTotal?: number;
};

type UsageData = {
  totalAllotted: number;
  used: number;
  remaining: number;
  features: FeatureUsage[];
};

// Default feature palette (slate/indigo)
const FEATURE_COLORS = [
  "#4f46e5", // indigo-600
  "#6366f1", // indigo-500
  "#7c3aed", // violet-600
  "#2563eb", // blue-600
  "#475569", // slate-600
  "#64748b", // slate-500
];

function buildUsageFromApi(
  totalAllotted: number,
  casesCount: number,
  documentsCount: number,
  aiAnalysesUsed: number
): UsageData {
  const used = casesCount + documentsCount * 2 + aiAnalysesUsed * 3; // weighted units for demo
  const cappedUsed = Math.min(used, totalAllotted);
  const features: FeatureUsage[] = [
    { name: "Cases", used: casesCount, color: FEATURE_COLORS[0] },
    { name: "Documents", used: documentsCount, color: FEATURE_COLORS[1] },
    { name: "AI Analyses", used: aiAnalysesUsed, color: FEATURE_COLORS[2] },
  ];
  const totalFeatureUnits = features.reduce((s, f) => s + f.used, 0);
  features.forEach((f) => {
    f.percentageOfTotal = totalFeatureUnits > 0 ? (f.used / totalFeatureUnits) * 100 : 0;
  });
  return {
    totalAllotted,
    used: cappedUsed,
    remaining: Math.max(0, totalAllotted - cappedUsed),
    features,
  };
}

// Demo data when API doesn't provide enough or for fallback
const DEMO_USAGE: UsageData = {
  totalAllotted: 5000,
  used: 3200,
  remaining: 1800,
  features: [
    { name: "Document Drafting", used: 1200, color: FEATURE_COLORS[0], percentageOfTotal: 37.5 },
    { name: "Case Research", used: 1500, color: FEATURE_COLORS[1], percentageOfTotal: 46.875 },
    { name: "Client Intake", used: 500, color: FEATURE_COLORS[2], percentageOfTotal: 15.625 },
  ],
};

export default function SettingsUsagePage() {
  const { token } = useAuth();
  const [usageData, setUsageData] = useState<UsageData>(DEMO_USAGE);
  const [loading, setLoading] = useState(true);
  const [showUsedBreakdown, setShowUsedBreakdown] = useState(true); // show feature breakdown by default (as if "Used" was clicked)

  useEffect(() => {
    if (!token) return;
    let ignore = false;
    (async () => {
      try {
        const stats = await getSubscriptionUsage(token);
        const totalAllotted = 10000; // could come from plan/limits API later
        const data = buildUsageFromApi(
          totalAllotted,
          stats.casesCount ?? 0,
          stats.documentsCount ?? 0,
          stats.aiAnalysesUsed ?? 0
        );
        if (data.features.some((f) => f.used > 0)) {
          const totalFeatureUnits = data.features.reduce((s, f) => s + f.used, 0);
          data.features.forEach((f) => {
            f.percentageOfTotal =
              totalFeatureUnits > 0 ? (f.used / totalFeatureUnits) * 100 : 0;
          });
          if (!ignore) setUsageData(data);
        }
      } catch {
        // keep DEMO_USAGE on error
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [token]);

  const percentageUsed = useMemo(
    () =>
      usageData.totalAllotted > 0
        ? Math.round((usageData.used / usageData.totalAllotted) * 100)
        : 0,
    [usageData]
  );

  const chartData = useMemo(
    () => ({
      labels: ["Used", "Remaining"],
      datasets: [
        {
          data: [usageData.used, usageData.remaining],
          backgroundColor: ["#4f46e5", "#e2e8f0"],
          borderColor: ["#4f46e5", "#cbd5e1"],
          borderWidth: 1,
          hoverBackgroundColor: ["#6366f1", "#f1f5f9"],
        },
      ],
    }),
    [usageData]
  );

  const centerTextPlugin = useMemo(
    () => ({
      id: "centerText",
      beforeDraw(chart: ChartContext) {
        const { ctx, width, height } = chart;
        ctx.save();
        const text = percentageUsed + "%";
        const fontSize = (height / 90).toFixed(0);
        ctx.font = "bold " + fontSize + "px sans-serif";
        ctx.textBaseline = "middle";
        ctx.textAlign = "center";
        ctx.fillStyle = "#1e293b";
        ctx.fillText(text, width / 2, height / 2);
        ctx.restore();
      },
    }),
    [percentageUsed]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: true,
      cutout: "72%",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item: { label?: string; raw?: unknown }) => {
              const total = usageData.used + usageData.remaining;
              const pct = total > 0 ? ((item.raw as number) / total * 100).toFixed(1) : "0";
              return `${item.label}: ${item.raw} units (${pct}%)`;
            },
          },
        },
      },
      onClick: (_evt: unknown, elements: { index: number }[]) => {
        if (elements.length > 0) {
          setShowUsedBreakdown(elements[0].index === 0);
        }
      },
    }),
    [usageData]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Usage Tracker</CardTitle>
        <CardDescription>
          Your usage this period. Click the &quot;Used&quot; segment to see feature breakdown.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-slate-500">Loading usage...</p>
        ) : (
          <div className="grid gap-6 md:grid-cols-[1fr,1fr]">
            {/* Chart container */}
            <div className="flex flex-col items-center justify-center rounded-xl border border-slate-200 bg-slate-50/50 p-6">
              <div className="relative h-[280px] w-full max-w-[280px]">
                <Doughnut
                  data={chartData}
                  options={options}
                  plugins={[centerTextPlugin]}
                />
              </div>
              <p className="mt-3 text-center text-xs text-slate-500">
                Total allotted: {usageData.totalAllotted.toLocaleString()} units
              </p>
            </div>

            {/* Feature breakdown panel */}
            <div className="rounded-xl border border-slate-200 bg-white p-6">
              <h3 className="mb-4 text-sm font-semibold text-slate-900">
                {showUsedBreakdown ? "Feature breakdown (Used)" : "Usage summary"}
              </h3>
              {showUsedBreakdown ? (
                <ul className="space-y-3">
                  {usageData.features.map((f) => (
                    <li key={f.name} className="flex items-center justify-between gap-4">
                      <span
                        className="h-3 w-3 shrink-0 rounded-full"
                        style={{ backgroundColor: f.color }}
                      />
                      <span className="flex-1 text-sm text-slate-700">{f.name}</span>
                      <span className="text-sm font-medium text-slate-900">{f.used.toLocaleString()}</span>
                      {f.percentageOfTotal != null && (
                        <span className="w-12 text-right text-xs text-slate-500">
                          {f.percentageOfTotal.toFixed(1)}%
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-600">
                  Used: {usageData.used.toLocaleString()} · Remaining:{" "}
                  {usageData.remaining.toLocaleString()}
                </p>
              )}
              <p className="mt-4 text-xs text-slate-500">
                Click the indigo &quot;Used&quot; segment on the chart to show this breakdown.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
