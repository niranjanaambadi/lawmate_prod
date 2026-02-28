"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  BookOpen,
  Loader2,
  AlertCircle,
  CheckCircle2,
  FileText,
  ChevronDown,
  Upload,
  X,
} from "lucide-react";
import {
  listCases,
  getCaseDocuments,
  getDocumentViewUrl,
  createLegalInsightJob,
  uploadLegalInsightPdf,
  getLegalInsightJob,
  getLegalInsightResult,
  CaseListItem,
  DocumentListItem,
  LegalInsightJob,
  LegalInsightResult,
  SummaryItem,
  CitationRef,
} from "@/lib/api";
import { PdfViewer } from "@/components/hearing-day/PdfViewer";
import { cn } from "@/lib/utils";
import { NotebookDrawer, NotebookToggleButton } from "@/components/notebooks/NotebookDrawer";

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_MESSAGES: Record<string, string> = {
  queued: "Queued…",
  extracting: "Indexing Judgment…",
  ocr: "Extracting Text (OCR)…",
  summarizing: "Analyzing Legal Reasoning…",
  validating: "Validating Citations…",
  completed: "Analysis Complete",
  failed: "Analysis Failed",
};

const TABS = [
  { key: "facts", label: "Facts" },
  { key: "issues", label: "Issues" },
  { key: "arguments", label: "Arguments" },
  { key: "ratio", label: "Ratio Decidendi" },
  { key: "final_order", label: "Final Order" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const POLL_INTERVAL_MS = 2000;

// ── SummaryItemCard ──────────────────────────────────────────────────────────

interface SummaryItemCardProps {
  item: SummaryItem;
  citation_map: Record<string, CitationRef>;
  onCitationClick: (ref: CitationRef, id: string) => void;
  activeCitationId: string | null;
}

function SummaryItemCard({
  item,
  citation_map,
  onCitationClick,
  activeCitationId,
}: SummaryItemCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm space-y-3">
      <p className="text-sm leading-relaxed text-slate-800">{item.text}</p>
      {item.citation_ids.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {item.citation_ids.map((id) => {
            const ref = citation_map[id];
            if (!ref) {
              return (
                <span
                  key={id}
                  className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-400"
                  title="Reference not found in citation map"
                >
                  Ref not found
                </span>
              );
            }
            const isActive = activeCitationId === id;
            return (
              <button
                key={id}
                onClick={() => onCitationClick(ref, id)}
                className={cn(
                  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-all",
                  isActive
                    ? "bg-amber-400 text-amber-900 shadow-sm ring-2 ring-amber-300"
                    : "bg-indigo-100 text-indigo-700 hover:bg-indigo-200"
                )}
                title={`Jump to page ${ref.page_number}`}
              >
                p.{ref.page_number}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── StatusBar ────────────────────────────────────────────────────────────────

interface StatusBarProps {
  job: LegalInsightJob;
}

function StatusBar({ job }: StatusBarProps) {
  const message = STATUS_MESSAGES[job.status] ?? "Processing…";
  const progressPct = Math.max(0, Math.min(100, job.progress ?? 0));
  const isFailed = job.status === "failed";
  const isCompleted = job.status === "completed";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span
          className={cn(
            "flex items-center gap-1.5 font-medium",
            isFailed
              ? "text-red-600"
              : isCompleted
              ? "text-green-600"
              : "text-indigo-600"
          )}
        >
          {isFailed ? (
            <AlertCircle className="h-3.5 w-3.5" />
          ) : isCompleted ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
          ) : (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          )}
          {message}
        </span>
        <span className="text-slate-500">{progressPct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            isFailed
              ? "bg-red-400"
              : isCompleted
              ? "bg-green-500"
              : "bg-indigo-500"
          )}
          style={{ width: `${progressPct}%` }}
        />
      </div>
      {isFailed && job.error && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
          {job.error}
        </p>
      )}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function LegalInsightPage() {
  const { token } = useAuth();

  // Input mode: select an existing case document or upload a PDF directly
  const [inputMode, setInputMode] = useState<"case" | "upload">("case");

  // Selector state (case mode)
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [casesLoading, setCasesLoading] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>("");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  // Upload state (upload mode)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedPdfUrl, setUploadedPdfUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Job & result state
  const [job, setJob] = useState<LegalInsightJob | null>(null);
  const [result, setResult] = useState<LegalInsightResult | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Viewer state
  const [activeTab, setActiveTab] = useState<TabKey>("facts");
  const [activePage, setActivePage] = useState<number | undefined>(undefined);
  const [activeCitation, setActiveCitation] = useState<CitationRef | null>(null);
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load cases on mount ────────────────────────────────────────────────────

  useEffect(() => {
    if (!token) return;
    setCasesLoading(true);
    listCases({ page: 1, perPage: 100 }, token)
      .then((res) => setCases(res.items ?? []))
      .catch((err) => setError(err.message ?? "Failed to load cases."))
      .finally(() => setCasesLoading(false));
  }, [token]);

  // ── Load documents when case is selected ──────────────────────────────────

  const handleCaseChange = useCallback(
    async (caseId: string) => {
      setSelectedCaseId(caseId);
      setSelectedDocumentId("");
      setDocuments([]);
      setPdfUrl(null);
      setJob(null);
      setResult(null);
      setError(null);
      setActivePage(undefined);
      setActiveCitation(null);
      setActiveCitationId(null);

      if (!caseId || !token) return;
      setDocsLoading(true);
      try {
        const res = await getCaseDocuments(caseId, token);
        const allDocs = res.items ?? res.data ?? [];
        const filtered = allDocs.filter(
          (d) =>
            d.category === "judgment" ||
            d.category === "order" ||
            d.category === "Judgment" ||
            d.category === "Order"
        );
        setDocuments(filtered);
      } catch (err: any) {
        setError(err.message ?? "Failed to load documents.");
      } finally {
        setDocsLoading(false);
      }
    },
    [token]
  );

  // ── Load PDF URL when document is selected ────────────────────────────────

  const handleDocumentChange = useCallback(
    async (docId: string) => {
      setSelectedDocumentId(docId);
      setPdfUrl(null);
      setJob(null);
      setResult(null);
      setError(null);
      setActivePage(undefined);
      setActiveCitation(null);
      setActiveCitationId(null);

      if (!docId || !token) return;
      try {
        const res = await getDocumentViewUrl(docId, token);
        setPdfUrl(res.url);
      } catch (err: any) {
        setError(err.message ?? "Failed to get document URL.");
      }
    },
    [token]
  );

  // ── Stop polling helper ───────────────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  // ── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current);
      }
      if (uploadedPdfUrl) URL.revokeObjectURL(uploadedPdfUrl);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Switch input mode ─────────────────────────────────────────────────────

  const handleModeSwitch = useCallback(
    (mode: "case" | "upload") => {
      setInputMode(mode);
      stopPolling();
      setJob(null);
      setResult(null);
      setError(null);
      setActivePage(undefined);
      setActiveCitation(null);
      setActiveCitationId(null);
    },
    [stopPolling]
  );

  // ── File selection handler ────────────────────────────────────────────────

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0] ?? null;
      if (uploadedPdfUrl) URL.revokeObjectURL(uploadedPdfUrl);
      setUploadedFile(file);
      setUploadedPdfUrl(file ? URL.createObjectURL(file) : null);
      setJob(null);
      setResult(null);
      setError(null);
      setActivePage(undefined);
      setActiveCitation(null);
      setActiveCitationId(null);
    },
    [uploadedPdfUrl]
  );

  // ── Clear uploaded file ───────────────────────────────────────────────────

  const handleClearUpload = useCallback(() => {
    if (uploadedPdfUrl) URL.revokeObjectURL(uploadedPdfUrl);
    setUploadedFile(null);
    setUploadedPdfUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setJob(null);
    setResult(null);
    setError(null);
  }, [uploadedPdfUrl]);

  // ── Poll job status ───────────────────────────────────────────────────────

  const startPolling = useCallback(
    (jobId: string) => {
      if (!token) return;
      setIsPolling(true);

      const poll = async () => {
        try {
          const updated = await getLegalInsightJob(jobId, token);
          setJob(updated);

          if (updated.status === "completed") {
            stopPolling();
            try {
              const res = await getLegalInsightResult(jobId, token);
              setResult(res);
            } catch (err: any) {
              setError(err.message ?? "Failed to fetch result.");
            }
          } else if (updated.status === "failed") {
            stopPolling();
            setError(updated.error ?? "Analysis failed.");
          }
        } catch (err: any) {
          stopPolling();
          setError(err.message ?? "Polling failed.");
        }
      };

      poll();
      pollIntervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    },
    [token, stopPolling]
  );

  // ── Analyze button handler ────────────────────────────────────────────────

  const handleAnalyze = useCallback(async () => {
    if (!token) return;
    if (inputMode === "case" && !selectedDocumentId) return;
    if (inputMode === "upload" && !uploadedFile) return;

    stopPolling();
    setJob(null);
    setResult(null);
    setError(null);
    setActivePage(undefined);
    setActiveCitation(null);
    setActiveCitationId(null);
    setAnalyzeLoading(true);

    try {
      const newJob =
        inputMode === "upload"
          ? await uploadLegalInsightPdf(uploadedFile!, token)
          : await createLegalInsightJob(selectedDocumentId, token);

      setJob(newJob);
      setAnalyzeLoading(false);

      if (newJob.status === "completed") {
        const res = await getLegalInsightResult(newJob.job_id, token);
        setResult(res);
      } else if (newJob.status !== "failed") {
        startPolling(newJob.job_id);
      }
    } catch (err: any) {
      setError(err.message ?? "Failed to start analysis.");
      setAnalyzeLoading(false);
    }
  }, [inputMode, selectedDocumentId, uploadedFile, token, stopPolling, startPolling]);

  // ── Citation click handler ────────────────────────────────────────────────

  const handleCitationClick = useCallback(
    (ref: CitationRef, id: string) => {
      setActiveCitation(ref);
      setActiveCitationId(id);
      if (ref.page_number) {
        setActivePage(ref.page_number);
      }
    },
    []
  );

  // ── Notebook drawer ───────────────────────────────────────────────────────

  const [notebookOpen, setNotebookOpen] = useState(false);

  // ── Derived values ────────────────────────────────────────────────────────

  const isJobRunning =
    !!job &&
    job.status !== "completed" &&
    job.status !== "failed";

  const analyzeDisabled =
    (inputMode === "case" ? !selectedDocumentId : !uploadedFile) ||
    isJobRunning ||
    analyzeLoading;

  // For the PDF viewer: in upload mode use the local object URL; in case mode
  // use the presigned S3 URL fetched from the backend.
  const activePdfUrl = inputMode === "upload" ? uploadedPdfUrl : pdfUrl;

  const activeItems: SummaryItem[] =
    result?.summary[activeTab] ?? [];

  const highlightBbox =
    activeCitation?.bbox
      ? {
          left: activeCitation.bbox.x,
          top: activeCitation.bbox.y,
          width: activeCitation.bbox.width,
          height: activeCitation.bbox.height,
        }
      : null;

  // ── Case label helper ─────────────────────────────────────────────────────

  const caseLabel = (c: CaseListItem) =>
    [c.case_number, c.efiling_number].filter(Boolean).join(" · ") ||
    c.petitioner_name ||
    c.id;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* ── Left panel ────────────────────────────────────────────────────── */}
      <div className="flex w-[420px] shrink-0 flex-col border-r border-slate-200 bg-white overflow-y-auto">
        {/* Header */}
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-center gap-2 mb-1">
            <BookOpen className="h-5 w-5 text-indigo-600" />
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Judgement Analyzer AI</h1>
          </div>
          <p className="text-xs text-slate-500">
            AI-powered judgment summarizer with clickable citations
          </p>
        </div>

        {/* Controls */}
        <div className="p-4 space-y-3 border-b border-slate-200">
          {/* Mode toggle */}
          <div className="flex rounded-md border border-slate-200 overflow-hidden text-xs font-medium">
            <button
              onClick={() => handleModeSwitch("case")}
              className={cn(
                "flex-1 py-1.5 transition-colors",
                inputMode === "case"
                  ? "bg-indigo-600 text-white"
                  : "bg-white text-slate-500 hover:bg-slate-50"
              )}
            >
              From Case
            </button>
            <button
              onClick={() => handleModeSwitch("upload")}
              className={cn(
                "flex-1 py-1.5 transition-colors",
                inputMode === "upload"
                  ? "bg-indigo-600 text-white"
                  : "bg-white text-slate-500 hover:bg-slate-50"
              )}
            >
              Upload PDF
            </button>
          </div>

          {inputMode === "case" ? (
            <>
              {/* Case selector */}
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">
                  Case
                </label>
                {casesLoading ? (
                  <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Loading cases…
                  </div>
                ) : (
                  <div className="relative">
                    <select
                      value={selectedCaseId}
                      onChange={(e) => handleCaseChange(e.target.value)}
                      className="w-full appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
                    >
                      <option value="">— Select a case —</option>
                      {cases.map((c) => (
                        <option key={c.id} value={c.id}>
                          {caseLabel(c)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  </div>
                )}
              </div>

              {/* Document selector */}
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1">
                  Judgment / Order document
                </label>
                {docsLoading ? (
                  <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Loading documents…
                  </div>
                ) : (
                  <div className="relative">
                    <select
                      value={selectedDocumentId}
                      onChange={(e) => handleDocumentChange(e.target.value)}
                      disabled={!selectedCaseId || documents.length === 0}
                      className="w-full appearance-none rounded-md border border-slate-200 bg-white px-3 py-2 pr-8 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="">
                        {!selectedCaseId
                          ? "— Select a case first —"
                          : documents.length === 0
                          ? "— No judgment/order documents —"
                          : "— Select a document —"}
                      </option>
                      {documents.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.title || d.id}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  </div>
                )}
              </div>
            </>
          ) : (
            /* Upload mode */
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">
                Judgment PDF
              </label>
              {uploadedFile ? (
                <div className="flex items-center gap-2 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm">
                  <FileText className="h-4 w-4 text-indigo-600 shrink-0" />
                  <span className="flex-1 truncate text-slate-700 text-xs">
                    {uploadedFile.name}
                  </span>
                  <button
                    onClick={handleClearUpload}
                    className="shrink-0 text-slate-400 hover:text-red-500 transition-colors"
                    title="Remove file"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex flex-col items-center justify-center gap-1.5 rounded-md border-2 border-dashed border-slate-200 bg-white px-4 py-5 text-slate-400 hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-600 transition-colors cursor-pointer"
                >
                  <Upload className="h-5 w-5" />
                  <span className="text-xs font-medium">Click to select PDF</span>
                  <span className="text-[11px]">Kerala HC · Supreme Court judgments</span>
                </button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>
          )}

          {/* Analyze button */}
          <button
            onClick={handleAnalyze}
            disabled={analyzeDisabled}
            className={cn(
              "w-full flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all",
              analyzeDisabled
                ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                : "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm"
            )}
          >
            {analyzeLoading || isJobRunning ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Analyzing…
              </>
            ) : (
              <>
                <FileText className="h-4 w-4" />
                Analyze Judgment
              </>
            )}
          </button>

          {/* Error message */}
          {error && (
            <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 p-3 text-xs text-red-700">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </div>

        {/* Status / Progress */}
        {job && (
          <div className="px-4 py-3 border-b border-slate-200">
            <StatusBar job={job} />
          </div>
        )}

        {/* Summary tabs and content */}
        {result && (
          <div className="flex flex-col flex-1 overflow-hidden">
            {/* Tab bar */}
            <div className="flex overflow-x-auto border-b border-slate-200 shrink-0">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    "whitespace-nowrap px-3 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors shrink-0",
                    activeTab === tab.key
                      ? "border-indigo-600 text-indigo-600"
                      : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
                  )}
                >
                  {tab.label}
                  {result.summary[tab.key]?.length > 0 && (
                    <span
                      className={cn(
                        "ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px]",
                        activeTab === tab.key
                          ? "bg-indigo-100 text-indigo-700"
                          : "bg-slate-100 text-slate-500"
                      )}
                    >
                      {result.summary[tab.key].length}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Active tab content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {activeItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center text-slate-400">
                  <FileText className="h-8 w-8 mb-2 opacity-40" />
                  <p className="text-sm">No items found for this section.</p>
                </div>
              ) : (
                activeItems.map((item, idx) => (
                  <SummaryItemCard
                    key={idx}
                    item={item}
                    citation_map={result.citation_map}
                    onCitationClick={handleCitationClick}
                    activeCitationId={activeCitationId}
                  />
                ))
              )}
            </div>
          </div>
        )}

        {/* Empty state when no result yet and not loading */}
        {!result && !job && (
          <div className="flex flex-col items-center justify-center flex-1 p-6 text-center text-slate-400">
            <BookOpen className="h-10 w-10 mb-3 opacity-30" />
            <p className="text-sm font-medium text-slate-500">No analysis yet</p>
            <p className="text-xs mt-1 max-w-[240px]">
              Select a case document or upload a PDF directly, then click{" "}
              <span className="font-medium text-slate-600">Analyze Judgment</span> to get
              an AI-powered structured summary with clickable citations.
            </p>
          </div>
        )}
      </div>

      {/* ── Right panel — PDF viewer ───────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden">
        <PdfViewer
          url={activePdfUrl}
          activePage={activePage}
          highlightBbox={highlightBbox}
        />
      </div>

      {/* ── Notebook drawer ────────────────────────────────────────────────── */}
      <NotebookToggleButton
        isOpen={notebookOpen}
        onClick={() => setNotebookOpen((v) => !v)}
      />
      <NotebookDrawer
        caseId={selectedCaseId || undefined}
        token={token}
        isOpen={notebookOpen}
        onClose={() => setNotebookOpen(false)}
      />
    </div>
  );
}
