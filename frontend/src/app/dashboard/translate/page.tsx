"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  translateTextStream,
  translateDocumentStream,
  TranslateDocumentStreamDoneEvent,
  exportTranslation,
  openCaseNotebook,
  createNotebookNote,
  getCases,
  TranslateDirection,
  TranslateDirectionInput,
  TranslateTextResponse,
  TranslateDocumentResponse,
  GlossaryTerm,
  CaseOption,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  AlertCircle,
  ArrowLeftRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Copy,
  Download,
  FileText,
  FolderOpen,
  Languages,
  Loader2,
  NotebookPen,
  Scan,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────

type Tab = "text" | "document";

// ── Helpers ────────────────────────────────────────────────────────────────

function directionLabel(dir: TranslateDirection): { from: string; to: string } {
  return dir === "en_to_ml"
    ? { from: "English", to: "Malayalam" }
    : { from: "Malayalam", to: "English" };
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "text/plain",
];

// ── Glossary term highlighting (Task 7) ────────────────────────────────────

interface GlossaryHighlightProps {
  text: string;
  terms: GlossaryTerm[];
  direction: TranslateDirection;
}

function GlossaryHighlight({ text, terms, direction }: GlossaryHighlightProps) {
  if (!terms.length) {
    return (
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
        {text}
      </p>
    );
  }

  // Highlight the *target*-language terms that appear in the translated output
  const sorted = [...terms].sort((a, b) => b.target.length - a.target.length);

  const escaped = sorted
    .map((t) => t.target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .filter(Boolean)
    .join("|");

  if (!escaped) {
    return (
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
        {text}
      </p>
    );
  }

  const regex = new RegExp(`(${escaped})`, "g");
  const parts = text.split(regex);

  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
      {parts.map((part, i) => {
        const term = sorted.find((t) => t.target === part);
        if (term) {
          const tooltip =
            direction === "en_to_ml"
              ? `Glossary (EN): ${term.source}`
              : `Glossary (ML): ${term.source}`;
          return (
            <span
              key={i}
              className="border-b border-dotted border-indigo-400 text-indigo-700 cursor-help"
              title={tooltip}
            >
              {part}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

// ── Quality panel ──────────────────────────────────────────────────────────

interface QualityPanelProps {
  glossaryHits: number;
  warnings: string[];
  charCount: number;
  chunks?: number;
}

function QualityPanel({
  glossaryHits,
  warnings,
  charCount,
  chunks,
}: QualityPanelProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3 text-sm">
      <p className="font-medium text-slate-700 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-indigo-500" />
        Translation Quality
      </p>
      <div className="grid grid-cols-2 gap-3 text-slate-600">
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide">
            Glossary matches
          </p>
          <p className="font-semibold text-indigo-600">{glossaryHits}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide">
            Characters
          </p>
          <p className="font-semibold">{charCount.toLocaleString()}</p>
        </div>
        {chunks !== undefined && (
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wide">
              Chunks processed
            </p>
            <p className="font-semibold">{chunks}</p>
          </div>
        )}
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide">
            Warnings
          </p>
          <p
            className={cn(
              "font-semibold",
              warnings.length > 0 ? "text-amber-600" : "text-green-600"
            )}
          >
            {warnings.length === 0 ? "None" : warnings.length}
          </p>
        </div>
      </div>
      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((w, i) => (
            <p
              key={i}
              className="flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 rounded px-2 py-1"
            >
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Export dropdown ────────────────────────────────────────────────────────

interface ExportMenuProps {
  disabled: boolean;
  onExport: (fmt: "pdf" | "docx") => void;
  loading: boolean;
}

function ExportMenu({ disabled, onExport, loading }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative">
      <Button
        variant="outline"
        size="sm"
        disabled={disabled || loading}
        onClick={() => setOpen((o) => !o)}
      >
        {loading ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Download className="mr-2 h-4 w-4" />
        )}
        Export
        <ChevronDown className="ml-1 h-3 w-3" />
      </Button>
      {open && (
        <div className="absolute right-0 mt-1 w-40 rounded-md border border-slate-200 bg-white shadow-lg z-10">
          <button
            className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 text-slate-700"
            onClick={() => {
              onExport("pdf");
              setOpen(false);
            }}
          >
            <FileText className="h-4 w-4 text-red-500" />
            Download PDF
          </button>
          <button
            className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 text-slate-700"
            onClick={() => {
              onExport("docx");
              setOpen(false);
            }}
          >
            <FileText className="h-4 w-4 text-blue-500" />
            Download DOCX
          </button>
        </div>
      )}
    </div>
  );
}

// ── Add-to-Case modal ──────────────────────────────────────────────────────

interface AddToCaseModalProps {
  translated: string;
  direction: TranslateDirection;
  token: string | null;
  onClose: () => void;
}

function AddToCaseModal({
  translated,
  direction,
  token,
  onClose,
}: AddToCaseModalProps) {
  const [cases, setCases] = useState<CaseOption[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [noteTitle, setNoteTitle] = useState(
    `Translation (${direction === "en_to_ml" ? "EN→ML" : "ML→EN"})`
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingCases(true);
    getCases(token)
      .then((data: CaseOption[]) => setCases(data))
      .catch(() => setError("Failed to load cases."))
      .finally(() => setLoadingCases(false));
  }, [token]);

  async function handleSave() {
    if (!selectedCaseId) return;
    setSaving(true);
    setError(null);
    try {
      const paragraphs = translated
        .split("\n\n")
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p) => ({
          type: "paragraph",
          content: [{ type: "text", text: p }],
        }));
      const content_json = { type: "doc", content: paragraphs };
      const notebook = await openCaseNotebook(selectedCaseId, token);
      await createNotebookNote(
        notebook.id,
        { title: noteTitle, content_text: translated, content_json },
        token
      );
      setSaved(true);
      setTimeout(onClose, 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save note.");
    } finally {
      setSaving(false);
    }
  }

  const caseLabel = (c: CaseOption) =>
    [c.case_number, c.efiling_number].filter(Boolean).join(" · ") || c.id;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div className="flex items-center gap-2">
            <NotebookPen className="h-5 w-5 text-indigo-600" />
            <h2 className="text-base font-semibold text-slate-800">
              Add to Case Notebook
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">
              Note title
            </label>
            <input
              type="text"
              value={noteTitle}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setNoteTitle(e.target.value)
              }
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={200}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">
              Select case
            </label>
            {loadingCases ? (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading cases…
              </div>
            ) : (
              <select
                value={selectedCaseId}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                  setSelectedCaseId(e.target.value)
                }
                className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">— Choose a case —</option>
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {caseLabel(c)}
                    {c.petitioner_name ? ` · ${c.petitioner_name}` : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">
              Preview (first 200 chars)
            </label>
            <div className="rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-xs text-slate-600 font-mono leading-relaxed">
              {translated.slice(0, 200)}
              {translated.length > 200 ? "…" : ""}
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              {error}
            </div>
          )}

          {saved && (
            <div className="flex items-center gap-2 rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-700">
              <CheckCircle2 className="h-4 w-4" />
              Note saved to case notebook!
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t px-5 py-4">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!selectedCaseId || saving || saved}
            onClick={handleSave}
          >
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : saved ? (
              <>
                <CheckCircle2 className="mr-2 h-4 w-4" />
                Saved!
              </>
            ) : (
              <>
                <NotebookPen className="mr-2 h-4 w-4" />
                Save to notebook
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Action bar ─────────────────────────────────────────────────────────────

interface ActionBarProps {
  translated: string;
  direction: TranslateDirection;
  title: string;
  token: string | null;
  onCopy: () => void;
  copied: boolean;
}

function ActionBar({
  translated,
  direction,
  title,
  token,
  onCopy,
  copied,
}: ActionBarProps) {
  const [exportLoading, setExportLoading] = useState(false);
  const [showAddToCase, setShowAddToCase] = useState(false);

  async function handleExport(fmt: "pdf" | "docx") {
    setExportLoading(true);
    try {
      const blob = await exportTranslation(
        translated,
        title,
        direction,
        fmt,
        token
      );
      triggerDownload(blob, `${title}_${direction}.${fmt}`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Export failed.");
    } finally {
      setExportLoading(false);
    }
  }

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap">
        <Button variant="outline" size="sm" onClick={onCopy}>
          {copied ? (
            <>
              <CheckCircle2 className="mr-2 h-4 w-4 text-green-500" />
              Copied!
            </>
          ) : (
            <>
              <Copy className="mr-2 h-4 w-4" />
              Copy
            </>
          )}
        </Button>

        <ExportMenu
          disabled={false}
          onExport={handleExport}
          loading={exportLoading}
        />

        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAddToCase(true)}
        >
          <FolderOpen className="mr-2 h-4 w-4" />
          Add to Case
        </Button>
      </div>

      {showAddToCase && (
        <AddToCaseModal
          translated={translated}
          direction={direction}
          token={token}
          onClose={() => setShowAddToCase(false)}
        />
      )}
    </>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function TranslatePage() {
  const { token } = useAuth();

  // Direction state
  const [autoDetect, setAutoDetect] = useState(false);
  const [direction, setDirection] = useState<TranslateDirection>("en_to_ml");
  const [activeTab, setActiveTab] = useState<Tab>("text");

  // Text-mode state
  const [inputText, setInputText] = useState("");
  const [textResult, setTextResult] = useState<TranslateTextResponse | null>(
    null
  );
  const [textLoading, setTextLoading] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [textCopied, setTextCopied] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const streamAbortRef = useRef<(() => void) | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Document-mode state
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docResult, setDocResult] = useState<TranslateDocumentResponse | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docCopied, setDocCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Streaming state for document translation
  const [docStreamingText, setDocStreamingText] = useState("");
  const [docStreamChunk, setDocStreamChunk] = useState(0);   // chunks done so far
  const [docStreamTotal, setDocStreamTotal] = useState(0);   // total chunks
  const [docStreamPhase, setDocStreamPhase] = useState<"idle" | "extracting" | "translating">("idle");
  const docStreamAbortRef = useRef<(() => void) | null>(null);
  const docAccumulatedRef = useRef<string>("");
  const [docFileUrl, setDocFileUrl] = useState<string | null>(null);

  // For display: use resolved direction from result, or the manual selection
  const displayDirection: TranslateDirection =
    (textResult?.direction as TranslateDirection) ?? direction;
  const { from, to } = directionLabel(displayDirection);

  // Cleanup stream on unmount
  useEffect(() => {
    return () => {
      streamAbortRef.current?.();
    };
  }, []);

  function toggleDirection() {
    if (autoDetect) return;
    setDirection((d) => (d === "en_to_ml" ? "ml_to_en" : "en_to_ml"));
    setTextResult(null);
    setDocResult(null);
    setTextError(null);
    setDocError(null);
    setStreamingText("");
  }

  function toggleAutoDetect() {
    setAutoDetect((v) => !v);
    setTextResult(null);
    setStreamingText("");
    setTextError(null);
  }

  // ── Text translation with streaming (Task 4) ─────────────────────────────

  function handleTranslateText() {
    if (!inputText.trim() || textLoading) return;

    streamAbortRef.current?.();
    streamAbortRef.current = null;

    setTextLoading(true);
    setIsStreaming(true);
    setTextError(null);
    setTextResult(null);
    setStreamingText("");

    const dir: TranslateDirectionInput = autoDetect ? "auto" : direction;

    const abort = translateTextStream(
      inputText,
      dir,
      token,
      (chunk) => {
        setStreamingText((prev) => prev + chunk);
      },
      (done) => {
        setIsStreaming(false);
        setTextLoading(false);
        streamAbortRef.current = null;
        const resolved = done.direction as TranslateDirection;
        // Update manual direction pill to match detected direction
        if (autoDetect) setDirection(resolved);
        setTextResult({
          translated: done.full_text,
          direction: resolved,
          glossary_hits: done.glossary_hits,
          warnings: done.warnings,
          char_count: done.char_count,
          glossary_terms: done.glossary_terms,
        });
        setStreamingText("");
      },
      (err) => {
        setIsStreaming(false);
        setTextLoading(false);
        streamAbortRef.current = null;
        setTextError(err);
        setStreamingText("");
      }
    );

    streamAbortRef.current = abort;
  }

  // Ctrl+Enter / Cmd+Enter shortcut (Task 7)
  const handleTextareaKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        handleTranslateText();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [inputText, textLoading, autoDetect, direction, token]
  );

  async function copyText() {
    const text = textResult?.translated ?? streamingText;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setTextCopied(true);
    setTimeout(() => setTextCopied(false), 2000);
  }

  // ── Document translation ──────────────────────────────────────────────────

  // Create / revoke object URL for document preview
  useEffect(() => {
    if (!docFile) { setDocFileUrl(null); return; }
    const url = URL.createObjectURL(docFile);
    setDocFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [docFile]);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0] ?? null;
    if (!file) return;
    if (
      !ALLOWED_TYPES.includes(file.type) &&
      !file.name.match(/\.(pdf|docx|doc|txt)$/i)
    ) {
      setDocError("Unsupported file type. Please upload a PDF, DOCX, or TXT.");
      return;
    }
    setDocFile(file);
    setDocResult(null);
    setDocError(null);
    setDocStreamingText("");
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0] ?? null;
    if (!file) return;
    if (
      !ALLOWED_TYPES.includes(file.type) &&
      !file.name.match(/\.(pdf|docx|doc|txt)$/i)
    ) {
      setDocError("Unsupported file type.");
      return;
    }
    setDocFile(file);
    setDocResult(null);
    setDocError(null);
    setDocStreamingText("");
  }

  function handleTranslateDoc() {
    if (!docFile || docLoading) return;

    // Abort any previous stream
    docStreamAbortRef.current?.();
    docStreamAbortRef.current = null;

    setDocLoading(true);
    setDocError(null);
    setDocResult(null);
    setDocStreamingText("");
    setDocStreamChunk(0);
    setDocStreamTotal(0);
    setDocStreamPhase("extracting");
    docAccumulatedRef.current = "";

    const abort = translateDocumentStream(
      docFile,
      direction,
      token,
      // onExtracted — OCR done, chunks known
      (totalChunks, _charCount) => {
        setDocStreamTotal(totalChunks);
        setDocStreamPhase("translating");
      },
      // onChunk — one translated chunk arrived
      (_index, _total, text, _failed) => {
        docAccumulatedRef.current = docAccumulatedRef.current
          ? docAccumulatedRef.current + "\n\n" + text
          : text;
        setDocStreamChunk((n) => n + 1);
        setDocStreamingText(docAccumulatedRef.current);
      },
      // onDone — all chunks done
      (result: TranslateDocumentStreamDoneEvent) => {
        setDocLoading(false);
        setDocStreamPhase("idle");
        docStreamAbortRef.current = null;
        setDocResult({
          translated: docAccumulatedRef.current,
          direction: result.direction,
          filename: result.filename,
          mime_type: docFile.type || "application/octet-stream",
          chunks: result.total_chunks,
          glossary_hits: result.glossary_hits,
          warnings: result.warnings,
          char_count: result.char_count,
        });
        setDocStreamingText("");
      },
      // onError
      (err) => {
        setDocLoading(false);
        setDocStreamPhase("idle");
        docStreamAbortRef.current = null;
        docAccumulatedRef.current = "";
        setDocError(err);
        setDocStreamingText("");
      }
    );

    docStreamAbortRef.current = abort;
  }

  // Cleanup stream on unmount / file change
  useEffect(() => {
    return () => { docStreamAbortRef.current?.(); };
  }, []);

  async function copyDoc() {
    if (!docResult) return;
    await navigator.clipboard.writeText(docResult.translated);
    setDocCopied(true);
    setTimeout(() => setDocCopied(false), 2000);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Languages className="h-6 w-6 text-indigo-600" />
          Legal Translator
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Translate legal documents and text between English and Malayalam.
          Case numbers, act citations, and legal entities are preserved exactly.
        </p>
      </div>

      {/* Direction controls */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Auto-detect toggle (Task 3) */}
        <button
          onClick={toggleAutoDetect}
          className={cn(
            "flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium border transition-colors",
            autoDetect
              ? "bg-indigo-600 text-white border-indigo-600"
              : "bg-white text-slate-500 border-slate-200 hover:border-indigo-300 hover:text-indigo-600"
          )}
          title="Let the backend detect the source language automatically"
        >
          <Scan className="h-3.5 w-3.5" />
          Auto-detect
        </button>

        {/* Language pills + swap button */}
        <span
          className={cn(
            "rounded-full px-3 py-1 text-sm font-medium",
            autoDetect ? "opacity-40" : "",
            !autoDetect && displayDirection === "en_to_ml"
              ? "bg-indigo-100 text-indigo-700"
              : "bg-slate-100 text-slate-500"
          )}
        >
          English
        </span>
        <button
          onClick={toggleDirection}
          disabled={autoDetect}
          className={cn(
            "flex items-center justify-center rounded-full bg-white border border-slate-200 p-2 shadow-sm transition-colors",
            autoDetect
              ? "opacity-40 cursor-not-allowed"
              : "hover:bg-slate-50"
          )}
          title={
            autoDetect
              ? "Disable auto-detect to switch manually"
              : "Swap languages"
          }
        >
          <ArrowLeftRight className="h-4 w-4 text-slate-600" />
        </button>
        <span
          className={cn(
            "rounded-full px-3 py-1 text-sm font-medium",
            autoDetect ? "opacity-40" : "",
            !autoDetect && displayDirection === "ml_to_en"
              ? "bg-indigo-100 text-indigo-700"
              : "bg-slate-100 text-slate-500"
          )}
        >
          Malayalam
        </span>

        {autoDetect ? (
          <span className="ml-1 text-xs text-indigo-500 font-medium">
            Direction detected automatically from text
          </span>
        ) : (
          <span className="ml-1 text-xs text-slate-400">
            Translating:{" "}
            <strong className="text-slate-600">
              {from} → {to}
            </strong>
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {(["text", "document"] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === tab
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            )}
          >
            {tab === "text" ? (
              <span className="flex items-center gap-1.5">
                <FileText className="h-4 w-4" /> Text
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <Upload className="h-4 w-4" /> Document
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Text tab ── */}
      {activeTab === "text" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input card */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {autoDetect ? "Source text" : `${from} text`}
              </CardTitle>
              <CardDescription>
                Paste legal text · max 15,000 characters · Ctrl+Enter to translate
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                ref={textareaRef}
                value={inputText}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  setInputText(e.target.value)
                }
                onKeyDown={handleTextareaKeyDown}
                placeholder={
                  autoDetect
                    ? "Paste English or Malayalam legal text — direction is auto-detected…"
                    : `Paste ${from.toLowerCase()} legal text here…`
                }
                className="w-full min-h-[260px] resize-y rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 placeholder:text-slate-400"
                maxLength={15000}
              />
              <div className="flex items-center justify-between">
                {/* Live char count with colour warning (Task 7) */}
                <span
                  className={cn(
                    "text-xs tabular-nums",
                    inputText.length >= 14000
                      ? "text-red-500 font-semibold"
                      : inputText.length >= 12000
                      ? "text-amber-500 font-medium"
                      : "text-slate-400"
                  )}
                >
                  {inputText.length.toLocaleString()} / 15,000
                </span>
                <Button
                  onClick={handleTranslateText}
                  disabled={!inputText.trim() || textLoading}
                  size="sm"
                >
                  {textLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {isStreaming ? "Streaming…" : "Translating…"}
                    </>
                  ) : (
                    <>
                      <Zap className="mr-2 h-4 w-4" />
                      Translate
                    </>
                  )}
                </Button>
              </div>
              {textError && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  {textError}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Output card */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {textResult
                  ? `${to} translation`
                  : autoDetect
                  ? "Translation"
                  : `${to} translation`}
              </CardTitle>
              <CardDescription>
                {textResult
                  ? `Complete · ${textResult.glossary_hits} glossary term${textResult.glossary_hits !== 1 ? "s" : ""} applied`
                  : isStreaming
                  ? "Streaming from KHC legal model…"
                  : "Translation will appear here"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="min-h-[260px] rounded-md border border-slate-200 bg-slate-50 p-3">
                {/* Live streaming preview */}
                {isStreaming && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-xs text-indigo-500 font-medium">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Translating with KHC glossary…
                    </div>
                    {streamingText ? (
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-500">
                        {streamingText}
                      </p>
                    ) : (
                      <div className="flex items-center justify-center min-h-[200px]">
                        <div className="flex gap-1.5">
                          {[0, 1, 2].map((i) => (
                            <span
                              key={i}
                              className="block h-2 w-2 rounded-full bg-indigo-300 animate-bounce"
                              style={{ animationDelay: `${i * 0.15}s` }}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Final result with glossary highlighting */}
                {textResult && !isStreaming && (
                  <GlossaryHighlight
                    text={textResult.translated}
                    terms={textResult.glossary_terms ?? []}
                    direction={textResult.direction as TranslateDirection}
                  />
                )}

                {/* Empty state */}
                {!textLoading && !textResult && !isStreaming && (
                  <p className="text-sm text-slate-400 italic">
                    Enter text and click Translate — or press{" "}
                    <kbd className="rounded border border-slate-200 bg-white px-1 py-0.5 text-xs font-mono">
                      Ctrl+Enter
                    </kbd>{" "}
                    — to see the result here.
                  </p>
                )}
              </div>

              {textResult && !isStreaming && (
                <>
                  <ActionBar
                    translated={textResult.translated}
                    direction={textResult.direction as TranslateDirection}
                    title="Legal Translation"
                    token={token}
                    onCopy={copyText}
                    copied={textCopied}
                  />
                  <QualityPanel
                    glossaryHits={textResult.glossary_hits}
                    warnings={textResult.warnings}
                    charCount={textResult.char_count}
                  />
                  {(textResult.glossary_terms ?? []).length > 0 && (
                    <p className="text-xs text-slate-400 flex items-center gap-1.5">
                      <span className="inline-block w-5 border-b border-dotted border-indigo-400" />
                      Underlined terms are glossary matches — hover to see the
                      source.
                    </p>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Document tab ── */}
      {activeTab === "document" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="flex flex-col">
            <CardHeader className="pb-3">
              {docFile ? (
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="text-base truncate">{docFile.name}</CardTitle>
                    <CardDescription>{formatBytes(docFile.size)}</CardDescription>
                  </div>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="shrink-0 flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50 transition-colors"
                    title="Choose a different file"
                  >
                    <Upload className="h-3 w-3" />
                    Change
                  </button>
                </div>
              ) : (
                <>
                  <CardTitle className="text-base">Upload document</CardTitle>
                  <CardDescription>
                    Supported formats: PDF, DOCX, TXT · Max 10 MB
                  </CardDescription>
                </>
              )}
            </CardHeader>
            <CardContent className="flex flex-col gap-4 flex-1">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                className="hidden"
                onChange={handleFileChange}
              />

              {docFile && docFileUrl ? (
                /* ── Document preview ──────────────────────────────── */
                docFile.type === "application/pdf" || docFile.name.endsWith(".pdf") ? (
                  <iframe
                    src={docFileUrl}
                    className="w-full rounded-md border border-slate-200 bg-white"
                    style={{ height: "420px" }}
                    title="Document preview"
                  />
                ) : (
                  /* DOCX / TXT — browsers can't render these natively */
                  <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-slate-200 bg-slate-50 text-slate-400"
                    style={{ height: "420px" }}>
                    <FileText className="h-10 w-10" />
                    <p className="text-sm text-center">
                      Preview not available for {docFile.name.split(".").pop()?.toUpperCase()} files.
                      <br />
                      <span className="text-xs">The document will be translated as-is.</span>
                    </p>
                  </div>
                )
              ) : (
                /* ── Upload drop zone ──────────────────────────────── */
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className="flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-slate-200 bg-slate-50 p-8 cursor-pointer hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
                  style={{ minHeight: "260px" }}
                >
                  <Upload className="h-8 w-8 text-slate-400" />
                  <div className="text-center">
                    <p className="text-sm font-medium text-slate-700">
                      Drag & drop or click to upload
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      PDF, DOCX, or TXT
                    </p>
                  </div>
                </div>
              )}

              <Button
                onClick={handleTranslateDoc}
                disabled={!docFile || docLoading}
                className="w-full"
              >
                {docLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Translating document…
                  </>
                ) : (
                  <>
                    <Languages className="mr-2 h-4 w-4" />
                    Translate document ({from} → {to})
                  </>
                )}
              </Button>

              {docError && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  {docError}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Translated document</CardTitle>
              <CardDescription>
                {docResult
                  ? `${docResult.filename} — ${docResult.chunks} chunk${docResult.chunks !== 1 ? "s" : ""} processed`
                  : docStreamPhase === "extracting"
                  ? "Running OCR on document…"
                  : docStreamPhase === "translating" && docStreamTotal > 0
                  ? `Translating chunk ${docStreamChunk} of ${docStreamTotal}…`
                  : "Upload and translate a document to see the result"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Progress bar — visible while streaming */}
              {docLoading && docStreamTotal > 0 && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="flex items-center gap-1.5">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {docStreamPhase === "extracting"
                        ? "Extracting text with OCR…"
                        : `Chunk ${docStreamChunk} / ${docStreamTotal}`}
                    </span>
                    <span className="tabular-nums">
                      {docStreamTotal > 0
                        ? Math.round((docStreamChunk / docStreamTotal) * 100)
                        : 0}%
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-300"
                      style={{
                        width: docStreamTotal > 0
                          ? `${Math.round((docStreamChunk / docStreamTotal) * 100)}%`
                          : "0%",
                      }}
                    />
                  </div>
                </div>
              )}
              {/* Extracting spinner (before first chunk) */}
              {docLoading && docStreamPhase === "extracting" && (
                <div className="flex h-full min-h-[40px] items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running OCR — this may take a moment for scanned PDFs…
                </div>
              )}
              <div className="min-h-[260px] max-h-[400px] overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
                {/* Live streaming text */}
                {docStreamingText ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                    {docStreamingText}
                    {docLoading && (
                      <span className="inline-block ml-1 h-3.5 w-0.5 bg-indigo-400 animate-pulse" />
                    )}
                  </p>
                ) : docLoading && docStreamPhase !== "idle" ? (
                  <div className="flex h-full min-h-[220px] items-center justify-center">
                    <div className="flex gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          className="block h-2 w-2 rounded-full bg-indigo-300 animate-bounce"
                          style={{ animationDelay: `${i * 0.15}s` }}
                        />
                      ))}
                    </div>
                  </div>
                ) : docResult ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
                    {docResult.translated}
                  </p>
                ) : (
                  <p className="text-sm text-slate-400 italic">
                    Translated text will appear here.
                  </p>
                )}
              </div>
              {docResult && (
                <>
                  <ActionBar
                    translated={docResult.translated}
                    direction={direction}
                    title={
                      docResult.filename.replace(/\.[^.]+$/, "") ||
                      "Document Translation"
                    }
                    token={token}
                    onCopy={copyDoc}
                    copied={docCopied}
                  />
                  <QualityPanel
                    glossaryHits={docResult.glossary_hits}
                    warnings={docResult.warnings}
                    charCount={docResult.char_count}
                    chunks={docResult.chunks}
                  />
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Footer */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-500 flex gap-2">
        <BookOpen className="h-4 w-4 shrink-0 text-indigo-400 mt-0.5" />
        <p>
          The translator uses a built-in legal glossary of{" "}
          <strong>6,000+ English–Malayalam terms</strong> with deterministic
          placeholder protection. Case numbers, section references, act names,
          dates, and Latin phrases are locked before translation and restored
          verbatim afterwards. Glossary matches are{" "}
          <span className="border-b border-dotted border-indigo-400 text-indigo-600">
            underlined
          </span>{" "}
          in the output — hover to see the source term.
        </p>
      </div>
    </div>
  );
}
