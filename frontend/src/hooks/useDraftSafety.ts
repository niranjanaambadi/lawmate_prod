/**
 * useDraftSafety
 * ===============
 * Per-tab draft tracking with cross-tab lock broadcasting.
 *
 * Prevents two tabs from silently overwriting each other's in-progress drafts
 * by:
 *   1. Advertising when this tab acquires an exclusive draft lock
 *   2. Surfacing a "locked by another tab" warning when another tab holds the lock
 *   3. Providing isDirty / markDirty / markClean helpers for the "unsaved changes"
 *      indicator in the editor header
 *
 * Usage:
 *   const { isDirty, isLockedByOtherTab, markDirty, markClean, acquireLock, releaseLock }
 *     = useDraftSafety("note", noteId);
 *
 *   // In your autosave handler:
 *   markDirty();
 *   // ... user edits ...
 *   await saveNote();
 *   markClean();
 *
 * The `draftKey` is namespaced by resource + id so two different notes in two
 * different tabs do not interfere with each other.
 */

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { tabSync, getTabId } from "@/lib/tabSync";

interface UseDraftSafetyReturn {
  /** True when there are local unsaved changes */
  isDirty: boolean;
  /** True when a different tab claims the lock for this same draft key */
  isLockedByOtherTab: boolean;
  /** The tab ID that holds the lock (undefined if none or this tab) */
  lockHolderTabId: string | undefined;
  /** Mark that the user has made unsaved changes */
  markDirty: () => void;
  /** Mark that the draft is clean (saved or discarded) */
  markClean: () => void;
  /** Broadcast DRAFT_LOCK_ACQUIRED to inform other tabs this tab is editing */
  acquireLock: () => void;
  /** Broadcast DRAFT_LOCK_RELEASED to inform other tabs this tab stopped editing */
  releaseLock: () => void;
}

export function useDraftSafety(
  resource: string,
  id: string
): UseDraftSafetyReturn {
  const draftKey = `${resource}:${id}`;
  const tabId    = useRef(getTabId());

  const [isDirty,            setIsDirty]            = useState(false);
  const [lockHolderTabId,    setLockHolderTabId]    = useState<string | undefined>(undefined);

  // Derived: locked by a *different* tab
  const isLockedByOtherTab =
    lockHolderTabId !== undefined && lockHolderTabId !== tabId.current;

  // ── Cross-tab listener ────────────────────────────────────────────────────

  useEffect(() => {
    if (!tabSync) return;

    const unsub = tabSync.subscribe((msg) => {
      if (
        msg.type === "DRAFT_LOCK_ACQUIRED" &&
        msg.draftKey === draftKey &&
        msg.tabId !== tabId.current
      ) {
        setLockHolderTabId(msg.tabId);
      }

      if (
        msg.type === "DRAFT_LOCK_RELEASED" &&
        msg.draftKey === draftKey
      ) {
        setLockHolderTabId((prev) => (prev === msg.tabId ? undefined : prev));
      }
    });

    return unsub;
  }, [draftKey]);

  // ── Warn before unload when dirty ────────────────────────────────────────

  useEffect(() => {
    if (!isDirty) return;

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // modern browsers ignore the custom message
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [isDirty]);

  // ── Public API ────────────────────────────────────────────────────────────

  const markDirty = useCallback(() => setIsDirty(true), []);
  const markClean = useCallback(() => setIsDirty(false), []);

  const acquireLock = useCallback(() => {
    tabSync?.broadcast({ type: "DRAFT_LOCK_ACQUIRED", draftKey });
    setLockHolderTabId(tabId.current); // optimistic local update
  }, [draftKey]);

  const releaseLock = useCallback(() => {
    tabSync?.broadcast({ type: "DRAFT_LOCK_RELEASED", draftKey });
    setLockHolderTabId((prev) => (prev === tabId.current ? undefined : prev));
  }, [draftKey]);

  // Auto-release on unmount
  useEffect(() => {
    return () => {
      if (isDirty) {
        tabSync?.broadcast({ type: "DRAFT_LOCK_RELEASED", draftKey });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    isDirty,
    isLockedByOtherTab,
    lockHolderTabId,
    markDirty,
    markClean,
    acquireLock,
    releaseLock,
  };
}
