const getBaseUrl = () =>
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || ""
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const API_TIMEOUT_MS = 30000;

// ── Helpers for Tab ID header ─────────────────────────────────────────────────
// Imported lazily (client-only module; SSR returns "ssr")
function getTabIdHeader(): string {
  if (typeof window === "undefined") return "";
  try {
    // Avoid a hard import cycle — read directly from sessionStorage
    const TAB_ID_KEY = "lawmate_tab_id";
    return sessionStorage.getItem(TAB_ID_KEY) || "";
  } catch {
    return "";
  }
}

// ── ConflictError ────────────────────────────────────────────────────────────
/**
 * Thrown when the server returns HTTP 409 Conflict with a structured body.
 * Catch this in save handlers and surface the ConflictModal.
 */
export interface ConflictDetail {
  message: string;
  current_version: number;
  current_record: Record<string, unknown>;
}

export class ConflictError extends Error {
  readonly status = 409;
  readonly payload: ConflictDetail;

  constructor(payload: ConflictDetail) {
    super(payload.message);
    this.name = "ConflictError";
    this.payload = payload;
  }
}

// ── Core request helper ───────────────────────────────────────────────────────

export async function apiRequest<T = unknown>(
  endpoint: string,
  options: RequestInit & { token?: string | null; timeoutMs?: number } = {}
): Promise<T> {
  const { token, timeoutMs, ...init } = options;
  const baseUrl = getBaseUrl().replace(/\/$/, "");
  const url = endpoint.startsWith("http") ? endpoint : `${baseUrl}${endpoint}`;
  const tabId = getTabIdHeader();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }
  if (tabId) {
    (headers as Record<string, string>)["X-Tab-ID"] = tabId;
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs ?? API_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(url, { ...init, headers, signal: controller.signal });
  } catch (error: any) {
    if (error?.name === "AbortError") {
      throw new Error("Request timed out. Please check backend connectivity.");
    }
    throw new Error("Network error. Please verify backend is running and reachable.");
  } finally {
    clearTimeout(timeoutId);
  }
  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Unauthorized");
  }
  if (res.status === 409) {
    const body = await res.json().catch(() => ({})) as Partial<ConflictDetail>;
    throw new ConflictError({
      message: body.message || "Conflict: this record was modified elsewhere.",
      current_version: body.current_version ?? 0,
      current_record: body.current_record ?? {},
    });
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText || "Request failed");
  }
  const contentType = res.headers.get("content-type");
  if (contentType?.includes("application/json")) return res.json() as Promise<T>;
  return res.text() as Promise<T>;
}

export const authApi = {
  login: (email: string, password: string) =>
    apiRequest<{ access_token: string; user: AuthUser }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      timeoutMs: 60000,
    }),
  register: (data: RegisterPayload) =>
    apiRequest<{ id: string }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  forgotPassword: (email: string) =>
    apiRequest<{ success: boolean }>("/api/v1/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, password: string) =>
    apiRequest<{ success: boolean }>("/api/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),
  me: (token: string) =>
    apiRequest<AuthUser>("/api/v1/auth/me", { method: "GET", token }),
  startProfileVerification: (fullName: string, verifyVia: "phone" | "email", token: string) =>
    apiRequest<{
      success: boolean;
      message: string;
      verify_via?: "phone" | "email";
      masked_mobile?: string;
      masked_email?: string;
      expires_in_seconds?: number;
      dev_otp?: string;
    }>(
      "/api/v1/auth/profile-verification/start",
      {
        method: "POST",
        token,
        timeoutMs: 90000,
        body: JSON.stringify({ full_name: fullName, verify_via: verifyVia }),
      }
    ),
  confirmProfileVerification: (otp: string, token: string) =>
    apiRequest<{ success: boolean; message: string; verified_at?: string }>(
      "/api/v1/auth/profile-verification/confirm",
      {
        method: "POST",
        token,
        timeoutMs: 90000,
        body: JSON.stringify({ otp }),
      }
    ),
};

export interface AuthUser {
  id: string;
  email: string;
  khc_advocate_id: string;
  khc_advocate_name: string;
  role: string;
  is_verified: boolean;
  profile_verified_at?: string | null;
  mobile?: string | null;
  khc_enrollment_number?: string | null;
  khc_advocate_code?: string | null;   // numeric adv_cd for hckinfo digicourt
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  last_login_at?: string | null;
  last_sync_at?: string | null;
  preferences?: Record<string, unknown>;
}

export interface RegisterPayload {
  email: string;
  password: string;
  khc_advocate_id: string;
  khc_advocate_name: string;
  mobile?: string;
  khc_enrollment_number?: string;
}

const getAuthHeaders = (token: string | null) =>
  token ? { Authorization: `Bearer ${token}` } : {};

/** Cases (for AI Insights "Save to case") */
export async function getCases(token: string | null) {
  const baseUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const url = `${baseUrl.replace(/\/$/, "")}/api/v1/cases/?per_page=100`;
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(url, {
    headers,
  });
  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText || "Request failed");
  }
  const data = await res.json();
  return data.items ?? data.cases ?? data ?? [];
}

export interface CaseOption {
  id: string;
  case_number?: string | null;
  efiling_number: string;
  case_type?: string;
  petitioner_name?: string;
}

export interface CaseListItem {
  id: string;
  case_number: string | null;
  efiling_number: string;
  case_type: string;
  case_year: number;
  party_role: string;
  petitioner_name: string;
  respondent_name: string;
  efiling_date: string;
  status: string;
  next_hearing_date: string | null;
  last_synced_at: string | null;
  updated_at: string;
}

