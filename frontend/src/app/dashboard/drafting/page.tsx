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

  // Debounce timer — prevents multiple rapid uploads firing multiple extractions
  const ctxDebounceRef = useRef<NodeJS.Timeout | null>(null);

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

    // Auto-extract case context after upload.
    // Debounced by 1.5s so rapid multi-file uploads trigger only one extraction.
    if (ctxDebounceRef.current) clearTimeout(ctxDebounceRef.current);
    ctxDebounceRef.current = setTimeout(() => {
      handleRefreshContext();
    }, 1500);
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <div className="w-56 shrink-0 border-r-2 border-slate-200 flex flex-col overflow-hidden bg-slate-50">
            <div className="px-3 pt-3 pb-1.5 border-b border-slate-200">
              <p className="text-[11px] font-bold text-indigo-700 uppercase tracking-widest">
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
              hasDocuments={(currentWs.documents?.length ?? 0) > 0}
              onRefresh={handleRefreshContext}
              isRefreshing={refreshingCtx}
            />

            {/* Chat + Studio side by side — resizable via drag handle */}
            <div ref={splitRef} className="flex flex-1 overflow-hidden">
              {/* Chat — takes the remaining width */}
              <div className="flex flex-col overflow-hidden" style={{ flex: `0 0 ${100 - studioPct}%`, minWidth: "20%" }}>
                <div className="px-3 pt-2.5 pb-1.5 border-b border-slate-200 bg-white">
                  <p className="text-[11px] font-bold text-indigo-700 uppercase tracking-widest">
                    Chat
                  </p>
                </div>
                <ChatPanel
                  workspaceId={currentWs.id}
                  token={token!}
                  onDraftFromMessage={(text) => openBriefModal(text)}
                />
              </div>

              {/* Drag handle — wider hit area with visible indicator line */}
              <div
                onMouseDown={onSplitMouseDown}
                className="w-3 shrink-0 cursor-col-resize flex items-center justify-center bg-slate-100 hover:bg-indigo-100 active:bg-indigo-200 border-x border-slate-200 transition-colors group"
                title="Drag to resize"
              >
                <div className="w-0.5 h-8 rounded-full bg-slate-300 group-hover:bg-indigo-400 transition-colors" />
              </div>

              {/* Drafting Studio — width controlled by studioPct */}
              <div className="flex flex-col overflow-hidden" style={{ flex: `0 0 ${studioPct}%`, minWidth: "20%" }}>
                <div className="px-3 pt-2.5 pb-1.5 border-b border-slate-200 bg-white flex items-center justify-between">
                  <p className="text-[11px] font-bold text-indigo-700 uppercase tracking-widest">
                    Drafting Studio
                  </p>
                  <button
                    onClick={() => openBriefModal()}
                    className="flex items-center gap-1 text-[11px] font-semibold bg-indigo-600 text-white px-2.5 py-1 rounded-md hover:bg-indigo-700 active:bg-indigo-800 shadow-sm transition-colors"
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
