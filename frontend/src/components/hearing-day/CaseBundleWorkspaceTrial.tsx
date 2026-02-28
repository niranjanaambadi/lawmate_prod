"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Node as TiptapNode, mergeAttributes } from "@tiptap/core";
import { PdfViewer, type TextSelectionPayload } from "@/components/hearing-day/PdfViewer";

type SavePayload = {
  contentJson: Record<string, unknown>;
  contentText: string;
  citations: Array<{ text: string; pageNumber: number; docId: string | null }>;
};

type TrialProps = {
  pdfUrl?: string;
  caseTitle?: string;
  docId?: string;
  initialNotes?: string;
  onSave?: (payload: SavePayload) => void;
};

type SelectionState = { text: string; pageNumber: number; bbox?: { left: number; top: number; width: number; height: number } } | null;

const CitationNode = TiptapNode.create({
  name: "citation",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      text: { default: "" },
      pageNumber: { default: 1 },
      docId: { default: null },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-citation="true"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, { "data-citation": "true", class: "cbw-citation" }),
      `\"${String(HTMLAttributes.text || "")}\" - p.${String(HTMLAttributes.pageNumber || "1")}`,
    ];
  },

  addNodeView() {
    return ({ node }) => {
      const dom = document.createElement("span");
      dom.className = "cbw-citation";
      dom.textContent = `\"${node.attrs.text}\" - p.${node.attrs.pageNumber}`;
      dom.onclick = () => {
        window.dispatchEvent(
          new CustomEvent("citation:jump", {
            detail: { pageNumber: node.attrs.pageNumber, docId: node.attrs.docId },
          })
        );
      };
      return { dom };
    };
  },
});

function usePdfSelection() {
  const [selection, setSelection] = useState<SelectionState>(null);
  const clear = useCallback(() => {
    setSelection(null);
    window.getSelection()?.removeAllRanges();
  }, []);
  return { selection, setSelection, clear };
}

