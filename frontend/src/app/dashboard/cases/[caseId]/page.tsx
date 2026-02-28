"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/contexts/AuthContext";
import { Loader2, Paperclip, Upload, X } from "lucide-react";

import {
  getCaseById,
  getCaseDocuments,
  getDocumentViewUrl,
  getHearingNote,
  importLocalDocument,
  refreshCaseStatusForCase,
  type DocumentListItem,
  type CaseStatusLookupResult,
  type HearingNoteResponse,
} from "@/lib/api";

type CaseDetail = Record<string, unknown> & {
  id: string;
  case_number: string | null;
  efiling_number: string;
  case_type: string;
  case_year: number;
  party_role: string;
  petitioner_name: string;
  respondent_name: string;
  status: string;
  court_status?: string | null;
  cnr_number?: string | null;
  efiling_date?: string | null;
  bench_type?: string | null;
  judge_name?: string | null;
  next_hearing_date?: string | null;
  first_hearing_date?: string | null;
  last_order_date?: string | null;
  last_synced_at?: string | null;
  khc_source_url?: string | null;
  stage?: string | null;
  hearing_history?: Record<string, unknown>[] | null;
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  const raw = String(value).trim();
  if (!raw) return "-";
  let d: Date;
  const dmy = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (dmy) {
    const day = Number(dmy[1]);
    const month = Number(dmy[2]);
    const year = Number(dmy[3]);
    d = new Date(year, month - 1, day);
  } else {
    d = new Date(raw);
  }
  if (Number.isNaN(d.getTime())) return "-";
  const hasTime = /T\d{2}:\d{2}|\d{1,2}:\d{2}/.test(raw);
  return hasTime ? d.toLocaleString() : d.toLocaleDateString();
}

function formatDateOnly(value?: string | null) {
  if (!value) return "-";
  const raw = String(value).trim();
  if (!raw) return "-";
  const dmy = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  const d = dmy
    ? new Date(Number(dmy[3]), Number(dmy[2]) - 1, Number(dmy[1]))
    : new Date(raw);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString();
}

function asText(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value.trim() || "-";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "-";
}

function getFirstValue(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    if (k in row && row[k] !== null && row[k] !== undefined && String(row[k]).trim() !== "") {
      return asText(row[k]);
    }
  }
  return "-";
}