export interface CasesPageResponse {
  items: CaseListItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface CasesListParams {
  page?: number;
  perPage?: number;
  q?: string;
  status?: string;
  partyRole?: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
}

export async function listCases(
  params: CasesListParams,
  token: string | null
): Promise<CasesPageResponse> {
  const qs = new URLSearchParams();
  qs.set("page", String(params.page ?? 1));
  qs.set("per_page", String(params.perPage ?? 20));
  if (params.q) qs.set("q", params.q);
  if (params.status) qs.set("status", params.status);
  if (params.partyRole) qs.set("party_role", params.partyRole);
  if (params.sortBy) qs.set("sort_by", params.sortBy);
  if (params.sortDir) qs.set("sort_dir", params.sortDir);

  return apiRequest<CasesPageResponse>(`/api/v1/cases/?${qs.toString()}`, { token });
}

export async function getCaseById(caseId: string, token: string | null): Promise<CaseListItem & Record<string, unknown>> {
  return apiRequest<CaseListItem & Record<string, unknown>>(`/api/v1/cases/${caseId}`, { token });
}

export async function deleteCase(caseId: string, token: string | null): Promise<{ message: string; case_id: string }> {
  return apiRequest<{ message: string; case_id: string }>(`/api/v1/cases/${caseId}`, {
    method: "DELETE",
    token,
  });
}

export interface RecycleBinResponse {
  items: CaseListItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export async function listDeletedCases(
  params: { page?: number; perPage?: number } = {},
  token: string | null
): Promise<RecycleBinResponse> {
  const q = new URLSearchParams();
  q.set("page", String(params.page ?? 1));
  q.set("per_page", String(params.perPage ?? 20));
  return apiRequest<RecycleBinResponse>(`/api/v1/cases/recycle-bin/items?${q.toString()}`, { token });
}

export async function restoreCase(caseId: string, token: string | null): Promise<{ message: string; case_id: string }> {
  return apiRequest<{ message: string; case_id: string }>(`/api/v1/cases/${caseId}/restore`, {
    method: "POST",
    token,
  });
}

export interface PendingCaseStatusRow {
  id: string;
  case_number: string;
  status_text?: string | null;
  stage?: string | null;
  last_order_date?: string | null;
  next_hearing_date?: string | null;
  source_url?: string | null;
  fetched_at: string;
  updated_at: string;
  // Latest hearing history row fields
  business_date?: string | null;
  tentative_date?: string | null;
  purpose_of_hearing?: string | null;
  order_text?: string | null;
  judge_name?: string | null;
}

export async function getPendingCaseStatuses(token: string | null): Promise<PendingCaseStatusRow[]> {
  return apiRequest<PendingCaseStatusRow[]>("/api/v1/cases/pending-status", { token });
}

export interface TrackedCaseStatusRow {
  id: string;
  case_number: string;
  status_text?: string | null;
  stage?: string | null;
  last_order_date?: string | null;
  next_hearing_date?: string | null;
  source_url?: string | null;
  full_details_url?: string | null;
  fetched_at?: string | null;
  updated_at: string;
}

export async function getTrackedCaseStatuses(token: string | null): Promise<TrackedCaseStatusRow[]> {
  return apiRequest<TrackedCaseStatusRow[]>("/api/v1/cases/tracked-status", { token });
}

// ── Advocate Cause List (hckinfo digicourt) ───────────────────────────────────

export interface AdvocateCauseListRow {
  id:                string;
  date:              string;
  item_no:           number | null;
  court_hall:        string | null;
  court_hall_number: number | null;
  bench:             string | null;
  list_type:         string | null;
  judge_name:        string | null;
  case_no:           string | null;
  petitioner:        string | null;
  respondent:        string | null;
  fetched_at:        string | null;
}

export interface AdvocateCauseListResponse {
  date:          string;
  advocate_name: string;
  total:         number;
  rows:          AdvocateCauseListRow[];
  from_cache:    boolean;
}

export async function getAdvocateCauseList(
  token:       string | null,
  targetDate?: string,           // YYYY-MM-DD; defaults to tomorrow on the server
): Promise<AdvocateCauseListResponse> {
  const suffix = targetDate ? `?target_date=${targetDate}` : "";
  return apiRequest<AdvocateCauseListResponse>(
    `/api/v1/advocate-cause-list${suffix}`,
    { token },
  );
}

export async function refreshAdvocateCauseList(
  token:       string | null,
  targetDate?: string,
): Promise<AdvocateCauseListResponse> {
  const suffix = targetDate ? `?target_date=${targetDate}` : "";
  return apiRequest<AdvocateCauseListResponse>(
    `/api/v1/advocate-cause-list/refresh${suffix}`,
    { token, method: "POST" },
  );
}

export interface CauseListJobSummary {
  success: boolean;
  status: "started" | "completed";
  date: string;
  message?: string;
  // Present only when status === "completed" (legacy sync response kept for compat)
  total_advocates_processed?: number;
  total_with_listings?: number;
  total_with_errors?: number;
  page_count?: number;
}

export async function runCauseListJobForDate(
  date: string,
  token: string | null
): Promise<CauseListJobSummary> {
  const q = new URLSearchParams({ date }).toString();
  // Short timeout — the endpoint now returns immediately (background job).
  return apiRequest<CauseListJobSummary>(`/api/cause-list/process?${q}`, {
    method: "POST",
    token,
    timeoutMs: 15000,
  });
}

export interface CaseStatusLookupResult {
  found: boolean;
  case_number: string;
  case_type?: string | null;
  filing_number?: string | null;
  filing_date?: string | null;
  registration_number?: string | null;
  registration_date?: string | null;
  cnr_number?: string | null;
  efile_number?: string | null;
  first_hearing_date?: string | null;
  status_text?: string | null;
  coram?: string | null;
  stage?: string | null;
  last_order_date?: string | null;
  next_hearing_date?: string | null;
  last_listed_date?: string | null;
  last_listed_bench?: string | null;
  last_listed_list?: string | null;
  last_listed_item?: string | null;
  petitioner_name?: string | null;
  petitioner_advocates?: string[] | null;
  respondent_name?: string | null;
  respondent_advocates?: string[] | null;
  served_on?: string[] | null;
  acts?: string[] | null;
  sections?: string[] | null;
  hearing_history?: Record<string, unknown>[] | null;
  interim_orders?: Record<string, unknown>[] | null;
  category_details?: Record<string, unknown> | null;
  objections?: Record<string, unknown>[] | null;
  summary?: string | null;
  source_url?: string | null;
  full_details_url?: string | null;
  fetched_at: string;
  message?: string | null;
}

export async function queryCaseStatus(
  caseNumber: string,
  token: string | null
): Promise<CaseStatusLookupResult> {
  return apiRequest<CaseStatusLookupResult>("/api/v1/cases/case-status/query", {
    method: "POST",
    token,
    timeoutMs: 180000,
    body: JSON.stringify({ case_number: caseNumber }),
  });
}

export async function refreshCaseStatusForCase(
  caseId: string,
  token: string | null
): Promise<CaseStatusLookupResult> {
  return apiRequest<CaseStatusLookupResult>(`/api/v1/cases/${caseId}/case-status/refresh`, {
    method: "POST",
    token,
    timeoutMs: 180000,
  });
}

export async function addCaseToDashboard(
  payload: {
    case_number: string;
    petitioner_name?: string | null;
    respondent_name?: string | null;
    status_text?: string | null;
    stage?: string | null;
    last_order_date?: string | null;
    next_hearing_date?: string | null;
    source_url?: string | null;
    full_details_url?: string | null;
  },
  token: string | null
): Promise<{ success: boolean; created: boolean; case_id: string; message: string }> {
  return apiRequest<{ success: boolean; created: boolean; case_id: string; message: string }>(
    "/api/v1/cases/case-status/add-to-dashboard",
    {
      method: "POST",
      token,
      timeoutMs: 60000,
      body: JSON.stringify(payload),
    }
  );
}


/** Hearing Day: search cases (debounced from UI) */
export async function searchCases(
  q: string,
  limit: number,
  token: string | null
): Promise<{ cases: CaseOption[]; items?: CaseOption[] }> {
  const data = await apiRequest<{ cases: CaseOption[]; items?: CaseOption[] }>(
    `/api/v1/cases/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    { token }
  );
  return data as { cases: CaseOption[]; items?: CaseOption[] };
}

/** Hearing Day: get documents for a case */
export async function getCaseDocuments(
  caseId: string,
  token: string | null
): Promise<{ data: DocumentListItem[]; items?: DocumentListItem[] }> {
  const data = await apiRequest<{ data: DocumentListItem[]; items?: DocumentListItem[] }>(
    `/api/v1/cases/${caseId}/documents`,
    { token }
  );
  const d = data as { data?: DocumentListItem[]; items?: DocumentListItem[] };
  return { data: d.data ?? [], items: d.items ?? d.data ?? [] };
}

export interface DocumentListItem {
  id: string;
  case_id: string;
  category?: string;
  title: string;
  s3_key: string;
  s3_bucket?: string;
  uploaded_at?: string | null;
  upload_status?: string;
  [key: string]: unknown;
}

/** Hearing Day: get hearing note for case */
export async function getHearingNote(
  caseId: string,
  token: string | null
): Promise<HearingNoteResponse> {
  return apiRequest<HearingNoteResponse>(`/api/v1/hearing-day/${caseId}/note`, { token });
}

/** Hearing Day: create/update hearing note (optimistic lock via version) */
export async function putHearingNote(
  caseId: string,
  payload: { content_json: Record<string, unknown> | null; content_text: string | null; version: number },
  token: string | null
): Promise<HearingNoteResponse> {
  return apiRequest<HearingNoteResponse>(`/api/v1/hearing-day/${caseId}/note`, {
    method: "PUT",
    body: JSON.stringify(payload),
    token,
  });
}

export interface HearingNoteResponse {
  id: string;
  case_id: string;
  user_id: string;
  content_json: Record<string, unknown> | null;
  content_text: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

/** Hearing Day: add citation */
export async function createHearingCitation(
  caseId: string,
  payload: {
    hearing_note_id: string;
    doc_id: string;
    page_number: number;
    quote_text?: string;
    bbox_json?: Record<string, unknown>;
    anchor_id?: string;
  },
  token: string | null
): Promise<HearingCitationResponse> {
  return apiRequest<HearingCitationResponse>(`/api/v1/hearing-day/${caseId}/citations`, {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}

export interface HearingCitationResponse {
  id: string;
  hearing_note_id: string;
  doc_id: string;
  page_number: number;
  quote_text: string | null;
  bbox_json: Record<string, unknown> | null;
  anchor_id: string | null;
  created_at: string;
}

/** Hearing Day: list citations for case note */
export async function getHearingCitations(
  caseId: string,
  token: string | null
): Promise<{ data: HearingCitationResponse[]; items?: HearingCitationResponse[] }> {
  const data = await apiRequest<{ data: HearingCitationResponse[]; items?: HearingCitationResponse[] }>(
    `/api/v1/hearing-day/${caseId}/citations`,
    { token }
  );
  const d = data as { data?: HearingCitationResponse[]; items?: HearingCitationResponse[] };
  return { data: d.data ?? [], items: d.items ?? d.data ?? [] };
}

export interface HearingNoteEnrichment {
  id: string;
  hearing_note_id: string;
  user_id: string;
  model: string;
  note_version: number;
  citation_hash: string;
  enrichment_json: Record<string, unknown>;
  status: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface HearingNoteEnrichmentRunResponse {
  success: boolean;
  from_cache: boolean;
  deterministic_only: boolean;
  enrichment: HearingNoteEnrichment;
}

export async function enrichHearingNote(
  caseId: string,
  token: string | null
): Promise<HearingNoteEnrichmentRunResponse> {
  return apiRequest<HearingNoteEnrichmentRunResponse>(`/api/v1/hearing-day/${caseId}/enrich`, {
    method: "POST",
    token,
    timeoutMs: 120000,
  });
}

export async function getHearingNoteEnrichment(
  caseId: string,
  token: string | null
): Promise<HearingNoteEnrichment> {
  return apiRequest<HearingNoteEnrichment>(`/api/v1/hearing-day/${caseId}/enrichment`, { token });
}

export interface NoteAttachment {
  id: string;
  note_id: string;
  file_url: string;
  s3_key?: string | null;
  s3_bucket?: string | null;
  file_name?: string | null;
  content_type?: string | null;
  file_size?: number | null;
  ocr_text?: string | null;
  uploaded_at: string;
  created_at: string;
}

export interface NotebookNote {
  id: string;
  notebook_id: string;
  title: string;
  order_index: number;
  content_json?: Record<string, unknown> | null;
  content_text?: string | null;
  /** Optimistic concurrency version — incremented on every successful save */
  version: number;
  created_at: string;
  updated_at: string;
  attachments: NoteAttachment[];
}

export interface CaseNotebook {
  id: string;
  user_id: string;
  case_id: string;
  created_at: string;
  updated_at: string;
  notes: NotebookNote[];
}

export interface CaseNotebookListItem {
  notebook_id: string;
  case_id: string;
  case_number?: string | null;
  efiling_number: string;
  case_type?: string | null;
  petitioner_name?: string | null;
  respondent_name?: string | null;
  note_count: number;
  updated_at: string;
}

export interface NotebookSearchItem {
  note_id: string;
  notebook_id: string;
  case_id: string;
  case_number?: string | null;
  efiling_number: string;
  note_title: string;
  snippet: string;
  updated_at: string;
}

export async function listCaseNotebooks(token: string | null): Promise<CaseNotebookListItem[]> {
  return apiRequest<CaseNotebookListItem[]>("/api/v1/notebooks/", { token });
}

export async function openCaseNotebook(caseId: string, token: string | null): Promise<CaseNotebook> {
  return apiRequest<CaseNotebook>(`/api/v1/notebooks/cases/${caseId}/open`, {
    method: "POST",
    token,
  });
}

export async function getCaseNotebook(caseId: string, token: string | null): Promise<CaseNotebook> {
  return apiRequest<CaseNotebook>(`/api/v1/notebooks/cases/${caseId}`, { token });
}

export async function createNotebookNote(
  notebookId: string,
  payload: {
    title: string;
    order_index?: number;
    content_json?: Record<string, unknown> | null;
    content_text?: string | null;
  },
  token: string | null
): Promise<NotebookNote> {
  return apiRequest<NotebookNote>(`/api/v1/notebooks/${notebookId}/notes`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export async function updateNotebookNote(
  noteId: string,
  payload: {
    title?: string;
    order_index?: number;
    content_json?: Record<string, unknown> | null;
    content_text?: string | null;
    /** Include the current version for optimistic concurrency checks (HTTP 409 on mismatch) */
    version?: number;
  },
  token: string | null
): Promise<NotebookNote> {
  return apiRequest<NotebookNote>(`/api/v1/notebooks/notes/${noteId}`, {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  });
}

export async function deleteNotebookNote(noteId: string, token: string | null): Promise<{ success: boolean; note_id: string }> {
  return apiRequest<{ success: boolean; note_id: string }>(`/api/v1/notebooks/notes/${noteId}`, {
    method: "DELETE",
    token,
  });
}

export async function uploadNotebookAttachment(
  noteId: string,
  file: File,
  token: string | null,
  ocrText?: string
): Promise<NoteAttachment> {
  const baseUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const url = `${baseUrl.replace(/\/$/, "")}/api/v1/notebooks/notes/${noteId}/attachments/upload`;
  const form = new FormData();
  form.append("file", file);
  if (ocrText) form.append("ocr_text", ocrText);
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { method: "POST", headers, body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Attachment upload failed");
  }
  return res.json();
}

export async function getNotebookAttachmentViewUrl(
  noteId: string,
  attachmentId: string,
  token: string | null
): Promise<{ url: string; expires_in: number }> {
  return apiRequest<{ url: string; expires_in: number }>(
    `/api/v1/notebooks/notes/${noteId}/attachments/${attachmentId}/view-url`,
    { token }
  );
}

export async function searchNotebookNotes(q: string, token: string | null): Promise<NotebookSearchItem[]> {
  return apiRequest<NotebookSearchItem[]>(`/api/v1/notebooks/search?q=${encodeURIComponent(q)}`, { token });
}

export async function sendNotebookToHearingDay(
  noteId: string,
  payload: { mode: "chapter" | "selection"; selected_text?: string },
  token: string | null
): Promise<{ success: boolean; mode: "chapter" | "selection"; hearing_note_id: string; version: number }> {
  return apiRequest<{ success: boolean; mode: "chapter" | "selection"; hearing_note_id: string; version: number }>(
    `/api/v1/notebooks/notes/${noteId}/send-to-hearing-day`,
    {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }
  );
}

/** Get short-lived view URL for a document (do not store) */
export async function getDocumentViewUrl(
  documentId: string,
  token: string | null,
  expiresIn?: number
): Promise<{ url: string; expires_in: number }> {
  const q = expiresIn != null ? `?expires_in=${expiresIn}` : "";
  return apiRequest<{ url: string; expires_in: number }>(
    `/api/v1/documents/${documentId}/view-url${q}`,
    { token }
  );
}

/** Extract document text via Bedrock PDF support (text-only or full visual mode) */
export async function extractDocument(
  file: File,
  token: string | null,
  useVisualMode: boolean = true
): Promise<{
  extractedText: string;
  pageCount: number;
  processingMode: "text_only" | "full_visual";
}> {
  const baseUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const url = `${baseUrl.replace(/\/$/, "")}/api/v1/ai-insights/extract-document`;
  const form = new FormData();
  form.append("file", file);
  form.append("use_visual_mode", useVisualMode ? "true" : "false");
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: form,
  });

  if (res.status === 401) {
    const errBody = await res.json().catch(() => ({}));
    const detail = (errBody as { detail?: string }).detail;
    if (typeof window !== "undefined") {
      window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
    }
    throw new Error(detail || "Unauthorized. Please sign in again.");
  }
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    const detail = (errBody as { detail?: string }).detail;
    throw new Error(detail || res.statusText || "Extraction failed");
  }
  return res.json();
}

/** Chat about the current document (Q&A using extracted text). */
export async function chatAboutDocument(
  payload: {
    extractedText: string;
    question: string;
    conversationHistory?: { role: string; content: string }[];
  },
  token: string | null
): Promise<{ response: string }> {
  const data = await apiRequest<{ response: string }>("/api/v1/ai-insights/chat", {
    method: "POST",
    body: JSON.stringify({
      extractedText: payload.extractedText,
      question: payload.question,
      conversationHistory: payload.conversationHistory ?? [],
    }),
    token,
  });
  return data as { response: string };
}

/** Initiate upload: get presigned URL and document id. Optional extractedText is stored on the document. */
export async function initiateUpload(
  payload: {
    caseId: string;
    category: string;
    title: string;
    fileName: string;
    fileSize: number;
    contentType?: string;
    extractedText?: string;
  },
  token: string | null
): Promise<{ documentId: string; uploadUrl: string; s3Key: string }> {
  const data = await apiRequest<{ data: { documentId: string; uploadUrl: string; s3Key: string } }>(
    "/api/v1/upload/initiate",
    {
      method: "POST",
      body: JSON.stringify({
        caseId: payload.caseId,
        category: payload.category,
        title: payload.title,
        fileName: payload.fileName,
        fileSize: payload.fileSize,
        contentType: payload.contentType || "application/pdf",
        extractedText: payload.extractedText ?? undefined,
      }),
      token,
    }
  );
  const d = (data as { data?: { documentId: string; uploadUrl: string; s3Key: string } }).data;
  if (!d?.documentId || !d?.uploadUrl) throw new Error("Invalid initiate response");
  return { documentId: d.documentId, uploadUrl: d.uploadUrl, s3Key: d.s3Key };
}

/** Confirm document upload after PUT to presigned URL */
export async function confirmDocumentUpload(documentId: string, token: string | null) {
  return apiRequest<{ data: unknown }>(`/api/v1/documents/${documentId}/confirm`, {
    method: "POST",
    token,
  });
}

export const OCR_PAGE_BREAK = "\n\n<<<PAGE_BREAK>>>\n\n";

export async function extractOcrText(
  file: File,
  token: string | null,
  options?: { language?: string; forceOcr?: boolean }
): Promise<{
  text: string;
  pageTexts: string[];
  pages: number;
  language: string;
  ocrEngine: string;
}> {
  const baseUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const url = `${baseUrl.replace(/\/$/, "")}/api/v1/ocr/extract`;
  const form = new FormData();
  form.append("file", file);
  form.append("language", (options?.language || "mal+eng").trim() || "mal+eng");
  form.append("force_ocr", options?.forceOcr ? "true" : "false");

  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "OCR extraction failed");
  }
  return res.json();
}

export async function createSearchablePdf(
  file: File,
  token: string | null,
  options: { text: string; language?: string; outputFormat?: "pdf" | "pdfa"; forceOcr?: boolean }
): Promise<{
  blob: Blob;
  pdfFormat: string;
  ocrEngine: string;
  searchable: boolean;
  textPages: number;
  totalPages: number;
  imageDpi: string;
}> {
  const baseUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const url = `${baseUrl.replace(/\/$/, "")}/api/v1/ocr/create-searchable-pdf`;
  const form = new FormData();
  form.append("file", file);
  form.append("text", options.text);
  form.append("language", (options.language || "mal+eng").trim() || "mal+eng");
  form.append("output_format", options.outputFormat || "pdf");
  form.append("force_ocr", options.forceOcr ? "true" : "false");

  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Searchable PDF generation failed");
  }

  return {
    blob: await res.blob(),
    pdfFormat: res.headers.get("X-PDF-Format") || "pdf",
    ocrEngine: res.headers.get("X-OCR-Engine") || "unknown",
    searchable: (res.headers.get("X-OCR-Searchable") || "false").toLowerCase() === "true",
    textPages: Number(res.headers.get("X-OCR-Text-Pages") || "0"),
    totalPages: Number(res.headers.get("X-OCR-Pages") || "0"),
    imageDpi: res.headers.get("X-Image-DPI") || "",
  };
}

export interface CauseListRelevantItem {
  case_id: string;
  case_number: string | null;
  efiling_number: string;
  case_type: string;
  party_role: string;
  petitioner_name: string;
  respondent_name: string;
  listing_date: string;
  source: "daily" | "weekly" | "advanced" | "monthly";
  color: "green" | "yellow" | "blue" | "gray";
  court_number?: string | null;
  bench_name?: string | null;
  item_no?: string | null;
}

export interface CauseListDayGroup {
  date: string;
  items: CauseListRelevantItem[];
}

export interface CauseListRelevantResponse {
  from_date: string;
  to_date: string;
  total: number;
  days: CauseListDayGroup[];
}

export interface CauseListRenderedHtmlResponse {
  listing_date: string;
  source: "daily" | "weekly" | "advanced" | "monthly";
  total: number;
  html: string;
}

export interface CauseListAllItem {
  id: string;
  case_number: string;
  listing_date: string;
  source: "daily" | "weekly" | "advanced" | "monthly";
  cause_list_type?: string | null;
  court_number?: string | null;
  bench_name?: string | null;
  item_no?: string | null;
  party_names?: string | null;
  petitioner_name?: string | null;
  respondent_name?: string | null;
  advocate_names?: string | null;
  fetched_from_url?: string | null;
}

export interface CauseListAllResponse {
  listing_date: string;
  source: "daily" | "weekly" | "advanced" | "monthly";
  total: number;
  items: CauseListAllItem[];
}


export async function getTodayAtCourt(token: string | null): Promise<CauseListRelevantResponse> {
  return apiRequest<CauseListRelevantResponse>("/api/v1/causelist/today", { token });
}

export async function getRelevantCauseList(
  params: { fromDate?: string; toDate?: string; source?: "daily" | "weekly" | "advanced" | "monthly" } = {},
  token: string | null
): Promise<CauseListRelevantResponse> {
  const q = new URLSearchParams();
  if (params.fromDate) q.set("from_date", params.fromDate);
  if (params.toDate) q.set("to_date", params.toDate);
  if (params.source) q.set("source", params.source);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiRequest<CauseListRelevantResponse>(`/api/v1/causelist/relevant${suffix}`, { token });
}

export async function getRenderedCauseListHtml(
  params: { listingDate?: string; source?: "daily" | "weekly" | "advanced" | "monthly" } = {},
  token: string | null
): Promise<CauseListRenderedHtmlResponse> {
  const q = new URLSearchParams();
  if (params.listingDate) q.set("listing_date", params.listingDate);
  if (params.source) q.set("source", params.source);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiRequest<CauseListRenderedHtmlResponse>(`/api/v1/causelist/rendered-html${suffix}`, { token });
}


export async function getAllCauseList(
  params: { listingDate?: string; source?: "daily" | "weekly" | "advanced" | "monthly" } = {},
  token: string | null
): Promise<CauseListAllResponse> {
  const q = new URLSearchParams();
  if (params.listingDate) q.set("listing_date", params.listingDate);
  if (params.source) q.set("source", params.source);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiRequest<CauseListAllResponse>(`/api/v1/causelist/all${suffix}`, { token });
}

export async function syncDailyCauseList(token: string | null): Promise<
  Array<{
    source: string;
    fetched: number;
    runs: number;
    inserted: number;
    updated: number;
    failed_runs: number;
    listing_dates: string[];
  }>
> {
  return apiRequest<
    Array<{
      source: string;
      fetched: number;
      runs: number;
      inserted: number;
      updated: number;
      failed_runs: number;
      listing_dates: string[];
    }>
  >("/api/v1/causelist/sync?source=daily", {
    method: "POST",
    token,
    timeoutMs: 300000,
  });
}

export async function getMyCauseListByAdvocate(
  params: { listingDate?: string; source?: "daily" | "weekly" | "advanced" | "monthly" } = {},
  token: string | null
): Promise<CauseListAllResponse> {
  const q = new URLSearchParams();
  if (params.listingDate) q.set("listing_date", params.listingDate);
  if (params.source) q.set("source", params.source);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiRequest<CauseListAllResponse>(`/api/v1/causelist/mine-by-advocate${suffix}`, { token });
}

export interface ProfileUpdatePayload {
  email?: string;
  mobile?: string | null;
  khc_enrollment_number?: string | null;
  khc_advocate_code?: string | null;    // numeric adv_cd for hckinfo digicourt
  preferences?: Record<string, unknown>;
}

export interface SubscriptionPlan {
  id: string;
  name: string;
  description: string;
  price_monthly: number;
  price_annually: number;
  features: Record<string, unknown>;
  popular: boolean;
}

export interface SubscriptionCurrent {
  id: string;
  userId: string;
  plan: string;
  status: string;
  billingCycle: string;
  amount: number;
  currency: string;
  startDate: string;
  endDate: string;
  trialEndDate?: string | null;
  autoRenew: boolean;
  paymentMethod?: string | null;
}

export interface UsageStats {
  periodStart: string;
  periodEnd: string;
  casesCount: number;
  documentsCount: number;
  storageUsedGb: number;
  aiAnalysesUsed: number;
}

export interface InvoiceItem {
  id: string;
  amount: number;
  currency: string;
  status: string;
  invoiceDate: string;
  dueDate: string;
  paidDate?: string | null;
  invoiceUrl?: string | null;
}

export async function getMyProfile(token: string | null): Promise<AuthUser> {
  const res = await apiRequest<{ data: AuthUser }>("/api/v1/user/profile", { token });
  return res.data;
}

export async function updateMyProfile(
  payload: ProfileUpdatePayload,
  token: string | null
): Promise<AuthUser> {
  const res = await apiRequest<{ data: AuthUser }>("/api/v1/user/profile", {
    method: "PATCH",
    token,
    body: JSON.stringify(payload),
  });
  return res.data;
}

export async function getCurrentSubscription(token: string | null): Promise<SubscriptionCurrent> {
  const res = await apiRequest<{ data: SubscriptionCurrent }>("/api/v1/subscription/current", { token });
  return res.data;
}

export async function getSubscriptionPlans(token: string | null): Promise<SubscriptionPlan[]> {
  const res = await apiRequest<{ data: SubscriptionPlan[] }>("/api/v1/subscription/plans", { token });
  return res.data;
}

export async function getSubscriptionUsage(token: string | null): Promise<UsageStats> {
  const res = await apiRequest<{ data: UsageStats }>("/api/v1/subscription/usage", { token });
  return res.data;
}

export async function getSubscriptionInvoices(token: string | null): Promise<InvoiceItem[]> {
  const res = await apiRequest<{ data: InvoiceItem[] }>("/api/v1/subscription/invoices", { token });
  return res.data;
}

export interface ImportedDocument {
  id: string;
  case_id: string;
  title: string;
  description?: string | null;
  category: string;
  s3_key: string;
  s3_bucket: string;
  file_size: number;
  content_type: string;
  source_url?: string | null;
  upload_status: string;
  uploaded_at?: string | null;
  created_at?: string;
}

export async function importLocalDocument(
  payload: {
    caseId: string;
    title: string;
    category?: string;
    description?: string;
    file: File;
  },
  token: string | null
): Promise<ImportedDocument> {
  const baseUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const url = `${baseUrl.replace(/\/$/, "")}/api/v1/upload/import/local`;
  const form = new FormData();
  form.append("caseId", payload.caseId);
  form.append("title", payload.title);
  form.append("category", payload.category || "misc");
  if (payload.description) form.append("description", payload.description);
  form.append("file", payload.file);
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { method: "POST", headers, body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Local import failed");
  }
  const body = await res.json();
  return body.data.document as ImportedDocument;
}

export async function importExternalDocument(
  payload: {
    caseId: string;
    provider?: "google_drive" | "onedrive";
    sourceUrl: string;
    title: string;
    category?: string;
    description?: string;
  },
  token: string | null
): Promise<{ document: ImportedDocument; provider: string }> {
  const res = await apiRequest<{ data: { document: ImportedDocument; provider: string } }>(
    "/api/v1/upload/import/external",
    {
      method: "POST",
      token,
      timeoutMs: 120000,
      body: JSON.stringify(payload),
    }
  );
  return res.data;
}

// ── Translation ────────────────────────────────────────────────────────────

export type TranslateDirection = "en_to_ml" | "ml_to_en";

export interface TranslateTextResponse {
  translated: string;
  direction: TranslateDirection;
  glossary_hits: number;
  warnings: string[];
  char_count: number;
}

export interface TranslateDocumentResponse {
  translated: string;
  direction: TranslateDirection;
  filename: string;
  mime_type: string;
  chunks: number;
  glossary_hits: number;
  warnings: string[];
  char_count: number;
}

/**
 * Translate a plain-text legal document.
 */
export async function translateText(
  text: string,
  direction: TranslateDirection,
  token: string | null
): Promise<TranslateTextResponse> {
  return apiRequest<TranslateTextResponse>("/api/v1/translate/text", {
    method: "POST",
    token,
    timeoutMs: 120_000,
    body: JSON.stringify({ text, direction }),
  });
}

/**
 * Upload a document file (PDF / DOCX / TXT) for translation.
 */
export async function translateDocument(
  file: File,
  direction: TranslateDirection,
  token: string | null
): Promise<TranslateDocumentResponse> {
  const baseUrl = (
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  const formData = new FormData();
  formData.append("file", file);
  formData.append("direction", direction);

  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 300_000);
  let res: Response;
  try {
    res = await fetch(`${baseUrl}/api/v1/translate/document`, {
      method: "POST",
      headers,
      body: formData,
      signal: controller.signal,
    });
  } catch (error: any) {
    if (error?.name === "AbortError") throw new Error("Document translation timed out.");
    throw new Error("Network error during document translation.");
  } finally {
    clearTimeout(timeoutId);
  }

  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText || "Translation failed");
  }
  return res.json() as Promise<TranslateDocumentResponse>;
}

// ── Translation export ─────────────────────────────────────────────────────

/**
 * Export translated text as a PDF or DOCX file download.
 * Returns a Blob that can be saved via URL.createObjectURL.
 */
export async function exportTranslation(
  text: string,
  title: string,
  direction: TranslateDirection,
  format: "pdf" | "docx",
  token: string | null
): Promise<Blob> {
  const baseUrl = (
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${baseUrl}/api/v1/translate/export`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text, title, direction, format }),
  });

  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText || "Export failed");
  }
  return res.blob();
}

