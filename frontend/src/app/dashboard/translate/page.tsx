"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  translateText,
  translateDocument,
  exportTranslation,
  openCaseNotebook,
  createNotebookNote,
  getCases,
  TranslateDirection,
  TranslateTextResponse,
  TranslateDocumentResponse,
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
  Upload,
  X,
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

// ── Quality panel ──────────────────────────────────────────────────────────

interface QualityPanelProps {
  glossaryHits: number;
  warnings: string[];
  charCount: number;
  chunks?: number;
}

function QualityPanel({ glossaryHits, warnings, charCount, chunks }: QualityPanelProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3 text-sm">
      <p className="font-medium text-slate-700 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-indigo-500" />
        Translation Quality
      </p>
      <div className="grid grid-cols-2 gap-3 text-slate-600">
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide">Glossary matches</p>
          <p className="font-semibold text-indigo-600">{glossaryHits}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide">Characters</p>
          <p className="font-semibold">{charCount.toLocaleString()}</p>
        </div>
        {chunks !== undefined && (
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wide">Chunks processed</p>
            <p className="font-semibold">{chunks}</p>
          </div>
        )}
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-wide">Warnings</p>
          <p className={cn("font-semibold", warnings.length > 0 ? "text-amber-600" : "text-green-600")}>
            {warnings.length === 0 ? "None" : warnings.length}
          </p>
        </div>
      </div>
      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((w, i) => (
            <p key={i} className="flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 rounded px-2 py-1">
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
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
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
            onClick={() => { onExport("pdf"); setOpen(false); }}
          >
            <FileText className="h-4 w-4 text-red-500" />
            Download PDF
          </button>
          <button
            className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 text-slate-700"
            onClick={() => { onExport("docx"); setOpen(false); }}
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

function AddToCaseModal({ translated, direction, token, onClose }: AddToCaseModalProps) {
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
      // Build ProseMirror JSON from plain paragraphs
      const paragraphs = translated
        .split("\n\n")
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p) => ({ type: "paragraph", content: [{ type: "text", text: p }] }));
      const content_json = { type: "doc", content: paragraphs };

      const notebook = await openCaseNotebook(selectedCaseId, token);
      await createNotebookNote(
        notebook.id,
        { title: noteTitle, content_text: translated, content_json },
        token
      );
      setSaved(true);
      setTimeout(onClose, 1500);
    } catch (err: any) {
      setError(err.message ?? "Failed to save note.");
    } finally {
      setSaving(false);
    }
  }

  const caseLabel = (c: CaseOption) =>
    [c.case_number, c.efiling_number].filter(Boolean).join(" · ") || c.id;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div className="flex items-center gap-2">
            <NotebookPen className="h-5 w-5 text-indigo-600" />
            <h2 className="text-base font-semibold text-slate-800">Add to Case Notebook</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Note title</label>
            <input
              type="text"
              value={noteTitle}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNoteTitle(e.target.value)}
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={200}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Select case</label>
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
              {translated.slice(0, 200)}{translated.length > 200 ? "…" : ""}
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

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t px-5 py-4">
          <Button variant="outline" size="sm" onClick={onClose} disabled={saving}>
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

