/**
 * useVisibilityRefresh
 * ======================
 * Triggers a refetch callback when the user switches back to this tab after
 * the data has gone stale.  Prevents hammering the server on every tab switch
 * by enforcing a minimum stale threshold before re-fetching.
 *
 * Usage:
 *   useVisibilityRefresh(fetchHearingNotes, { staleThresholdMs: 30_000 });
 *
 * The hook also respects leader election — only the leader tab should poll;
 * non-leader tabs only refetch on visibility change.  Pass `leaderOnly: true`
 * to restrict the callback to the leader tab.
 */

import { useEffect, useRef, useCallback } from "react";
import { tabSync } from "@/lib/tabSync";

interface UseVisibilityRefreshOptions {
  /**
   * Minimum milliseconds since the last successful fetch before a visibility
   * event triggers a refetch.  Default: 30 000 ms (30 s).
   */
  staleThresholdMs?: number;
  /**
   * If true, only the leader tab (as determined by tabSync) will execute the
   * callback.  Non-leader tabs still reset their own stale timer on visibility
   * so they pick up leader changes.  Default: false.
   */
  leaderOnly?: boolean;
  /**
   * If true, the hook is disabled (useful for conditional logic).
   */
  disabled?: boolean;
}

export function useVisibilityRefresh(
  onRefresh: () => void | Promise<void>,
  options: UseVisibilityRefreshOptions = {}
) {
  const { staleThresholdMs = 30_000, leaderOnly = false, disabled = false } = options;

  // Stable ref so we don't re-register the listener on every render
  const onRefreshRef = useRef(onRefresh);
  useEffect(() => { onRefreshRef.current = onRefresh; }, [onRefresh]);

  // Track when we last refreshed
  const lastRefreshRef = useRef<number>(Date.now());

  /** Call this after a successful fetch to reset the stale clock */
  const markRefreshed = useCallback(() => {
    lastRefreshRef.current = Date.now();
  }, []);

  useEffect(() => {
    if (disabled) return;

    async function handleVisibility() {
      if (document.visibilityState !== "visible") return;

      const age = Date.now() - lastRefreshRef.current;
      if (age < staleThresholdMs) return;

      // Honour leader restriction
      if (leaderOnly && tabSync && !tabSync.isLeader) return;

      lastRefreshRef.current = Date.now(); // optimistic — avoids double-fire
      try {
        await onRefreshRef.current();
      } catch {
        // If refresh fails we don't reset the timer so the next visibility
        // event will retry
        lastRefreshRef.current = 0;
      }
    }

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [staleThresholdMs, leaderOnly, disabled]);

  return { markRefreshed };
}
