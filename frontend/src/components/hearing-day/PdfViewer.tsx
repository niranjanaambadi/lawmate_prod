"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { SpecialZoomLevel, Viewer, Worker } from "@react-pdf-viewer/core";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";

export interface TextSelectionPayload {
  text: string;
  pageNumber: number;
  bbox: { left: number; top: number; width: number; height: number };
}

interface PdfViewerProps {
  url: string | null;
  fileSource?: string | { url: string; httpHeaders?: Record<string, string> } | null;
  onTextSelected?: (payload: TextSelectionPayload) => void;
  onLoadError?: (error: Error) => void;
  onSelectionSupportChange?: (supported: boolean) => void;
  allowIframeFallback?: boolean;
  activePage?: number;
  highlightBbox?: { left: number; top: number; width: number; height: number } | null;
  highlightText?: string | null;
  searchQuery?: string;
  pageWidth?: number;
}

function parsePageIndexFromTestId(testId: string | null): number | null {
  if (!testId) return null;
  const prefix = "core__page-layer-";
  if (!testId.startsWith(prefix)) return null;
  const raw = Number(testId.slice(prefix.length));
  return Number.isFinite(raw) ? raw : null;
}

function toPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value >= 0 && value <= 1) return value * 100;
  return value;
}

export function PdfViewer({
  url,
  fileSource,
  onTextSelected,
  onLoadError,
  onSelectionSupportChange,
  activePage,
  highlightBbox,
  highlightText,
  searchQuery,
}: PdfViewerProps) {
  const lastLoadErrorMessageRef = useRef<string>("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const jumpToPageRef = useRef<((pageIndex: number) => void) | null>(null);
  const lastSelectionKeyRef = useRef<string>("");
  const highlightedTextElRef = useRef<HTMLElement | null>(null);
  const highlightedBoxElRef = useRef<HTMLElement | null>(null);
  const searchHighlightedElsRef = useRef<HTMLElement[]>([]);
  const pageNavPluginInstance = useRef(pageNavigationPlugin());

  useEffect(() => {
    jumpToPageRef.current = pageNavPluginInstance.current.jumpToPage;
  }, []);

  const clearSearchHighlights = useCallback(() => {
    for (const el of searchHighlightedElsRef.current) {
      el.style.background = "";
      el.style.borderRadius = "";
      el.style.boxShadow = "";
    }
    searchHighlightedElsRef.current = [];
  }, []);

  const fileUrl = useMemo(() => {
    if (typeof url === "string" && url.trim()) return url;
    if (typeof fileSource === "string") return fileSource;
    if (fileSource && typeof fileSource === "object" && typeof fileSource.url === "string") return fileSource.url;
    return null;
  }, [fileSource, url]);
  const fileHeaders = useMemo(() => {
    if (fileSource && typeof fileSource === "object" && fileSource.httpHeaders) {
      return fileSource.httpHeaders;
    }
    return undefined;
  }, [fileSource]);

  useEffect(() => {
    onSelectionSupportChange?.(!!fileUrl);
  }, [onSelectionSupportChange, fileUrl]);

  // ── All hooks must be declared before any conditional return ─────────────

  const captureSelection = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
    const text = sel.toString().trim();
    if (!text) return;

    const range = sel.getRangeAt(0);
    const anchor =
      range.commonAncestorContainer.nodeType === globalThis.Node.ELEMENT_NODE
        ? (range.commonAncestorContainer as Element)
        : range.commonAncestorContainer.parentElement;
    const pageLayer = anchor?.closest("[data-testid^='core__page-layer-']") as HTMLElement | null;
    if (!pageLayer) return;

    const pageIndex = parsePageIndexFromTestId(pageLayer.getAttribute("data-testid"));
    if (pageIndex == null) return;

    const rect = range.getBoundingClientRect();
    const pageRect = pageLayer.getBoundingClientRect();
    if (!pageRect.width || !pageRect.height) return;

    const left = ((rect.left - pageRect.left) / pageRect.width) * 100;
    const top = ((rect.top - pageRect.top) / pageRect.height) * 100;
    const width = (rect.width / pageRect.width) * 100;
    const height = (rect.height / pageRect.height) * 100;

    const key = `${pageIndex + 1}:${Math.round(left)}:${Math.round(top)}:${text.slice(0, 80)}`;
    if (lastSelectionKeyRef.current === key) return;
    lastSelectionKeyRef.current = key;

    onTextSelected?.({
      text,
      pageNumber: pageIndex + 1,
      bbox: {
        left: Math.max(0, Math.min(100, left)),
        top: Math.max(0, Math.min(100, top)),
        width: Math.max(0, Math.min(100, width)),
        height: Math.max(0, Math.min(100, height)),
      },
    });
  }, [onTextSelected]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const onMouseUp = () => setTimeout(captureSelection, 0);
    container.addEventListener("mouseup", onMouseUp);
    return () => container.removeEventListener("mouseup", onMouseUp);
  }, [captureSelection]);

  useEffect(() => {
    const onSelectionChange = () => setTimeout(captureSelection, 0);
    document.addEventListener("selectionchange", onSelectionChange);
    return () => document.removeEventListener("selectionchange", onSelectionChange);
  }, [captureSelection]);

  useEffect(() => {
    clearSearchHighlights();
    const query = (searchQuery || "").trim().toLowerCase();
    if (!query) return;

    const root = containerRef.current;
    if (!root) return;

    const textSpans = Array.from(
      root.querySelectorAll(".rpv-core__text-layer span, .rpv-core__text-layer-text")
    ) as HTMLElement[];

    let firstMatch: HTMLElement | null = null;
    for (const span of textSpans) {
      const text = (span.textContent || "").toLowerCase();
      if (!text.includes(query)) continue;
      span.style.background = "rgba(59,130,246,0.25)";
      span.style.borderRadius = "3px";
      span.style.boxShadow = "0 0 0 1px rgba(59,130,246,0.5) inset";
      searchHighlightedElsRef.current.push(span);
      if (!firstMatch) firstMatch = span;
    }

    if (firstMatch) {
      firstMatch.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    return () => {
      clearSearchHighlights();
    };
  }, [searchQuery, fileUrl, clearSearchHighlights]);

  useEffect(() => {
    if (!activePage || activePage < 1) return;
    const jump = jumpToPageRef.current;
    if (jump) {
      jump(activePage - 1);
      return;
    }
    const root = containerRef.current;
    if (!root) return;
    let attempt = 0;
    const maxAttempts = 10;
    const scrollToPage = () => {
      const target = root.querySelector(
        `[data-testid="core__page-layer-${activePage - 1}"]`
      ) as HTMLElement | null;
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      attempt += 1;
      if (attempt < maxAttempts) window.setTimeout(scrollToPage, 120);
    };
    scrollToPage();
  }, [activePage, fileUrl]);

  useEffect(() => {
    if (highlightedTextElRef.current) {
      highlightedTextElRef.current.style.background = "";
      highlightedTextElRef.current.style.borderRadius = "";
      highlightedTextElRef.current = null;
    }
    if (highlightedBoxElRef.current) {
      highlightedBoxElRef.current.remove();
      highlightedBoxElRef.current = null;
    }

    const root = containerRef.current;
    if (!root) return;
    if (!activePage || activePage < 1) return;

    const pageLayer = root.querySelector(
      `[data-testid="core__page-layer-${activePage - 1}"]`
    ) as HTMLElement | null;
    if (!pageLayer) return;

    if (highlightBbox && highlightBbox.width > 0 && highlightBbox.height > 0) {
      const overlay = document.createElement("div");
      overlay.className = "pointer-events-none absolute border-2 border-amber-400 bg-amber-300/30";
      overlay.style.left = `${Math.max(0, Math.min(100, toPercent(highlightBbox.left)))}%`;
      overlay.style.top = `${Math.max(0, Math.min(100, toPercent(highlightBbox.top)))}%`;
      overlay.style.width = `${Math.max(0, Math.min(100, toPercent(highlightBbox.width)))}%`;
      overlay.style.height = `${Math.max(0, Math.min(100, toPercent(highlightBbox.height)))}%`;
      pageLayer.style.position = "relative";
      pageLayer.appendChild(overlay);
      highlightedBoxElRef.current = overlay;
    }

    const quote = (highlightText || "").trim().toLowerCase();
    if (!quote) return;

    const textSpans = Array.from(
      pageLayer.querySelectorAll(".rpv-core__text-layer span, .rpv-core__text-layer-text")
    ) as HTMLElement[];
    const hit = textSpans.find((span) => (span.textContent || "").toLowerCase().includes(quote));
    if (!hit) return;
    hit.style.background = "rgba(251,191,36,0.45)";
    hit.style.borderRadius = "3px";
    highlightedTextElRef.current = hit;
    hit.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activePage, highlightBbox, highlightText, fileUrl]);

  // ── Conditional render AFTER all hooks ───────────────────────────────────

  if (!fileUrl) {
    return (
      <div className="flex h-full min-h-[200px] items-center justify-center bg-slate-100 text-slate-500">
        Select a document
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-auto bg-slate-200">
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
        <div className="h-full">
          <Viewer
            fileUrl={fileUrl}
            httpHeaders={fileHeaders}
            defaultScale={SpecialZoomLevel.PageWidth}
            plugins={[pageNavPluginInstance.current]}
            renderLoader={(percentages: number) => {
              const safe = Math.max(0, Math.min(100, Math.round(percentages || 0)));
              return (
                <div className="flex h-full min-h-[220px] items-center justify-center bg-slate-100 p-6">
                  <div className="w-full max-w-md rounded-md border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-sm font-medium text-slate-700">Loading PDF...</p>
                      <p className="text-sm font-semibold text-slate-900">{safe}%</p>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200">
                      <div
                        className="h-full rounded-full bg-slate-900 transition-all duration-200 ease-out"
                        style={{ width: `${safe}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            }}
            onDocumentLoad={() => {
              lastLoadErrorMessageRef.current = "";
              onSelectionSupportChange?.(true);
            }}
            renderError={(loadError: { message?: string }) => {
              const message = loadError?.message || "unknown error";
              if (lastLoadErrorMessageRef.current !== message) {
                lastLoadErrorMessageRef.current = message;
                onLoadError?.(new Error(message));
                onSelectionSupportChange?.(false);
              }
              return (
                <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 bg-slate-100 p-4 text-center">
                  <p className="text-sm text-red-600">Failed to load PDF: {message}</p>
                  <p className="text-xs text-slate-500">Check CORS on the document source or try again.</p>
                </div>
              );
            }}
          />
        </div>
      </Worker>
    </div>
  );
}