function ActionBar({ translated, direction, title, token, onCopy, copied }: ActionBarProps) {
  const [exportLoading, setExportLoading] = useState(false);
  const [showAddToCase, setShowAddToCase] = useState(false);

  async function handleExport(fmt: "pdf" | "docx") {
    setExportLoading(true);
    try {
      const blob = await exportTranslation(translated, title, direction, fmt, token);
      triggerDownload(blob, `${title}_${direction}.${fmt}`);
    } catch (err: any) {
      alert(err.message ?? "Export failed.");
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

        <Button variant="outline" size="sm" onClick={() => setShowAddToCase(true)}>
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

  const [direction, setDirection] = useState<TranslateDirection>("en_to_ml");
  const [activeTab, setActiveTab] = useState<Tab>("text");

  const [inputText, setInputText] = useState("");
  const [textResult, setTextResult] = useState<TranslateTextResponse | null>(null);
  const [textLoading, setTextLoading] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [textCopied, setTextCopied] = useState(false);

  const [docFile, setDocFile] = useState<File | null>(null);
  const [docResult, setDocResult] = useState<TranslateDocumentResponse | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [docCopied, setDocCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { from, to } = directionLabel(direction);

  function toggleDirection() {
    setDirection((d) => (d === "en_to_ml" ? "ml_to_en" : "en_to_ml"));
    setTextResult(null);
    setDocResult(null);
    setTextError(null);
    setDocError(null);
  }

  async function handleTranslateText() {
    if (!inputText.trim()) return;
    setTextLoading(true);
    setTextError(null);
    setTextResult(null);
    try {
      setTextResult(await translateText(inputText, direction, token));
    } catch (err: any) {
      setTextError(err.message ?? "Translation failed.");
    } finally {
      setTextLoading(false);
    }
  }

  async function copyText() {
    if (!textResult) return;
    await navigator.clipboard.writeText(textResult.translated);
    setTextCopied(true);
    setTimeout(() => setTextCopied(false), 2000);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0] ?? null;
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type) && !file.name.match(/\.(pdf|docx|doc|txt)$/i)) {
      setDocError("Unsupported file type. Please upload a PDF, DOCX, or TXT file.");
      return;
    }
    setDocFile(file);
    setDocResult(null);
    setDocError(null);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0] ?? null;
    if (!file) return;
    if (!ALLOWED_TYPES.includes(file.type) && !file.name.match(/\.(pdf|docx|doc|txt)$/i)) {
      setDocError("Unsupported file type.");
      return;
    }
    setDocFile(file);
    setDocResult(null);
    setDocError(null);
  }

  async function handleTranslateDoc() {
    if (!docFile) return;
    setDocLoading(true);
    setDocError(null);
    setDocResult(null);
    try {
      setDocResult(await translateDocument(docFile, direction, token));
    } catch (err: any) {
      setDocError(err.message ?? "Document translation failed.");
    } finally {
      setDocLoading(false);
    }
  }

  async function copyDoc() {
    if (!docResult) return;
    await navigator.clipboard.writeText(docResult.translated);
    setDocCopied(true);
    setTimeout(() => setDocCopied(false), 2000);
  }

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

      {/* Direction toggle */}
      <div className="flex items-center gap-3">
        <span className={cn("rounded-full px-3 py-1 text-sm font-medium",
          direction === "en_to_ml" ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-500")}>
          English
        </span>
        <button
          onClick={toggleDirection}
          className="flex items-center justify-center rounded-full bg-white border border-slate-200 p-2 shadow-sm hover:bg-slate-50 transition-colors"
          title="Swap languages"
        >
          <ArrowLeftRight className="h-4 w-4 text-slate-600" />
        </button>
        <span className={cn("rounded-full px-3 py-1 text-sm font-medium",
          direction === "ml_to_en" ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-500")}>
          Malayalam
        </span>
        <span className="ml-1 text-xs text-slate-400">
          Translating: <strong className="text-slate-600">{from} → {to}</strong>
        </span>
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
              <span className="flex items-center gap-1.5"><FileText className="h-4 w-4" /> Text</span>
            ) : (
              <span className="flex items-center gap-1.5"><Upload className="h-4 w-4" /> Document</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Text tab ── */}
      {activeTab === "text" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{from} text</CardTitle>
              <CardDescription>Paste your legal text below (max 15 000 characters)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                value={inputText}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInputText(e.target.value)}
                placeholder={`Paste ${from.toLowerCase()} legal text here…`}
                className="w-full min-h-[260px] resize-y rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 placeholder:text-slate-400"
                maxLength={15000}
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  {inputText.length.toLocaleString()} / 15,000 characters
                </span>
                <Button onClick={handleTranslateText} disabled={!inputText.trim() || textLoading} size="sm">
                  {textLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Translating…</> : <><Languages className="mr-2 h-4 w-4" />Translate</>}
                </Button>
              </div>
              {textError && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />{textError}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{to} translation</CardTitle>
              <CardDescription>{textResult ? "Translation complete" : "Translation will appear here"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="min-h-[260px] rounded-md border border-slate-200 bg-slate-50 p-3">
                {textLoading ? (
                  <div className="flex h-full min-h-[220px] items-center justify-center">
                    <div className="text-center space-y-2 text-slate-400">
                      <Loader2 className="h-8 w-8 animate-spin mx-auto" />
                      <p className="text-sm">Translating with legal glossary…</p>
                    </div>
                  </div>
                ) : textResult ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{textResult.translated}</p>
                ) : (
                  <p className="text-sm text-slate-400 italic">Enter text and click Translate to see the result here.</p>
                )}
              </div>
              {textResult && (
                <>
                  <ActionBar
                    translated={textResult.translated}
                    direction={direction}
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
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Document tab ── */}
      {activeTab === "document" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Upload document</CardTitle>
              <CardDescription>Supported formats: PDF, DOCX, TXT · Max 10 MB</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors",
                  docFile ? "border-indigo-300 bg-indigo-50" : "border-slate-200 bg-slate-50 hover:border-indigo-300 hover:bg-indigo-50"
                )}
              >
                <Upload className="h-8 w-8 text-slate-400" />
                {docFile ? (
                  <div className="text-center">
                    <p className="text-sm font-medium text-indigo-700">{docFile.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{formatBytes(docFile.size)}</p>
                  </div>
                ) : (
                  <div className="text-center">
                    <p className="text-sm font-medium text-slate-700">Drag & drop or click to upload</p>
                    <p className="text-xs text-slate-400 mt-0.5">PDF, DOCX, or TXT</p>
                  </div>
                )}
              </div>
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.txt" className="hidden" onChange={handleFileChange} />
              <Button onClick={handleTranslateDoc} disabled={!docFile || docLoading} className="w-full">
                {docLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Translating document…</> : <><Languages className="mr-2 h-4 w-4" />Translate document ({from} → {to})</>}
              </Button>
              {docError && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />{docError}
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
                  : "Upload and translate a document to see the result"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="min-h-[260px] max-h-[400px] overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
                {docLoading ? (
                  <div className="flex h-full min-h-[220px] items-center justify-center">
                    <div className="text-center space-y-2 text-slate-400">
                      <Loader2 className="h-8 w-8 animate-spin mx-auto" />
                      <p className="text-sm">Translating document chunks…</p>
                      <p className="text-xs">Large documents may take a moment</p>
                    </div>
                  </div>
                ) : docResult ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{docResult.translated}</p>
                ) : (
                  <p className="text-sm text-slate-400 italic">Translated text will appear here.</p>
                )}
              </div>
              {docResult && (
                <>
                  <ActionBar
                    translated={docResult.translated}
                    direction={direction}
                    title={docResult.filename.replace(/\.[^.]+$/, "") || "Document Translation"}
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
          <strong>1000+ English–Malayalam terms</strong> to ensure consistent translation of legal vocabulary.
          Case numbers, section references, act names, dates, and Latin phrases are automatically preserved
          verbatim and never altered by the AI model.
        </p>
      </div>
    </div>
  );
}
