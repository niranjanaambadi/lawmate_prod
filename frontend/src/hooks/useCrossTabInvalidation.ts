/**
 * useCrossTabInvalidation
 * ========================
 * Listens for CACHE_INVALIDATE messages from other tabs and fires a refetch
 * callback whenever the invalidated resource matches the one this hook watches.
 *
 * Usage:
 *   // Refetch any time another tab touches "cases"
 *   useCrossTabInvalidation("cases", fetchCases);
 *
 *   // Only react when a specific record is invalidated
 *   useCrossTabInvalidation("notes", refetchNote, noteId);
 *
 *   // Broadcast invalidation (e.g. after a successful mutation):
 *   const { invalidate } = useCrossTabInvalidation("cases", fetchCases);
 *   await updateCase(...)
 *   invalidate();           // tell every other tab to refetch
 */

import { useEffect, useCallback, useRef } from "react";
import { tabSync } from "@/lib/tabSync";

interface UseCrossTabInvalidationOptions {
  /** Only react to messages where msg.id matches this value (optional) */
  id?: string;
  /** Skip broadcasting/listening (useful for SSR or conditionally) */
  disabled?: boolean;
}

export function useCrossTabInvalidation(
  resource: string,
  onInvalidate: () => void,
  options: UseCrossTabInvalidationOptions = {}
) {
  const { id, disabled = false } = options;

  // Keep a stable ref to the callback so we never need to re-subscribe
  const onInvalidateRef = useRef(onInvalidate);
  useEffect(() => { onInvalidateRef.current = onInvalidate; }, [onInvalidate]);

  // Subscribe to cross-tab messages
  useEffect(() => {
    if (disabled || !tabSync) return;

    const unsub = tabSync.subscribe((msg) => {
      if (msg.type !== "CACHE_INVALIDATE") return;
      if (msg.resource !== resource) return;
      if (id !== undefined && msg.id !== undefined && msg.id !== id) return;
      onInvalidateRef.current();
    });

    return unsub;
  }, [resource, id, disabled]);

  // Returns a function callers use to broadcast invalidation to other tabs
  const invalidate = useCallback((specificId?: string) => {
    if (disabled || !tabSync) return;
    tabSync.broadcast({
      type: "CACHE_INVALIDATE",
      resource,
      ...(specificId !== undefined ? { id: specificId } : {}),
    });
  }, [resource, disabled]);

  return { invalidate };
}
