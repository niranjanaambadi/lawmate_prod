"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import {
  Bold, Italic, Heading1, Heading2,
  List, ListOrdered, Sparkles, Save, Copy, Check,
  ChevronDown, Loader2, Download, Monitor, Cloud, FileText,
} from "lucide-react";
import type { DraftingDraft } from "@/lib/api";

interface Props {
  workspaceId: string;
  activeDraft: DraftingDraft | null;
  drafts:      DraftingDraft[];
  token:       string;
  onSaved:     (draft: DraftingDraft) => void;
  onSelectDraft: (draftId: string) => void;
}

const AI_ASSIST_OPTIONS = [
  { label: "Rephrase",               prompt: "Rephrase the following text clearly and formally:" },
  { label: "Strengthen this ground", prompt: "Strengthen the following legal ground with better reasoning and citations:" },
  { label: "Add legal citation",     prompt: "Suggest an appropriate legal citation or precedent for the following:" },
  { label: "Translate to Malayalam", prompt: "Translate the following legal text to Malayalam:" },
];

// ── Google Identity Services helper ──────────────────────────────────────────

async function loadGIS(): Promise<void> {
  if ((window as any).google?.accounts?.oauth2) return;
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.onload  = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google Identity Services"));
    document.body.appendChild(script);
  });
}

async function getDriveAccessToken(): Promise<string> {
  await loadGIS();
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  if (!clientId) throw new Error("NEXT_PUBLIC_GOOGLE_CLIENT_ID is not set");
  return new Promise((resolve, reject) => {
    const tokenClient = (window as any).google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope:     "https://www.googleapis.com/auth/drive.file",
      callback:  (resp: any) => {
        if (resp.error) reject(new Error(resp.error));
        else resolve(resp.access_token as string);
      },
    });
    tokenClient.requestAccessToken();
  });
}

async function uploadBlobToDrive(
  blob: Blob,
  filename: string,
  mimeType: string,
  accessToken: string,
): Promise<{ id: string; name: string }> {
  const metadata = { name: filename, mimeType };
  const form = new FormData();
  form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
  form.append("file", blob);
  const res = await fetch(
    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
    { method: "POST", headers: { Authorization: `Bearer ${accessToken}` }, body: form },
  );
  if (!res.ok) throw new Error(`Drive upload failed: ${res.statusText}`);
  return res.json();
}

// ── Plain-text → HTML conversion ──────────────────────────────────────────────
// The backend saves Claude's response as plain text with \n\n paragraph breaks
// and optional markdown-lite markers.  TipTap expects HTML; without this
// conversion all whitespace collapses and the draft appears as one blob.

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inlineMarkdown(s: string): string {
  return escHtml(s)
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*(.+?)\*\*/g,     "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g,         "<em>$1</em>")
    .replace(/__(.+?)__/g,         "<strong>$1</strong>")
    .replace(/_(.+?)_/g,           "<em>$1</em>");
}

