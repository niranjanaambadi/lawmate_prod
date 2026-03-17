"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Send, Loader2, FileText, Pencil, AlertTriangle, Trash2, ArrowRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useWorkspaceStore } from "@/stores/workspaceStore";

// ── Message types ──────────────────────────────────────────────────────────────

interface ContextMismatchPayload {
  reason:   string;
  onClear:  () => void;
  onKeep:   () => void;
}

interface Message {
  role:                "user" | "assistant" | "system";
  content:             string;
  citedDocIds?:        string[];
  isThinking?:         boolean;
  contextMismatch?:    ContextMismatchPayload;
}

// ── Sub-component: inline confirmation card ───────────────────────────────────

function ContextMismatchCard({ payload }: { payload: ContextMismatchPayload }) {
  const [clearing, setClearing] = useState(false);

  const handleClear = async () => {
    setClearing(true);
    await payload.onClear();
  };

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm space-y-2">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
        <div>
          <p className="font-medium text-amber-800">New case detected</p>
          {payload.reason && (
            <p className="text-amber-700 text-xs mt-0.5">{payload.reason}</p>
          )}
          <p className="text-amber-700 text-xs mt-1">
            Clear all documents and start fresh for this new matter?
          </p>
        </div>
      </div>
      <div className="flex gap-2 pt-1">
        <button
          onClick={handleClear}
          disabled={clearing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 text-white text-xs font-medium hover:bg-amber-700 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {clearing
            ? <Loader2 className="h-3 w-3 animate-spin" />
            : <Trash2 className="h-3 w-3" />}
          Yes, clear workspace
        </button>
        <button
          onClick={payload.onKeep}
          disabled={clearing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-300 text-amber-700 text-xs font-medium hover:bg-amber-100 disabled:opacity-60"
        >
          <ArrowRight className="h-3 w-3" />
          No, keep going
        </button>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  workspaceId:        string;
  token:              string;
  onDraftFromMessage: (text: string) => void;
  disabled?:          boolean;
}

export default function ChatPanel({ workspaceId, token, onDraftFromMessage, disabled }: Props) {
  const [messages,  setMessages]  = useState<Message[]>([]);
  const [input,     setInput]     = useState("");
  const [streaming, setStreaming] = useState(false);
  const [thinking,  setThinking]  = useState(false);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const abortRef    = useRef<() => void>(() => {});

  const clearDocuments = useWorkspaceStore((s) => s.clearDocuments);

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Core send — optionally bypass shift detection on retry
  const sendMessage = useCallback(async (
    text: string,
    history: { role: string; content: string }[],
    skipShiftDetection: boolean,
  ) => {
    setStreaming(true);
    setThinking(false);

    // Add placeholder assistant message
    setMessages((prev) => [...prev, { role: "assistant", content: "", isThinking: false }]);

    const { streamDraftingChat, clearWorkspaceDocuments } = await import("@/lib/api");

    const cleanup = streamDraftingChat(
      workspaceId,
      text,
      history,
      token,
      {
        onDelta: (chunk) => {
          setThinking(false);
          setMessages((prev) => {
            const msgs = [...prev];
            const last  = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { ...last, content: last.content + chunk };
            }
            return msgs;
          });
        },
        onThinking: () => setThinking(true),
        onCitedDocs: (ids) => {
          setMessages((prev) => {
            const msgs = [...prev];
            const last  = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { ...last, citedDocIds: ids };
            }
            return msgs;
          });
        },

        // ── Topic-shift: replace placeholder with inline card ──────────────
        onContextMismatch: (reason) => {
          setStreaming(false);
          setThinking(false);

          setMessages((prev) => {
            const msgs = [...prev];
            // Replace the empty assistant placeholder with the card
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant" && !last.content) {
              msgs[msgs.length - 1] = {
                role:    "system",
                content: "",
                contextMismatch: {
                  reason,
                  onClear: async () => {
                    // 1. Delete all docs via API
                    await clearWorkspaceDocuments(workspaceId, token);
                    // 2. Sync store (removes doc badges, resets context panel)
                    clearDocuments(workspaceId);
                    // 3. Remove card from history
                    setMessages((m) => m.filter((msg) => !msg.contextMismatch));
                    // 4. Re-send the original message, skipping detection
                    setMessages((m) => [...m, { role: "user", content: text }]);
                    sendMessage(text, [], true);
                  },
                  onKeep: () => {
                    // Remove the card, re-send with detection bypassed
                    setMessages((m) => m.filter((msg) => !msg.contextMismatch));
                    setMessages((m) => [...m, { role: "user", content: text }]);
                    sendMessage(text, history, true);
                  },
                },
              };
            }
            return msgs;
          });
        },

        onDone: (fullText) => {
          setStreaming(false);
          setThinking(false);
          setMessages((prev) => {
            const msgs = [...prev];
            const last  = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { ...last, content: fullText };
            }
            return msgs;
          });
        },
        onError: (msg) => {
          setStreaming(false);
          setThinking(false);
          setMessages((prev) => [
            ...prev.slice(0, -1),
            { role: "assistant", content: `⚠️ ${msg}` },
          ]);
        },
      },
      skipShiftDetection,
    );
    abortRef.current = cleanup;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, token, clearDocuments]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming || disabled) return;

    setInput("");
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    await sendMessage(text, history, false);
  }, [input, streaming, disabled, messages, sendMessage]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-slate-400 text-sm mt-8">
            <p>Ask anything about your uploaded documents</p>
            <p className="text-xs mt-1 text-slate-300">
              or request a draft: "Draft a bail application based on these documents"
            </p>
          </div>
        )}

        {messages.map((msg, idx) => {
          // ── Inline mismatch card ─────────────────────────────────────────
          if (msg.contextMismatch) {
            return (
              <div key={idx} className="flex justify-start">
                <div className="max-w-[90%] w-full">
                  <ContextMismatchCard payload={msg.contextMismatch} />
                </div>
              </div>
            );
          }

          // ── Regular chat bubble ──────────────────────────────────────────
          return (
            <div
              key={idx}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={[
                  "max-w-[85%] rounded-xl px-3 py-2 text-sm",
                  msg.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-100 text-slate-800",
                ].join(" ")}
              >
                {msg.role === "user" ? (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <>
                    {msg.isThinking && streaming && !msg.content && (
                      <div className="flex items-center gap-2 text-slate-400 text-xs">
                        <Loader2 className="h-3 w-3 animate-spin" /> Thinking…
                      </div>
                    )}
                    {msg.content && (
                      <div className="prose prose-sm max-w-none prose-slate">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    )}
                    {streaming && idx === messages.length - 1 && msg.content && (
                      <span className="inline-block w-1.5 h-3.5 bg-slate-400 animate-pulse ml-0.5" />
                    )}
                    {/* Cited docs */}
                    {msg.citedDocIds && msg.citedDocIds.length > 0 && (
                      <div className="mt-1.5 flex gap-1 flex-wrap">
                        {msg.citedDocIds.map((id) => (
                          <span key={id} className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 bg-indigo-100 text-indigo-600 rounded-full">
                            <FileText className="h-2.5 w-2.5" /> {id.slice(0, 8)}…
                          </span>
                        ))}
                      </div>
                    )}
                    {/* Draft-from-this button */}
                    {msg.content && !streaming && (
                      <button
                        onClick={() => onDraftFromMessage(msg.content)}
                        className="mt-2 flex items-center gap-1 text-[11px] text-indigo-600 hover:text-indigo-700"
                      >
                        <Pencil className="h-3 w-3" /> Draft from this
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-slate-200 p-2 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          rows={2}
          placeholder="Ask a question or request a draft…"
          disabled={streaming || disabled}
          className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-60"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || streaming || disabled}
          className="h-9 w-9 flex items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
        >
          {streaming
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : <Send className="h-4 w-4" />
          }
        </button>
      </div>
    </div>
  );
}
