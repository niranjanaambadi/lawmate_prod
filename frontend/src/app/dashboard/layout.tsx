"use client";

import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LogOut, Scale } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Input } from "@/components/ui/input";
import { authApi } from "@/lib/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading, user, token, logout, refreshUser } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [verifyVia, setVerifyVia] = useState<"phone" | "email">("phone");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<"identity" | "otp">("identity");
  const [maskedMobile, setMaskedMobile] = useState<string | null>(null);
  const [maskedEmail, setMaskedEmail] = useState<string | null>(null);
  const [verificationMessage, setVerificationMessage] = useState<string | null>(null);
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [loadingVerify, setLoadingVerify] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const needsProfileVerification = useMemo(
    () => Boolean(user && !user.profile_verified_at),
    [user]
  );

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace(`/signin?callbackUrl=${encodeURIComponent("/dashboard")}`);
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
          <p className="text-sm text-slate-400">Loading workspace...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  if (needsProfileVerification) {
    const requestOtp = async () => {
      if (!token) return;
      try {
        setLoadingVerify(true);
        setVerifyError(null);
        const res = await authApi.startProfileVerification(fullName.trim(), verifyVia, token);
        setMaskedMobile(res.masked_mobile || null);
        setMaskedEmail(res.masked_email || null);
        setVerificationMessage(res.message || null);
        setDevOtp(res.dev_otp || null);
        setStep("otp");
      } catch (e) {
        setVerifyError(e instanceof Error ? e.message : "Failed to send OTP");
      } finally {
        setLoadingVerify(false);
      }
    };

    const confirmOtp = async () => {
      if (!token) return;
      try {
        setLoadingVerify(true);
        setVerifyError(null);
        await authApi.confirmProfileVerification(otp.trim(), token);
        await refreshUser();
      } catch (e) {
        setVerifyError(e instanceof Error ? e.message : "OTP verification failed");
      } finally {
        setLoadingVerify(false);
      }
    };

    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-indigo-50 p-4">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-xl">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600">
              <Scale className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Welcome to LawMate</h2>
              <p className="text-xs text-slate-500">Please verify your identity to proceed</p>
            </div>
          </div>

          {step === "identity" ? (
            <div className="space-y-3">
              <Input
                placeholder="Enter your full name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={loadingVerify}
              />
              <div className="flex items-center gap-4 text-sm">
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    checked={verifyVia === "phone"}
                    onChange={() => setVerifyVia("phone")}
                    disabled={loadingVerify}
                    className="accent-indigo-600"
                  />
                  <span className="text-slate-700">Verify via phone</span>
                </label>
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    checked={verifyVia === "email"}
                    onChange={() => setVerifyVia("email")}
                    disabled={loadingVerify}
                    className="accent-indigo-600"
                  />
                  <span className="text-slate-700">Verify via email</span>
                </label>
              </div>
              <Button className="w-full" onClick={requestOtp} disabled={!fullName.trim() || loadingVerify}>
                {loadingVerify ? "Sending OTP..." : "Send OTP"}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {maskedMobile && (
                <p className="text-sm text-slate-600">
                  OTP sent to registered phone ({maskedMobile}).
                </p>
              )}
              {maskedEmail && (
                <p className="text-sm text-slate-600">
                  OTP sent to registered email ({maskedEmail}).
                </p>
              )}
              {verificationMessage && (
                <p className="text-sm text-slate-700">{verificationMessage}</p>
              )}
              {devOtp && (
                <p className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-700">
                  Dev OTP: <span className="font-semibold">{devOtp}</span>
                </p>
              )}
              <Input
                placeholder="Enter OTP"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                disabled={loadingVerify}
              />
              <Button className="w-full" onClick={confirmOtp} disabled={!otp.trim() || loadingVerify}>
                {loadingVerify ? "Verifying..." : "Verify OTP"}
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  setStep("identity");
                  setOtp("");
                  setVerificationMessage(null);
                  setVerifyError(null);
                }}
                disabled={loadingVerify}
              >
                Change Details
              </Button>
            </div>
          )}

          {verifyError && (
            <p className="mt-3 text-sm text-rose-600">{verifyError}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col pl-64">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-white/95 px-6 shadow-sm backdrop-blur-sm">
          <div />
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold leading-tight text-slate-800">
                {user?.khc_advocate_name || user?.email}
              </p>
              {user?.khc_advocate_id && (
                <p className="text-xs leading-tight text-slate-400">
                  {user.khc_advocate_id}
                </p>
              )}
            </div>
            {user?.khc_advocate_name && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100">
                <span className="text-xs font-bold text-indigo-700">
                  {user.khc_advocate_name.charAt(0).toUpperCase()}
                </span>
              </div>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => logout()}
              className="h-8 w-8 text-slate-400 hover:text-slate-700"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>
        <main className="flex-1 overflow-auto py-6">
          <div className="w-full px-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
