"use client";

import { useAuth } from "@/contexts/AuthContext";
import { getAdvocateCauseList, AdvocateCauseListResponse } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";

export function useCauseList(dateStr: string) {
  const { token } = useAuth();
  const [data, setData] = useState<AdvocateCauseListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCauseList = useCallback(async () => {
    if (!dateStr || !token) {
      setData(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await getAdvocateCauseList(token, dateStr);
      setData(res);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : "Unable to load cause list.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [dateStr, token]);

  useEffect(() => {
    void fetchCauseList();
  }, [fetchCauseList]);

  return {
    data,
    loading,
    error,
    refetch: fetchCauseList,
    setData,
  };
}