function plainTextToHtml(raw: string): string {
  if (!raw) return "";
  // If content already looks like HTML, pass it through untouched
  if (/^[\s\n]*</.test(raw)) return raw;

  const lines = raw.split("\n");
  const parts: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^# (.+)/.test(line))       { parts.push(`<h1>${inlineMarkdown(line.slice(2).trim())}</h1>`); continue; }
    if (/^## (.+)/.test(line))      { parts.push(`<h2>${inlineMarkdown(line.slice(3).trim())}</h2>`); continue; }
    if (/^### (.+)/.test(line))     { parts.push(`<h3>${inlineMarkdown(line.slice(4).trim())}</h3>`); continue; }
    if (/^#### (.+)/.test(line))    { parts.push(`<h3>${inlineMarkdown(line.slice(5).trim())}</h3>`); continue; }
    if (/^[*-] (.+)/.test(line))    { parts.push(`<li>${inlineMarkdown(line.replace(/^[*-] /, ""))}</li>`); continue; }
    if (line.trim() === "")         { parts.push("<p></p>"); continue; }
    parts.push(`<p>${inlineMarkdown(line)}</p>`);
  }

  // Wrap consecutive <li> items in <ul>
  return parts
    .join("")
    .replace(/(<li>[^]*?<\/li>)+/g, (match) => `<ul>${match}</ul>`);
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DraftingStudio({
  workspaceId, activeDraft, drafts, token, onSaved, onSelectDraft,
}: Props) {
  const [copied,        setCopied]       = useState(false);
  const [saving,        setSaving]       = useState(false);
  const [showAIMenu,    setShowAIMenu]   = useState(false);
  const [aiProcessing,  setAiProcessing] = useState(false);
  const [draftMenuOpen, setDraftMenuOpen] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting,     setExporting]    = useState(false);
  const [driveStatus,   setDriveStatus]  = useState<"idle" | "uploading" | "done" | "error">("idle");
  const printZoneRef = useRef<HTMLDivElement>(null);
  const lastSavedRef = useRef<string>("");
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: "Generated draft will appear here…" }),
    ],
    content: plainTextToHtml(activeDraft?.content ?? ""),
    editorProps: {
      attributes: { class: "prose prose-sm max-w-none focus:outline-none min-h-[160px] px-1" },
    },
  });

  // Update editor when activeDraft changes
  useEffect(() => {
    if (!editor || !activeDraft) return;
    const asHtml = plainTextToHtml(activeDraft.content ?? "");
    if (editor.getHTML() !== asHtml) {
      editor.commands.setContent(asHtml);
      lastSavedRef.current = asHtml;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDraft?.id]);

  // Auto-save every 30s
  useEffect(() => {
    if (!editor || !activeDraft) return;
    const triggerSave = async () => {
      const content = editor.getHTML();
      if (content === lastSavedRef.current) return;
      setSaving(true);
      try {
        const { saveDraft } = await import("@/lib/api");
        const updated = await saveDraft(workspaceId, activeDraft.id, content, token);
        lastSavedRef.current = content;
        onSaved(updated);
      } catch { /* silently ignore */ }
      finally { setSaving(false); }
    };
    saveTimerRef.current = setInterval(triggerSave, 30000);
    return () => { if (saveTimerRef.current) clearInterval(saveTimerRef.current); };
  }, [editor, activeDraft?.id, workspaceId, token, onSaved]);

  const handleManualSave = async () => {
    if (!editor || !activeDraft) return;
    const content = editor.getHTML();
    setSaving(true);
    try {
      const { saveDraft } = await import("@/lib/api");
      const updated = await saveDraft(workspaceId, activeDraft.id, content, token);
      lastSavedRef.current = content;
      onSaved(updated);
    } catch { /* noop */ }
    finally { setSaving(false); }
  };

  const handleCopy = () => {
    if (!editor) return;
    navigator.clipboard.writeText(editor.getText());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleAIAssist = async (promptPrefix: string) => {
    if (!editor || aiProcessing) return;
    setShowAIMenu(false);
    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to, " ").trim();
    if (!selectedText) { alert("Select text first, then choose an AI Assist option."); return; }
    setAiProcessing(true);
    let result = "";
    const { streamDraftingChat } = await import("@/lib/api");
    await new Promise<void>((resolve) => {
      streamDraftingChat(workspaceId, `${promptPrefix}\n\n${selectedText}`, [], token, {
        onDelta: (chunk) => { result += chunk; },
        onDone:  () => {
          editor.chain().focus().deleteRange({ from, to }).insertContentAt(from, result).run();
          resolve();
        },
        onError: (msg) => { alert(`AI Assist error: ${msg}`); resolve(); },
      }, true);
    });
    setAiProcessing(false);
  };

  // ── DOCX generation (shared) ───────────────────────────────────────────────

  const generateDocxBlob = useCallback(async (): Promise<Blob> => {
    const HTMLtoDOCX = (await import("html-to-docx")).default;
    const html = editor!.getHTML();
    return await (HTMLtoDOCX as any)(html, null, {
      title:    activeDraft!.title,
      font:     "Times New Roman",
      fontSize: 24,                  // half-points → 12pt
      margins:  { top: 1440, bottom: 1440, left: 1800, right: 1440 },  // ~1 inch
    }) as Blob;
  }, [editor, activeDraft]);

  // ── Export: DOCX → local machine ──────────────────────────────────────────

  const handleDownloadDocxLocal = async () => {
    if (!editor || !activeDraft) return;
    setExporting(true);
    setExportMenuOpen(false);
    try {
      const blob     = await generateDocxBlob();
      const filename = `${activeDraft.title}.docx`;

      if ("showSaveFilePicker" in window) {
        // Chrome/Edge: native "Save As" dialog with folder choice
        const handle = await (window as any).showSaveFilePicker({
          suggestedName: filename,
          types: [{
            description: "Word Document",
            accept: { "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"] },
          }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
      } else {
        // Firefox / Safari fallback — downloads to default Downloads folder
        const url = URL.createObjectURL(blob);
        const a   = document.createElement("a");
        a.href     = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") alert("Download failed: " + String(err?.message ?? err));
    } finally {
      setExporting(false);
    }
  };

  // ── Export: DOCX → Google Drive ───────────────────────────────────────────

  const handleUploadDocxToDrive = async () => {
    if (!editor || !activeDraft) return;
    setExportMenuOpen(false);
    setDriveStatus("uploading");
    try {
      const accessToken = await getDriveAccessToken();
      const blob        = await generateDocxBlob();
      const filename    = `${activeDraft.title}.docx`;
      const DOCX_MIME   = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
      await uploadBlobToDrive(blob, filename, DOCX_MIME, accessToken);
      setDriveStatus("done");
      setTimeout(() => setDriveStatus("idle"), 3000);
    } catch (err: any) {
      const msg = err?.message ?? String(err);
      if (!msg.includes("popup_closed") && !msg.includes("AbortError")) {
        alert("Google Drive upload failed: " + msg);
      }
      setDriveStatus("error");
      setTimeout(() => setDriveStatus("idle"), 2000);
    }
  };

  // ── Export: PDF → local (print dialog via isolated window) ───────────────
  // Opening a dedicated window avoids the "empty PDF" bug caused by nested
  // visibility issues when printing from the main app window.

  const handlePrintPDF = () => {
    setExportMenuOpen(false);
    if (!editor || !activeDraft) return;
    const html  = editor.getHTML();
    const title = activeDraft.title ?? "Draft";
    const win   = window.open("", "_blank", "width=900,height=700");
    if (!win) { alert("Pop-up blocked — please allow pop-ups for this site and try again."); return; }
    win.document.write(`<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${title.replace(/</g, "&lt;")}</title>
  <style>
    @page { margin: 2cm; }
    body { font-family: 'Times New Roman', serif; font-size: 12pt; line-height: 1.6; color: #000; margin: 0; }
    h1 { font-size: 16pt; font-weight: bold; margin: 0 0 12pt; }
    h2 { font-size: 14pt; font-weight: bold; margin: 12pt 0 8pt; }
    h3 { font-size: 13pt; font-weight: bold; margin: 10pt 0 6pt; }
    p  { margin: 0 0 8pt; }
    ul, ol { margin: 0 0 8pt; padding-left: 20pt; }
    strong { font-weight: bold; }
    em     { font-style: italic; }
  </style>
</head>
<body>${html}</body>
</html>`);
    win.document.close();
    win.focus();
    // Small delay lets the browser finish rendering before the print dialog opens
    setTimeout(() => { win.print(); win.close(); }, 250);
  };

  if (!activeDraft) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-slate-400">
        No draft selected — generate a draft from the Chat panel or the Brief modal.
      </div>
    );
  }

  const exportBusy = exporting || driveStatus === "uploading";

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-2 py-1.5 border-b-2 border-slate-200 bg-slate-50 flex-wrap shrink-0">

        {/* Draft selector */}
        <div className="relative mr-2">
          <button
            onClick={() => setDraftMenuOpen((o) => !o)}
            className="flex items-center gap-1 text-xs font-medium text-slate-700 border border-slate-300 rounded-md px-2 py-1 bg-white hover:border-indigo-400 hover:text-indigo-700 max-w-[160px] shadow-sm transition-colors"
          >
            <span className="truncate">{activeDraft.title.slice(0, 20)}…</span>
            <ChevronDown className="h-3 w-3 shrink-0" />
          </button>
          {draftMenuOpen && (
            <div className="absolute top-full left-0 mt-1 w-64 bg-white border border-slate-200 rounded-lg shadow-xl z-20 max-h-48 overflow-y-auto">
              {drafts.map((d) => (
                <button
                  key={d.id}
                  onClick={() => { onSelectDraft(d.id); setDraftMenuOpen(false); }}
                  className={`w-full text-left px-3 py-2 text-xs hover:bg-indigo-50 transition-colors ${d.id === activeDraft.id ? "text-indigo-700 font-semibold bg-indigo-50" : "text-slate-700"}`}
                >
                  <p className="truncate">{d.title}</p>
                  <p className="text-slate-400 text-[10px]">v{d.version}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="h-5 w-px bg-slate-300 mx-1" />

        {/* Format buttons */}
        <ToolbarBtn onClick={() => editor?.chain().focus().toggleBold().run()} title="Bold">
          <Bold className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor?.chain().focus().toggleItalic().run()} title="Italic">
          <Italic className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()} title="H1">
          <Heading1 className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} title="H2">
          <Heading2 className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor?.chain().focus().toggleBulletList().run()} title="Bullet list">
          <List className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor?.chain().focus().toggleOrderedList().run()} title="Numbered list">
          <ListOrdered className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <div className="h-5 w-px bg-slate-300 mx-1" />

        {/* AI Assist */}
        <div className="relative">
          <button
            onClick={() => setShowAIMenu((o) => !o)}
            className="flex items-center gap-1.5 text-xs font-semibold bg-indigo-600 text-white px-2.5 py-1 rounded-md hover:bg-indigo-700 active:bg-indigo-800 shadow-sm transition-colors disabled:opacity-50"
            disabled={aiProcessing}
          >
            {aiProcessing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            AI Assist
          </button>
          {showAIMenu && (
            <div className="absolute top-full left-0 mt-1 w-52 bg-white border border-slate-200 rounded-lg shadow-xl z-20">
              {AI_ASSIST_OPTIONS.map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => handleAIAssist(opt.prompt)}
                  className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 first:rounded-t-lg last:rounded-b-lg transition-colors"
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right-side actions */}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-[10px] text-slate-400 font-medium">v{activeDraft.version}</span>

          {/* Copy */}
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 border border-transparent hover:border-slate-200 px-1.5 py-1 rounded-md transition-colors"
            title="Copy plain text"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
          </button>

          {/* Export dropdown */}
          <div className="relative">
            <button
              onClick={() => setExportMenuOpen((o) => !o)}
              disabled={exportBusy}
              className="flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-indigo-700 border border-slate-300 bg-white hover:border-indigo-400 px-2.5 py-1 rounded-md shadow-sm transition-colors disabled:opacity-50"
              title="Export"
            >
              {exportBusy
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Download className="h-3.5 w-3.5" />
              }
              <span>
                {driveStatus === "done"
                  ? <span className="text-green-600">Saved!</span>
                  : driveStatus === "error"
                  ? <span className="text-red-500">Error</span>
                  : "Export"}
              </span>
              <ChevronDown className="h-3 w-3" />
            </button>

            {exportMenuOpen && (
              <div className="absolute top-full right-0 mt-1 w-56 bg-white border border-slate-200 rounded-lg shadow-xl z-30 py-1">

                {/* DOCX section */}
                <p className="px-3 pt-1.5 pb-0.5 text-[10px] font-bold text-indigo-600 uppercase tracking-wider flex items-center gap-1">
                  <FileText className="h-3 w-3" /> Word (.docx)
                </p>
                <button
                  onClick={handleDownloadDocxLocal}
                  className="w-full text-left flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                >
                  <Monitor className="h-3.5 w-3.5 text-slate-400" />
                  This computer
                </button>
                <button
                  onClick={handleUploadDocxToDrive}
                  className="w-full text-left flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                >
                  <Cloud className="h-3.5 w-3.5 text-blue-500" />
                  Google Drive
                </button>

                <div className="border-t border-slate-200 my-1" />

                {/* PDF section */}
                <p className="px-3 pt-1.5 pb-0.5 text-[10px] font-bold text-indigo-600 uppercase tracking-wider flex items-center gap-1">
                  <FileText className="h-3 w-3" /> PDF
                </p>
                <button
                  onClick={handlePrintPDF}
                  className="w-full text-left flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                >
                  <Monitor className="h-3.5 w-3.5 text-slate-400" />
                  Save as PDF
                </button>
              </div>
            )}
          </div>

          {/* Save */}
          <button
            onClick={handleManualSave}
            disabled={saving}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 px-1.5 py-0.5 rounded disabled:opacity-50"
            title="Save"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Editor content — ref used by print handler */}
      <div ref={printZoneRef} className="flex-1 overflow-y-auto px-4 py-3">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

function ToolbarBtn({
  onClick, children, title,
}: { onClick: () => void; children: React.ReactNode; title?: string }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="p-1.5 rounded-md text-slate-600 hover:bg-indigo-100 hover:text-indigo-700 active:bg-indigo-200 transition-colors"
    >
      {children}
    </button>
  );
}
