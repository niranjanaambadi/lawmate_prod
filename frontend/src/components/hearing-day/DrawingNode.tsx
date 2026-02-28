"use client";

import { Node, mergeAttributes } from "@tiptap/core";

/** Simple drawing block: stores SVG or data URL. Can be replaced with Excalidraw/canvas later. */
export const DrawingExtension = Node.create({
  name: "drawing",

  group: "block",
  content: "inline*",
  atom: true,

  addAttributes() {
    return {
      src: { default: "" },
      width: { default: 400 },
      height: { default: 200 },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-type="drawing"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes({ "data-type": "drawing" }, this.options.HTMLAttributes, HTMLAttributes),
      ["div", { class: "rounded border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-sm text-slate-500" }, "Drawing block (stylus/canvas can be added here)"],
    ];
  },
});
