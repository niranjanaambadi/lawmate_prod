"""
Pydantic validation schemas
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# ============================================================================
# User Schemas
# ============================================================================

class UserBase(BaseModel):
    email: EmailStr
    khc_advocate_id: str = Field(..., min_length=5, max_length=50)
    khc_advocate_name: str = Field(..., min_length=2, max_length=255)

class UserLogin(BaseModel):
    """Login schema"""
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password - request reset link"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password with token from email"""
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class UserRegister(BaseModel):
    """Registration schema"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    khc_advocate_id: str
    khc_advocate_name: str
    mobile: Optional[str] = None
    khc_enrollment_number: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)
    mobile: Optional[str] = None
    khc_enrollment_number: Optional[str] = None
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    khc_advocate_name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None

class UserResponse(UserBase):
    id: UUID
    mobile: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    profile_verified_at: Optional[datetime] = None
    created_at: datetime
    last_login_at: Optional[datetime]
    preferences: Dict[str, Any]
    
    class Config:
        from_attributes = True

class UserOut(UserBase):
    id: UUID
    mobile: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    profile_verified_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ProfileVerificationStartRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    verify_via: str = Field(..., pattern="^(phone|email)$")


class ProfileVerificationStartResponse(BaseModel):
    success: bool
    message: str
    verify_via: Optional[str] = None
    masked_mobile: Optional[str] = None
    masked_email: Optional[str] = None
    expires_in_seconds: Optional[int] = None
    dev_otp: Optional[str] = None


class ProfileVerificationConfirmRequest(BaseModel):
    otp: str = Field(..., min_length=4, max_length=8)


class ProfileVerificationConfirmResponse(BaseModel):
    success: bool
    message: str
    verified_at: Optional[datetime] = None

# ============================================================================
# Case Schemas
# ============================================================================

class CaseBase(BaseModel):
    efiling_number: str = Field(..., min_length=5)
    case_number: Optional[str] = None
    case_type: str = Field(..., min_length=1)
    case_year: int = Field(..., ge=2000, le=2100)
    party_role: str = Field(..., pattern='^(petitioner|respondent|appellant|defendant)$')
    petitioner_name: str = Field(..., min_length=2)
    respondent_name: str = Field(..., min_length=2)
    efiling_date: datetime
    efiling_details: Optional[str] = None
    next_hearing_date: Optional[datetime] = None
    status: str = "filed"
    bench_type: Optional[str] = None
    judge_name: Optional[str] = None
    khc_source_url: Optional[str] = None

class CaseCreate(CaseBase):
    advocate_id: UUID

class CaseUpdate(BaseModel):
    case_number: Optional[str] = None
    status: Optional[str] = None
    next_hearing_date: Optional[datetime] = None
    bench_type: Optional[str] = None
    judge_name: Optional[str] = None
    court_number: Optional[str] = None

class CaseResponse(CaseBase):
    id: UUID
    advocate_id: UUID
    last_synced_at: Optional[datetime]
    sync_status: str
    is_visible: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CaseListResponse(BaseModel):
    cases: List[CaseResponse]
    total: int
    skip: int
    limit: int


class CaseLiveStatusResponse(BaseModel):
    case_id: UUID
    status: Optional[str] = None
    next_hearing_date: Optional[datetime] = None
    bench_type: Optional[str] = None
    judge_name: Optional[str] = None
    court_number: Optional[str] = None
    source_url: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    next_check_at: Optional[datetime] = None
    check_count: int = 0
    error_count: int = 0
    changed_fields: List[str] = []
    fetched_at: Optional[datetime] = None
    verification_required: bool = False
    verification_message: Optional[str] = None


class CourtSessionStatusResponse(BaseModel):
    session_valid: bool = False
    verification_required: bool = True
    message: str
    verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    last_fetch_at: Optional[datetime] = None
    last_refresh_at: Optional[datetime] = None


class CourtCaptchaVerifyRequest(BaseModel):
    captcha_text: str = Field(..., min_length=1, max_length=20)


class CourtRefreshResponse(BaseModel):
    status: str
    fetched_cases: int = 0
    updated_cases: int = 0
    last_fetch_at: Optional[datetime] = None
    message: Optional[str] = None


class PendingCaseStatusResponse(BaseModel):
    id: UUID
    case_number: str
    status_text: Optional[str] = None
    stage: Optional[str] = None
    last_order_date: Optional[datetime] = None
    next_hearing_date: Optional[datetime] = None
    source_url: Optional[str] = None
    fetched_at: datetime
    updated_at: datetime
    # Latest hearing history row fields (from raw_court_data)
    business_date: Optional[str] = None
    tentative_date: Optional[str] = None
    purpose_of_hearing: Optional[str] = None
    order_text: Optional[str] = None
    judge_name: Optional[str] = None

    class Config:
        from_attributes = True


class TrackedCaseStatusResponse(BaseModel):
    id: UUID
    case_number: str
    status_text: Optional[str] = None
    stage: Optional[str] = None
    last_order_date: Optional[datetime] = None
    next_hearing_date: Optional[datetime] = None
    source_url: Optional[str] = None
    full_details_url: Optional[str] = None
    fetched_at: Optional[datetime] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class CaseStatusLookupRequest(BaseModel):
    case_number: str = Field(..., min_length=3, max_length=120)


class CaseStatusLookupResponse(BaseModel):
    found: bool
    case_number: str
    case_type: Optional[str] = None
    filing_number: Optional[str] = None
    filing_date: Optional[datetime] = None
    registration_number: Optional[str] = None
    registration_date: Optional[datetime] = None
    cnr_number: Optional[str] = None
    efile_number: Optional[str] = None
    first_hearing_date: Optional[datetime] = None
    status_text: Optional[str] = None
    coram: Optional[str] = None
    stage: Optional[str] = None
    last_order_date: Optional[datetime] = None
    next_hearing_date: Optional[datetime] = None
    last_listed_date: Optional[datetime] = None
    last_listed_bench: Optional[str] = None
    last_listed_list: Optional[str] = None
    last_listed_item: Optional[str] = None
    petitioner_name: Optional[str] = None
    petitioner_advocates: Optional[List[str]] = None
    respondent_name: Optional[str] = None
    respondent_advocates: Optional[List[str]] = None
    served_on: Optional[List[str]] = None
    acts: Optional[List[str]] = None
    sections: Optional[List[str]] = None
    hearing_history: Optional[List[Dict[str, Any]]] = None
    interim_orders: Optional[List[Dict[str, Any]]] = None
    category_details: Optional[Dict[str, Any]] = None
    objections: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None
    source_url: Optional[str] = None
    full_details_url: Optional[str] = None
    fetched_at: datetime
    message: Optional[str] = None


class AddCaseToDashboardRequest(BaseModel):
    case_number: str = Field(..., min_length=3, max_length=120)
    petitioner_name: Optional[str] = None
    respondent_name: Optional[str] = None
    status_text: Optional[str] = None
    stage: Optional[str] = None
    last_order_date: Optional[datetime] = None
    next_hearing_date: Optional[datetime] = None
    source_url: Optional[str] = None
    full_details_url: Optional[str] = None


class AddCaseToDashboardResponse(BaseModel):
    success: bool
    created: bool
    case_id: str
    message: str


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentBase(BaseModel):
    khc_document_id: str
    category: str
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class DocumentCreate(DocumentBase):
    case_id: UUID
    s3_key: str
    s3_bucket: str = "lawmate-case-pdfs"
    file_size: int = Field(..., gt=0)
    source_url: Optional[str] = None

class DocumentResponse(DocumentBase):
    id: UUID
    case_id: UUID
    s3_key: str
    s3_bucket: str
    file_size: int
    upload_status: str
    uploaded_at: Optional[datetime]
    is_locked: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Add after DocumentCreate schema (around line 150)

class DocumentUpdate(BaseModel):
    """Schema for document updates"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = None
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# Hearing Day Schemas
# ============================================================================

