"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  compareDocuments,
  downloadComparisonMemo,
  type ComparisonResult,
  type DiffBlock,
} from "@/lib/api";
import {
  FileText,
  Upload,
  GitCompare,
  Eye,
  BookOpen,
  Hash,
  Download,
  AlertTriangle,
  CheckCircle2,
  MinusCircle,
  PlusCircle,
  RefreshCw,
  Languages,
  Gavel,
  Calendar,
  DollarSign,
  Tag,
  ArrowRight,
  XCircle,
  Loader2,
  Info,
} from "lucide-react";

// ────────────────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────────────────

type ViewMode = "side-by-side" | "prayer-watch" | "legal-entities";
type OcrLanguage = "eng" | "mal" | "mal+eng";

interface UploadSlot {
  file: File | null;
  name: string;
  dragging: boolean;
}

// ────────────────────────────────────────────────────────────────────────────
// Helpers — legal-entity inline highlighter
// ────────────────────────────────────────────────────────────────────────────

const SECTION_RE =
  /(\bSection\s+\d+[A-Z]?(?:\([a-z0-9]+\))*(?:\s+(?:of\s+the\s+)?(?:Cr\.?P\.?C\.?|I\.?P\.?C\.?|C\.?P\.?C\.?|Evidence\s+Act|Kerala\b[^\s,]*))?|\bArticle\s+\d+[A-Z]?|\b(?:Order|Rule)\s+\d+[A-Z]?\s+Rule\s+\d+[A-Z]?)/gi;
const DATE_RE =
  /(\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b)/gi;
const CITATION_RE =
  /(\b(?:AIR|SCC|SCR|All|Bom|Mad|Cal|Del|Ker|MLJ|KLT|KLJ|KHC)\s*\d{4}\s*(?:SC|HC|SCC|[A-Z]{1,5})?\s*\d+\b|\b\d{4}\s+SCC\s+\d+\b|\bWP\s*\(?\s*C\s*\)?\s*No\.?\s*\d+\s*\/\s*\d{4}\b)/gi;
const AMOUNT_RE =
  /((?:Rs\.?|₹|INR)\s*[\d,]+(?:\.\d{1,2})?|\b[\d,]+(?:\.\d{1,2})?\s*(?:lakhs?|crores?|rupees?)\b)/gi;

function highlightLegalEntities(text: string): React.ReactNode[] {
  if (!text) return [];

  // Build a combined regex with named groups simulation via alternation
  const ALL_RE = new RegExp(
    `(${SECTION_RE.source})|(${DATE_RE.source})|(${CITATION_RE.source})|(${AMOUNT_RE.source})`,
    "gi"
  );

  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = ALL_RE.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));

    const matched = m[0];
    const isSection = SECTION_RE.test(matched);
    const isDate = !isSection && DATE_RE.test(matched);
    const isCitation = !isSection && !isDate && CITATION_RE.test(matched);
    const isAmount = !isSection && !isDate && !isCitation && AMOUNT_RE.test(matched);

    // Reset regex state
    SECTION_RE.lastIndex = 0;
    DATE_RE.lastIndex = 0;
    CITATION_RE.lastIndex = 0;
    AMOUNT_RE.lastIndex = 0;

    let cls = "";
    if (isSection) cls = "bg-violet-100 text-violet-800 rounded px-0.5 font-medium";
    else if (isDate) cls = "bg-sky-100 text-sky-700 rounded px-0.5 font-medium";
    else if (isCitation) cls = "bg-amber-100 text-amber-800 rounded px-0.5 font-medium";
    else if (isAmount) cls = "bg-emerald-100 text-emerald-800 rounded px-0.5 font-medium";

    nodes.push(
      <mark key={m.index} className={cls}>
        {matched}
      </mark>
    );
    last = m.index + matched.length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

