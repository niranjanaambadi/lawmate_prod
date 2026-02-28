"use client";

import { useCallback, useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { useEditor, EditorContent, Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { CitationExtension } from "./CitationNode";
import { DrawingExtension } from "./DrawingNode";

export interface CitationAttrs {
  anchorId: string;
  docId: string;
  pageNumber: number;
  quoteText: string;
  bbox?: { left: number; top: number; width: number; height: number };
}

export interface HearingNoteEditorRef {
  insertCitation: (attrs: CitationAttrs) => boolean;
}

export interface HearingNoteEditorProps {
  initialContentJson: Record<string, unknown> | null;
  placeholder?: string;
  onChange?: (json: Record<string, unknown>, text: string) => void;
  onCitationClick?: (attrs: { docId: string; pageNumber: number; bbox?: unknown; anchorId?: string; quoteText?: string }) => void;
  className?: string;
}

function useCitationClick(
  editor: Editor | null,
  onCitationClick: HearingNoteEditorProps["onCitationClick"]
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cbRef = useRef(onCitationClick);
  cbRef.current = onCitationClick;

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { docId?: string; pageNumber?: number; bbox?: unknown; anchorId?: string; quoteText?: string };
      if (detail?.docId != null && detail?.pageNumber != null) {
        cbRef.current?.({
          docId: detail.docId,
          pageNumber: detail.pageNumber,
          bbox: detail.bbox,
          anchorId: detail.anchorId,
          quoteText: detail.quoteText,
        });
      }
    };
    el.addEventListener("citation-click", handler);
    return () => el.removeEventListener("citation-click", handler);
  }, []);
  return containerRef;
}

export const HearingNoteEditor = forwardRef<HearingNoteEditorRef, HearingNoteEditorProps>(function HearingNoteEditor(
  {
    initialContentJson,
    placeholder = "Add hearing notes… Select text in the PDF and use the button to add a citation.",
    onChange,
    onCitationClick,
    className = "",
  },
  ref
) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Placeholder.configure({ placeholder }),
      CitationExtension,
      DrawingExtension,
    ],
    content: initialContentJson ?? undefined,
    editorProps: {
      attributes: {
        class: "prose prose-sm max-w-none min-h-[200px] p-3 focus:outline-none",
      },
    },
    onUpdate: ({ editor }) => {
      onChange?.(editor.getJSON(), editor.getText());
    },
  });

  const containerRef = useCitationClick(editor, onCitationClick);

  useImperativeHandle(ref, () => ({
    insertCitation(attrs: CitationAttrs) {
      return editor?.commands.insertCitation(attrs) ?? false;
    },
  }), [editor]);

  return (
    <div ref={containerRef} className={className}>
      <EditorContent editor={editor} />
    </div>
  );
});
