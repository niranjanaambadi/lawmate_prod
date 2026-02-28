"use client";

import { forwardRef, useEffect, useImperativeHandle } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";

type NotebookEditorProps = {
  contentJson: Record<string, unknown> | null;
  onChange: (json: Record<string, unknown>, text: string) => void;
  placeholder?: string;
};

export interface NotebookEditorRef {
  getSelectedText: () => string;
}

export const NotebookEditor = forwardRef<NotebookEditorRef, NotebookEditorProps>(function NotebookEditor(
  { contentJson, onChange, placeholder }: NotebookEditorProps,
  ref
) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Placeholder.configure({ placeholder: placeholder || "Write your case notebook notes..." }),
    ],
    content: contentJson ?? { type: "doc", content: [{ type: "paragraph" }] },
    editorProps: {
      attributes: {
        class:
          "prose prose-sm max-w-none min-h-[360px] p-4 focus:outline-none rounded-md border border-slate-200 bg-white",
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getJSON() as Record<string, unknown>, editor.getText());
    },
  });

  useEffect(() => {
    if (!editor) return;
    if (contentJson) {
      editor.commands.setContent(contentJson, { emitUpdate: false });
      return;
    }
    editor.commands.clearContent(true);
  }, [contentJson, editor]);

  useImperativeHandle(
    ref,
    () => ({
      getSelectedText() {
        if (!editor) return "";
        const { from, to } = editor.state.selection;
        if (from === to) return "";
        return editor.state.doc.textBetween(from, to, "\n").trim();
      },
    }),
    [editor]
  );

  return <EditorContent editor={editor} />;
});
