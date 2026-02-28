"use client";

import { useMemo, useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Doc = {
  id: string;
  title: string;
  content: string;
};

function parseDocs(raw: string): Doc[] {
  const trimmed = raw.trim();
  if (!trimmed) return [];

  const blocks = trimmed.split(/\n(?=# )/);

  return blocks
    .map((block, idx) => {
      const clean = block.trim();
      if (!clean) return null;
      const [firstLine, ...rest] = clean.split("\n");
      const title = firstLine.replace(/^#\s*/, "").trim() || "Untitled";
      const id =
        "doc-" +
        idx +
        "-" +
        title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      return {
        id,
        title,
        content: clean,
      };
    })
    .filter((d): d is Doc => Boolean(d));
}

export function HelpCenterClient({ raw }: { raw: string }) {
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);

  const docs = useMemo(() => parseDocs(raw), [raw]);

  const filtered = useMemo(() => {
    if (!query.trim()) return docs;
    const q = query.toLowerCase();
    return docs.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        d.content.toLowerCase().includes(q)
    );
  }, [docs, query]);

  useEffect(() => {
    if (!docs.length) return;
    if (!activeId) {
      setActiveId(docs[0].id);
      return;
    }
    const stillVisible = filtered.some((d) => d.id === activeId);
    if (!stillVisible && filtered[0]) {
      setActiveId(filtered[0].id);
    }
  }, [docs, filtered, activeId]);

  if (!docs.length) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold text-slate-900">
          Help Center
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Documentation will appear here once it is configured.
        </p>
      </div>
    );
  }

  const activeDoc =
    filtered.find((d) => d.id === activeId) ?? filtered[0] ?? docs[0];

  return (
    <div className="flex h-full flex-col bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-xl font-semibold text-slate-900">
          Help Center
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Search across LawMate documentation to learn how each page and
          workflow works.
        </p>
        <div className="mt-4 max-w-xl">
          <Input
            placeholder="Search help articles (features, pages, workflows)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="bg-slate-50"
          />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 divide-x divide-slate-200">
        <aside className="w-72 flex-shrink-0 bg-slate-50">
          <div className="h-full overflow-y-auto px-3 py-4">
            <ul className="space-y-1 text-sm">
              {filtered.map((doc) => {
                const isActive = doc.id === activeId;
                return (
                  <li key={doc.id}>
                    <button
                      type="button"
                      onClick={() => setActiveId(doc.id)}
                      className={cn(
                        "w-full rounded-md px-3 py-2 text-left transition-colors",
                        isActive
                          ? "bg-indigo-600 text-white"
                          : "text-slate-700 hover:bg-slate-200"
                      )}
                    >
                      {doc.title}
                    </button>
                  </li>
                );
              })}
              {!filtered.length && (
                <li className="px-3 py-2 text-xs text-slate-500">
                  No articles match your search.
                </li>
              )}
            </ul>
          </div>
        </aside>

        <section className="flex-1 bg-white">
          <div className="prose prose-slate max-w-none px-6 py-6 text-slate-800 prose-headings:font-semibold prose-headings:text-slate-900 prose-h1:text-2xl prose-h2:mt-8 prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2 prose-h2:text-lg prose-h3:mt-6 prose-h3:text-base prose-p:leading-relaxed prose-ul:my-3 prose-li:my-1 prose-strong:font-semibold prose-strong:text-slate-900">
            {activeDoc?.content && (
              <ReactMarkdown
                components={{
                  h1: ({ children }) => (
                    <h1 className="text-2xl font-semibold text-slate-900">
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="mt-8 border-b border-slate-200 pb-2 text-lg font-semibold text-slate-900">
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="mt-6 text-base font-semibold text-slate-900">
                      {children}
                    </h3>
                  ),
                  p: ({ children }) => (
                    <p className="my-2 leading-relaxed text-slate-700">
                      {children}
                    </p>
                  ),
                  ul: ({ children }) => (
                    <ul className="my-3 list-disc space-y-1 pl-6 text-slate-700">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="my-3 list-decimal space-y-1 pl-6 text-slate-700">
                      {children}
                    </ol>
                  ),
                  li: ({ children }) => (
                    <li className="my-0.5">{children}</li>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-semibold text-slate-900">
                      {children}
                    </strong>
                  ),
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      target={href?.startsWith("http") ? "_blank" : undefined}
                      rel={href?.startsWith("http") ? "noopener noreferrer" : undefined}
                      className="text-indigo-600 underline hover:text-indigo-800"
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {activeDoc.content}
              </ReactMarkdown>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default HelpCenterClient;

