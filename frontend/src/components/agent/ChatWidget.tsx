"use client";

/**
 * src/components/agent/ChatWidget.tsx
 *
 * Reusable LawMate AI chat widget.
 *
 * Usage:
 *   <ChatWidget page="global" />
 *   <ChatWidget page="case_detail" caseId={caseId} defaultOpen />
 *   <ChatWidget page="hearing_day" caseId={caseId} defaultOpen />
 *   <ChatWidget page="cause_list" defaultOpen />
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Scale } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

// ── Types ────────────────────────────────────────────────────────────────────

type Page = "global" | "case_detail" | "hearing_day" | "cause_list";

interface ChatWidgetProps {
  page:         Page;
  caseId?:      string;
  defaultOpen?: boolean;
}

interface ChatMessage {
  id:      string;
  role:    "user" | "assistant";
  content: string;
  tools?:  ToolEvent[];
  error?:  boolean;
}

interface ToolEvent {
  tool:    string;
  success: boolean;
  summary: string;
}

// SSE event shapes from agent.py
type AgentEvent =
  | { type: "tool_start";  tool: string; input: Record<string, unknown> }
  | { type: "tool_end";    tool: string; success: boolean; summary: string }
  | { type: "text_delta";  text: string }
  | { type: "done";        full_text: string }
  | { type: "error";       message: string };

// ── Tool display names ───────────────────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  get_case_status:         "eCourts",
  get_hearing_history:     "Hearing History",
  get_cause_list:          "Cause List",
  get_advocate_cause_list: "KHC Digicourt",
  get_roster:              "KHC Roster",
  search_judgments:        "Judgments",
  search_resources:        "Legal Resources",
  create_calendar_event:   "Calendar",
  get_calendar_events:     "Calendar",
  delete_calendar_event:   "Calendar",
  draft_document:          "Draft",
};

const TOOL_ICONS: Record<string, string> = {
  get_case_status:         "⚖️",
  get_hearing_history:     "📋",
  get_cause_list:          "📅",
  get_advocate_cause_list: "🔍",
  get_roster:              "👨‍⚖️",
  search_judgments:        "📚",
  search_resources:        "📖",
  create_calendar_event:   "🗓️",
  get_calendar_events:     "🗓️",
  delete_calendar_event:   "🗓️",
  draft_document:          "✍️",
};

// Page-specific placeholder messages
const PLACEHOLDERS: Record<Page, string> = {
  global:       "Ask anything — case status, judgments, drafting...",
  case_detail:  "Ask about this case, find precedents, draft documents...",
  hearing_day:  "What happened last time? Get your item number. Draft arguments.",
  cause_list:   "Which court am I in first? How many cases today?",
};

const PAGE_GREETINGS: Record<Page, string> = {
  global:       "Hello! I'm your LawMate AI assistant. How can I help you today?",
  case_detail:  "I have this case loaded. Ask me about status, history, precedents, or I can draft something for you.",
  hearing_day:  "Ready for today's hearing. I can pull your item number, last order, or draft quick arguments.",
  cause_list:   "I can see your cause list. Ask me about your schedule, court halls, or judge assignments for today.",
};

// ── Unique ID ────────────────────────────────────────────────────────────────

let _id = 0;
const uid = () => `m_${++_id}_${Date.now()}`;

// ── Component ────────────────────────────────────────────────────────────────

export default function ChatWidget({ page, caseId, defaultOpen = false }: ChatWidgetProps) {
  const { token } = useAuth();

  const [isOpen,       setIsOpen]       = useState(defaultOpen);
  const [messages,     setMessages]     = useState<ChatMessage[]>([
    { id: uid(), role: "assistant", content: PAGE_GREETINGS[page] },
  ]);
  const [input,        setInput]        = useState("");
  const [isStreaming,  setIsStreaming]  = useState(false);
  const [activeTools,  setActiveTools]  = useState<string[]>([]);

  const conversationId = useRef(crypto.randomUUID());
  const bottomRef      = useRef<HTMLDivElement>(null);
  const inputRef       = useRef<HTMLTextAreaElement>(null);
  const abortRef       = useRef<AbortController | null>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 100);
  }, [isOpen]);

  // Build history for API (only text messages, no tool metadata)
  const buildHistory = useCallback((msgs: ChatMessage[]) =>
    msgs
      .filter(m => !m.error)
      .map(m => ({ role: m.role, content: m.content }))
      .slice(-20), // last 20 messages for context window management
  []);

  // ── Send message ────────────────────────────────────────────────────────────

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming || !token) return;

    // Append user message
    const userMsg: ChatMessage = { id: uid(), role: "user", content: text };
    setMessages(prev => {
      const next = [...prev, userMsg];

      // Append empty assistant message to stream into
      const assistantMsg: ChatMessage = {
        id:      uid(),
        role:    "assistant",
        content: "",
        tools:   [],
      };

      sendStream(next, [...next, assistantMsg]);
      return [...next, assistantMsg];
    });

    setInput("");
    setIsStreaming(true);
    setActiveTools([]);
  }, [input, isStreaming, token]); // eslint-disable-line

  const sendStream = useCallback(async (
    historyMsgs: ChatMessage[],
    allMsgs:     ChatMessage[],
  ) => {
    const assistantMsgId = allMsgs[allMsgs.length - 1].id;
    abortRef.current = new AbortController();

    try {
      const res = await fetch("/api/agent?stream=true", {
        method:  "POST",
        headers: {
          "Content-Type":  "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({
          message:         historyMsgs[historyMsgs.length - 1].content,
          page,
          case_id:         caseId ?? null,
          conversation_id: conversationId.current,
          history:         buildHistory(historyMsgs.slice(0, -1)),
        }),
        signal: abortRef.current.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Request failed: ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") break;

          let event: AgentEvent;
          try {
            event = JSON.parse(data);
          } catch {
            continue;
          }

          handleEvent(event, assistantMsgId);
        }
      }

    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;

      setMessages(prev => prev.map(m =>
        m.id === assistantMsgId
          ? { ...m, content: "Something went wrong. Please try again.", error: true }
          : m
      ));
    } finally {
      setIsStreaming(false);
      setActiveTools([]);
      abortRef.current = null;
    }
  }, [token, page, caseId, buildHistory]); // eslint-disable-line

  // ── Handle SSE events ───────────────────────────────────────────────────────

  const handleEvent = useCallback((event: AgentEvent, assistantMsgId: string) => {
    switch (event.type) {

      case "tool_start":
        setActiveTools(prev => [...new Set([...prev, event.tool])]);
        break;

      case "tool_end":
        setActiveTools(prev => prev.filter(t => t !== event.tool));
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, tools: [...(m.tools ?? []), { tool: event.tool, success: event.success, summary: event.summary }] }
            : m
        ));
        break;

      case "text_delta":
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, content: m.content + event.text }
            : m
        ));
        break;

      case "error":
        setMessages(prev => prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, content: `Error: ${event.message}`, error: true }
            : m
        ));
        break;
    }
  }, []);

  // ── Stop streaming ──────────────────────────────────────────────────────────

  const stopStreaming = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setActiveTools([]);
  };

  // ── Keyboard handling ───────────────────────────────────────────────────────

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Floating toggle button — only shown when widget is closed */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-2xl shadow-lg
                     bg-gray-900 text-white text-sm font-medium
                     hover:bg-gray-800 active:scale-95 transition-all duration-150"
          aria-label="Open LawMate AI"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-600">
            <Scale className="h-4 w-4 text-white" />
          </span>
          <span>LawMate AI</span>
        </button>
      )}

      {/* Chat panel */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col w-[420px] h-[620px] max-h-[90vh]
                        rounded-2xl shadow-2xl border border-gray-200 bg-white overflow-hidden">

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-gray-900 text-white shrink-0">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600">
                <Scale className="h-5 w-5 text-white" />
              </span>
              <div>
                <p className="text-sm font-semibold leading-none">LawMate AI</p>
                <p className="text-xs text-gray-400 mt-0.5">Kerala High Court Assistant</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Clear chat */}
              <button
                onClick={() => setMessages([{ id: uid(), role: "assistant", content: PAGE_GREETINGS[page] }])}
                className="text-gray-400 hover:text-white transition-colors text-xs px-2 py-1 rounded hover:bg-gray-700"
                title="Clear chat"
              >
                Clear
              </button>
              {/* Close */}
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-white transition-colors w-7 h-7 flex items-center justify-center rounded hover:bg-gray-700"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Active tool indicators */}
          {activeTools.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-4 py-2 bg-blue-50 border-b border-blue-100 shrink-0">
              {activeTools.map(tool => (
                <span key={tool} className="inline-flex items-center gap-1 text-xs bg-white border border-blue-200
                                            text-blue-700 px-2 py-0.5 rounded-full shadow-sm animate-pulse">
                  <span>{TOOL_ICONS[tool] ?? "🔧"}</span>
                  <span>{TOOL_LABELS[tool] ?? tool}</span>
                  <span className="text-blue-400">···</span>
                </span>
              ))}
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scroll-smooth">
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="px-4 py-3 border-t border-gray-100 bg-gray-50 shrink-0">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={PLACEHOLDERS[page]}
                disabled={isStreaming}
                rows={1}
                className="flex-1 resize-none rounded-xl border border-gray-200 bg-white px-3 py-2.5
                           text-sm text-gray-900 placeholder-gray-400 outline-none
                           focus:border-gray-400 focus:ring-2 focus:ring-gray-100
                           disabled:opacity-50 disabled:cursor-not-allowed
                           max-h-32 overflow-y-auto leading-relaxed"
                style={{ minHeight: "42px" }}
                onInput={e => {
                  const el = e.currentTarget;
                  el.style.height = "auto";
                  el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
                }}
              />

              {isStreaming ? (
                <button
                  onClick={stopStreaming}
                  className="shrink-0 w-10 h-10 rounded-xl bg-red-500 hover:bg-red-600
                             text-white flex items-center justify-center transition-colors"
                  aria-label="Stop"
                >
                  ⏹
                </button>
              ) : (
                <button
                  onClick={sendMessage}
                  disabled={!input.trim()}
                  className="shrink-0 w-10 h-10 rounded-xl bg-gray-900 hover:bg-gray-700
                             text-white flex items-center justify-center transition-colors
                             disabled:opacity-30 disabled:cursor-not-allowed active:scale-95"
                  aria-label="Send"
                >
                  ↑
                </button>
              )}
            </div>
            <p className="mt-1.5 text-[10px] text-gray-400 text-center">
              Enter to send · Shift+Enter for new line
            </p>
          </div>

        </div>
      )}
    </>
  );
}

