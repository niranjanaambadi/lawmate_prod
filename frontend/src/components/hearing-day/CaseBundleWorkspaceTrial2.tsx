"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Node as TiptapNode, mergeAttributes } from "@tiptap/core";
import { PdfViewer, type TextSelectionPayload } from "@/components/hearing-day/PdfViewer";

type Trial2Props = {
  pdfUrl?: string;
  fileSource?: string | { url: string; httpHeaders?: Record<string, string> } | null;
  docId?: string;
  caseTitle?: string;
  initialContentJson?: Record<string, unknown> | null;
  initialNotes?: string;
  onSave?: (payload: {
    contentJson: Record<string, unknown>;
    contentText: string;
    citations: Array<{
      text: string;
      quoteText: string;
      pageNumber: number;
      docId: string | null;
      anchorId: string;
    }>;
  }) => void;
  onEnrich?: () => void;
  saving?: boolean;
  enriching?: boolean;
};

type Selection = { text: string; pageNumber: number } | null;

const CitationNode = TiptapNode.create({
  name: "citation",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      text: { default: "" },
      quoteText: { default: "" },
      pageNumber: { default: 1 },
      docId: { default: null },
      anchorId: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-citation]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, { "data-citation": "true" }),
      `\"${String(HTMLAttributes.quoteText || HTMLAttributes.text || "")}\" - p.${String(HTMLAttributes.pageNumber || "1")}`,
    ];
  },

  addNodeView() {
    return ({ node }) => {
      const dom = document.createElement("span");
      dom.className = "citation-chip";
      dom.setAttribute("title", `Jump to page ${node.attrs.pageNumber}`);

      const dot = document.createElement("span");
      dot.className = "citation-dot";

      const quote = document.createElement("span");
      quote.className = "citation-text";
      const quoteText = String(node.attrs.quoteText || node.attrs.text || "");
      quote.textContent = `\"${quoteText}\"`;

      const badge = document.createElement("span");
      badge.className = "citation-badge";
      badge.textContent = `p.${node.attrs.pageNumber}`;

      const arrow = document.createElement("span");
      arrow.className = "citation-arrow";
      arrow.textContent = "↗";

      dom.appendChild(dot);
      dom.appendChild(quote);
      dom.appendChild(badge);
      dom.appendChild(arrow);

      dom.addEventListener("click", () => {
        window.dispatchEvent(
          new CustomEvent("citation:jump", {
            detail: { pageNumber: node.attrs.pageNumber, docId: node.attrs.docId, quoteText },
          })
        );
      });

      return { dom };
    };
  },
});

function EditorToolbar({ editor }: { editor: any }) {
  const btns = [
    {
      label: "B",
      title: "Bold",
      s: { fontWeight: 700 },
      fn: () => editor?.chain().focus().toggleBold().run(),
      active: () => editor?.isActive("bold"),
    },
    {
      label: "I",
      title: "Italic",
      s: { fontStyle: "italic" },
      fn: () => editor?.chain().focus().toggleItalic().run(),
      active: () => editor?.isActive("italic"),
    },
    {
      label: "•",
      title: "Bullet list",
      s: {},
      fn: () => editor?.chain().focus().toggleBulletList().run(),
      active: () => editor?.isActive("bulletList"),
    },
    {
      label: "1.",
      title: "Ordered list",
      s: { fontSize: 10 },
      fn: () => editor?.chain().focus().toggleOrderedList().run(),
      active: () => editor?.isActive("orderedList"),
    },
    {
      label: "H",
      title: "Heading",
      s: { fontSize: 10, fontWeight: 700 },
      fn: () => editor?.chain().focus().toggleHeading({ level: 2 }).run(),
      active: () => editor?.isActive("heading", { level: 2 }),
    },
  ];
  return (
    <div className="cbw-toolbar">
      {btns.map(({ label, title, s, fn, active }) => (
        <button key={label} className={`cbw-tb-btn${active() ? " active" : ""}`} title={title} style={s} onClick={fn}>
          {label}
        </button>
      ))}
    </div>
  );
}

function PdfIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ opacity: 0.55 }}>
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function NotesIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ opacity: 0.55 }}>
      <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

