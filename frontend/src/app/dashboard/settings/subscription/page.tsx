"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCurrentSubscription,
  getSubscriptionInvoices,
  getSubscriptionPlans,
  getSubscriptionUsage,
  createSubscriptionOrder,
  verifySubscriptionPayment,
  type InvoiceItem,
  type SubscriptionCurrent,
  type SubscriptionPlan,
  type UsageStats,
} from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

// ── Razorpay helpers (browser-only) ──────────────────────────────────────────

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined") return reject(new Error("SSR"));
    if ((window as any).Razorpay) return resolve();
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Razorpay SDK"));
    document.body.appendChild(script);
  });
}

interface RazorpaySubscriptionResponse {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
}

function openRazorpaySubscriptionCheckout(opts: {
  keyId: string;
  subscriptionId: string;
  amountPaise: number;
  name: string;
  description: string;
}): Promise<RazorpaySubscriptionResponse> {
  return new Promise((resolve, reject) => {
    const rzp = new (window as any).Razorpay({
      key: opts.keyId,
      subscription_id: opts.subscriptionId,
      name: opts.name,
      description: opts.description,
      handler: resolve,
      modal: { ondismiss: () => reject(new Error("Payment cancelled")) },
      theme: { color: "#f59e0b" },
    });
    rzp.on("payment.failed", (resp: any) =>
      reject(new Error(resp?.error?.description || "Payment failed"))
    );
    rzp.open();
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function daysRemaining(dateStr?: string | null): number | null {
  if (!dateStr) return null;
  const end = new Date(dateStr);
  if (Number.isNaN(end.getTime())) return null;
  return Math.ceil((end.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsSubscriptionPage() {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionCurrent | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);

  const [subscribeLoading, setSubscribeLoading] = useState(false);
  const [subscribeMessage, setSubscribeMessage] = useState<string | null>(null);

  function loadData() {
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
    return () => { ignore = true; };
  }

  useEffect(() => {
    const cleanup = loadData();
    return cleanup;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const currentPlan = useMemo(
    () => plans.find((p) => p.id.toUpperCase() === (subscription?.plan || "").toUpperCase()) || null,
    [plans, subscription]
  );

  // Trial / expiry state
  const trialDaysLeft = daysRemaining(subscription?.trialEndDate);
  const isActive = subscription?.status?.toUpperCase() === "ACTIVE";
  const isTrialing = subscription?.status?.toUpperCase() === "TRIAL";
  const trialExpired = isTrialing && trialDaysLeft !== null && trialDaysLeft <= 0;
  const showSubscribeButton = !isActive; // show for trial, free, expired

  async function handleSubscribe() {
    if (!token) return;
    setSubscribeLoading(true);
    setSubscribeMessage(null);
    try {
      await loadRazorpayScript();

      // 1. Create Razorpay subscription on backend
      const order = await createSubscriptionOrder(token);

      // 2. Open Razorpay checkout modal
      const payment = await openRazorpaySubscriptionCheckout({
        keyId: order.keyId,
        subscriptionId: order.subscriptionId,
        amountPaise: order.amountPaise,
        name: "LawMate",
        description: order.planType === "early_bird"
          ? "Early Bird — ₹1,200/month"
          : "Professional — ₹1,500/month",
      });

      // 3. Verify signature on backend → activate plan in DB
      await verifySubscriptionPayment(token, {
        razorpay_payment_id: payment.razorpay_payment_id,
        razorpay_subscription_id: payment.razorpay_subscription_id,
        razorpay_signature: payment.razorpay_signature,
      });

      setSubscribeMessage("Subscription activated! Welcome to LawMate Professional.");
      loadData(); // refresh
    } catch (err: any) {
      const msg = err?.message || "";
      if (msg !== "Payment cancelled") {
        setSubscribeMessage(msg || "Something went wrong. Please try again.");
      }
    } finally {
      setSubscribeLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Subscription</CardTitle>
        <CardDescription>Your current plan, usage, and billing.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">

        {loading ? <p className="text-sm text-slate-500">Loading subscription…</p> : null}
        {error ? <p className="text-sm text-rose-600">{error}</p> : null}

        {subscription && !loading ? (
          <>
            {/* ── Trial expiry banner ─────────────────────────────────────── */}
            {trialExpired && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="text-sm font-semibold text-red-700">
                  Your free trial has ended.
                </p>
                <p className="mt-1 text-sm text-red-600">
                  Subscribe now to continue using LawMate without interruption.
                </p>
              </div>
            )}

            {isTrialing && !trialExpired && trialDaysLeft !== null && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm font-semibold text-amber-800">
                  {trialDaysLeft === 0
                    ? "Your free trial ends today."
                    : `Free trial: ${trialDaysLeft} day${trialDaysLeft === 1 ? "" : "s"} remaining.`}
                </p>
                <p className="mt-1 text-sm text-amber-700">
                  Subscribe before your trial ends to keep full access.
                </p>
              </div>
            )}

            {/* ── Plan status grid ────────────────────────────────────────── */}
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Current Plan</p>
                <p className="text-base font-semibold capitalize">
                  {currentPlan?.name || subscription.plan?.toLowerCase()}
                </p>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Status</p>
                <p className={`text-base font-semibold capitalize ${
                  isActive ? "text-emerald-600" : trialExpired ? "text-red-600" : "text-amber-600"
                }`}>
                  {isActive ? "Active" : trialExpired ? "Trial ended" : "Trial"}
                </p>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">
                  {isActive ? "Next renewal" : "Trial ends"}
                </p>
                <p className="text-base font-semibold">
                  {isActive ? formatDate(subscription.endDate) : formatDate(subscription.trialEndDate)}
                </p>
              </div>
            </div>

            {/* ── Subscribe button ─────────────────────────────────────────── */}
            {showSubscribeButton && (
              <div className="rounded-xl border-2 border-amber-200 bg-amber-50 p-5">
                <p className="text-sm font-semibold text-slate-800">
                  LawMate Professional
                </p>
                <p className="mt-1 text-2xl font-bold text-slate-900">
                  ₹1,200
                  <span className="text-sm font-normal text-slate-500"> /month</span>
                  <span className="ml-2 text-xs font-normal text-slate-400 line-through">₹1,500</span>
                </p>
                <p className="mt-0.5 text-xs text-slate-400">+ 18% GST · Early bird pricing</p>
                <ul className="mt-3 space-y-1 text-sm text-slate-600">
                  <li>✓ 20 cases · 60 documents · 100 AI analyses / month</li>
                  <li>✓ All features included</li>
                  <li>✓ Unlimited ₹200 top-ups when you need more</li>
                  <li>✓ Cancel anytime</li>
                </ul>
                <button
                  onClick={handleSubscribe}
                  disabled={subscribeLoading}
                  className="mt-4 w-full rounded-lg bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-60 transition-colors"
                >
                  {subscribeLoading ? "Opening checkout…" : "Subscribe now — ₹1,200/month"}
                </button>
                {subscribeMessage && (
                  <p className={`mt-2 text-sm font-medium ${
                    subscribeMessage.includes("activated") ? "text-emerald-700" : "text-red-600"
                  }`}>
                    {subscribeMessage}
                  </p>
                )}
              </div>
            )}

            {/* ── Usage summary ────────────────────────────────────────────── */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Usage This Period</p>
                <p className="mt-2 text-sm">Cases: {usage?.casesCount ?? 0}</p>
                <p className="text-sm">Documents: {usage?.documentsCount ?? 0}</p>
                <p className="text-sm">Storage: {Number(usage?.storageUsedGb ?? 0).toFixed(2)} GB</p>
                <p className="text-sm">AI Analyses: {usage?.aiAnalysesUsed ?? 0}</p>
              </div>
              <div className="rounded-md border p-3">
                <p className="text-xs text-slate-500">Plan Window</p>
                <p className="mt-2 text-sm">Start: {formatDate(subscription.startDate)}</p>
                <p className="text-sm">End: {formatDate(subscription.endDate)}</p>
                {subscription.trialEndDate && (
                  <p className="text-sm">Trial End: {formatDate(subscription.trialEndDate)}</p>
                )}
              </div>
            </div>

            {/* ── Invoices ─────────────────────────────────────────────────── */}
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
                            ₹{(invoice.amount / 100).toLocaleString("en-IN")} {invoice.currency}
                          </td>
                          <td className="py-2 pr-3 capitalize">{invoice.status?.toLowerCase()}</td>
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