export default function CaseDetailPage() {
  const params = useParams<{ caseId: string }>();
  const caseId = params.caseId;
  const { token } = useAuth();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [hearingNote, setHearingNote] = useState<HearingNoteResponse | null>(null);
  const [latestCourtData, setLatestCourtData] = useState<CaseStatusLookupResult | null>(null);
  const [openingDocId, setOpeningDocId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showHearingNotes, setShowHearingNotes] = useState(false);
  const [loadingHearingNotes, setLoadingHearingNotes] = useState(false);

  // PDF upload state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const loadAll = async () => {
    if (!token || !caseId) return;
    const [caseRes, docRes, noteRes] = await Promise.all([
      getCaseById(caseId, token),
      getCaseDocuments(caseId, token),
      getHearingNote(caseId, token).catch(() => null),
    ]);
    setData(caseRes as CaseDetail);
    setDocuments(docRes.items || docRes.data || []);
    setHearingNote(noteRes);
  };

  useEffect(() => {
    if (!token || !caseId) return;
    let ignore = false;
    setLoading(true);
    setError(null);
    loadAll()
      .catch((e) => {
        if (ignore) return;
        setError(e instanceof Error ? e.message : "Failed to load case");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [token, caseId]);

  const openDocument = async (doc: DocumentListItem) => {
    if (!token) return;
    try {
      setOpeningDocId(doc.id);
      const { url } = await getDocumentViewUrl(doc.id, token, 1800);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to open document");
    } finally {
      setOpeningDocId(null);
    }
  };

  const toggleHearingNotes = async () => {
    if (!token || !caseId) return;
    if (showHearingNotes) {
      setShowHearingNotes(false);
      return;
    }
    try {
      setLoadingHearingNotes(true);
      const noteRes = await getHearingNote(caseId, token).catch(() => null);
      setHearingNote(noteRes);
      setShowHearingNotes(true);
    } finally {
      setLoadingHearingNotes(false);
    }
  };

  const refreshFromCourt = async () => {
    if (!token || !caseId) return;
    try {
      setRefreshing(true);
      setError(null);
      const live: CaseStatusLookupResult = await refreshCaseStatusForCase(caseId, token);
      if (!live.found) {
        setError(live.message || "Case not found on court portal.");
        return;
      }
      setLatestCourtData(live);
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh case details");
    } finally {
      setRefreshing(false);
    }
  };

  const handleUploadPdf = async () => {
    if (!token || !caseId || !uploadFile) return;
    try {
      setUploading(true);
      setUploadError(null);
      const title = uploadTitle.trim() || uploadFile.name.replace(/\.pdf$/i, "");
      await importLocalDocument({ caseId, title, file: uploadFile }, token);
      // Refresh document list
      const docRes = await getCaseDocuments(caseId, token);
      setDocuments(docRes.items || docRes.data || []);
      // Reset upload form
      setUploadFile(null);
      setUploadTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <div className="text-slate-600">Loading case details...</div>;
  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return <div className="text-slate-600">Case not found.</div>;
  const displayHistory = (latestCourtData?.hearing_history || data.hearing_history || null) as Record<string, unknown>[] | null;
  const historyRows = Array.isArray(displayHistory) ? displayHistory : [];

  // Deduplicate by composite key: business_date + judge_name + purpose + order
  const deduplicatedHistoryRows = (() => {
    const seen = new Set<string>();
    return historyRows.filter((row) => {
      const r = (row || {}) as Record<string, unknown>;
      const key = [
        getFirstValue(r, ["business_date", "posting_date", "listed_on", "date"]),
        getFirstValue(r, ["judge_name", "hon_judge_name", "judge", "bench", "coram"]),
        getFirstValue(r, ["purpose_of_hearing", "purpose", "stage"]),
        getFirstValue(r, ["order", "order_text", "remarks"]),
      ].join("|");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();

  const firstHistoryRow = deduplicatedHistoryRows.length > 0 ? deduplicatedHistoryRows[0] : null;
  const lastHistoryRow = deduplicatedHistoryRows.length > 0 ? deduplicatedHistoryRows[deduplicatedHistoryRows.length - 1] : null;

  const displayStatus = asText(latestCourtData?.status_text ?? data.court_status ?? data.status);

  const displayBench = asText(
    latestCourtData?.stage ??
    data.bench_type ??
    (lastHistoryRow ? getFirstValue(lastHistoryRow, ["judge_name", "judge", "hon_judge_name", "coram"]) : null)
  );

  const displayJudge = asText(
    latestCourtData?.coram ??
    data.judge_name ??
    (lastHistoryRow ? getFirstValue(lastHistoryRow, ["judge_name", "judge", "hon_judge_name", "coram"]) : null)
  );

  const displayFirstHearing =
    latestCourtData?.first_hearing_date ||
    data.first_hearing_date ||
    (firstHistoryRow ? getFirstValue(firstHistoryRow, ["business_date", "date"]) : null);

  const displayLastHearing =
    latestCourtData?.last_order_date ||
    data.last_order_date ||
    (lastHistoryRow ? getFirstValue(lastHistoryRow, ["business_date", "date"]) : null);

  const displayNextHearing =
    latestCourtData?.next_hearing_date ||
    data.next_hearing_date ||
    (lastHistoryRow ? getFirstValue(lastHistoryRow, ["next_date", "tentative_date"]) : null);
  const displayCnr = asText(latestCourtData?.cnr_number ?? data.cnr_number ?? null);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{data.case_number || data.efiling_number}</h1>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <Link href={`/dashboard/hearing-day/${caseId}`}>Go to Hearing Day</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={`/dashboard/notebooks?caseId=${caseId}`}>Open Notebook</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/dashboard/cases">Back to cases</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Case Summary</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <p className="text-xs uppercase text-slate-500">Case Name</p>
              <p className="font-medium">{data.petitioner_name} vs {data.respondent_name}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Status</p>
              <p className="capitalize font-medium">{displayStatus}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Type</p>
              <p>{data.case_type} / {data.case_year}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">E-Filing Date</p>
              <p>{formatDateOnly(data.efiling_date)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">CNR Number</p>
              <p>{displayCnr}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Role</p>
              <p className="capitalize">{data.party_role}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Bench</p>
              <p>{displayBench}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Judge</p>
              <p>{displayJudge}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">First Hearing</p>
              <p>{formatDateOnly(displayFirstHearing)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Last Hearing / Order</p>
              <p>{formatDateOnly(displayLastHearing)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Next Hearing</p>
              <p>{formatDateOnly(displayNextHearing)}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Last Synced</p>
              <div className="flex flex-wrap items-center gap-2">
                <span>{formatDate(data.last_synced_at)}</span>
                <Button variant="outline" size="sm" onClick={refreshFromCourt} disabled={refreshing}>
                  {refreshing ? "Refreshing..." : "Refresh from Court"}
                </Button>
              </div>
            </div>
            <div className="md:col-span-2">
              <p className="text-xs uppercase text-slate-500">Source</p>
              {data.khc_source_url ? (
                <a className="text-blue-700 hover:underline break-all" href={data.khc_source_url} target="_blank" rel="noreferrer">
                  {data.khc_source_url}
                </a>
              ) : (
                <p>-</p>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-900">History of Case Hearing</p>
              <p className="text-xs text-slate-500">
                {deduplicatedHistoryRows.length > 0
                  ? `${deduplicatedHistoryRows.length} record${deduplicatedHistoryRows.length !== 1 ? "s" : ""}${deduplicatedHistoryRows.length < historyRows.length ? ` (${historyRows.length - deduplicatedHistoryRows.length} duplicate${historyRows.length - deduplicatedHistoryRows.length !== 1 ? "s" : ""} removed)` : ""}`
                  : "No records"}
              </p>
            </div>

            {deduplicatedHistoryRows.length === 0 ? (
              <p className="text-xs text-slate-600">
                No hearing history loaded yet. Click <span className="font-medium">Refresh from Court</span> to fetch.
              </p>
            ) : (
              <div className="max-h-[28rem] overflow-auto rounded border bg-white">
                <table className="min-w-full text-xs">
                  <thead className="sticky top-0 bg-slate-100 text-slate-700">
                    <tr>
                      <th className="border-b px-2 py-2 text-left">#</th>
                      <th className="border-b px-2 py-2 text-left">Cause List Type</th>
                      <th className="border-b px-2 py-2 text-left">Hon&apos; Judge Name</th>
                      <th className="border-b px-2 py-2 text-left">Business Date</th>
                      <th className="border-b px-2 py-2 text-left">Next Date</th>
                      <th className="border-b px-2 py-2 text-left">Purpose</th>
                      <th className="border-b px-2 py-2 text-left">Order</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deduplicatedHistoryRows.map((row, idx) => {
                      const r = (row || {}) as Record<string, unknown>;
                      const causeListType = getFirstValue(r, ["cause_list_type", "list_type", "list", "causeListType"]);
                      const judgeName = getFirstValue(r, ["judge_name", "hon_judge_name", "judge", "bench", "coram"]);
                      const businessDate = getFirstValue(r, ["business_date", "posting_date", "listed_on", "date"]);
                      const nextDate = getFirstValue(r, ["next_date", "next_hearing_date", "tentative_date"]);
                      const purpose = getFirstValue(r, ["purpose_of_hearing", "purpose", "stage"]);
                      const order = getFirstValue(r, ["order", "order_text", "remarks"]);
                      const rowNo = getFirstValue(r, ["sl_no", "serial_no", "index", "no"]);

                      return (
                        <tr key={`${idx}-${rowNo}`} className="align-top odd:bg-white even:bg-slate-50/70">
                          <td className="border-b px-2 py-2">{rowNo === "-" ? idx + 1 : rowNo}</td>
                          <td className="border-b px-2 py-2">{causeListType}</td>
                          <td className="border-b px-2 py-2">{judgeName}</td>
                          <td className="border-b px-2 py-2">{businessDate}</td>
                          <td className="border-b px-2 py-2">{nextDate}</td>
                          <td className="border-b px-2 py-2">{purpose}</td>
                          <td className="border-b px-2 py-2 max-w-[24rem] whitespace-pre-wrap break-words">{order}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Documents</CardTitle>
            <div className="flex items-center gap-2">
              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setUploadFile(f);
                  setUploadTitle(f ? f.name.replace(/\.pdf$/i, "") : "");
                  setUploadError(null);
                }}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip className="mr-1.5 h-4 w-4" />
                Upload PDF
              </Button>
              <Button variant="outline" size="sm" onClick={() => void toggleHearingNotes()} disabled={loadingHearingNotes}>
                {loadingHearingNotes
                  ? "Loading notes..."
                  : showHearingNotes
                    ? "Hide Hearing Day Notes"
                    : "Show Hearing Day Notes"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Inline upload form — shown after user picks a file */}
          {uploadFile && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-3 space-y-3">
              <p className="text-sm font-medium text-indigo-900 flex items-center gap-2">
                <Paperclip className="h-4 w-4" />
                {uploadFile.name}
                <span className="text-xs text-indigo-600 font-normal">
                  ({(uploadFile.size / 1024).toFixed(0)} KB)
                </span>
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  className="h-8 max-w-xs text-sm"
                  placeholder="Document title (optional)"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  disabled={uploading}
                />
                <Button size="sm" onClick={() => void handleUploadPdf()} disabled={uploading}>
                  {uploading ? (
                    <><Loader2 className="mr-1.5 h-4 w-4 animate-spin" />Uploading…</>
                  ) : (
                    <><Upload className="mr-1.5 h-4 w-4" />Upload</>
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={uploading}
                  onClick={() => {
                    setUploadFile(null);
                    setUploadTitle("");
                    setUploadError(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                >
                  <X className="mr-1 h-4 w-4" />
                  Clear
                </Button>
              </div>
              {uploadError && (
                <p className="text-sm text-red-600">{uploadError}</p>
              )}
            </div>
          )}

          {documents.length === 0 ? (
            <p className="text-slate-600">No documents uploaded for this case yet.</p>
          ) : (
            <div className="space-y-2">
              {documents.map((doc) => (
                <div key={doc.id} className="flex items-center justify-between rounded border p-3">
                  <div>
                    <p className="font-medium">{doc.title}</p>
                    <p className="text-xs text-slate-500">
                      {doc.category || "document"} • {doc.upload_status || "unknown"}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={openingDocId === doc.id}
                    onClick={() => void openDocument(doc)}
                  >
                    {openingDocId === doc.id ? "Opening..." : "Open"}
                  </Button>
                </div>
              ))}
            </div>
          )}

          {showHearingNotes && (
            <div className="space-y-3 border-t pt-4">
              <div className="text-sm font-medium text-slate-900">Hearing Day Notes</div>
              {!hearingNote || (!hearingNote.content_text && !hearingNote.content_json) ? (
                <p className="text-slate-600">No hearing day notes saved for this case yet.</p>
              ) : (
                <>
                  <div className="text-xs text-slate-500">
                    Last updated: {formatDate(hearingNote.updated_at)} • Version: {hearingNote.version}
                  </div>
                  <div className="max-h-80 overflow-auto rounded border bg-slate-50 p-3">
                    <pre className="whitespace-pre-wrap text-sm text-slate-800">
                      {hearingNote.content_text || JSON.stringify(hearingNote.content_json, null, 2)}
                    </pre>
                  </div>
                  <Button variant="outline" asChild size="sm">
                    <Link href={`/dashboard/hearing-day/${caseId}`}>Go to Hearing Day</Link>
                  </Button>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
 
  );
}