export default function CaseBundleWorkspaceTrial({
  pdfUrl,
  caseTitle = "Trial Hearing Workspace",
  docId = "trial-doc",
  initialNotes = "",
  onSave,
}: TrialProps) {
  const [splitPct, setSplitPct] = useState(50);

  const isDragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const pdfContainerRef = useRef<HTMLDivElement>(null);
  const [activePage, setActivePage] = useState<number | undefined>(undefined);

  const { selection, setSelection, clear: clearSelection } = usePdfSelection();

  const editor = useEditor({
    extensions: [StarterKit, CitationNode],
    content: initialNotes || "<p>Start your hearing notes here...</p>",
    immediatelyRender: false,
  });

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setSplitPct(Math.min(Math.max(pct, 25), 75));
    };
    const onUp = () => {
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ pageNumber?: number }>;
      const pageNumber = custom.detail?.pageNumber || 1;
      setActivePage(pageNumber);
    };
    window.addEventListener("citation:jump", handler);
    return () => window.removeEventListener("citation:jump", handler);
  }, []);

  const onDividerMouseDown = useCallback(() => {
    isDragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const insertCitation = useCallback(() => {
    if (!selection || !editor) return;
    editor
      .chain()
      .focus()
      .insertContent({
        type: "citation",
        attrs: { text: selection.text, pageNumber: selection.pageNumber, docId },
      })
      .insertContent(" ")
      .run();
    clearSelection();
  }, [selection, editor, docId, clearSelection]);

  const handleSave = useCallback(() => {
    if (!editor) return;
    const json = editor.getJSON();
    const citations: Array<{ text: string; pageNumber: number; docId: string | null }> = [];

    const walk = (node: any) => {
      if (node?.type === "citation") {
        citations.push({
          text: String(node.attrs?.text || ""),
          pageNumber: Number(node.attrs?.pageNumber || 1),
          docId: node.attrs?.docId ?? null,
        });
      }
      (node?.content || []).forEach(walk);
    };
    (json.content || []).forEach(walk);

    const payload: SavePayload = {
      contentJson: json as unknown as Record<string, unknown>,
      contentText: editor.getText(),
      citations,
    };

    if (onSave) onSave(payload);
    else console.log("[trial-save]", payload);
  }, [editor, onSave]);

  return (
    <div className="cbw-root">
      <div className="cbw-topbar">
        <div className="cbw-title">{caseTitle}</div>
        <div className="cbw-actions">
          {selection ? (
            <button className="cbw-btn-primary" onClick={insertCitation}>
              Insert Citation (p.{selection.pageNumber})
            </button>
          ) : null}
          <button className="cbw-btn" onClick={handleSave}>
            Save Notes
          </button>
        </div>
      </div>

      <div className="cbw-body" ref={containerRef}>
        <div className="cbw-panel" style={{ width: `${splitPct}%` }} ref={pdfContainerRef}>
          <div className="cbw-panel-header">PDF Bundle</div>
          <div className="cbw-panel-body">
            {pdfUrl ? (
              <PdfViewer
                url={pdfUrl}
                activePage={activePage}
                onTextSelected={(payload: TextSelectionPayload) => {
                  const next = payload?.text?.trim();
                  if (!next) return;
                  setSelection({ text: next, pageNumber: payload.pageNumber, bbox: payload.bbox });
                }}
              />
            ) : (
              <div className="cbw-empty">No PDF URL provided</div>
            )}
          </div>
          {selection ? (
            <div className="cbw-selection">
              "{selection.text.slice(0, 80)}{selection.text.length > 80 ? "..." : ""}" (p.{selection.pageNumber})
            </div>
          ) : null}
        </div>

        <div className="cbw-divider" onMouseDown={onDividerMouseDown} />

        <div className="cbw-panel" style={{ width: `${100 - splitPct}%` }}>
          <div className="cbw-panel-header">Hearing Notes</div>
          <div className="cbw-panel-body cbw-editor-wrap">
            <EditorContent editor={editor} className="cbw-editor" />
          </div>
        </div>
      </div>

      <style jsx>{`
        .cbw-root { display: flex; flex-direction: column; height: calc(100vh - 9rem); border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: #fff; }
        .cbw-topbar { height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; border-bottom: 1px solid #e5e7eb; background: #f8fafc; }
        .cbw-title { font-weight: 600; font-size: 14px; color: #0f172a; }
        .cbw-actions { display: flex; gap: 8px; }
        .cbw-btn, .cbw-btn-primary { font-size: 12px; border-radius: 6px; padding: 6px 10px; border: 1px solid #cbd5e1; background: #fff; }
        .cbw-btn-primary { background: #0f172a; color: #fff; border-color: #0f172a; }
        .cbw-body { flex: 1; display: flex; min-height: 0; }
        .cbw-panel { display: flex; flex-direction: column; min-width: 0; }
        .cbw-panel-header { height: 36px; border-bottom: 1px solid #e5e7eb; padding: 0 10px; display: flex; align-items: center; font-size: 12px; font-weight: 600; color: #334155; background: #f8fafc; }
        .cbw-panel-body { flex: 1; min-height: 0; overflow: auto; }
        .cbw-divider { width: 6px; cursor: col-resize; background: #e2e8f0; }
        .cbw-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: #64748b; font-size: 13px; }
        .cbw-selection { border-top: 1px solid #e5e7eb; padding: 8px 10px; font-size: 12px; color: #334155; background: #f8fafc; }
        .cbw-editor-wrap { padding: 10px; }
        .cbw-editor :global(.ProseMirror) { min-height: 280px; outline: none; font-size: 14px; color: #111827; }
        .cbw-editor :global(.cbw-citation) { background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; border-radius: 6px; padding: 1px 6px; cursor: pointer; }
      `}</style>
    </div>
  );
}
