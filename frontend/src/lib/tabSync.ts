/**
 * Tab Sync Infrastructure — LawMate
 * ====================================
 * BroadcastChannel-based cross-tab messaging with:
 *   - Per-tab ID (sessionStorage, survives refresh, dies with tab)
 *   - Leader election (localStorage heartbeat — leader handles polling)
 *   - localStorage event fallback for older Safari (<15.4)
 *
 * Usage:
 *   import { tabSync, getTabId } from "@/lib/tabSync";
 *   tabSync?.broadcast({ type: "CACHE_INVALIDATE", resource: "cases" });
 *   const unsub = tabSync?.subscribe((msg) => { ... });
 */

const TAB_ID_KEY    = "lawmate_tab_id";
const LEADER_KEY    = "lawmate_tab_leader";
const CHANNEL_NAME  = "lawmate_tabs";
const LEADER_TTL_MS = 6_000;   // after 6 s without a heartbeat, the leader is assumed dead
const HEARTBEAT_MS  = 2_000;

// ────────────────────────────────────────────────────────────────────────────
// Tab ID — unique per tab session (not shared across tabs)
// ────────────────────────────────────────────────────────────────────────────

function generateTabId(): string {
  return `tab_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function getTabId(): string {
  if (typeof sessionStorage === "undefined") return "ssr";
  let id = sessionStorage.getItem(TAB_ID_KEY);
  if (!id) {
    id = generateTabId();
    sessionStorage.setItem(TAB_ID_KEY, id);
  }
  return id;
}

// ────────────────────────────────────────────────────────────────────────────
// Message types
// ────────────────────────────────────────────────────────────────────────────

export type TabSyncMessage =
  | { type: "AUTH_LOGOUT";          tabId: string }
  | { type: "AUTH_TOKEN_UPDATE";    tabId: string; token: string }
  | { type: "CACHE_INVALIDATE";     tabId: string; resource: string; id?: string }
  | { type: "DRAFT_LOCK_ACQUIRED";  tabId: string; draftKey: string }
  | { type: "DRAFT_LOCK_RELEASED";  tabId: string; draftKey: string }
  | { type: "LEADER_HEARTBEAT";     tabId: string; ts: number };

type MessageHandler = (msg: TabSyncMessage) => void;

/**
 * Distributive version of Omit — correctly strips a key from every member
 * of a union type instead of collapsing to only shared keys.
 */
type DistributiveOmit<T, K extends keyof any> = T extends unknown ? Omit<T, K> : never;

// ────────────────────────────────────────────────────────────────────────────
// TabSyncManager
// ────────────────────────────────────────────────────────────────────────────

class TabSyncManager {
  private channel: BroadcastChannel | null = null;
  private handlers = new Set<MessageHandler>();
  readonly tabId: string;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private _isLeader = false;

  constructor() {
    this.tabId = getTabId();
    this._init();
  }

  private _init() {
    // Primary: BroadcastChannel (Chrome 54+, FF 38+, Safari 15.4+, Edge 79+)
    if (typeof BroadcastChannel !== "undefined") {
      this.channel = new BroadcastChannel(CHANNEL_NAME);
      this.channel.onmessage = (e: MessageEvent) => {
        const msg = e.data as TabSyncMessage;
        if (msg?.tabId !== this.tabId) this._dispatch(msg);
      };
    }

    // Fallback: storage events (works cross-tab even on older Safari)
    window.addEventListener("storage", (e: StorageEvent) => {
      if (e.key === `${CHANNEL_NAME}_msg` && e.newValue) {
        try {
          const msg = JSON.parse(e.newValue) as TabSyncMessage;
          if (msg?.tabId !== this.tabId) this._dispatch(msg);
        } catch { /* ignore malformed */ }
      }
    });

    // Leader election
    this._tryClaimLeader();

    // Release on unload
    window.addEventListener("beforeunload", () => this._releaseLeader());
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  broadcast(msg: DistributiveOmit<TabSyncMessage, "tabId">) {
    const full = { ...msg, tabId: this.tabId } as TabSyncMessage;
    this.channel?.postMessage(full);
    // localStorage fallback — write a timestamped value to trigger storage events
    try {
      localStorage.setItem(`${CHANNEL_NAME}_msg`, JSON.stringify({ ...full, _ts: Date.now() }));
    } catch { /* quota exceeded — ignore */ }
  }

  subscribe(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  get isLeader(): boolean { return this._isLeader; }

  // ── Internal ────────────────────────────────────────────────────────────────

  private _dispatch(msg: TabSyncMessage) {
    this.handlers.forEach((h) => {
      try { h(msg); } catch { /* handler errors must not crash the bus */ }
    });
  }

  private _tryClaimLeader() {
    const now = Date.now();
    let leader: { id: string; ts: number } | null = null;
    try {
      const raw = localStorage.getItem(LEADER_KEY);
      leader = raw ? JSON.parse(raw) : null;
    } catch { /* storage unavailable */ }

    if (!leader || now - leader.ts > LEADER_TTL_MS || leader.id === this.tabId) {
      this._becomeLeader();
    }
    // else: another alive tab holds leadership — check again after TTL
    else {
      setTimeout(() => this._tryClaimLeader(), LEADER_TTL_MS + 500);
    }
  }

  private _becomeLeader() {
    if (this._isLeader) return;
    this._isLeader = true;
    this._writeLeaderRecord();
    this.heartbeatTimer = setInterval(() => {
      // Verify we still hold leadership (another tab may have taken over)
      try {
        const raw = localStorage.getItem(LEADER_KEY);
        const leader = raw ? JSON.parse(raw) : null;
        if (leader?.id !== this.tabId) {
          this._resignLeader();
          return;
        }
      } catch { /* ignore */ }
      this._writeLeaderRecord();
    }, HEARTBEAT_MS);
  }

  private _writeLeaderRecord() {
    try {
      localStorage.setItem(LEADER_KEY, JSON.stringify({ id: this.tabId, ts: Date.now() }));
    } catch { /* ignore */ }
  }

  private _resignLeader() {
    this._isLeader = false;
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private _releaseLeader() {
    if (!this._isLeader) return;
    try {
      const raw = localStorage.getItem(LEADER_KEY);
      const leader = raw ? JSON.parse(raw) : null;
      if (leader?.id === this.tabId) localStorage.removeItem(LEADER_KEY);
    } catch { /* ignore */ }
    this._resignLeader();
  }
}

// ── Singleton — one instance per tab ────────────────────────────────────────
export const tabSync: TabSyncManager | null =
  typeof window !== "undefined" ? new TabSyncManager() : null;