// Word-level diff renderer
function WordDiffText({
  wordDiff,
  side,
}: {
  wordDiff: Array<{ op: string; left: string; right: string }>;
  side: "left" | "right";
}) {
  return (
    <>
      {wordDiff.map((chunk, i) => {
        if (chunk.op === "equal") {
          return <span key={i}>{side === "left" ? chunk.left : chunk.right} </span>;
        }
        if (chunk.op === "delete" && side === "left" && chunk.left) {
          return (
            <span key={i} className="bg-red-200 text-red-900 rounded px-0.5 line-through">
              {chunk.left}{" "}
            </span>
          );
        }
        if (chunk.op === "insert" && side === "right" && chunk.right) {
          return (
            <span key={i} className="bg-green-200 text-green-900 rounded px-0.5">
              {chunk.right}{" "}
            </span>
          );
        }
        if (chunk.op === "replace") {
          const text = side === "left" ? chunk.left : chunk.right;
          if (!text) return null;
          return (
            <span
              key={i}
              className={
                side === "left"
                  ? "bg-red-100 text-red-900 rounded px-0.5 line-through"
                  : "bg-green-100 text-green-900 rounded px-0.5"
              }
            >
              {text}{" "}
            </span>
          );
        }
        return null;
      })}
    </>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Sub-components
// ────────────────────────────────────────────────────────────────────────────

function DropZone({
  slot,
  label,
  docLabel,
  onChange,
  onNameChange,
  onDragChange,
}: {
  slot: UploadSlot;
  label: string;
  docLabel: string;
  onChange: (file: File) => void;
  onNameChange: (n: string) => void;
  onDragChange: (v: boolean) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      onDragChange(false);
      const f = e.dataTransfer.files[0];
      if (f) onChange(f);
    },
    [onChange, onDragChange]
  );

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
        {label}
      </label>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          onDragChange(true);
        }}
        onDragLeave={() => onDragChange(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 cursor-pointer transition-all min-h-[120px]
          ${slot.dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:border-indigo-400 hover:bg-slate-50"}
          ${slot.file ? "border-indigo-300 bg-indigo-50/50" : ""}`}
      >
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff,.bmp"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onChange(f);
          }}
        />
        {slot.file ? (
          <>
            <FileText className="h-7 w-7 text-indigo-500" />
            <p className="text-sm font-medium text-indigo-700 text-center break-all">
              {slot.file.name}
            </p>
            <p className="text-xs text-slate-400">
              {(slot.file.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </>
        ) : (
          <>
            <Upload className="h-7 w-7 text-slate-300" />
            <p className="text-sm text-slate-500 text-center">
              Drop {docLabel} here or{" "}
              <span className="text-indigo-600 font-medium">browse</span>
            </p>
            <p className="text-xs text-slate-400">PDF · DOCX · PNG · JPG · TXT (max 30 MB)</p>
          </>
        )}
      </div>

      <input
        type="text"
        placeholder={`${docLabel} label (optional)`}
        value={slot.name}
        onChange={(e) => onNameChange(e.target.value)}
        className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Diff Block Renderers
// ────────────────────────────────────────────────────────────────────────────

function BlockRow({ block }: { block: DiffBlock }) {
  const { type, left_text, right_text, word_diff, is_substantive } = block;

  const leftBg =
    type === "delete"
      ? "bg-red-50 border-l-4 border-red-400"
      : type === "replace"
      ? "bg-amber-50 border-l-4 border-amber-400"
      : type === "equal"
      ? ""
      : "bg-slate-50";

  const rightBg =
    type === "insert"
      ? "bg-green-50 border-l-4 border-green-400"
      : type === "replace"
      ? "bg-amber-50 border-l-4 border-amber-400"
      : type === "equal"
      ? ""
      : "bg-slate-50";

  const renderSide = (text: string, side: "left" | "right") => {
    if (!text) {
      return (
        <div className="text-slate-300 text-xs italic py-2 px-3 h-full flex items-center">
          (not present)
        </div>
      );
    }
    if (type === "replace" && word_diff && word_diff.length > 0) {
      return (
        <div className="text-sm leading-relaxed py-2 px-3 text-slate-700 whitespace-pre-wrap">
          <WordDiffText wordDiff={word_diff} side={side} />
        </div>
      );
    }
    if (type === "equal") {
      return (
        <div className="text-sm leading-relaxed py-2 px-3 text-slate-600 whitespace-pre-wrap">
          {text}
        </div>
      );
    }
    return (
      <div className="text-sm leading-relaxed py-2 px-3 text-slate-700 whitespace-pre-wrap">
        {highlightLegalEntities(text)}
      </div>
    );
  };

  return (
    <div className={`grid grid-cols-2 gap-0 border-b border-slate-100 ${is_substantive ? "ring-1 ring-amber-300 ring-inset" : ""}`}>
      {/* Left */}
      <div className={`min-h-[2.5rem] ${leftBg}`}>{renderSide(left_text, "left")}</div>
      {/* Divider */}
      <div className="border-l border-slate-200" />
      {/* Right */}
      <div className={`min-h-[2.5rem] ${rightBg} -ml-px`}>{renderSide(right_text, "right")}</div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Main Page
// ────────────────────────────────────────────────────────────────────────────

export default function DocComparePage() {
  const { user } = useAuth();
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;

  const [slotA, setSlotA] = useState<UploadSlot>({ file: null, name: "", dragging: false });
  const [slotB, setSlotB] = useState<UploadSlot>({ file: null, name: "", dragging: false });
  const [language, setLanguage] = useState<OcrLanguage>("eng");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("side-by-side");
  const [downloadingMemo, setDownloadingMemo] = useState(false);

  // Filter controls
  const [showEqual, setShowEqual] = useState(false);
  const [showOnlySubstantive, setShowOnlySubstantive] = useState(false);

  // Scroll sync
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncingRef = useRef(false);

  const syncScroll = useCallback((source: "left" | "right") => {
    if (syncingRef.current) return;
    syncingRef.current = true;
    const src = source === "left" ? leftRef.current : rightRef.current;
    const dst = source === "left" ? rightRef.current : leftRef.current;
    if (src && dst) {
      const ratio =
        src.scrollTop / (src.scrollHeight - src.clientHeight || 1);
      dst.scrollTop = ratio * (dst.scrollHeight - dst.clientHeight);
    }
    requestAnimationFrame(() => { syncingRef.current = false; });
  }, []);

  // ── Run comparison ────────────────────────────────────────────────────────

  const handleCompare = async () => {
    if (!slotA.file || !slotB.file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await compareDocuments(
        slotA.file,
        slotB.file,
        slotA.name || undefined,
        slotB.name || undefined,
        language,
        token!
      );
      setResult(data);
      setViewMode("side-by-side");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Comparison failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Download Memo ─────────────────────────────────────────────────────────

  const handleDownloadMemo = async () => {
    if (!result) return;
    setDownloadingMemo(true);
    try {
      await downloadComparisonMemo(result.comparison_id, result.doc_a_name, token!);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to generate memo.");
    } finally {
      setDownloadingMemo(false);
    }
  };

  // ── Filtered blocks ───────────────────────────────────────────────────────

  const filteredBlocks = result
    ? result.blocks.filter((b) => {
        if (!showEqual && b.type === "equal") return false;
        if (showOnlySubstantive && !b.is_substantive && b.type !== "equal") return false;
        return true;
      })
    : [];

  // ────────────────────────────────────────────────────────────────────────
  // Render
  // ────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-50">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <div className="flex-none bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-600 shadow-sm">
            <GitCompare className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Document Comparison AI</h1>
            <p className="text-sm text-slate-500">
              Semantic legal diffing · Prayer Watch · Bilingual OCR · Export Memo
            </p>
          </div>
        </div>
      </div>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-auto">
        <div className="max-w-screen-2xl mx-auto px-6 py-5 space-y-5">

          {/* ── Upload Panel ─────────────────────────────────────────────── */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <DropZone
                slot={slotA}
                label="Document A — Original"
                docLabel="original document"
                onChange={(f) => setSlotA((s) => ({ ...s, file: f, name: s.name || f.name }))}
                onNameChange={(n) => setSlotA((s) => ({ ...s, name: n }))}
                onDragChange={(v) => setSlotA((s) => ({ ...s, dragging: v }))}
              />
              <DropZone
                slot={slotB}
                label="Document B — Amended / New"
                docLabel="amended document"
                onChange={(f) => setSlotB((s) => ({ ...s, file: f, name: s.name || f.name }))}
                onNameChange={(n) => setSlotB((s) => ({ ...s, name: n }))}
                onDragChange={(v) => setSlotB((s) => ({ ...s, dragging: v }))}
              />
            </div>

            {/* Options row */}
            <div className="mt-4 flex flex-wrap items-center gap-4">
              {/* Language */}
              <div className="flex items-center gap-2">
                <Languages className="h-4 w-4 text-slate-400" />
                <label className="text-sm text-slate-600 font-medium">OCR Language:</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as OcrLanguage)}
                  className="text-sm border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                >
                  <option value="eng">English</option>
                  <option value="mal">Malayalam</option>
                  <option value="mal+eng">Malayalam + English</option>
                </select>
              </div>

              <div className="flex-1" />

              {/* Compare button */}
              <button
                onClick={handleCompare}
                disabled={!slotA.file || !slotB.file || loading}
                className="flex items-center gap-2 bg-violet-600 hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold px-6 py-2 rounded-lg shadow-sm transition-colors"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Comparing…
                  </>
                ) : (
                  <>
                    <GitCompare className="h-4 w-4" />
                    Compare Documents
                  </>
                )}
              </button>
            </div>

            {error && (
              <div className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                {error}
              </div>
            )}
          </div>

          {/* ── Results ──────────────────────────────────────────────────── */}
          {result && (
            <>
              {/* Summary bar */}
              <SummaryBar result={result} onDownloadMemo={handleDownloadMemo} downloadingMemo={downloadingMemo} />

              {/* View mode tabs */}
              <div className="flex gap-1 bg-white rounded-xl border border-slate-200 shadow-sm p-1">
                <TabBtn
                  active={viewMode === "side-by-side"}
                  icon={<Eye className="h-4 w-4" />}
                  label="Side-by-Side"
                  onClick={() => setViewMode("side-by-side")}
                />
                <TabBtn
                  active={viewMode === "prayer-watch"}
                  icon={<Gavel className="h-4 w-4" />}
                  label="Prayer Watch"
                  onClick={() => setViewMode("prayer-watch")}
                  badge={result.prayer_diff.filter((b) => b.type !== "equal").length || undefined}
                />
                <TabBtn
                  active={viewMode === "legal-entities"}
                  icon={<Hash className="h-4 w-4" />}
                  label="Legal Entities"
                  onClick={() => setViewMode("legal-entities")}
                  badge={
                    (result.legal_entity_changes.sections_added?.length || 0) +
                      (result.legal_entity_changes.sections_removed?.length || 0) +
                      (result.legal_entity_changes.citations_added?.length || 0) +
                      (result.legal_entity_changes.citations_removed?.length || 0) || undefined
                  }
                />
              </div>

              {/* ── Side-by-Side View ─────────────────────────────────── */}
              {viewMode === "side-by-side" && (
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                  {/* Toolbar */}
                  <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex-wrap">
                    <FilterToggle
                      active={showEqual}
                      label="Show unchanged"
                      onClick={() => setShowEqual((v) => !v)}
                    />
                    <FilterToggle
                      active={showOnlySubstantive}
                      label="Substantive only"
                      onClick={() => setShowOnlySubstantive((v) => !v)}
                    />
                    <div className="flex-1" />
                    <LegendItem color="bg-green-100 border-l-4 border-green-400" label="Added" />
                    <LegendItem color="bg-red-50 border-l-4 border-red-400" label="Deleted" />
                    <LegendItem color="bg-amber-50 border-l-4 border-amber-400" label="Changed" />
                    <div className="h-4 w-px bg-slate-200" />
                    <span className="text-xs text-violet-700 font-medium px-1.5 py-0.5 bg-violet-50 rounded">§ Section</span>
                    <span className="text-xs text-sky-700 font-medium px-1.5 py-0.5 bg-sky-50 rounded">📅 Date</span>
                    <span className="text-xs text-amber-700 font-medium px-1.5 py-0.5 bg-amber-50 rounded">⚖ Citation</span>
                    <span className="text-xs text-emerald-700 font-medium px-1.5 py-0.5 bg-emerald-50 rounded">₹ Amount</span>
                  </div>

                  {/* Column headers */}
                  <div className="grid grid-cols-2 bg-slate-800 text-white text-sm font-semibold">
                    <div className="px-4 py-2.5 flex items-center gap-2">
                      <MinusCircle className="h-4 w-4 text-red-400" />
                      {result.doc_a_name}
                    </div>
                    <div className="px-4 py-2.5 flex items-center gap-2 border-l border-slate-700">
                      <PlusCircle className="h-4 w-4 text-green-400" />
                      {result.doc_b_name}
                    </div>
                  </div>

                  {/* Sync-scroll diff body */}
                  <div
                    className="overflow-y-auto"
                    style={{ maxHeight: "65vh" }}
                    onScroll={() => syncScroll("left")}
                    ref={leftRef}
                  >
                    {filteredBlocks.length === 0 ? (
                      <div className="py-16 text-center text-slate-400 text-sm">
                        No blocks to display — try enabling "Show unchanged".
                      </div>
                    ) : (
                      filteredBlocks.map((block, idx) => (
                        <BlockRow key={idx} block={block} />
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* ── Prayer Watch ──────────────────────────────────────── */}
              {viewMode === "prayer-watch" && (
                <PrayerWatchPanel result={result} />
              )}

              {/* ── Legal Entities ────────────────────────────────────── */}
              {viewMode === "legal-entities" && (
                <LegalEntitiesPanel result={result} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Summary Bar
// ────────────────────────────────────────────────────────────────────────────

function SummaryBar({
  result,
  onDownloadMemo,
  downloadingMemo,
}: {
  result: ComparisonResult;
  onDownloadMemo: () => void;
  downloadingMemo: boolean;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
      <div className="flex flex-wrap items-center gap-4">
        <StatPill
          icon={<PlusCircle className="h-4 w-4 text-green-500" />}
          label="Added"
          value={result.total_additions}
          color="text-green-700"
        />
        <StatPill
          icon={<MinusCircle className="h-4 w-4 text-red-500" />}
          label="Deleted"
          value={result.total_deletions}
          color="text-red-700"
        />
        <StatPill
          icon={<RefreshCw className="h-4 w-4 text-amber-500" />}
          label="Modified"
          value={result.total_changes}
          color="text-amber-700"
        />
        <StatPill
          icon={<AlertTriangle className="h-4 w-4 text-violet-500" />}
          label="Substantive"
          value={result.substantive_changes}
          color="text-violet-700"
        />

        {result.prayer_a || result.prayer_b ? (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-50 border border-orange-200 rounded-lg text-xs text-orange-700 font-medium">
            <Gavel className="h-3.5 w-3.5" />
            Prayer section detected
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500">
            <Info className="h-3.5 w-3.5" />
            No prayer section found
          </div>
        )}

        <div className="flex-1" />

        <button
          onClick={onDownloadMemo}
          disabled={downloadingMemo}
          className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {downloadingMemo ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Download className="h-4 w-4" />
          )}
          Export Comparison Memo
        </button>
      </div>
    </div>
  );
}

function StatPill({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-lg border border-slate-100">
      {icon}
      <div>
        <p className={`text-lg font-bold leading-none ${color}`}>{value}</p>
        <p className="text-xs text-slate-500 mt-0.5">{label}</p>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Prayer Watch Panel
// ────────────────────────────────────────────────────────────────────────────

function PrayerWatchPanel({ result }: { result: ComparisonResult }) {
  const changes = result.prayer_diff.filter((b) => b.type !== "equal");

  return (
    <div className="space-y-4">
      {/* Banner */}
      <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 flex items-start gap-3">
        <Gavel className="h-5 w-5 text-orange-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-orange-800">Prayer Watch</p>
          <p className="text-xs text-orange-700 mt-0.5">
            The prayer / relief section has been isolated for comparison.
            {changes.length > 0
              ? ` ${changes.length} line(s) differ between the two versions.`
              : " No differences detected in the prayer section."}
          </p>
        </div>
      </div>

      {/* Side-by-side prayer text */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="grid grid-cols-2 bg-orange-700 text-white text-sm font-semibold">
          <div className="px-4 py-2.5">Original Prayer — {result.doc_a_name}</div>
          <div className="px-4 py-2.5 border-l border-orange-600">Amended Prayer — {result.doc_b_name}</div>
        </div>

        {result.prayer_diff.length === 0 ? (
          <div className="grid grid-cols-2 gap-0">
            <div className="p-4 text-sm text-slate-600 whitespace-pre-wrap border-r border-slate-100">
              {result.prayer_a || <span className="text-slate-300 italic">No prayer section detected in Document A.</span>}
            </div>
            <div className="p-4 text-sm text-slate-600 whitespace-pre-wrap">
              {result.prayer_b || <span className="text-slate-300 italic">No prayer section detected in Document B.</span>}
            </div>
          </div>
        ) : (
          <div>
            {result.prayer_diff.map((block, idx) => {
              const leftBg =
                block.type === "delete" ? "bg-red-50 border-l-4 border-red-400" :
                block.type === "replace" ? "bg-amber-50 border-l-4 border-amber-400" : "";
              const rightBg =
                block.type === "insert" ? "bg-green-50 border-l-4 border-green-400" :
                block.type === "replace" ? "bg-amber-50 border-l-4 border-amber-400" : "";

              return (
                <div key={idx} className="grid grid-cols-2 border-b border-slate-100">
                  <div className={`px-4 py-2.5 text-sm text-slate-700 ${leftBg}`}>
                    {block.word_diff && block.left_text && block.right_text ? (
                      <WordDiffText wordDiff={block.word_diff} side="left" />
                    ) : (
                      block.left_text || <span className="text-slate-300 italic">(not present)</span>
                    )}
                  </div>
                  <div className={`px-4 py-2.5 text-sm text-slate-700 border-l border-slate-100 ${rightBg}`}>
                    {block.word_diff && block.left_text && block.right_text ? (
                      <WordDiffText wordDiff={block.word_diff} side="right" />
                    ) : (
                      block.right_text || <span className="text-slate-300 italic">(not present)</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Legal Entities Panel
// ────────────────────────────────────────────────────────────────────────────

function LegalEntitiesPanel({ result }: { result: ComparisonResult }) {
  const lec = result.legal_entity_changes;

  const groups = [
    {
      label: "Sections & Articles",
      icon: <BookOpen className="h-4 w-4 text-violet-500" />,
      added: lec.sections_added || [],
      removed: lec.sections_removed || [],
      common: lec.sections_common || [],
      addColor: "bg-violet-50 text-violet-800 border border-violet-200",
      removeColor: "bg-red-50 text-red-700 border border-red-200",
      commonColor: "bg-slate-50 text-slate-600 border border-slate-200",
    },
    {
      label: "Case Citations",
      icon: <Gavel className="h-4 w-4 text-amber-500" />,
      added: lec.citations_added || [],
      removed: lec.citations_removed || [],
      common: lec.citations_common || [],
      addColor: "bg-amber-50 text-amber-800 border border-amber-200",
      removeColor: "bg-red-50 text-red-700 border border-red-200",
      commonColor: "bg-slate-50 text-slate-600 border border-slate-200",
    },
    {
      label: "Key Dates",
      icon: <Calendar className="h-4 w-4 text-sky-500" />,
      added: lec.dates_added || [],
      removed: lec.dates_removed || [],
      common: [],
      addColor: "bg-sky-50 text-sky-800 border border-sky-200",
      removeColor: "bg-red-50 text-red-700 border border-red-200",
      commonColor: "",
    },
    {
      label: "Monetary Amounts",
      icon: <DollarSign className="h-4 w-4 text-emerald-500" />,
      added: lec.amounts_added || [],
      removed: lec.amounts_removed || [],
      common: [],
      addColor: "bg-emerald-50 text-emerald-800 border border-emerald-200",
      removeColor: "bg-red-50 text-red-700 border border-red-200",
      commonColor: "",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 flex items-start gap-3">
        <Tag className="h-5 w-5 text-violet-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-violet-800">Legal Entity Analysis</p>
          <p className="text-xs text-violet-700 mt-0.5">
            Changes to sections, case citations, key dates, and monetary amounts are isolated below.
            These are the elements most likely to have substantive legal implications.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {groups.map((g) => (
          <div key={g.label} className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
            <div className="flex items-center gap-2 mb-3">
              {g.icon}
              <h3 className="text-sm font-semibold text-slate-800">{g.label}</h3>
            </div>

            {g.added.length === 0 && g.removed.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No changes detected.</p>
            ) : (
              <div className="space-y-3">
                {g.added.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-green-600 mb-1.5 flex items-center gap-1">
                      <PlusCircle className="h-3.5 w-3.5" /> Added in Document B
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {g.added.map((item, i) => (
                        <span key={i} className={`text-xs px-2 py-1 rounded-md font-medium ${g.addColor}`}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {g.removed.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-red-600 mb-1.5 flex items-center gap-1">
                      <MinusCircle className="h-3.5 w-3.5" /> Removed from Document A
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {g.removed.map((item, i) => (
                        <span key={i} className={`text-xs px-2 py-1 rounded-md font-medium ${g.removeColor}`}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {g.common.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-slate-500 mb-1.5 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Present in both
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {g.common.slice(0, 10).map((item, i) => (
                        <span key={i} className={`text-xs px-2 py-1 rounded-md ${g.commonColor}`}>
                          {item}
                        </span>
                      ))}
                      {g.common.length > 10 && (
                        <span className="text-xs text-slate-400">+{g.common.length - 10} more</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Tiny UI helpers
// ────────────────────────────────────────────────────────────────────────────

function TabBtn({
  active,
  icon,
  label,
  onClick,
  badge,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all flex-1 justify-center
        ${active
          ? "bg-violet-600 text-white shadow-sm"
          : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        }`}
    >
      {icon}
      {label}
      {badge !== undefined && badge > 0 && (
        <span
          className={`ml-1 text-xs rounded-full px-1.5 py-0.5 font-semibold
            ${active ? "bg-white/20 text-white" : "bg-violet-100 text-violet-700"}`}
        >
          {badge}
        </span>
      )}
    </button>
  );
}

function FilterToggle({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border transition-colors font-medium
        ${active
          ? "bg-indigo-50 border-indigo-300 text-indigo-700"
          : "bg-white border-slate-200 text-slate-500 hover:border-slate-300"
        }`}
    >
      <span
        className={`h-3 w-3 rounded-sm border flex items-center justify-center transition-colors
          ${active ? "bg-indigo-500 border-indigo-500" : "border-slate-300 bg-white"}`}
      >
        {active && (
          <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5">
            <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        )}
      </span>
      {label}
    </button>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`h-3 w-4 rounded-sm ${color}`} />
      <span className="text-xs text-slate-500">{label}</span>
    </div>
  );
}
