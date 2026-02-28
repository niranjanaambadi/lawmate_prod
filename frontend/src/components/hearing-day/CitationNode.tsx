"use client";

import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";
import { CitationView } from "./CitationView";

export interface CitationAttributes {
  anchorId: string;
  docId: string;
  pageNumber: number;
  quoteText: string;
  bbox?: { left: number; top: number; width: number; height: number };
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    citation: {
      setCitation: (attrs: CitationAttributes) => ReturnType;
      insertCitation: (attrs: CitationAttributes) => ReturnType;
    };
  }
}

export const CitationExtension = Node.create({
  name: "citation",

  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      anchorId: { default: "" },
      docId: { default: "" },
      pageNumber: { default: 1 },
      quoteText: { default: "" },
      bbox: { default: null },
    };
  },

  addCommands() {
    return {
      setCitation:
        (attrs) =>
        ({ chain }) =>
          chain().focus().insertContent({ type: this.name, attrs }).run(),
      insertCitation:
        (attrs) =>
        ({ chain }) =>
          chain().focus().insertContent({ type: this.name, attrs }).run(),
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-type="citation"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes({ "data-type": "citation" }, this.options.HTMLAttributes, HTMLAttributes),
      `[${HTMLAttributes.quoteText?.slice(0, 30) ?? "cite"}…]`,
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(CitationView);
  },
});