// openCaseNotebook and createNotebookNote already defined above (lines ~610-636)

// ── Legal Insight (Judgment Summarizer) ──────────────────────────────────────

export interface LegalInsightJob {
  job_id: string;
  status: "queued" | "extracting" | "ocr" | "summarizing" | "validating" | "completed" | "failed";
  progress: number;
  error: string | null;
}

export interface CitationRef {
  page_number: number;
  bbox: { x: number; y: number; width: number; height: number } | null;
}

export interface SummaryItem {
  text: string;
  citation_ids: string[];
}

export interface LegalInsightResult {
  summary: {
    facts: SummaryItem[];
    issues: SummaryItem[];
    arguments: SummaryItem[];
    ratio: SummaryItem[];
    final_order: SummaryItem[];
  };
  citation_map: Record<string, CitationRef>;
}

export async function createLegalInsightJob(
  document_id: string,
  token: string
): Promise<LegalInsightJob> {
  return apiRequest<LegalInsightJob>("/api/v1/legal-insight/jobs", {
    method: "POST",
    body: JSON.stringify({ document_id }),
    token,
  });
}

export async function uploadLegalInsightPdf(
  file: File,
  token: string
): Promise<LegalInsightJob> {
  const baseUrl = (
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${baseUrl}/api/v1/legal-insight/jobs/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = `/signin?callbackUrl=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || res.statusText || "Upload failed");
  }
  return res.json() as Promise<LegalInsightJob>;
}

export async function getLegalInsightJob(
  job_id: string,
  token: string
): Promise<LegalInsightJob> {
  return apiRequest<LegalInsightJob>(`/api/v1/legal-insight/jobs/${job_id}`, {
    token,
  });
}

export async function getLegalInsightResult(
  job_id: string,
  token: string
): Promise<LegalInsightResult> {
  return apiRequest<LegalInsightResult>(`/api/v1/legal-insight/jobs/${job_id}/result`, {
    token,
  });
}

// ── Case Prep AI ─────────────────────────────────────────────────────────────

export type PrepMode =
  | "argument_builder"
  | "devils_advocate"
  | "bench_simulation"
  | "order_analysis"
  | "relief_drafting"
  | "precedent_finder";

export const PREP_MODE_LABELS: Record<PrepMode, string> = {
  argument_builder: "Argument Builder",
  devils_advocate:  "Devil's Advocate",
  bench_simulation: "Bench Simulation",
  order_analysis:   "Order Analysis",
  relief_drafting:  "Relief Drafting",
  precedent_finder: "Precedent Finder",
};

export interface PrepMessage {
  role:    "user" | "assistant";
  content: string;
}

export interface PrepSession {
  id:           string;
  case_id:      string;
  user_id:      string;
  mode:         PrepMode;
  mode_label:   string;
  document_ids: string[];
  messages:     PrepMessage[];
  created_at:   string;
  updated_at:   string;
}

export interface HearingBriefRecord {
  id:              string;
  case_id:         string;
  hearing_date:    string;
  content:         string;
  focus_areas:     string[];
  bundle_snapshot: Record<string, unknown> | null;
  created_at:      string;
}

// Create a new prep session
export async function createPrepSession(
  payload: { case_id: string; mode: PrepMode; document_ids: string[] },
  token: string
): Promise<PrepSession> {
  return apiRequest<PrepSession>("/api/v1/prep-sessions/", {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}

// List prep sessions (optionally filtered by case)
export async function listPrepSessions(
  token: string,
  case_id?: string
): Promise<PrepSession[]> {
  const qs = case_id ? `?case_id=${case_id}` : "";
  return apiRequest<PrepSession[]>(`/api/v1/prep-sessions/${qs}`, { token });
}

// Get a single prep session
export async function getPrepSession(
  session_id: string,
  token: string
): Promise<PrepSession> {
  return apiRequest<PrepSession>(`/api/v1/prep-sessions/${session_id}`, { token });
}

// Switch mode
export async function switchPrepMode(
  session_id: string,
  mode: PrepMode,
  token: string
): Promise<PrepSession> {
  return apiRequest<PrepSession>(`/api/v1/prep-sessions/${session_id}/mode`, {
    method: "PATCH",
    body: JSON.stringify({ mode }),
    token,
  });
}

// Update documents in scope
export async function updatePrepDocuments(
  session_id: string,
  document_ids: string[],
  token: string
): Promise<PrepSession> {
  return apiRequest<PrepSession>(`/api/v1/prep-sessions/${session_id}/documents`, {
    method: "PATCH",
    body: JSON.stringify({ document_ids }),
    token,
  });
}

// Delete a session
export async function deletePrepSession(
  session_id: string,
  token: string
): Promise<void> {
  await apiRequest<void>(`/api/v1/prep-sessions/${session_id}`, {
    method: "DELETE",
    token,
  });
}

// Export session to HearingBrief
export async function exportPrepSession(
  session_id: string,
  payload: { hearing_date?: string; focus_areas?: string[] },
  token: string
): Promise<HearingBriefRecord> {
  return apiRequest<HearingBriefRecord>(
    `/api/v1/prep-sessions/${session_id}/export`,
    {
      method: "POST",
      body: JSON.stringify(payload),
      token,
    }
  );
}

/**
 * streamPrepChat
 *
 * Opens an SSE connection to POST /api/v1/prep-sessions/{id}/chat/stream
 * and calls onDelta / onDone / onError as events arrive.
 *
 * Returns a cleanup function that aborts the stream.
 */
export function streamPrepChat(
  session_id: string,
  message: string,
  token: string,
  handlers: {
    onDelta:      (text: string) => void;
    onDone:       (fullText: string) => void;
    onError:      (msg: string) => void;
    onWarning?:   (msg: string) => void;
    onToolStart?: (tool: string, input: Record<string, unknown>) => void;
    onToolEnd?:   (tool: string, success: boolean, summary: string) => void;
  }
): () => void {
  const controller = new AbortController();

  const baseUrl = (
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL || ""
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  (async () => {
    try {
      const res = await fetch(
        `${baseUrl}/api/v1/prep-sessions/${session_id}/chat/stream`,
        {
          method:  "POST",
          headers: {
            "Content-Type":  "application/json",
            Authorization:   `Bearer ${token}`,
          },
          body:    JSON.stringify({ message }),
          signal:  controller.signal,
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        handlers.onError(
          (err as { detail?: string }).detail || res.statusText || "Stream failed"
        );
        return;
      }

      const reader  = res.body!.getReader();
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
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "text_delta")  handlers.onDelta(event.text ?? "");
            if (event.type === "done")        handlers.onDone(event.full_text ?? "");
            if (event.type === "error")       handlers.onError(event.message ?? "Stream error");
            if (event.type === "warning")     handlers.onWarning?.(event.message ?? "");
            if (event.type === "tool_start")  handlers.onToolStart?.(event.tool ?? "", event.input ?? {});
            if (event.type === "tool_end")    handlers.onToolEnd?.(event.tool ?? "", event.success ?? false, event.summary ?? "");
          } catch {
            // non-JSON line — skip
          }
        }
      }
    } catch (err: unknown) {
      if ((err as { name?: string }).name !== "AbortError") {
        handlers.onError(String(err));
      }
    }
  })();

  return () => controller.abort();
}

// ════════════════════════════════════════════════════════════════════════════
// Document Comparison
// ════════════════════════════════════════════════════════════════════════════

export interface LegalEntities {
  sections: string[];
  dates: string[];
  citations: string[];
  amounts: string[];
}

export interface DiffBlock {
  type: "equal" | "insert" | "delete" | "replace";
  left_text: string;
  right_text: string;
  left_start: number;
  right_start: number;
  entities_left: LegalEntities;
  entities_right: LegalEntities;
  is_substantive: boolean;
  word_diff: Array<{ op: string; left: string; right: string }> | null;
}

export interface LegalEntityChanges {
  sections_added: string[];
  sections_removed: string[];
  sections_common: string[];
  citations_added: string[];
  citations_removed: string[];
  citations_common: string[];
  amounts_added: string[];
  amounts_removed: string[];
  dates_added: string[];
  dates_removed: string[];
}

export interface ComparisonResult {
  comparison_id: string;
  doc_a_name: string;
  doc_b_name: string;
  blocks: DiffBlock[];
  prayer_a: string | null;
  prayer_b: string | null;
  prayer_diff: DiffBlock[];
  total_additions: number;
  total_deletions: number;
  total_changes: number;
  substantive_changes: number;
  legal_entity_changes: LegalEntityChanges;
  created_at: string;
}

/**
 * Upload two documents and receive a full semantic legal comparison result.
 */
export async function compareDocuments(
  fileA: File,
  fileB: File,
  docAName?: string,
  docBName?: string,
  language: string = "eng",
  token: string = ""
): Promise<ComparisonResult> {
  const form = new FormData();
  form.append("file_a", fileA);
  form.append("file_b", fileB);
  if (docAName) form.append("doc_a_name", docAName);
  if (docBName) form.append("doc_b_name", docBName);
  form.append("language", language);

  const base = getBaseUrl();
  const res = await fetch(`${base}/api/v1/doc-compare/compare`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!res.ok) {
    let msg = `Comparison failed (HTTP ${res.status})`;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }

  return res.json();
}

/**
 * Download the Comparison Memo PDF for a given comparison_id.
 * Triggers a browser download automatically.
 */
export async function downloadComparisonMemo(
  comparisonId: string,
  docAName: string,
  token: string = ""
): Promise<void> {
  const base = getBaseUrl();
  const res = await fetch(`${base}/api/v1/doc-compare/memo/${comparisonId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    let msg = `Memo generation failed (HTTP ${res.status})`;
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `LawMate_ComparisonMemo_${docAName.slice(0, 30).replace(/[^a-z0-9]/gi, "_")}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
