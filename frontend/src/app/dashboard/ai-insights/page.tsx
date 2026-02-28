"use client";
import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import {
  getCases,
  extractDocument,
  initiateUpload,
  confirmDocumentUpload,
  chatAboutDocument,
  type CaseOption,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileText, Loader2, Upload, CheckCircle2, MessageCircle, Send, Sparkles, Database } from "lucide-react";
import { NotebookDrawer, NotebookToggleButton } from "@/components/notebooks/NotebookDrawer";

type Step = "upload" | "extracted" | "saved";

export default function AIInsightsPage() {
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("upload");
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [extractedText, setExtractedText] = useState("");
  const [pageCount, setPageCount] = useState(0);
  const [processingMode, setProcessingMode] = useState<"text_only" | "full_visual">("full_visual");
  const [useVisualMode, setUseVisualMode] = useState(true);

  const [cases, setCases] = useState<CaseOption[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [documentTitle, setDocumentTitle] = useState("");
  const [category, setCategory] = useState("case_file");

  const [chatMessages, setChatMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    getCases(token)
      .then((list) => setCases(Array.isArray(list) ? list : []))
      .catch(() => setCases([]));
  }, [token]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setFile(f ?? null);
    setError(null);
    if (f?.name) setDocumentTitle(f.name.replace(/\.pdf$/i, ""));
  };

  const handleExtract = async () => {
    if (!file) return;
    if (!token) {
      setError("Please sign in again. Your session may have expired.");
      return;
    }
    setExtracting(true);
    setError(null);
    try {
      const result = await extractDocument(file, token, useVisualMode);
      setExtractedText(result.extractedText);
      setPageCount(result.pageCount);
      setProcessingMode(result.processingMode);
      setStep("extracted");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  const handleSaveToCase = async () => {
    if (!file || !token || !selectedCaseId) {
      setError("Please select a case and enter a document title.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { documentId, uploadUrl } = await initiateUpload(
        {
          caseId: selectedCaseId,
          category,
          title: documentTitle || file.name,
          fileName: file.name,
          fileSize: file.size,
          contentType: file.type || "application/pdf",
          extractedText: extractedText.trim() || undefined,
        },
        token
      );
      const putRes = await fetch(uploadUrl, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": file.type || "application/pdf" },
      });
      if (!putRes.ok) throw new Error("Upload to storage failed");
      await confirmDocumentUpload(documentId, token);
      setStep("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save to case failed");
    } finally {
      setSaving(false);
    }
  };

  const handleChatSend = async () => {
    const q = chatInput.trim();
    if (!q || !token || !extractedText.trim()) {
      if (!extractedText.trim()) setError("Extract a document first, or add text above to ask about.");
      return;
    }
    setChatLoading(true);
    setError(null);
    const userMessage: { role: "user"; content: string } = { role: "user", content: q };
    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    try {
      const history = chatMessages.map((m) => ({ role: m.role, content: m.content }));
      const { response } = await chatAboutDocument(
        { extractedText, question: q, conversationHistory: history },
        token
      );
      setChatMessages((prev) => [...prev, { role: "assistant", content: response }]);
    } catch (e) {
      setChatMessages((prev) => [...prev, { role: "assistant", content: (e instanceof Error ? e.message : "Request failed") }]);
    } finally {
      setChatLoading(false);
    }
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const modeLabel =
    processingMode === "full_visual" ? "Claude PDF Chat (full visual)" : "Converse Document Chat (text only)";
  const stepIndex = step === "upload" ? 1 : step === "extracted" ? 2 : 3;

  const [notebookOpen, setNotebookOpen] = useState(false);

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-800 p-6 text-slate-100 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">AI Insights</h1>
            <p className="mt-1 text-sm text-slate-300">
              Extract structured understanding from court PDFs, ask questions, and save results directly to a case.
            </p>
          </div>
          <div className="flex gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${stepIndex >= 1 ? "bg-white text-slate-900" : "bg-slate-700 text-slate-200"}`}>1. Upload</span>
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${stepIndex >= 2 ? "bg-white text-slate-900" : "bg-slate-700 text-slate-200"}`}>2. Analyze</span>
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${stepIndex >= 3 ? "bg-white text-slate-900" : "bg-slate-700 text-slate-200"}`}>3. Save</span>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Document Intake
            </CardTitle>
            <CardDescription>
              Choose processing mode and extract text from an uploaded PDF.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className={`cursor-pointer rounded-xl border p-4 transition ${useVisualMode ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-400"}`}>
                <div className="flex items-start gap-2">
                  <input
                    type="radio"
                    name="processingMode"
                    checked={useVisualMode}
                    onChange={() => setUseVisualMode(true)}
                    className="mt-1 h-4 w-4"
                  />
                  <div>
                    <p className="text-sm font-semibold">Claude PDF Chat</p>
                    <p className="mt-1 text-xs text-slate-600">Best for visual layouts, charts, and scanned complexity.</p>
                  </div>
                </div>
              </label>
              <label className={`cursor-pointer rounded-xl border p-4 transition ${!useVisualMode ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-400"}`}>
                <div className="flex items-start gap-2">
                  <input
                    type="radio"
                    name="processingMode"
                    checked={!useVisualMode}
                    onChange={() => setUseVisualMode(false)}
                    className="mt-1 h-4 w-4"
                  />
                  <div>
                    <p className="text-sm font-semibold">Text-only Extraction</p>
                    <p className="mt-1 text-xs text-slate-600">Faster and lower token usage for clean digital PDFs.</p>
                  </div>
                </div>
              </label>
            </div>

            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-2">
                <Label htmlFor="pdf-upload">PDF File</Label>
                <Input
                  id="pdf-upload"
                  type="file"
                  accept=".pdf,application/pdf"
                  onChange={onFileChange}
                  className="max-w-sm"
                />
              </div>
              <Button onClick={handleExtract} disabled={!file || !token || extracting}>
                {extracting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Extracting
                  </>
                ) : (
                  <>
                    <Upload className="mr-2 h-4 w-4" />
                    Extract Document
                  </>
                )}
              </Button>
            </div>

            {file && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                <p className="font-medium">{file.name}</p>
                <p className="text-xs text-slate-500">Size {(file.size / 1024).toFixed(1)} KB</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" />
              Session Summary
            </CardTitle>
            <CardDescription>Live status of this document analysis run.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="rounded-lg border p-3">
              <p className="text-xs uppercase tracking-wide text-slate-500">Mode</p>
              <p className="mt-1 font-medium text-slate-800">{modeLabel}</p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs uppercase tracking-wide text-slate-500">Pages Extracted</p>
              <p className="mt-1 font-medium text-slate-800">{pageCount || 0}</p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs uppercase tracking-wide text-slate-500">Current Step</p>
              <p className="mt-1 font-medium text-slate-800">{stepIndex}/3</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6">
            <p className="text-sm text-red-700">{error}</p>
          </CardContent>
        </Card>
      )}

      {step === "extracted" && (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <Card className="border-slate-200">
            <CardHeader>
              <CardTitle>Extracted Text Workspace</CardTitle>
              <CardDescription>
                {pageCount} page(s) processed in {modeLabel}. Edit the extracted text before saving.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <textarea
                value={extractedText}
                onChange={(e) => setExtractedText(e.target.value)}
                placeholder="(No text)"
                className="min-h-[460px] w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm font-mono whitespace-pre-wrap ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                spellCheck="false"
              />
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MessageCircle className="h-5 w-5" />
                  Document Q&A
                </CardTitle>
                <CardDescription>Ask focused questions using the current extracted text.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex max-h-80 flex-col overflow-hidden rounded-lg border bg-slate-50/50">
                  <div className="flex-1 space-y-3 overflow-y-auto p-3">
                    {chatMessages.length === 0 && (
                      <p className="text-sm text-slate-500">Try: &quot;Summarize key arguments&quot;, &quot;List parties and dates&quot;</p>
                    )}
                    {chatMessages.map((m, i) => (
                      <div
                        key={i}
                        className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${
                            m.role === "user" ? "bg-slate-900 text-white" : "bg-slate-200 text-slate-900"
                          }`}
                        >
                          {m.content}
                        </div>
                      </div>
                    ))}
                    {chatLoading && (
                      <div className="flex justify-start">
                        <div className="rounded-xl bg-slate-200 px-3 py-2 text-sm text-slate-600">
                          <Loader2 className="h-4 w-4 animate-spin" />
                        </div>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>
                  <div className="flex gap-2 border-t p-2">
                    <Input
                      placeholder="Ask a question..."
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleChatSend()}
                      disabled={chatLoading}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      onClick={handleChatSend}
                      disabled={chatLoading || !chatInput.trim()}
                      size="icon"
                      title="Send"
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle>
                  <span className="flex items-center gap-2">
                    <Database className="h-5 w-5" />
                    Save to Case
                  </span>
                </CardTitle>
                <CardDescription>Attach this AI-enhanced document to a case record.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="case-select">Case</Label>
                  <select
                    id="case-select"
                    value={selectedCaseId}
                    onChange={(e) => setSelectedCaseId(e.target.value)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                  >
                    <option value="">Select a case</option>
                    {cases.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.case_number || c.efiling_number} – {c.case_type ?? "Case"}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="doc-title">Document title</Label>
                  <Input
                    id="doc-title"
                    value={documentTitle}
                    onChange={(e) => setDocumentTitle(e.target.value)}
                    placeholder="e.g. Petition copy"
                  />
                </div>
                <div className="space-y-2 sm:max-w-xs">
                  <Label htmlFor="category-select">Category</Label>
                  <select
                    id="category-select"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                  >
                    <option value="case_file">Case file</option>
                    <option value="annexure">Annexure</option>
                    <option value="judgment">Judgment</option>
                    <option value="order">Order</option>
                    <option value="misc">Misc</option>
                  </select>
                </div>
                <Button onClick={handleSaveToCase} disabled={saving || !selectedCaseId}>
                  {saving ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Saving
                    </>
                  ) : (
                    "Save to case"
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {step === "saved" && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="pt-6 text-sm text-green-800">
            Document has been saved successfully. You can upload another file or continue asking questions.
          </CardContent>
        </Card>
      )}

      {/* ── Notebook drawer ──────────────────────────────────────────────── */}
      <NotebookToggleButton
        isOpen={notebookOpen}
        onClick={() => setNotebookOpen((v) => !v)}
        className="top-1/2 -translate-y-1/2"
      />
      <NotebookDrawer
        caseId={selectedCaseId || undefined}
        token={token}
        isOpen={notebookOpen}
        onClose={() => setNotebookOpen(false)}
      />
    </div>

  );
}