// ── MessageBubble sub-component ──────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>

      {/* Tool source badges — shown above assistant message */}
      {!isUser && message.tools && message.tools.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {message.tools.map((t, i) => (
            <span
              key={i}
              className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full
                          border font-medium
                          ${t.success
                            ? "bg-green-50 border-green-200 text-green-700"
                            : "bg-red-50 border-red-200 text-red-600"}`}
            >
              <span>{TOOL_ICONS[t.tool] ?? "🔧"}</span>
              <span>{t.summary}</span>
            </span>
          ))}
        </div>
      )}

      {/* Bubble */}
      <div
        className={`max-w-[88%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed
                    ${isUser
                      ? "bg-gray-900 text-white rounded-br-sm"
                      : message.error
                        ? "bg-red-50 text-red-700 border border-red-200 rounded-bl-sm"
                        : "bg-gray-100 text-gray-900 rounded-bl-sm"}`}
      >
        {/* Empty state while streaming */}
        {!isUser && !message.content && !message.error && (
          <span className="flex gap-1 items-center text-gray-400">
            <span className="animate-bounce" style={{ animationDelay: "0ms"   }}>·</span>
            <span className="animate-bounce" style={{ animationDelay: "150ms" }}>·</span>
            <span className="animate-bounce" style={{ animationDelay: "300ms" }}>·</span>
          </span>
        )}

        {/* Message content — preserve newlines */}
        {message.content && (
          <span style={{ whiteSpace: "pre-wrap" }}>{message.content}</span>
        )}
      </div>

    </div>
  );
}