export default function CaseBundleWorkspaceTrial2({
  pdfUrl,
  fileSource,
  docId = "doc-1",
  caseTitle = "WP 1234/2024",
  initialContentJson,
  initialNotes = "",
  onSave,
  onEnrich,
  saving = false,
  enriching = false,
}: Trial2Props) {
  const [splitPct, setSplitPct] = useState(50);
  const [selection, setSelection] = useState<Selection>(null);
  const [activePage, setActivePage] = useState<number | undefined>(undefined);

  const isDragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const onDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setSplitPct(Math.min(Math.max(((e.clientX - rect.left) / rect.width) * 100, 25), 75));
    };
    const onUp = () => {
      if (!isDragging.current) return;
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
    const handler = (e: Event) => {
      const event = e as CustomEvent<{ pageNumber?: number }>;
      const pageNumber = event.detail?.pageNumber || 1;
      setActivePage(pageNumber);
    };
    window.addEventListener("citation:jump", handler);
    return () => window.removeEventListener("citation:jump", handler);
  }, []);

  const editor = useEditor({
    extensions: [StarterKit, CitationNode],
    content: initialContentJson || initialNotes || "<p>Start your hearing notes here…</p>",
    immediatelyRender: false,
  });

  const clearSelection = useCallback(() => {
    setSelection(null);
    window.getSelection()?.removeAllRanges();
  }, []);

  const insertCitation = useCallback(() => {
    if (!selection || !editor) return;
    editor
      .chain()
      .focus()
      .insertContent({
        type: "citation",
        attrs: {
          text: selection.text,
          quoteText: selection.text,
          pageNumber: selection.pageNumber,
          docId,
          anchorId: crypto.randomUUID?.() ?? `cite-${Date.now()}`,
        },
      })
      .insertContent(" ")
      .run();
    clearSelection();
  }, [selection, editor, docId, clearSelection]);

  const handleSave = useCallback(() => {
    if (!editor || !onSave) return;
    const json = editor.getJSON();
    const citations: Array<{
      text: string;
      quoteText: string;
      pageNumber: number;
      docId: string | null;
      anchorId: string;
    }> = [];
    const walk = (n: any) => {
      if (n?.type === "citation") {
        citations.push({
          text: String(n.attrs?.text || ""),
          quoteText: String(n.attrs?.quoteText || n.attrs?.text || ""),
          pageNumber: Number(n.attrs?.pageNumber || 1),
          docId: n.attrs?.docId ?? null,
          anchorId: String(n.attrs?.anchorId || ""),
        });
      }
      n?.content?.forEach(walk);
    };
    json.content?.forEach(walk);
    onSave({ contentJson: json as Record<string, unknown>, contentText: editor.getText(), citations });
  }, [editor, onSave]);

  return (
    <>
      <style>{STYLES}</style>
      <div className="cbw-root">
        <header className="cbw-topbar">
          <div className="cbw-title-group">
            <span className="cbw-label">Case Bundle</span>
            <span className="cbw-case">{caseTitle}</span>
          </div>
          <div className="cbw-actions">
            {selection && (
              <button className="cbw-btn-insert" onClick={insertCitation}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12l7 7 7-7" /></svg>
                Insert Citation
                <span className="cbw-page-pill">p.{selection.pageNumber}</span>
              </button>
            )}
            <button className="cbw-btn-save" onClick={handleSave}>{saving ? "Saving..." : "Save Notes"}</button>
            {onEnrich ? (
              <button className="cbw-btn-save" onClick={onEnrich}>{enriching ? "Enriching..." : "Enrich Notes"}</button>
            ) : null}
          </div>
        </header>

        <div className="cbw-body" ref={containerRef}>
          <div className="cbw-panel" style={{ width: `${splitPct}%` }}>
            <div className="cbw-panel-header">
              <PdfIcon /> PDF Bundle
            </div>
            <div className="cbw-pdf-inner">
              <div className="cbw-pdf-wrap">
                {pdfUrl || fileSource ? (
                  <PdfViewer
                    url={pdfUrl ?? (typeof fileSource === "string" ? fileSource : fileSource?.url ?? null)}
                    fileSource={fileSource ?? null}
                    activePage={activePage}
                    onTextSelected={(payload: TextSelectionPayload) => {
                      const text = payload.text.trim();
                      if (!text) return;
                      setSelection({ text, pageNumber: payload.pageNumber });
                    }}
                  />
                ) : (
                  <div className="cbw-placeholder">
                    <p className="cbw-placeholder-title">No PDF loaded</p>
                    <p className="cbw-placeholder-sub">Pass a pdfUrl prop</p>
                  </div>
                )}
              </div>

              {selection && (
                <div className="cbw-toast">
                  <span className="cbw-toast-quote">"{selection.text.slice(0, 52)}{selection.text.length > 52 ? "…" : ""}"</span>
                  <span className="cbw-toast-page">p.{selection.pageNumber}</span>
                  <button className="cbw-toast-btn" onClick={insertCitation}>Insert into notes ↗</button>
                  <button className="cbw-toast-clear" onClick={clearSelection}>✕</button>
                </div>
              )}
            </div>
          </div>

          <div className="cbw-divider" onMouseDown={onDividerMouseDown}>
            <span className="cbw-divider-dots">⋮⋮</span>
          </div>

          <div className="cbw-panel cbw-panel-right" style={{ width: `${100 - splitPct}%` }}>
            <div className="cbw-panel-header">
              <NotesIcon /> Hearing Notes
              <EditorToolbar editor={editor} />
            </div>
            <div className="cbw-editor-scroll">
              <EditorContent editor={editor} className="cbw-editor" />
            </div>
            <footer className="cbw-editor-footer">
              <span className="cbw-footer-hint">
                Click any <span className="cbw-hint-chip">citation ↗</span> to jump back to that page in the PDF
              </span>
            </footer>
          </div>
        </div>
      </div>
    </>
  );
}

const STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0d1117; --bg-panel: #131920; --bg-surface: #1b2230; --bg-hover: #212d3d;
  --border: #232e3e; --border-lit: #35475f;
  --text: #dce4f0; --text-dim: #8899b4; --text-muted: #49596e;
  --gold: #c9a96e; --gold-dim: #7a5f35; --gold-glow: rgba(201,169,110,0.12);
  --chip-bg: #161d2b; --radius: 5px;
  --font: 'Lora', Georgia, serif; --mono: 'IBM Plex Mono', monospace;
}
.cbw-root { display:flex; flex-direction:column; height:calc(100vh - 10rem); background:var(--bg); color:var(--text); font-family:var(--font); overflow:hidden; border-radius: 10px; }
.cbw-topbar { display:flex; align-items:center; justify-content:space-between; padding:0 18px; height:50px; background:var(--bg-panel); border-bottom:1px solid var(--border); flex-shrink:0; gap:12px; }
.cbw-title-group { display:flex; align-items:center; gap:10px; }
.cbw-label { font-family:var(--mono); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:#e2e8f0; background:var(--bg-surface); padding:3px 9px; border-radius:4px; border:1px solid #475569; }
.cbw-case { font-size:16px; font-weight:700; color:#f8fafc; }
.cbw-actions { display:flex; align-items:center; gap:8px; }
.cbw-btn-insert { display:flex; align-items:center; gap:6px; padding:6px 13px; background:var(--gold); color:#0d1117; border:none; border-radius:var(--radius); font-family:var(--mono); font-size:11px; font-weight:500; cursor:pointer; }
.cbw-page-pill { background:rgba(0,0,0,0.2); border-radius:3px; padding:1px 5px; font-size:9px; }
.cbw-btn-save { padding:7px 14px; background:#ffffff; color:#0f172a; border:2px solid #cbd5e1; border-radius:var(--radius); font-family:var(--mono); font-size:12px; font-weight:700; cursor:pointer; }
.cbw-body { display:flex; flex:1; overflow:hidden; }
.cbw-panel { display:flex; flex-direction:column; overflow:hidden; position:relative; }
.cbw-panel-header { display:flex; align-items:center; gap:8px; padding:0 14px; height:40px; background:var(--bg-panel); border-bottom:1px solid var(--border); font-family:var(--mono); font-size:12px; font-weight:700; color:#e2e8f0; text-transform:uppercase; letter-spacing:0.08em; flex-shrink:0; }
.cbw-pdf-inner { flex:1; display:flex; flex-direction:column; overflow:hidden; position:relative; }
.cbw-pdf-wrap { flex:1; overflow:hidden; background:var(--bg); }
.cbw-placeholder { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:10px; padding:32px; text-align:center; color:var(--text-dim); }
.cbw-placeholder-title { font-size:15px; font-weight:600; color:var(--text-dim); margin-top:4px; }
.cbw-placeholder-sub { font-family:var(--mono); font-size:10px; color:var(--text-muted); max-width:380px; line-height:1.6; word-break:break-word; }
.cbw-toast { position:absolute; bottom:14px; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:8px; padding:8px 12px; background:var(--bg-panel); border:1px solid var(--gold-dim); border-radius:8px; z-index:30; max-width:94%; }
.cbw-toast-quote { font-size:12px; font-style:italic; color:var(--text-dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:220px; }
.cbw-toast-page { font-family:var(--mono); font-size:10px; color:var(--gold); white-space:nowrap; flex-shrink:0; }
.cbw-toast-btn { padding:4px 10px; background:var(--gold); color:#0d1117; border:none; border-radius:4px; font-family:var(--mono); font-size:10px; font-weight:600; cursor:pointer; white-space:nowrap; flex-shrink:0; }
.cbw-toast-clear { background:transparent; color:var(--text-muted); border:none; cursor:pointer; font-size:13px; flex-shrink:0; padding:2px 4px; line-height:1; }
.cbw-divider { width:8px; background:var(--bg); border-left:1px solid var(--border); border-right:1px solid var(--border); cursor:col-resize; flex-shrink:0; display:flex; align-items:center; justify-content:center; z-index:5; user-select:none; }
.cbw-divider-dots { font-size:10px; color:var(--border-lit); letter-spacing:-2px; line-height:1; writing-mode:vertical-rl; }
.cbw-panel-right { background:var(--bg-panel); }
.cbw-toolbar { display:flex; align-items:center; gap:4px; margin-left:auto; }
.cbw-tb-btn { padding:5px 10px; background:#ffffff; color:#0f172a; border:2px solid #cbd5e1; border-radius:4px; font-size:12px; font-weight:700; cursor:pointer; font-family:var(--mono); line-height:1.4; min-width:34px; text-align:center; }
.cbw-tb-btn:hover { background:#f8fafc; color:#020617; border-color:#94a3b8; }
.cbw-tb-btn.active { background:#fff7ed; color:#9a3412; border-color:#fb923c; }
.cbw-editor-scroll { flex:1; overflow-y:auto; padding:28px 30px 20px; background:#fdfaf3; }
.cbw-editor .ProseMirror { outline:none; min-height:320px; font-family:var(--font); font-size:17px; line-height:1.8; color:#0f172a; }
.citation-chip { display:inline-flex; align-items:center; gap:5px; background:var(--chip-bg); border:1px solid var(--gold-dim); border-radius:4px; padding:2px 7px 2px 5px; margin:0 2px; cursor:pointer; vertical-align:middle; }
.citation-dot { width:5px; height:5px; background:var(--gold); border-radius:50%; flex-shrink:0; opacity:0.8; }
.citation-text { font-style:italic; font-size:0.875em; color:#d4b87a; font-family:var(--font); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:260px; }
.citation-badge { font-family:var(--mono); font-size:9px; color:var(--gold); background:var(--gold-glow); padding:1px 5px; border-radius:3px; border:1px solid rgba(201,169,110,0.2); flex-shrink:0; letter-spacing:0.04em; }
.citation-arrow { font-size:10px; color:var(--gold); opacity:0.35; flex-shrink:0; }
.cbw-editor-footer { padding:8px 18px; border-top:1px solid var(--border); flex-shrink:0; background:var(--bg-panel); }
.cbw-footer-hint { font-family:var(--mono); font-size:10px; color:var(--text-muted); letter-spacing:0.03em; }
.cbw-hint-chip { color:var(--gold); border:1px solid var(--gold-dim); background:var(--gold-glow); padding:0px 5px; border-radius:3px; font-size:9px; }
`;
