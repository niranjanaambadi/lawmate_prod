"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getCaseDocuments,
  DocumentListItem,
  PrepMode,
  PrepMessage,
  PrepSession,
  createPrepSession,
  switchPrepMode,
  updatePrepDocuments,
  exportPrepSession,
  streamPrepChat,
} from "@/lib/api";
import { PrepModePanel, modeRequiresDocs } from "@/components/case-prep/PrepModePanel";
import { PrepDocumentPanel }               from "@/components/case-prep/PrepDocumentPanel";
import { PrepChatPanel, ToolActivity }     from "@/components/case-prep/PrepChatPanel";
import { NotebookDrawer, NotebookToggleButton } from "@/components/notebooks/NotebookDrawer";

// ── Types ─────────────────────────────────────────────────────────────────────

type PageStatus = "loading" | "ready" | "starting" | "error";

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({
  message,
  type,
  onDismiss,
}: {
  message:   string;
  type:      "success" | "error";
  onDismiss: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div
      className={cn(
        "fixed bottom-6 right-6 z-50 flex max-w-sm items-start gap-3 rounded-xl px-4 py-3 shadow-xl border",
        type === "success"
          ? "bg-white border-emerald-200 text-emerald-700"
          : "bg-white border-red-200 text-red-600"
      )}
    >
      {type === "success" ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
      ) : (
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
      )}
      <p className="text-sm">{message}</p>
      <button onClick={onDismiss} className="ml-2 text-slate-400 hover:text-slate-600">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CasePrepWorkspacePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const router     = useRouter();
  const { token }  = useAuth();

  // ── State ──────────────────────────────────────────────────────────────────
  const [pageStatus,     setPageStatus]     = useState<PageStatus>("loading");
  const [session,        setSession]        = useState<PrepSession | null>(null);
  const [documents,      setDocuments]      = useState<DocumentListItem[]>([]);
  const [selectedDocs,   setSelectedDocs]   = useState<string[]>([]);
  const [activeMode,     setActiveMode]     = useState<PrepMode>("argument_builder");
  const [docsLoading,    setDocsLoading]    = useState(false);
  const [messages,       setMessages]       = useState<PrepMessage[]>([]);
  const [streamText,     setStreamText]     = useState("");
  const [isStreaming,    setIsStreaming]     = useState(false);
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [exportLoading,  setExportLoading]  = useState(false);
  const [toast,          setToast]          = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [error,          setError]          = useState("");
  const [notebookOpen,   setNotebookOpen]   = useState(false);

  const stopStreamRef = useRef<(() => void) | null>(null);

  // ── Load documents ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!caseId || !token) return;
    setDocsLoading(true);
    getCaseDocuments(caseId, token)
      .then((res) => setDocuments(res.data ?? res.items ?? []))
      .catch(() => {/* non-fatal */})
      .finally(() => setDocsLoading(false));
  }, [caseId, token]);

  // ── Auto-select all docs on first load ─────────────────────────────────────
  useEffect(() => {
    if (documents.length > 0 && selectedDocs.length === 0 && !session) {
      setSelectedDocs(documents.map((d) => d.id));
    }
  }, [documents]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Finish initial load ────────────────────────────────────────────────────
  useEffect(() => {
    if (pageStatus === "loading") setPageStatus("ready");
  }, [pageStatus]);

  // ── Mode change ────────────────────────────────────────────────────────────
  const handleModeChange = useCallback(async (mode: PrepMode) => {
    setActiveMode(mode);
    if (!session || !token) return;
    try {
      const updated = await switchPrepMode(session.id, mode, token);
      setSession(updated);
    } catch {
      showToast("Could not switch mode — please try again.", "error");
    }
  }, [session, token]);

  // ── Document selection ─────────────────────────────────────────────────────
  const handleDocSelectionChange = useCallback(async (ids: string[]) => {
    setSelectedDocs(ids);
    if (!session || !token) return;
    try {
      const updated = await updatePrepDocuments(session.id, ids, token);
      setSession(updated);
    } catch {
      showToast("Could not update document scope.", "error");
    }
  }, [session, token]);

  // ── Start session ──────────────────────────────────────────────────────────
  // Precedent Finder can start without documents (uses IndianKanoon/KB directly)
  const canStart = modeRequiresDocs(activeMode)
    ? selectedDocs.length > 0
    : true;

  const handleStartSession = useCallback(async () => {
    if (!token || !canStart) return;
    setPageStatus("starting");
    try {
      const newSession = await createPrepSession(
        { case_id: caseId, mode: activeMode, document_ids: selectedDocs },
        token
      );
      setSession(newSession);
      setMessages([]);
      setToolActivities([]);
      setPageStatus("ready");
    } catch (err: unknown) {
      setError((err as { message?: string }).message || "Failed to start session.");
      setPageStatus("error");
    }
  }, [token, caseId, activeMode, selectedDocs, canStart]);

  // ── Send chat message ──────────────────────────────────────────────────────
  const handleSend = useCallback((userMessage: string) => {
    if (!session || !token || isStreaming) return;

    const userMsg: PrepMessage = { role: "user", content: userMessage };
    setMessages((prev) => [...prev, userMsg]);
    setStreamText("");
    setToolActivities([]);
    setIsStreaming(true);

    let accumulated = "";

    const stop = streamPrepChat(session.id, userMessage, token, {
      onDelta: (text) => {
        accumulated += text;
        setStreamText(accumulated);
      },
      onDone: (fullText) => {
        setMessages((prev) => [...prev, { role: "assistant", content: fullText }]);
        setStreamText("");
        setToolActivities([]);
        setIsStreaming(false);
        stopStreamRef.current = null;
      },
      onError: (msg) => {
        showToast(`Stream error: ${msg}`, "error");
        setStreamText("");
        setToolActivities([]);
        setIsStreaming(false);
        stopStreamRef.current = null;
      },
      onWarning: (msg) => {
        showToast(msg, "error");
      },
      onToolStart: (tool) => {
        // Add a "running" indicator
        setToolActivities((prev) => [
          ...prev,
          { tool, status: "running", summary: "" },
        ]);
      },
      onToolEnd: (tool, success, summary) => {
        // Transition the most recent matching "running" entry to "done"
        setToolActivities((prev) => {
          const idx = [...prev].reverse().findIndex(
            (a) => a.tool === tool && a.status === "running"
          );
          if (idx === -1) return prev;
          const realIdx = prev.length - 1 - idx;
          const updated = [...prev];
          updated[realIdx] = { tool, status: success ? "done" : "error", summary };
          return updated;
        });
      },
    });
    stopStreamRef.current = stop;
  }, [session, token, isStreaming]);

  // ── Export ─────────────────────────────────────────────────────────────────
  const handleExport = useCallback(async () => {
    if (!session || !token) return;
    setExportLoading(true);
    try {
      await exportPrepSession(session.id, {}, token);
      showToast("Hearing brief created successfully!", "success");
    } catch {
      showToast("Failed to export brief. Please try again.", "error");
    } finally {
      setExportLoading(false);
    }
  }, [session, token]);

  // ── Clear / new session ────────────────────────────────────────────────────
  const handleClearSession = useCallback(() => {
    stopStreamRef.current?.();
    setSession(null);
    setMessages([]);
    setStreamText("");
    setToolActivities([]);
    setIsStreaming(false);
    setPageStatus("ready");
  }, []);

  const showToast = (message: string, type: "success" | "error") =>
    setToast({ message, type });

  // ── Render states ──────────────────────────────────────────────────────────
  if (pageStatus === "loading") {
    return (
      <div className="flex h-[calc(100vh-4rem)] items-center justify-center bg-slate-50">
        <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
      </div>
    );
  }

  if (pageStatus === "error") {
    return (
      <div className="flex h-[calc(100vh-4rem)] flex-col items-center justify-center gap-4 bg-slate-50">
        <AlertCircle className="h-8 w-8 text-red-500" />
        <p className="text-sm text-slate-600">{error}</p>
        <button
          onClick={() => router.back()}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 shadow-sm hover:bg-slate-50"
        >
          Go back
        </button>
      </div>
    );
  }

  const sessionReady = !!session;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden bg-slate-50">

      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/case-prep")}
            className="text-slate-400 hover:text-slate-600"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <h1 className="text-sm font-semibold text-slate-800">Case Prep AI</h1>
          {session && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
              Session active
            </span>
          )}
        </div>

        {/* Session CTA */}
        {!session ? (
          <button
            onClick={handleStartSession}
            disabled={!canStart || pageStatus === "starting"}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all shadow-sm",
              !canStart
                ? "cursor-not-allowed bg-slate-100 text-slate-400"
                : "bg-indigo-600 text-white hover:bg-indigo-700"
            )}
          >
            {pageStatus === "starting" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Start Session
          </button>
        ) : (
          <button
            onClick={handleClearSession}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            New Session
          </button>
        )}
      </div>

      {/* ── Three-panel body ─────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left — Mode selector */}
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
          <PrepModePanel
            activeMode={activeMode}
            onModeChange={handleModeChange}
            disabled={isStreaming}
          />
        </aside>

        {/* Centre — Chat */}
        <main className="flex-1 overflow-hidden bg-white">
          <PrepChatPanel
            messages={messages}
            mode={activeMode}
            streamingText={streamText}
            isStreaming={isStreaming}
            isDisabled={!sessionReady}
            toolActivities={toolActivities}
            onSend={handleSend}
            onExport={handleExport}
            onClearSession={session ? handleClearSession : undefined}
            exportLoading={exportLoading}
          />
        </main>

        {/* Right — Documents */}
        <aside className="w-60 shrink-0 overflow-y-auto border-l border-slate-200 bg-white">
          <PrepDocumentPanel
            documents={documents}
            selectedIds={selectedDocs}
            onSelectionChange={handleDocSelectionChange}
            loading={docsLoading}
            disabled={isStreaming}
          />
        </aside>
      </div>

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onDismiss={() => setToast(null)}
        />
      )}

      {/* ── Notebook drawer ───────────────────────────────────────────── */}
      <NotebookToggleButton
        isOpen={notebookOpen}
        onClick={() => setNotebookOpen((v) => !v)}
      />
      <NotebookDrawer
        caseId={caseId}
        token={token}
        isOpen={notebookOpen}
        onClose={() => setNotebookOpen(false)}
      />
    </div>
  );
}
