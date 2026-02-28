"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Send, Loader2, Download, Trash2, Bot, User, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { PrepMessage, PrepMode, PREP_MODE_LABELS } from "@/lib/api";

// ── Tool activity types ────────────────────────────────────────────────────────

export interface ToolActivity {
  tool:    string;
  status:  "running" | "done" | "error";
  summary: string;
}

const TOOL_LABELS: Record<string, string> = {
  search_judgments: "Searching IndianKanoon",
  search_resources: "Searching legal resources",
  draft_document:   "Drafting document",
  get_case_status:  "Fetching case status",
  search_web:       "Searching the web",
};

function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? `Running ${tool.replace(/_/g, " ")}`;
}

// ── Tool indicator bubble ─────────────────────────────────────────────────────

function ToolIndicator({ activity }: { activity: ToolActivity }) {
  const isDone    = activity.status === "done";
  const isRunning = activity.status === "running";

  return (
    <div className="flex items-center gap-2 rounded-lg border border-cyan-100 bg-cyan-50 px-3 py-2 text-xs text-cyan-700">
      {isRunning ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-cyan-500" />
      ) : (
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-cyan-500" />
      )}
      <span className="font-medium">{toolLabel(activity.tool)}</span>
      {isDone && activity.summary && (
        <span className="ml-1 text-cyan-600">— {activity.summary}</span>
      )}
      {isRunning && <span className="text-cyan-500">…</span>}
    </div>
  );
}

// ── Markdown-lite renderer ────────────────────────────────────────────────────