class HearingNoteResponse(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    content_json: Optional[Dict[str, Any]] = None
    content_text: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HearingNotePut(BaseModel):
    content_json: Optional[Dict[str, Any]] = None
    content_text: Optional[str] = None
    version: int = Field(..., ge=1, description="Current version for optimistic lock")


class HearingNoteCitationCreate(BaseModel):
    hearing_note_id: UUID
    doc_id: UUID
    page_number: int = Field(..., ge=1)
    quote_text: Optional[str] = None
    bbox_json: Optional[Dict[str, Any]] = None
    anchor_id: Optional[str] = None


class HearingNoteCitationResponse(BaseModel):
    id: UUID
    hearing_note_id: UUID
    doc_id: UUID
    page_number: int
    quote_text: Optional[str] = None
    bbox_json: Optional[Dict[str, Any]] = None
    anchor_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class HearingNoteEnrichmentResponse(BaseModel):
    id: UUID
    hearing_note_id: UUID
    user_id: UUID
    model: str
    note_version: int
    citation_hash: str
    enrichment_json: Dict[str, Any]
    status: str
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HearingNoteEnrichmentRunResponse(BaseModel):
    success: bool
    from_cache: bool
    deterministic_only: bool
    enrichment: HearingNoteEnrichmentResponse


# ============================================================================
# Case Notebook Schemas
# ============================================================================

class NoteAttachmentResponse(BaseModel):
    id: UUID
    note_id: UUID
    file_url: str
    s3_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    file_name: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    ocr_text: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class NoteResponse(BaseModel):
    id: UUID
    notebook_id: UUID
    title: str
    order_index: int
    content_json: Optional[Dict[str, Any]] = None
    content_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    attachments: List[NoteAttachmentResponse] = []

    class Config:
        from_attributes = True


class CaseNotebookResponse(BaseModel):
    id: UUID
    user_id: UUID
    case_id: UUID
    created_at: datetime
    updated_at: datetime
    notes: List[NoteResponse] = []

    class Config:
        from_attributes = True


class CaseNotebookListItem(BaseModel):
    notebook_id: UUID
    case_id: UUID
    case_number: Optional[str] = None
    efiling_number: str
    case_type: Optional[str] = None
    petitioner_name: Optional[str] = None
    respondent_name: Optional[str] = None
    note_count: int
    updated_at: datetime


class NoteCreate(BaseModel):
    title: str = Field(default="Untitled", min_length=1, max_length=255)
    order_index: Optional[int] = None
    content_json: Optional[Dict[str, Any]] = None
    content_text: Optional[str] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    order_index: Optional[int] = None
    content_json: Optional[Dict[str, Any]] = None
    content_text: Optional[str] = None
    version: Optional[int] = Field(default=None, ge=1,
        description="Optimistic lock: current version held by the client. "
                    "If provided and doesn't match the server version a 409 is returned.")


class NoteAttachmentCreate(BaseModel):
    file_url: str
    ocr_text: Optional[str] = None
    file_name: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    s3_key: Optional[str] = None
    s3_bucket: Optional[str] = None


class NotebookSearchItem(BaseModel):
    note_id: UUID
    notebook_id: UUID
    case_id: UUID
    case_number: Optional[str] = None
    efiling_number: str
    note_title: str
    snippet: str
    updated_at: datetime


# ============================================================================
# Case History Schemas
# ============================================================================

class CaseHistoryCreate(BaseModel):
    case_id: UUID
    event_type: str
    event_date: datetime
    business_recorded: str
    judge_name: Optional[str] = None
    bench_type: Optional[str] = None
    next_hearing_date: Optional[datetime] = None

class CaseHistoryResponse(BaseModel):
    id: UUID
    case_id: UUID
    event_type: str
    event_date: datetime
    business_recorded: str
    judge_name: Optional[str]
    next_hearing_date: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

# ============================================================================
# AI Analysis Schemas
# ============================================================================

class AIAnalysisCreate(BaseModel):
    case_id: UUID

class AIAnalysisResponse(BaseModel):
    id: UUID
    case_id: UUID
    advocate_id: UUID
    status: str
    model_version: str
    analysis: Optional[Dict[str, Any]]
    urgency_level: Optional[str]
    case_summary: Optional[str]
    processed_at: Optional[datetime]
    processing_time_seconds: Optional[int]
    token_count: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True

# ============================================================================
# Detailed Case Response (with relationships)
# ============================================================================

class CaseDetailResponse(CaseResponse):
    documents: List[DocumentResponse] = []
    history: List[CaseHistoryResponse] = []
    ai_analysis: Optional[AIAnalysisResponse] = None

# ============================================================================
# Sync Schemas
# ============================================================================

class PDFLinkSchema(BaseModel):
    url: str
    document_id: str
    label: str
    category: str

class CaseSyncRequest(BaseModel):
    efiling_number: str
    case_number: Optional[str] = None
    case_type: Optional[str] = None
    case_year: Optional[int] = None
    party_role: Optional[str] = None
    petitioner_name: Optional[str] = None
    respondent_name: Optional[str] = None
    efiling_date: Optional[str] = None
    efiling_details: Optional[str] = None
    next_hearing_date: Optional[str] = None
    status: Optional[str] = None
    bench_type: Optional[str] = None
    judge_name: Optional[str] = None
    khc_source_url: Optional[str] = None
    pdf_links: List[PDFLinkSchema] = []
    khc_id: Optional[str] = None
    khc_name: Optional[str] = None

class DocumentSyncRequest(BaseModel):
    case_number: str
    khc_document_id: str
    category: str
    title: str
    s3_key: str
    file_size: int
    source_url: Optional[str] = None

# ============================================================================
# Dashboard Schemas
# ============================================================================

class DashboardStats(BaseModel):
    total_cases: int
    pending_cases: int
    disposed_cases: int
    upcoming_hearings: int
    total_documents: int
    cases_by_status: Dict[str, int]
    cases_by_type: Dict[str, int]
    monthly_trend: List[Dict[str, Any]]


class CauseListSyncResponse(BaseModel):
    source: str
    fetched: int
    runs: int
    inserted: int
    updated: int
    failed_runs: int
    listing_dates: List[str]


class CauseListRelevantItem(BaseModel):
    case_id: UUID
    case_number: Optional[str] = None
    efiling_number: str
    case_type: str
    party_role: str
    petitioner_name: str
    respondent_name: str
    listing_date: str
    source: str
    color: str
    court_number: Optional[str] = None
    bench_name: Optional[str] = None
    item_no: Optional[str] = None


class CauseListDayGroup(BaseModel):
    date: str
    items: List[CauseListRelevantItem]


class CauseListRelevantResponse(BaseModel):
    from_date: str
    to_date: str
    total: int
    days: List[CauseListDayGroup]


class CauseListRenderedHtmlResponse(BaseModel):
    listing_date: str
    source: str
    total: int
    html: str


class CauseListDailyHtmlResponse(BaseModel):
    listing_date: str
    html: str


class CauseListAllItem(BaseModel):
    id: str
    case_number: str
    listing_date: str
    source: str
    cause_list_type: Optional[str] = None
    court_number: Optional[str] = None
    bench_name: Optional[str] = None
    item_no: Optional[str] = None
    party_names: Optional[str] = None
    petitioner_name: Optional[str] = None
    respondent_name: Optional[str] = None
    advocate_names: Optional[str] = None
    fetched_from_url: Optional[str] = None


class CauseListAllResponse(BaseModel):
    listing_date: str
    source: str
    total: int
    items: List[CauseListAllItem]


class CauseListLiveItem(BaseModel):
    serial_no: Optional[str] = None
    case_number: str
    petitioner: Optional[str] = None
    respondent: Optional[str] = None
    advocate_name: Optional[str] = None
    court_number: Optional[str] = None
    bench: Optional[str] = None
    purpose: Optional[str] = None
    filing_mode: Optional[str] = None
    row_text: Optional[str] = None
    is_relevant: bool = False
    relevance_reason: Optional[str] = None


class CauseListLiveResponse(BaseModel):
    listing_date: str
    source: str
    total: int
    relevant_total: int
    items: List[CauseListLiveItem]


class CauseListDashboardItem(BaseModel):
    case_number: str
    serial_number: str
    section_label: Optional[str] = None
    court_number: Optional[str] = None
    bench_name: Optional[str] = None
    petitioner_names: List[str] = []
    respondent_names: List[str] = []
    advocates: List[str] = []
    listing_date: str


class CauseListDashboardResponse(BaseModel):
    advocate_name: Optional[str] = None
    listing_date: str
    total: int
    items: List[CauseListDashboardItem]


class CauseListCaseItemResponse(BaseModel):
    case_number: str
    serial_number: str
    case_type: Optional[str] = None
    case_year: Optional[int] = None
    section_type: Optional[str] = None
    section_label: Optional[str] = None
    court_number: Optional[str] = None
    bench_name: Optional[str] = None
    petitioner_names: List[str] = []
    respondent_names: List[str] = []
    advocates: List[str] = []
    listing_date: str


class CauseListCasesResponse(BaseModel):
    listing_date: str
    total: int
    items: List[CauseListCaseItemResponse]

# ============================================================================
# Subscription Schemas
# ============================================================================

class SubscriptionOut(BaseModel):
    id: str
    user_id: str
    plan: str
    status: str
    billing_cycle: str
    amount: float
    currency: str
    start_date: str
    end_date: str
    auto_renew: bool
    payment_method: Optional[str]
    created_at: str
    updated_at: str

class PlanDetails(BaseModel):
    id: str
    name: str
    description: str
    price_monthly: float
    price_annually: float
    features: Dict[str, Any]
    popular: bool

class UsageStats(BaseModel):
    cases_count: int
    documents_count: int
    storage_used_gb: float
    ai_analyses_used: int
    period_start: str
    period_end: str

class InvoiceOut(BaseModel):
    id: str
    subscription_id: str
    amount: float
    currency: str
    status: str
    invoice_date: str
    due_date: str
    paid_date: Optional[str]
    payment_method: Optional[str]
    invoice_url: Optional[str]

# Add to app/db/schemas.py

class CaseListItem(BaseModel):
    """Simplified case for list view"""
    id: UUID
    case_number: Optional[str]
    efiling_number: str
    case_type: str
    status: str
    petitioner_name: str
    respondent_name: str
    next_hearing_date: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

class PaginationMeta(BaseModel):
    """Pagination metadata"""
    total: int
    page: int
    per_page: int
    total_pages: int

class CaseListResponse(BaseModel):
    """Paginated case list response"""
    items: List[CaseResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
# ============================================================================
# Rebuild models to resolve forward references
# ============================================================================

CaseDetailResponse.model_rebuild()
