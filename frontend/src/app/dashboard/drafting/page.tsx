"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useAuth }        from "@/contexts/AuthContext";
import { useWorkspaceStore, type Workspace, type WorkspaceDraft, type CaseContext } from "@/stores/workspaceStore";
import {
  listWorkspaces, createWorkspace, updateWorkspace, deleteWorkspace,
  type DraftingDraft,
} from "@/lib/api";

import WorkspaceTabs     from "@/components/drafting/WorkspaceTabs";
import DocumentVault     from "@/components/drafting/DocumentVault";
import IntelligencePanel from "@/components/drafting/IntelligencePanel";
import ChatPanel         from "@/components/drafting/ChatPanel";
import DraftingStudio    from "@/components/drafting/DraftingStudio";
import DraftingBriefModal from "@/components/drafting/DraftingBriefModal";

export default function DraftingPage() {
  // token comes from AuthContext (key: "lawmate_access_token") — never read
  // localStorage directly from this page to avoid key-mismatch bugs.
  const { user, token } = useAuth();

  const {
    workspaces, activeWorkspaceId,
    setWorkspaces, addWorkspace, updateWorkspace: storeUpdateWorkspace,
    removeWorkspace, setActiveWorkspace,
    addDocument, removeDocument, setCitedDocIds, citedDocIds,
    addDraft, updateDraft, removeDraft,
    setActiveDraftId, activeDraftId,
    setCaseContext, activeWorkspace,
  } = useWorkspaceStore();

  const [loading,         setLoading]         = useState(true);
  const [briefModalOpen,  setBriefModalOpen]   = useState(false);
  const [briefPrefill,    setBriefPrefill]     = useState("");
  const [refreshingCtx,   setRefreshingCtx]    = useState(false);

  // ── Resizable Chat / Studio split ─────────────────────────────────────────
  // studioPct = percentage of the Chat+Studio row taken by Drafting Studio
  const [studioPct,    setStudioPct]    = useState(42);
  const splitRef                        = useRef<HTMLDivElement>(null);
  const dragging                        = useRef(false);

  const onSplitMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    e.preventDefault();
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current || !splitRef.current) return;
      const rect  = splitRef.current.getBoundingClientRect();
      const pct   = ((rect.right - e.clientX) / rect.width) * 100;
      setStudioPct(Math.min(70, Math.max(20, pct)));
    };
    const onMouseUp = () => { dragging.current = false; };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup",   onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup",   onMouseUp);
    };
  }, []);

  const currentWs    = activeWorkspace();
  const currentDraft = currentWs?.drafts.find((d) => d.id === activeDraftId) ?? null;

  // ── Load workspaces on mount ───────────────────────────────────────────────
  useEffect(() => {
    if (!token) { setLoading(false); return; }
    (async () => {
      try {
        const wsList = await listWorkspaces(token);
        setWorkspaces(wsList);
        if (wsList.length > 0 && !activeWorkspaceId) {
          setActiveWorkspace(wsList[0].id);
        }
      } catch (err) {
        console.error("Failed to load workspaces:", err);
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  // ── Workspace actions ──────────────────────────────────────────────────────
  const handleCreateWorkspace = async () => {
    if (!token) return;
    try {
      const ws = await createWorkspace("Untitled", token);
      addWorkspace(ws);
      setActiveWorkspace(ws.id);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Could not create workspace");
    }
  };

  const handleCloseWorkspace = async (id: string) => {
    // Just deactivate locally — don't delete from server
    if (activeWorkspaceId === id) {
      const remaining = workspaces.filter((w) => w.id !== id);
      setActiveWorkspace(remaining[0]?.id ?? null);
    }
    removeWorkspace(id);
    if (!token) return;
    try {
      await deleteWorkspace(id, token);
    } catch {/* silently ignore */}
  };

  const handleRename = async (id: string, label: string) => {
    storeUpdateWorkspace(id, { label });
    if (!token) return;
    try {
      await updateWorkspace(id, { label }, token);
    } catch {/* silently ignore */}
  };

  // ── Context refresh ────────────────────────────────────────────────────────
  const handleRefreshContext = async () => {
    if (!currentWs || !token) return;
    setRefreshingCtx(true);
    try {
      const { extractWorkspaceContext } = await import("@/lib/api");
      const ctx = await extractWorkspaceContext(currentWs.id, token);
      setCaseContext(currentWs.id, (ctx ?? {}) as CaseContext);
    } catch (err: unknown) {
      console.error("Context refresh failed:", err);
    } finally {
      setRefreshingCtx(false);
    }
  };

  // ── Document callbacks ─────────────────────────────────────────────────────
  const handleUploaded = useCallback((doc: unknown) => {
    if (!currentWs) return;
    addDocument(currentWs.id, doc as Workspace["documents"][0]);
  }, [currentWs?.id]);

  const handleDeleted = useCallback((docId: string) => {
    if (!currentWs) return;
    removeDocument(currentWs.id, docId);
  }, [currentWs?.id]);

  // ── Draft callbacks ────────────────────────────────────────────────────────
  const handleDraftGenerated = (draft: unknown) => {
    if (!currentWs) return;
    const d = draft as WorkspaceDraft;
    addDraft(currentWs.id, d);
    setActiveDraftId(d.id);
    setBriefModalOpen(false);
  };

  const handleDraftSaved = (draft: DraftingDraft) => {
    if (!currentWs) return;
    updateDraft(currentWs.id, draft.id, draft);
  };

  const handleSelectDraft = (draftId: string) => setActiveDraftId(draftId);

  const openBriefModal = (prefill = "") => {
    setBriefPrefill(prefill);
    setBriefModalOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        Loading workspaces…
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Workspace tab bar ─────────────────────────────────────────────── */}
      <WorkspaceTabs
        workspaces={workspaces}
        activeId={activeWorkspaceId}
        onSwitch={setActiveWorkspace}
        onClose={handleCloseWorkspace}
        onCreate={handleCreateWorkspace}
        onRename={handleRename}
      />

      {/* ── No workspace state ────────────────────────────────────────────── */}
      {!currentWs ? (
        <div className="flex flex-col items-center justify-center flex-1 gap-3 text-slate-400">
          <p className="text-sm">No workspace open</p>
          <button
            onClick={handleCreateWorkspace}
            className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
          >
            Create Workspace
          </button>
        </div>
      ) : (
        /* ── Main 3-panel layout ─────────────────────────────────────────── */
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Document Vault */}
          <div className="w-56 shrink-0 border-r border-slate-200 flex flex-col overflow-hidden">
            <div className="px-3 pt-2 pb-1">
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                Documents
              </p>
            </div>
            <DocumentVault
              workspaceId={currentWs.id}
              documents={currentWs.documents}
              citedDocIds={citedDocIds}
              token={token!}
              onUploaded={handleUploaded}
              onDeleted={handleDeleted}
            />
          </div>

          {/* Right side: Intelligence + Chat + Studio stacked */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Intelligence Panel (collapsible) */}
            <IntelligencePanel
              caseContext={currentWs.caseContext}
              onRefresh={handleRefreshContext}
              isRefreshing={refreshingCtx}
            />

            {/* Chat + Studio side by side — resizable via drag handle */}
            <div ref={splitRef} className="flex flex-1 overflow-hidden">
              {/* Chat — takes the remaining width */}
              <div className="flex flex-col overflow-hidden border-r border-slate-200" style={{ flex: `0 0 ${100 - studioPct}%`, minWidth: "20%" }}>
                <div className="px-3 pt-2 pb-0.5">
                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                    Chat
                  </p>
                </div>
                <ChatPanel
                  workspaceId={currentWs.id}
                  token={token!}
                  onDraftFromMessage={(text) => openBriefModal(text)}
                />
              </div>

              {/* Drag handle */}
              <div
                onMouseDown={onSplitMouseDown}
                className="w-1.5 shrink-0 cursor-col-resize bg-slate-200 hover:bg-indigo-400 active:bg-indigo-500 transition-colors"
                title="Drag to resize"
              />

              {/* Drafting Studio — width controlled by studioPct */}
              <div className="flex flex-col overflow-hidden" style={{ flex: `0 0 ${studioPct}%`, minWidth: "20%" }}>
                <div className="px-3 pt-2 pb-0.5 flex items-center justify-between">
                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                    Drafting Studio
                  </p>
                  <button
                    onClick={() => openBriefModal()}
                    className="text-[11px] text-indigo-600 hover:text-indigo-700"
                  >
                    + New Draft
                  </button>
                </div>
                <DraftingStudio
                  workspaceId={currentWs.id}
                  activeDraft={currentDraft as DraftingDraft | null}
                  drafts={currentWs.drafts as DraftingDraft[]}
                  token={token!}
                  onSaved={handleDraftSaved}
                  onSelectDraft={handleSelectDraft}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Brief modal */}
      {briefModalOpen && currentWs && (
        <DraftingBriefModal
          workspaceId={currentWs.id}
          caseContext={currentWs.caseContext}
          prefillText={briefPrefill}
          token={token!}
          onGenerated={handleDraftGenerated}
          onClose={() => setBriefModalOpen(false)}
        />
      )}
    </div>
  );
}