function renderMarkdown(text: string): React.ReactNode {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let key = 0;

  const inline = (s: string): React.ReactNode =>
    s.split(/(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, i) => {
      if (part.startsWith("***") && part.endsWith("***"))
        return <strong key={i}><em>{part.slice(3, -3)}</em></strong>;
      if (part.startsWith("**") && part.endsWith("**"))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("*") && part.endsWith("*"))
        return <em key={i}>{part.slice(1, -1)}</em>;
      return part;
    });

  for (const line of lines) {
    const k = key++;
    if (line.startsWith("### "))
      { nodes.push(<h3 key={k} className="mt-3 mb-0.5 text-sm font-bold text-slate-800">{inline(line.slice(4))}</h3>); continue; }
    if (line.startsWith("## "))
      { nodes.push(<h2 key={k} className="mt-3 mb-0.5 text-sm font-bold text-slate-900">{inline(line.slice(3))}</h2>); continue; }
    if (line.startsWith("# "))
      { nodes.push(<h1 key={k} className="mt-3 mb-0.5 text-base font-bold text-slate-900">{inline(line.slice(2))}</h1>); continue; }
    if (/^[-*•]\s/.test(line))
      { nodes.push(<li key={k} className="ml-4 list-disc text-slate-700">{inline(line.replace(/^[-*•]\s/, ""))}</li>); continue; }
    if (/^\d+\.\s/.test(line))
      { nodes.push(<li key={k} className="ml-4 list-decimal text-slate-700">{inline(line.replace(/^\d+\.\s/, ""))}</li>); continue; }
    if (/^[-=]{3,}$/.test(line.trim()))
      { nodes.push(<hr key={k} className="my-2 border-slate-200" />); continue; }
    if (!line.trim())
      { nodes.push(<div key={k} className="h-1" />); continue; }
    nodes.push(<p key={k} className="text-slate-700">{inline(line)}</p>);
  }
  return <>{nodes}</>;
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  msg,
  isStreaming = false,
}: {
  msg:         PrepMessage;
  isStreaming?: boolean;
}) {
  const isUser = msg.role === "user";

  return (
    <div className={cn("flex gap-2.5", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"
        )}
      >
        {isUser ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
      </div>

      <div
        className={cn(
          "max-w-[82%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-tr-sm bg-indigo-600 text-white"
            : "rounded-tl-sm border border-slate-200 bg-white text-slate-800 shadow-sm"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div className="space-y-0.5">
            {renderMarkdown(msg.content)}
            {isStreaming && (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse rounded-sm bg-slate-400" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface PrepChatPanelProps {
  messages:        PrepMessage[];
  mode:            PrepMode;
  streamingText:   string;
  isStreaming:     boolean;
  isDisabled:      boolean;
  toolActivities?: ToolActivity[];
  onSend:          (msg: string) => void;
  onExport:        () => void;
  onClearSession?: () => void;
  exportLoading?:  boolean;
}

export function PrepChatPanel({
  messages,
  mode,
  streamingText,
  isStreaming,
  isDisabled,
  toolActivities = [],
  onSend,
  onExport,
  onClearSession,
  exportLoading = false,
}: PrepChatPanelProps) {
  const [input,    setInput]    = useState("");
  const bottomRef               = useRef<HTMLDivElement>(null);
  const textareaRef             = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, toolActivities]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [input]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming || isDisabled) return;
    onSend(trimmed);
    setInput("");
  }, [input, isStreaming, isDisabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const streamingMsg = streamingText
    ? { role: "assistant" as const, content: streamingText }
    : null;

  const isEmpty = messages.length === 0 && !streamingMsg && toolActivities.length === 0;

  return (
    <div className="flex h-full flex-col">

      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
        <span className="text-xs text-slate-400">
          Mode:{" "}
          <span className="font-semibold text-indigo-600">
            {PREP_MODE_LABELS[mode]}
          </span>
        </span>
        <div className="flex items-center gap-2">
          {onClearSession && messages.length > 0 && (
            <button
              onClick={onClearSession}
              disabled={isStreaming}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs text-slate-400 transition hover:bg-slate-100 hover:text-red-500 disabled:opacity-40"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </button>
          )}
          <button
            onClick={onExport}
            disabled={exportLoading || messages.length === 0 || isStreaming}
            className="flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 transition hover:bg-indigo-100 disabled:opacity-40"
          >
            {exportLoading
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : <Download className="h-3.5 w-3.5" />}
            Export Brief
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 p-4">
        {isEmpty && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50">
              <Bot className="h-6 w-6 text-indigo-400" />
            </div>
            {isDisabled ? (
              <>
                <p className="text-sm font-medium text-slate-600">
                  {mode === "precedent_finder"
                    ? "Click Start Session to begin searching"
                    : "Select documents to begin"}
                </p>
                <p className="max-w-xs text-xs text-slate-400">
                  {mode === "precedent_finder"
                    ? "Precedent Finder uses IndianKanoon to search Kerala HC case law — no documents required."
                    : "Choose one or more case documents from the right panel, then click Start Session."}
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-slate-600">
                  Session ready — ask anything
                </p>
                <p className="max-w-xs text-xs text-slate-400">
                  {mode === "precedent_finder"
                    ? "Ask Claude to find precedents for any legal issue in your case."
                    : `Type a question or ask Claude to start in ${PREP_MODE_LABELS[mode]} mode.`}
                </p>
              </>
            )}
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}

        {/* Tool search indicators — shown in real time during Precedent Finder */}
        {toolActivities.map((activity, i) => (
          <ToolIndicator key={`tool-${i}`} activity={activity} />
        ))}

        {streamingMsg && <MessageBubble msg={streamingMsg} isStreaming />}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 bg-white p-3">
        <div
          className={cn(
            "flex items-end gap-2 rounded-xl border bg-white px-3 py-2 transition-all",
            isDisabled
              ? "border-slate-100 bg-slate-50 opacity-60"
              : "border-slate-200 shadow-sm focus-within:border-indigo-400 focus-within:ring-1 focus-within:ring-indigo-200"
          )}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isDisabled || isStreaming}
            placeholder={
              isDisabled
                ? "Start a session to chat…"
                : mode === "precedent_finder"
                  ? "Ask for precedents… e.g. \"Find bail judgments under NDPS Act\""
                  : "Ask a question… (Enter to send, Shift+Enter for new line)"
            }
            className="flex-1 resize-none bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
            style={{ maxHeight: 160 }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming || isDisabled}
            className={cn(
              "mb-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-all",
              !input.trim() || isStreaming || isDisabled
                ? "bg-slate-100 text-slate-400"
                : "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm"
            )}
          >
            {isStreaming
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : <Send className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}
