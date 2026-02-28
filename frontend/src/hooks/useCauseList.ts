"use client";

import { useAuth } from "@/contexts/AuthContext";
import { apiRequest } from "@/lib/api";
import { useCallback, useEffect, useRef, useState } from "react";

export interface CauseListResponse {
  html: string;
  total_listings: number;
  date: string;
}

export function useCauseList(dateStr: string) {
  const { token } = useAuth();
  const [data, setData] = useState<CauseListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchCauseList = useCallback(async () => {
    if (!dateStr || !token) {
      setData(null);
      setLoading(false);
      return;
    }

    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const qs = new URLSearchParams({ date: dateStr }).toString();
      const res = await apiRequest<CauseListResponse>(`/api/cause-list?${qs}`, {
        method: "GET",
        token,
        signal: controller.signal,
      });
      setData(res);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        return;
      }
      setError(err instanceof Error ? err.message : "Unable to load cause list.");
      setData(null);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [dateStr, token]);

  useEffect(() => {
    void fetchCauseList();

    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [fetchCauseList]);

  return {
    data,
    loading,
    error,
    refetch: fetchCauseList,
  };
}
