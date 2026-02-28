"use client";

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, type AuthUser, type RegisterPayload } from "@/lib/api";
import { tabSync, getTabId } from "@/lib/tabSync";

const TOKEN_KEY          = "lawmate_access_token";
const REFRESH_LOCK_KEY   = "lawmate_refresh_lock";
const REFRESH_LOCK_TTL   = 5_000; // 5 s — if holder crashes, lock auto-expires

// ── Cross-tab refresh lock ────────────────────────────────────────────────────
// Prevents every tab from hitting /me simultaneously on visibility change.

function acquireRefreshLock(tabId: string): boolean {
  try {
    const raw = localStorage.getItem(REFRESH_LOCK_KEY);
    if (raw) {
      const lock = JSON.parse(raw) as { id: string; ts: number };
      if (Date.now() - lock.ts < REFRESH_LOCK_TTL) return false; // held by another tab
    }
    localStorage.setItem(REFRESH_LOCK_KEY, JSON.stringify({ id: tabId, ts: Date.now() }));
    return true;
  } catch {
    return true; // storage unavailable — optimistically proceed
  }
}

function releaseRefreshLock(tabId: string) {
  try {
    const raw = localStorage.getItem(REFRESH_LOCK_KEY);
    if (!raw) return;
    const lock = JSON.parse(raw) as { id: string; ts: number };
    if (lock.id === tabId) localStorage.removeItem(REFRESH_LOCK_KEY);
  } catch { /* ignore */ }
}

// ── Token helpers ─────────────────────────────────────────────────────────────

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

function setStoredToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

// ── Types ─────────────────────────────────────────────────────────────────────

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterPayload) => Promise<void>;
  logout: () => void;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (token: string, password: string) => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router   = useRouter();
  const tabId    = useRef<string>("");
  const [user, setUser]       = useState<AuthUser | null>(null);
  const [token, setToken]     = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Resolve tab ID once on mount (client-only)
  useEffect(() => { tabId.current = getTabId(); }, []);

  // ── Core: load user profile from API ───────────────────────────────────────

  const loadUser = useCallback(async (t: string) => {
    try {
      const u = await authApi.me(t);
      setUser(u);
    } catch {
      setStoredToken(null);
      setToken(null);
      setUser(null);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const t = token || getStoredToken();
    if (!t) return;
    await loadUser(t);
  }, [loadUser, token]);

  // ── Initial hydration ──────────────────────────────────────────────────────

  useEffect(() => {
    const t = getStoredToken();
    if (!t) {
      setIsLoading(false);
      return;
    }
    setToken(t);
    loadUser(t).finally(() => setIsLoading(false));
  }, [loadUser]);

  // ── Cross-tab event listener ───────────────────────────────────────────────

  useEffect(() => {
    if (!tabSync) return;

    const unsub = tabSync.subscribe((msg) => {
      switch (msg.type) {
        // Another tab logged out → mirror immediately
        case "AUTH_LOGOUT": {
          setStoredToken(null);
          setToken(null);
          setUser(null);
          router.push("/signin");
          break;
        }

        // Another tab got a fresh token (login / token refresh) → adopt it
        case "AUTH_TOKEN_UPDATE": {
          const { token: newToken } = msg;
          setStoredToken(newToken);
          setToken(newToken);
          // Use refresh lock so only one tab re-fetches the user profile
          if (acquireRefreshLock(tabId.current)) {
            loadUser(newToken).finally(() => releaseRefreshLock(tabId.current));
          }
          break;
        }
      }
    });

    return unsub;
  }, [loadUser, router]);

  // ── Auth actions ───────────────────────────────────────────────────────────

  const login = useCallback(async (email: string, password: string) => {
    const { access_token, user: u } = await authApi.login(email, password);
    setStoredToken(access_token);
    setToken(access_token);
    setUser(u);
    // Notify other tabs so they pick up the session without another login
    tabSync?.broadcast({ type: "AUTH_TOKEN_UPDATE", token: access_token });
  }, []);

  const register = useCallback(async (data: RegisterPayload) => {
    await authApi.register(data);
    router.push("/signin?registered=true");
  }, [router]);

  const logout = useCallback(() => {
    // Broadcast first so other tabs can react before local state clears
    tabSync?.broadcast({ type: "AUTH_LOGOUT" });
    setStoredToken(null);
    setToken(null);
    setUser(null);
    router.push("/signin");
  }, [router]);

  const forgotPassword = useCallback(async (email: string) => {
    await authApi.forgotPassword(email);
  }, []);

  const resetPassword = useCallback(async (t: string, password: string) => {
    await authApi.resetPassword(t, password);
    router.push("/signin?reset=true");
  }, [router]);

  // ── Visibility-based refresh (leader-gated) ────────────────────────────────
  // When the user switches back to this tab after a long absence, silently
  // revalidate the session. The refresh lock ensures only one tab hits /me.

  useEffect(() => {
    const STALE_THRESHOLD = 30_000; // 30 s
    let lastRefresh = Date.now();

    function handleVisibility() {
      if (document.visibilityState !== "visible") return;
      const t = getStoredToken();
      if (!t) return;
      if (Date.now() - lastRefresh < STALE_THRESHOLD) return;
      if (!acquireRefreshLock(tabId.current)) return;

      lastRefresh = Date.now();
      loadUser(t).finally(() => releaseRefreshLock(tabId.current));
    }

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [loadUser]);

  // ── Context value ──────────────────────────────────────────────────────────

  const value: AuthContextValue = {
    user,
    token,
    isAuthenticated: !!user && !!token,
    isLoading,
    login,
    register,
    logout,
    forgotPassword,
    resetPassword,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
