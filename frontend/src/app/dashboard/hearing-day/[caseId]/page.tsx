"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

import {
  getCaseById,
  getCaseDocuments,
  getHearingNote,
  putHearingNote,
  createHearingCitation,
  enrichHearingNote,
  getHearingNoteEnrichment,
  importLocalDocument,
  type DocumentListItem,
  type HearingNoteEnrichment,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Paperclip, Upload, X } from "lucide-react";
import CaseBundleWorkspaceTrial2 from "@/components/hearing-day/CaseBundleWorkspaceTrial2";
import ChatWidget from "@/components/agent/ChatWidget";

export default function HearingDayCasePage() {
  const params = useParams();
  const router = useRouter();
  const caseId = String(params?.caseId ?? "");
  const { token } = useAuth();

  const [caseTitle, setCaseTitle] = useState("Hearing Day");

  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  const [viewUrl, setViewUrl] = useState<string | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [noteVersion, setNoteVersion] = useState(1);
  const [noteContentJson, setNoteContentJson] = useState<Record<string, unknown> | null>(null);
  const [noteContentText, setNoteContentText] = useState("");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  const [enrichment, setEnrichment] = useState<HearingNoteEnrichment | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [enrichmentMsg, setEnrichmentMsg] = useState<string | null>(null);

  const [manualUrlInput, setManualUrlInput] = useState("");
  const [manualPdfUrl, setManualPdfUrl] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId || !token) return;
    setLoading(true);
    setError(null);

    Promise.all([
      getCaseById(caseId, token).catch(() => null),
      getCaseDocuments(caseId, token),
      getHearingNote(caseId, token).catch(() => null),
      getHearingNoteEnrichment(caseId, token).catch(() => null),
    ])
      .then(([caseRes, docRes, noteRes, enrichRes]) => {
        if (caseRes) {
          const label = String(caseRes.case_number || caseRes.efiling_number || "Hearing Day");
          setCaseTitle(label);
        }

        const docs = docRes.data ?? [];
        setDocuments(docs);
        setActiveDocId((prev) => (prev && docs.some((d) => d.id === prev) ? prev : docs[0]?.id ?? null));

        if (noteRes) {
          setNoteVersion(noteRes.version);
          setNoteContentJson(noteRes.content_json ?? null);
          setNoteContentText(noteRes.content_text ?? "");
        } else {
          setNoteVersion(1);
          setNoteContentJson(null);
          setNoteContentText("");
        }

        setEnrichment(enrichRes);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load case bundle"))
      .finally(() => setLoading(false));
  }, [caseId, token]);

  useEffect(() => {
    if (!activeDocId || !token) {
      setViewUrl(null);
      return;
    }

    let cancelled = false;
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }

    const baseUrl = (
      typeof window !== "undefined"
        ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
        : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    ).replace(/\/$/, "");
    const backendUrl = `${baseUrl}/api/v1/documents/${activeDocId}/content`;

    fetch(backendUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/pdf",
      },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        const nextUrl = URL.createObjectURL(blob);
        objectUrlRef.current = nextUrl;
        setViewUrl(nextUrl);
      })
      .catch((e) => {
        if (!cancelled) {
          setViewUrl(null);
          setError(e instanceof Error ? e.message : "Failed loading document");
        }
      });

    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [activeDocId, token]);

  const saveNotes = useCallback(
    async (payload: {
      contentJson: Record<string, unknown>;
      contentText: string;
      citations: Array<{ text: string; quoteText: string; pageNumber: number; docId: string | null; anchorId: string }>;
    }) => {
      if (!caseId || !token) return;
      setSaveStatus("saving");
      setError(null);
      try {
        const updated = await putHearingNote(
          caseId,
          { content_json: payload.contentJson, content_text: payload.contentText, version: noteVersion },
          token
        );

        setNoteVersion(updated.version);
        setNoteContentJson(payload.contentJson);
        setNoteContentText(payload.contentText);

        if (payload.citations.length > 0) {
          await Promise.all(
            payload.citations
              .filter((c) => (c.docId || activeDocId) && c.pageNumber > 0)
              .map((c) =>
                createHearingCitation(
                  caseId,
                  {
                    hearing_note_id: updated.id,
                    doc_id: c.docId || activeDocId || "",
                    page_number: c.pageNumber,
                    quote_text: c.quoteText || c.text,
                    anchor_id: c.anchorId || crypto.randomUUID?.() || `cite-${Date.now()}`,
                  },
                  token
                ).catch(() => null)
              )
          );
        }

        setSaveStatus("saved");
        setTimeout(() => setSaveStatus("idle"), 1500);
      } catch (e) {
        setSaveStatus("error");
        setError(e instanceof Error ? e.message : "Failed to save notes");
      }
    },
    [caseId, token, noteVersion, activeDocId]
  );

  const runEnrich = useCallback(async () => {
    if (!caseId || !token) return;
    setEnriching(true);
    setEnrichmentMsg(null);
    try {
      const res = await enrichHearingNote(caseId, token);
      setEnrichment(res.enrichment);
      if (res.from_cache) setEnrichmentMsg("Loaded cached enrichment");
      else if (res.deterministic_only) setEnrichmentMsg("Deterministic enrichment only (LLM unavailable)");
      else setEnrichmentMsg("Enriched with deterministic + LLM");
    } catch (e) {
      setEnrichmentMsg(e instanceof Error ? e.message : "Enrichment failed");
    } finally {
      setEnriching(false);
    }
  }, [caseId, token]);

  const handleUploadPdf = async () => {
    if (!uploadFile || !token || !caseId) return;
    try {
      setUploading(true);
      setUploadError(null);
      const doc = await importLocalDocument(
        {
          caseId,
          title: uploadTitle.trim() || uploadFile.name.replace(/\.pdf$/i, ""),
          category: "hearing_prep",
          file: uploadFile,
        },
        token
      );
      // Refresh document list and auto-activate the new upload
      const docRes = await getCaseDocuments(caseId, token);
      const docs = docRes.data ?? [];
      setDocuments(docs);
      setActiveDocId(doc.id);
      setManualPdfUrl(null);
      // Reset form
      setUploadFile(null);
      setUploadTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const effectivePdfUrl = manualPdfUrl || viewUrl || undefined;
  const backendFileSource =
    !manualPdfUrl && activeDocId && token
      ? {
          url: `${(
            typeof window !== "undefined"
              ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
              : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
          ).replace(/\/$/, "")}/api/v1/documents/${activeDocId}/content`,
          httpHeaders: {
            Authorization: `Bearer ${token}`,
          },
        }
      : null;

  return (
    <>
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">{caseTitle}</h1>
            <p className="mt-1 text-sm text-slate-600">Case bundle workspace with notes, citations, and enrichment.</p>
          </div>
          <Button variant="outline" onClick={() => router.push("/dashboard/hearing-day")}>Back to Search</Button>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Load URL</label>
            <div className="flex gap-2">
              <Input
                value={manualUrlInput}
                onChange={(e) => setManualUrlInput(e.target.value)}
                placeholder="https://.../document.pdf"
              />
              <Button
                variant="outline"
                onClick={() => {
                  const raw = manualUrlInput.trim();
                  if (!raw) {
                    setManualPdfUrl(null);
                    return;
                  }
                  setManualPdfUrl(`/api/pdf-proxy?url=${encodeURIComponent(raw)}`);
                }}
              >
                Load
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">Case bundle documents</label>
            {documents.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {documents.map((doc) => (
                  <Button
                    key={doc.id}
                    size="sm"
                    variant={activeDocId === doc.id ? "secondary" : "outline"}
                    onClick={() => {
                      setManualPdfUrl(null);
                      setActiveDocId(doc.id);
                    }}
                  >
                    View Case Bundle: {doc.title}
                  </Button>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-500">No documents found for this case.</div>
            )}
          </div>
        </div>

        {/* ── Upload PDF to S3 ── */}
        <div className="mt-3 border-t border-slate-100 pt-3">
          <label className="text-sm font-medium text-slate-700">Upload PDF to case documents</label>

          {/* Hidden native file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setUploadFile(f);
              if (f && !uploadTitle) setUploadTitle(f.name.replace(/\.pdf$/i, ""));
              setUploadError(null);
            }}
          />

          <div className="mt-2 flex flex-wrap items-center gap-2">
            {/* Choose file button */}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Paperclip className="mr-1.5 h-3.5 w-3.5" />
              {uploadFile ? uploadFile.name : "Choose PDF"}
            </Button>

            {/* Title input — shown once a file is chosen */}
            {uploadFile && (
              <Input
                className="h-9 w-52 text-sm"
                placeholder="Document title"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
                disabled={uploading}
              />
            )}

            {/* Upload button — shown once a file is chosen */}
            {uploadFile && (
              <Button
                type="button"
                size="sm"
                disabled={uploading || !uploadTitle.trim()}
                onClick={handleUploadPdf}
              >
                {uploading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Uploading…
                  </>
                ) : (
                  <>
                    <Upload className="mr-1.5 h-3.5 w-3.5" />
                    Upload to case
                  </>
                )}
              </Button>
            )}

            {/* Clear selection */}
            {uploadFile && !uploading && (
              <button
                type="button"
                onClick={() => {
                  setUploadFile(null);
                  setUploadTitle("");
                  setUploadError(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
              >
                <X className="h-3 w-3" />
                Clear
              </button>
            )}

            {/* Upload error */}
            {uploadError && (
              <p className="text-xs text-red-600">{uploadError}</p>
            )}
          </div>
        </div>

        <div className="mt-2 flex items-center gap-2 text-xs">
          {loading ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading case...
            </>
          ) : null}
          {saveStatus === "saving" ? <span className="text-amber-600">Saving…</span> : null}
          {saveStatus === "saved" ? <span className="text-green-600">Saved</span> : null}
          {saveStatus === "error" ? <span className="text-red-600">Save error</span> : null}
          {error ? <span className="text-red-600">{error}</span> : null}
        </div>
      </div>

      <CaseBundleWorkspaceTrial2
        pdfUrl={effectivePdfUrl}
        fileSource={backendFileSource}
        docId={activeDocId || caseId}
        caseTitle={caseTitle}
        initialContentJson={noteContentJson}
        initialNotes={noteContentText}
        onSave={saveNotes}
        onEnrich={runEnrich}
        saving={saveStatus === "saving"}
        enriching={enriching}
      />

      <div className="rounded-lg border bg-white p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">AI Hearing Assist</h3>
          {enrichmentMsg ? <span className="text-xs text-slate-500">{enrichmentMsg}</span> : null}
        </div>
        {!enrichment ? (
          <p className="text-sm text-slate-600">No enrichment yet. Click “Enrich Notes”.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border p-3">
              <div className="mb-1 text-xs font-semibold uppercase text-slate-500">AI Brief</div>
              <p className="text-sm text-slate-800">{(enrichment.enrichment_json.case_brief as string) || "-"}</p>
            </div>
            <div className="rounded border p-3">
              <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Likely Questions</div>
              <ul className="list-disc space-y-1 pl-4 text-sm text-slate-800">
                {((enrichment.enrichment_json.judge_questions_likely as string[]) || []).slice(0, 6).map((q, i) => (
                  <li key={`${q}-${i}`}>{q}</li>
                ))}
              </ul>
            </div>
            <div className="rounded border p-3">
              <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Checklist</div>
              <ul className="list-disc space-y-1 pl-4 text-sm text-slate-800">
                {((enrichment.enrichment_json.action_checklist as string[]) || []).slice(0, 10).map((x, i) => (
                  <li key={`${x}-${i}`}>{x}</li>
                ))}
              </ul>
            </div>
            <div className="rounded border p-3">
              <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Risks</div>
              <ul className="list-disc space-y-1 pl-4 text-sm text-slate-800">
                {((enrichment.enrichment_json.risks as string[]) || []).slice(0, 8).map((x, i) => (
                  <li key={`${x}-${i}`}>{x}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>

    <ChatWidget page="hearing_day" caseId={caseId} />
    </>
  );
}
