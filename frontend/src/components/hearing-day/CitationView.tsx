"use client";

import { NodeViewWrapper } from "@tiptap/react";

export function CitationView({ node }: { node: { attrs: Record<string, unknown> } }) {
  const quoteText = (node.attrs.quoteText as string) ?? "";
  const label = quoteText.length > 40 ? quoteText.slice(0, 40) + "…" : quoteText;

  return (
    <NodeViewWrapper as="span" className="inline">
      <span
        role="button"
        tabIndex={0}
        className="cursor-pointer rounded bg-primary/15 px-1.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/25"
        data-doc-id={node.attrs.docId}
        data-page-number={node.attrs.pageNumber}
        data-anchor-id={node.attrs.anchorId}
        data-quote={quoteText}
        data-bbox={typeof node.attrs.bbox === "object" ? JSON.stringify(node.attrs.bbox) : undefined}
        onClick={(e) => {
          e.currentTarget.dispatchEvent(
            new CustomEvent("citation-click", { detail: node.attrs, bubbles: true })
          );
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            (e.currentTarget as HTMLElement).click();
          }
        }}
      >
        📎 {label || "Citation"}
      </span>
    </NodeViewWrapper>
  );
}
