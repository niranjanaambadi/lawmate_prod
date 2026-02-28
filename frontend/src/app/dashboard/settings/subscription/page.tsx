"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCurrentSubscription,
  getSubscriptionInvoices,
  getSubscriptionPlans,
  getSubscriptionUsage,
  type InvoiceItem,
  type SubscriptionCurrent,
  type SubscriptionPlan,
  type UsageStats,
} from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString();
}

export default function SettingsSubscriptionPage() {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionCurrent | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);

  useEffect(() => {
    if (!token) return;
    let ignore = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [subData, plansData, usageData, invoicesData] = await Promise.all([
          getCurrentSubscription(token),
          getSubscriptionPlans(token),
          getSubscriptionUsage(token),
          getSubscriptionInvoices(token),
        ]);
        if (ignore) return;
        setSubscription(subData);
        setPlans(plansData);
        setUsage(usageData);
        setInvoices(invoicesData);
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : "Failed to load subscription");
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [token]);

  const currentPlan = useMemo(
    () => plans.find((p) => p.id.toUpperCase() === (subscription?.plan || "").toUpperCase()) || null,
    [plans, subscription]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Subscription</CardTitle>
        <CardDescription>Your current plan, usage, and invoices.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? <p className="text-sm text-slate-500">Loading subscription...</p> : null}
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}
        {subscription && !loading ? (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Current Plan</p>
                <p className="text-base font-semibold">{currentPlan?.name || subscription.plan}</p>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Billing Cycle</p>
                <p className="text-base font-semibold">{subscription.billingCycle}</p>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Status</p>
                <p className="text-base font-semibold">{subscription.status}</p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Usage This Period</p>
                <p className="mt-2 text-sm">Cases: {usage?.casesCount ?? 0}</p>
                <p className="text-sm">Documents: {usage?.documentsCount ?? 0}</p>
                <p className="text-sm">Storage: {(usage?.storageUsedGb ?? 0).toFixed(2)} GB</p>
                <p className="text-sm">AI Analyses: {usage?.aiAnalysesUsed ?? 0}</p>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Plan Window</p>
                <p className="mt-2 text-sm">Start: {formatDate(subscription.startDate)}</p>
                <p className="text-sm">End: {formatDate(subscription.endDate)}</p>
                <p className="text-sm">Trial End: {formatDate(subscription.trialEndDate)}</p>
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium">Recent Invoices</h3>
              {invoices.length === 0 ? (
                <p className="text-sm text-slate-500">No invoices yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th className="py-2 pr-3">Date</th>
                        <th className="py-2 pr-3">Amount</th>
                        <th className="py-2 pr-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoices.slice(0, 10).map((invoice) => (
                        <tr key={invoice.id} className="border-b">
                          <td className="py-2 pr-3">{formatDate(invoice.invoiceDate)}</td>
                          <td className="py-2 pr-3">
                            ₹ {(invoice.amount / 100).toLocaleString("en-IN")} {invoice.currency}
                          </td>
                          <td className="py-2 pr-3">{invoice.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
