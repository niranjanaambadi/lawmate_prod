"""
SQLAlchemy ORM Models (source of truth: webapp/prisma/schema.prisma)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Enum as SQLEnum,
    ForeignKey,
    Float,
    Integer,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy import Index

from app.db.database import Base

# ============================================================================
# Enums
# ============================================================================

class UserRole(str, enum.Enum):
    """User roles"""
    advocate = "advocate"
    admin = "admin"

class CaseStatus(str, enum.Enum):
    """Case status enum"""
    filed = "filed"
    registered = "registered"
    pending = "pending"
    disposed = "disposed"
    transferred = "transferred"

class CasePartyRole(str, enum.Enum):
    """Party role in case"""
    petitioner = "petitioner"
    respondent = "respondent"
    appellant = "appellant"
    defendant = "defendant"

class DocumentCategory(str, enum.Enum):
    """Document categories"""
    case_file = "case_file"
    annexure = "annexure"
    judgment = "judgment"
    order = "order"
    misc = "misc"

class UploadStatus(str, enum.Enum):
    """Document upload status"""
    pending = "pending"
    uploading = "uploading"
    completed = "completed"
    failed = "failed"

class OCRStatus(str, enum.Enum):
    """OCR processing status"""
    not_required = "not_required"
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"

class CaseEventType(str, enum.Enum):
    """Case event types"""
    hearing = "hearing"
    order = "order"
    judgment = "judgment"
    filing = "filing"
    notice = "notice"

class AIAnalysisStatus(str, enum.Enum):
    """AI analysis status"""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"

class UrgencyLevel(str, enum.Enum):
    """Urgency levels"""
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class AIInsightType(str, enum.Enum):
    bundle_analysis = "bundle_analysis"
    precedents = "precedents"
    risk_assessment = "risk_assessment"
    rights_mapping = "rights_mapping"
    narrative = "narrative"
    counter_anticipation = "counter_anticipation"
    relief_evaluation = "relief_evaluation"


class InsightStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SubscriptionPlan(str, enum.Enum):
    free = "free"
    professional = "professional"
    enterprise = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    cancelled = "cancelled"
    expired = "expired"
    trial = "trial"


class BillingCycle(str, enum.Enum):
    monthly = "monthly"
    annually = "annually"


class PaymentMethod(str, enum.Enum):
    upi = "upi"
    card = "card"
    netbanking = "netbanking"
    none = "none"


class InvoiceStatus(str, enum.Enum):
    paid = "paid"
    pending = "pending"
    failed = "failed"

class CauseListSource(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    advanced = "advanced"
    monthly = "monthly"


class CauseListEnrichmentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class AdvocateCauseListFetchStatus(str, enum.Enum):
    fetched = "fetched"
    failed  = "failed"
    empty   = "empty"


class CalendarEventType(str, enum.Enum):
    hearing = "hearing"
    deadline = "deadline"
    filing = "filing"
    reminder = "reminder"
    meeting = "meeting"
    other = "other"


class CalendarEventSource(str, enum.Enum):
    agent = "agent"
    manual = "manual"
    court_sync = "court_sync"


# ============================================================================
# Models
# ============================================================================

class User(Base):
    """User/Advocate model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    mobile = Column(String(15), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    
    # KHC Identity
    khc_advocate_id     = Column(String(50),  unique=True, nullable=False, index=True)
    khc_advocate_name   = Column(String(255), nullable=False)
    khc_enrollment_number = Column(String(50), nullable=True)
    # Numeric advocate code used on hckinfo.keralacourts.in/digicourt (adv_cd param)
    khc_advocate_code   = Column(String(20),  nullable=True)
    
    # Profile
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.advocate)
    # server_default ensures raw SQL INSERTs also get is_active=TRUE, not NULL
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_verified = Column(Boolean, nullable=False, default=False)
    profile_verified_at = Column(TIMESTAMP, nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(TIMESTAMP, nullable=True)
    last_sync_at = Column(TIMESTAMP, nullable=True)
    
    # Password reset (same columns as webapp Prisma schema)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_token_expiry = Column(TIMESTAMP, nullable=True)
    verification_otp_code = Column(String(10), nullable=True)
    verification_otp_expires_at = Column(TIMESTAMP, nullable=True)
    
    # Preferences (JSON)
    preferences = Column(JSONB, nullable=False, default=dict)
    
    # Relationships
    cases = relationship("Case", back_populates="advocate", cascade="all, delete-orphan")
    ai_analyses = relationship("AIAnalysis", back_populates="advocate", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    usage_tracking = relationship("UsageTracking", back_populates="user", cascade="all, delete-orphan")
    hearing_notes = relationship("HearingNote", back_populates="user", cascade="all, delete-orphan")
    court_session_status = relationship("CourtSessionStatus", back_populates="user", uselist=False, cascade="all, delete-orphan")
    court_fetch_runs = relationship("CourtFetchRun", back_populates="user", cascade="all, delete-orphan")
    pending_case_statuses = relationship("CourtPendingCaseStatus", back_populates="user", cascade="all, delete-orphan")
    tracked_cases = relationship("TrackedCase", back_populates="user", cascade="all, delete-orphan")
    case_notebooks = relationship("CaseNotebook", back_populates="user", cascade="all, delete-orphan")


class KHCAdvocate(Base):
    """Master mapping for KHC ID -> Advocate Name -> Registered Phone."""
    __tablename__ = "khc_advocates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    khc_advocate_id = Column(String(50), unique=True, nullable=False, index=True)
    advocate_name = Column(String(255), nullable=False)
    mobile = Column(String(15), nullable=False)
    email = Column(String(255), nullable=True)
    source = Column(String(50), nullable=False, default="manual")
    source_member_id = Column(BigInteger, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Case(Base):
    """Legal case model"""
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys
    advocate_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Case Identification
    case_number = Column(String(100), nullable=True)
    efiling_number = Column(String(100), unique=True, nullable=False)
    case_type = Column(String(50), nullable=False)
    case_year = Column(Integer, nullable=False)
    
    # Party Information
    party_role = Column(SQLEnum(CasePartyRole), nullable=False)
    petitioner_name = Column(Text, nullable=False)
    respondent_name = Column(Text, nullable=False)
    
    # Filing Details
    efiling_date = Column(TIMESTAMP, nullable=False)
    efiling_details = Column(Text, nullable=True)
    
    # Court Assignment
    bench_type = Column(String(50), nullable=True)
    judge_name = Column(String(255), nullable=True)
    court_number = Column(String(50), nullable=True)
    
    # Status
    status = Column(SQLEnum(CaseStatus), nullable=False, default=CaseStatus.filed)
    next_hearing_date = Column(TIMESTAMP, nullable=True)
    court_status = Column(Text, nullable=True)
    sync_error = Column(Text, nullable=True)
    
    # Sync Metadata
    khc_source_url = Column(Text, nullable=True)
    last_synced_at = Column(TIMESTAMP, nullable=True)
    sync_status = Column(String(50), nullable=False, default="pending")
    raw_court_data = Column(JSONB, nullable=True)
    
    # Search
    search_vector = Column(Text, nullable=True)  # TSVECTOR in PostgreSQL
    
    # Soft Delete
    is_visible = Column(Boolean, nullable=False, default=True)
    transferred_reason = Column(Text, nullable=True)
    transferred_at = Column(TIMESTAMP, nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    advocate = relationship("User", back_populates="cases")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    history = relationship("CaseHistory", back_populates="case", cascade="all, delete-orphan")
    ai_analysis = relationship("AIAnalysis", back_populates="case", uselist=False, cascade="all, delete-orphan")
    ai_insights = relationship("AIInsight", back_populates="case", cascade="all, delete-orphan")
    hearing_briefs = relationship("HearingBrief", back_populates="case", cascade="all, delete-orphan")
    hearing_notes = relationship("HearingNote", back_populates="case", cascade="all, delete-orphan")
    prep_sessions = relationship("PrepSession", back_populates="case", cascade="all, delete-orphan")
    live_status_tracker = relationship("CaseLiveStatusTracker", back_populates="case", uselist=False, cascade="all, delete-orphan")
    live_status_snapshots = relationship("CaseLiveStatusSnapshot", back_populates="case", cascade="all, delete-orphan")
    notebooks = relationship("CaseNotebook", back_populates="case", cascade="all, delete-orphan")


class TrackedCase(Base):
    """Cases manually tracked by user (can include non-owned cases)."""
    __tablename__ = "tracked_cases"
    __table_args__ = (
        UniqueConstraint("user_id", "case_number", name="uq_tracked_cases_user_case"),
        Index("ix_tracked_cases_user_visible", "user_id", "is_visible"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    case_number = Column(String(120), nullable=False)
    case_type = Column(String(50), nullable=True)
    case_year = Column(Integer, nullable=True)
    petitioner_name = Column(Text, nullable=True)
    respondent_name = Column(Text, nullable=True)
    status_text = Column(Text, nullable=True)
    stage = Column(String(100), nullable=True)
    last_order_date = Column(TIMESTAMP, nullable=True)
    next_hearing_date = Column(TIMESTAMP, nullable=True)
    source_url = Column(Text, nullable=True)
    full_details_url = Column(Text, nullable=True)
    fetched_at = Column(TIMESTAMP, nullable=True)

    is_visible = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="tracked_cases")


class CaseLiveStatusTracker(Base):
    """Latest live-status tracking metadata per case."""
    __tablename__ = "case_live_status_trackers"

    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    last_checked_at = Column(TIMESTAMP, nullable=True)
    next_check_at = Column(TIMESTAMP, nullable=True, index=True)
    last_status_hash = Column(String(64), nullable=True)
    last_error = Column(Text, nullable=True)
    check_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    check_source = Column(String(50), nullable=False, default="mcp")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    case = relationship("Case", back_populates="live_status_tracker")


class CaseLiveStatusSnapshot(Base):
    """Immutable snapshots of live-status pulls."""
    __tablename__ = "case_live_status_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=True)
    next_hearing_date = Column(TIMESTAMP, nullable=True)
    bench_type = Column(String(100), nullable=True)
    judge_name = Column(String(255), nullable=True)
    court_number = Column(String(50), nullable=True)
    source_url = Column(Text, nullable=True)
    snapshot_hash = Column(String(64), nullable=False)
    check_source = Column(String(50), nullable=False, default="mcp")
    changed_fields = Column(ARRAY(String), nullable=False, default=list)
    raw_payload = Column(JSONB, nullable=True)
    fetched_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, index=True)

    case = relationship("Case", back_populates="live_status_snapshots")


class CourtSessionStatus(Base):
    """Per-user Kerala court session tracking."""
    __tablename__ = "court_session_status"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    session_cookies_enc = Column(Text, nullable=True)
    session_valid = Column(Boolean, nullable=False, default=False)
    verified_at = Column(TIMESTAMP, nullable=True)
    expires_at = Column(TIMESTAMP, nullable=True)
    last_refresh_at = Column(TIMESTAMP, nullable=True)
    last_fetch_at = Column(TIMESTAMP, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="court_session_status")


class CourtFetchRun(Base):
    """Audit trail of court fetch attempts."""
    __tablename__ = "court_fetch_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_source = Column(String(50), nullable=False, default="manual")
    requested_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP, nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    fetched_cases = Column(Integer, nullable=False, default=0)
    updated_cases = Column(Integer, nullable=False, default=0)
    raw_html_s3_key = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    user = relationship("User", back_populates="court_fetch_runs")


class CourtPendingCaseStatus(Base):
    """Latest fetched pending-case status rows from court portal per user."""
    __tablename__ = "court_pending_case_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    case_number = Column(String(120), nullable=False, index=True)
    normalized_case_number = Column(String(120), nullable=False, index=True)
    status_text = Column(String(120), nullable=True)
    stage = Column(String(255), nullable=True)
    last_order_date = Column(TIMESTAMP, nullable=True)
    next_hearing_date = Column(TIMESTAMP, nullable=True)
    source_url = Column(Text, nullable=True)
    row_hash = Column(String(64), nullable=False)
    fetched_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="pending_case_statuses")


class Document(Base):
    """Document/PDF model"""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    
    # Document Identity
    khc_document_id = Column(String(100), nullable=False)
    category = Column(SQLEnum(DocumentCategory), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # S3 Storage
    s3_key = Column(String(500), unique=True, nullable=False)
    s3_bucket = Column(String(100), nullable=False, default="lawmate-case-pdfs")
    s3_version_id = Column(String(100), nullable=True)
    
    # File Metadata
    file_size = Column(BigInteger, nullable=False)
    content_type = Column(String(50), nullable=False, default="application/pdf")
    checksum_md5 = Column(String(32), nullable=True)
    
    # Upload Tracking
    upload_status = Column(SQLEnum(UploadStatus), nullable=False, default=UploadStatus.pending)
    uploaded_at = Column(TIMESTAMP, nullable=True)
    upload_error = Column(Text, nullable=True)
    
    # Source
    source_url = Column(Text, nullable=True)
    
    # OCR Status
    is_ocr_required = Column(Boolean, nullable=False, default=False)
    ocr_status = Column(SQLEnum(OCRStatus), nullable=True, default=OCRStatus.not_required)
    ocr_job_id = Column(String(255), nullable=True)
    
    # AI Classification Fields
    extracted_text = Column(Text, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    ai_metadata = Column(JSONB, nullable=True)

    # Legal Hold
    is_locked = Column(Boolean, nullable=False, default=False)
    lock_reason = Column(String(255), nullable=True)
    locked_at = Column(TIMESTAMP, nullable=True)
    
    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    case = relationship("Case", back_populates="documents")
    orders = relationship("CaseHistory", back_populates="order_document")
    hearing_note_citations = relationship("HearingNoteCitation", back_populates="document", cascade="all, delete-orphan")


class HearingNote(Base):
    """Hearing day notes per case per user (one note per case per user)."""
    __tablename__ = "hearing_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content_json = Column(JSONB, nullable=True)
    content_text = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_hearing_notes_case_user"), Index("ix_hearing_notes_case_user", "case_id", "user_id"))

    case = relationship("Case", back_populates="hearing_notes")
    user = relationship("User", back_populates="hearing_notes")
    citations = relationship("HearingNoteCitation", back_populates="hearing_note", cascade="all, delete-orphan")
    enrichments = relationship("HearingNoteEnrichment", back_populates="hearing_note", cascade="all, delete-orphan")


class HearingNoteCitation(Base):
    """Citation from a hearing note to a document page/region."""
    __tablename__ = "hearing_note_citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hearing_note_id = Column(UUID(as_uuid=True), ForeignKey("hearing_notes.id", ondelete="CASCADE"), nullable=False)
    doc_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    quote_text = Column(Text, nullable=True)
    bbox_json = Column(JSONB, nullable=True)
    anchor_id = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_hearing_note_citations_note_id", "hearing_note_id"),)

    hearing_note = relationship("HearingNote", back_populates="citations")
    document = relationship("Document", back_populates="hearing_note_citations")


class HearingNoteEnrichment(Base):
    """Cached deterministic + LLM enrichment snapshots for hearing notes."""
    __tablename__ = "hearing_note_enrichments"
    __table_args__ = (
        Index("ix_hearing_note_enrichments_note_updated", "hearing_note_id", "updated_at"),
        Index("ix_hearing_note_enrichments_cache", "hearing_note_id", "note_version", "citation_hash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hearing_note_id = Column(UUID(as_uuid=True), ForeignKey("hearing_notes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model = Column(String(120), nullable=False, default="deterministic")
    note_version = Column(Integer, nullable=False, default=1)
    citation_hash = Column(String(64), nullable=False, default="")
    enrichment_json = Column(JSONB, nullable=False, default=dict)
    status = Column(String(30), nullable=False, default="completed")
    error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    hearing_note = relationship("HearingNote", back_populates="enrichments")


class CaseNotebook(Base):
    """One notebook per (user, case)."""
    __tablename__ = "case_notebooks"
    __table_args__ = (
        UniqueConstraint("user_id", "case_id", name="uq_case_notebooks_user_case"),
        Index("ix_case_notebooks_user_case", "user_id", "case_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="case_notebooks")
    case = relationship("Case", back_populates="notebooks")
    notes = relationship("Note", back_populates="notebook", cascade="all, delete-orphan")


class Note(Base):
    """Notebook chapter/note."""
    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_notebook_order", "notebook_id", "order_index"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notebook_id = Column(UUID(as_uuid=True), ForeignKey("case_notebooks.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, default="Untitled")
    order_index = Column(Integer, nullable=False, default=0)
    content_json = Column(JSONB, nullable=True)
    content_text = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)   # optimistic concurrency lock
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    notebook = relationship("CaseNotebook", back_populates="notes")
    attachments = relationship("NoteAttachment", back_populates="note", cascade="all, delete-orphan")


class NoteAttachment(Base):
    """Attachment metadata for notebook notes."""
    __tablename__ = "note_attachments"
    __table_args__ = (
        Index("ix_note_attachments_note", "note_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    note_id = Column(UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    file_url = Column(Text, nullable=False)
    s3_key = Column(Text, nullable=True)
    s3_bucket = Column(String(100), nullable=True)
    file_name = Column(String(255), nullable=True)
    content_type = Column(String(100), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    ocr_text = Column(Text, nullable=True)
    uploaded_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    note = relationship("Note", back_populates="attachments")


class CaseHistory(Base):
    """Case timeline/history model"""
    __tablename__ = "case_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    
    # Event Details
    event_type = Column(SQLEnum(CaseEventType), nullable=False)
    event_date = Column(TIMESTAMP, nullable=False)
    business_recorded = Column(Text, nullable=False)
    
    # Court Details
    judge_name = Column(String(255), nullable=True)
    bench_type = Column(String(50), nullable=True)
    court_number = Column(String(50), nullable=True)
    
    # Next Hearing
    next_hearing_date = Column(TIMESTAMP, nullable=True)
    
    # Associated Document
    order_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    
    # Timestamp
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    
    # Relationships
    case = relationship("Case", back_populates="history")
    order_document = relationship("Document", back_populates="orders", foreign_keys=[order_document_id])


class AIAnalysis(Base):
    """AI case analysis model"""
    __tablename__ = "ai_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), unique=True, nullable=False)
    advocate_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Analysis Metadata
    status = Column(SQLEnum(AIAnalysisStatus), nullable=False, default=AIAnalysisStatus.pending)
    model_version = Column(String(50), nullable=False, default="claude-3.5-sonnet")
    
    # Analysis Results (JSONB)
    analysis = Column(JSONB, nullable=True)
    
    # Extracted Fields (for faster queries)
    urgency_level = Column(SQLEnum(UrgencyLevel), nullable=True)
    case_summary = Column(Text, nullable=True)
    
    # Processing Metadata
    processed_at = Column(TIMESTAMP, nullable=True)
    processing_time_seconds = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=True)
    
    # Error Handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    case = relationship("Case", back_populates="ai_analysis")
    advocate = relationship("User", back_populates="ai_analyses")


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_type = Column(SQLEnum(AIInsightType), nullable=False)
    result = Column(JSONB, nullable=False)

    model = Column(String(255), nullable=False, default="anthropic.claude-3-haiku-20240307-v1:0")
    tokens_used = Column(Integer, nullable=True)

    status = Column(SQLEnum(InsightStatus), nullable=False, default=InsightStatus.completed)
    error = Column(Text, nullable=True)

    cached = Column(Boolean, nullable=False, default=False)
    cache_key = Column(String(255), nullable=True, index=True)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    expires_at = Column(TIMESTAMP, nullable=True)

    case = relationship("Case", back_populates="ai_insights")


class HearingBrief(Base):
    __tablename__ = "hearing_briefs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    hearing_date = Column(TIMESTAMP, nullable=False)
    content = Column(Text, nullable=False)
    focus_areas = Column(ARRAY(String), nullable=False, default=list)
    bundle_snapshot = Column(JSONB, nullable=True)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    case = relationship("Case", back_populates="hearing_briefs")


class PrepSession(Base):
    """
    A sustained hearing-preparation session between a lawyer and Claude.

    Documents in scope are tracked via document_ids (subset of the case's
    documents).  All messages are stored in a JSONB column so the lawyer
    can resume the session the next day.

    mode controls which system-prompt extension is active:
        argument_builder | devils_advocate | bench_simulation |
        order_analysis   | relief_drafting
    """
    __tablename__ = "prep_sessions"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id     = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode        = Column(String(50), nullable=False, default="argument_builder")
    document_ids = Column(ARRAY(UUID(as_uuid=False)), nullable=False, default=list)
    messages    = Column(JSONB, nullable=False, default=list)  # [{role, content, ts}]
    created_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    case = relationship("Case", back_populates="prep_sessions")
    user = relationship("User")

    __table_args__ = (
        Index("ix_prep_sessions_user_case", "user_id", "case_id"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    plan = Column(SQLEnum(SubscriptionPlan), nullable=False, default=SubscriptionPlan.free)
    status = Column(SQLEnum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.trial)
    billing_cycle = Column(SQLEnum(BillingCycle), nullable=False, default=BillingCycle.monthly)
    amount = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    start_date = Column(TIMESTAMP, nullable=False)
    end_date = Column(TIMESTAMP, nullable=False)
    trial_end_date = Column(TIMESTAMP, nullable=True)
    auto_renew = Column(Boolean, nullable=False, default=True)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=True)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")
    invoices = relationship("Invoice", back_populates="subscription", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(SQLEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.pending)
    invoice_date = Column(TIMESTAMP, nullable=False)
    due_date = Column(TIMESTAMP, nullable=False)
    paid_date = Column(TIMESTAMP, nullable=True)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=True)
    invoice_url = Column(Text, nullable=True)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    subscription = relationship("Subscription", back_populates="invoices")


class UsageTracking(Base):
    __tablename__ = "usage_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = Column(TIMESTAMP, nullable=False)
    period_end = Column(TIMESTAMP, nullable=False)
    cases_count = Column(Integer, nullable=False, default=0)
    documents_count = Column(Integer, nullable=False, default=0)
    storage_used_bytes = Column(BigInteger, nullable=False, default=0)
    ai_analyses_used = Column(Integer, nullable=False, default=0)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="usage_tracking")



class CauseListIngestionRun(Base):
    """
    Audit record for raw cause-list ingestion payloads stored in S3.
    """
    __tablename__ = "cause_list_ingestion_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(SQLEnum(CauseListSource), nullable=False, index=True)
    listing_date = Column(Date, nullable=False, index=True)
    fetched_from_url = Column(Text, nullable=False)
    s3_bucket = Column(String(100), nullable=False)
    s3_key = Column(String(500), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default="fetched")
    error = Column(Text, nullable=True)
    records_found = Column(Integer, nullable=False, default=0)
    records_upserted = Column(Integer, nullable=False, default=0)
    fetched_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    parsed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_cause_list_ingestion_source_date", "source", "listing_date"),
    )


class CauseList(Base):
    """
    Normalized cause-list header row (one row per listing_date+source+court+section+pdf).
    """
    __tablename__ = "cause_lists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_date = Column(Date, nullable=False, index=True)
    source = Column(SQLEnum(CauseListSource), nullable=False, index=True)
    court_number = Column(String(30), nullable=True)
    court_code = Column(String(20), nullable=True)
    court_label = Column(String(255), nullable=True)
    bench_name = Column(String(255), nullable=True)
    cause_list_type = Column(String(120), nullable=True)
    source_pdf_url = Column(Text, nullable=True)
    s3_bucket = Column(String(100), nullable=False)
    s3_key = Column(String(500), nullable=False)
    list_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "listing_date",
            "source",
            "court_number",
            "cause_list_type",
            "s3_key",
            name="uq_cause_lists_identity",
        ),
        Index("ix_cause_lists_date_source", "listing_date", "source"),
        Index("ix_cause_lists_court_date", "court_number", "listing_date"),
    )


class CauseListCaseItem(Base):
    """
    Parsed case-level row under a cause list.
    """
    __tablename__ = "case_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cause_list_id = Column(UUID(as_uuid=True), ForeignKey("cause_lists.id", ondelete="CASCADE"), nullable=False, index=True)
    serial_number = Column(String(30), nullable=False)
    parent_serial_number = Column(String(30), nullable=True)
    case_number_raw = Column(String(120), nullable=False)
    normalized_case_number = Column(String(120), nullable=False, index=True)
    case_type = Column(String(50), nullable=True)
    case_number = Column(String(40), nullable=True)
    case_year = Column(Integer, nullable=True)
    case_category = Column(String(30), nullable=True)
    filing_mode = Column(String(40), nullable=True)
    filing_mode_raw = Column(String(80), nullable=True)
    bench_type = Column(String(20), nullable=True)
    section_type = Column(String(50), nullable=True)
    section_label = Column(String(255), nullable=True)
    page_number = Column(Integer, nullable=True)
    item_no = Column(String(30), nullable=True)
    party_names = Column(Text, nullable=True)
    petitioner_names = Column(JSONB, nullable=True)
    respondent_names = Column(JSONB, nullable=True)
    remarks = Column(Text, nullable=True)
    status = Column(String(50), nullable=True)
    order_date = Column(Date, nullable=True)
    next_listing_date = Column(Date, nullable=True)
    interim_order_expiry = Column(Date, nullable=True)
    urgent_memo_by = Column(String(255), nullable=True)
    urgent_memo_service_status = Column(Text, nullable=True)
    mediation = Column(JSONB, nullable=True)
    arbitration = Column(JSONB, nullable=True)
    linked_cases = Column(JSONB, nullable=True)
    pending_compliance = Column(JSONB, nullable=True)
    raw_text = Column(Text, nullable=True)
    raw_data = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "cause_list_id",
            "serial_number",
            "normalized_case_number",
            name="uq_case_items_causelist_serial_case",
        ),
        Index("ix_case_items_case_date_lookup", "normalized_case_number"),
        Index("ix_case_items_type_year", "case_type", "case_year"),
        Index("ix_case_items_status", "status"),
        Index("ix_case_items_status_causelist", "status", "cause_list_id"),
    )


class CauseListAdvocate(Base):
    """
    Normalized advocate reference table for cause-list parsing.
    """
    __tablename__ = "advocates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_raw = Column(String(255), nullable=False)
    name_normalized = Column(String(255), nullable=False, index=True)
    honorific = Column(String(40), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("name_normalized", name="uq_advocates_name_normalized"),
    )


class CaseAdvocate(Base):
    """
    Junction table: which advocate appeared for which parsed case item.
    """
    __tablename__ = "case_advocates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_item_id = Column(UUID(as_uuid=True), ForeignKey("case_items.id", ondelete="CASCADE"), nullable=False, index=True)
    advocate_id = Column(UUID(as_uuid=True), ForeignKey("advocates.id", ondelete="CASCADE"), nullable=False, index=True)
    side = Column(String(20), nullable=True)  # petitioner | respondent | other
    role = Column(String(80), nullable=True)
    role_raw = Column(String(255), nullable=True)
    represented_parties = Column(ARRAY(String), nullable=True)
    is_served = Column(Boolean, nullable=True)
    organization = Column(String(255), nullable=True)
    is_lead_advocate = Column(Boolean, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("case_item_id", "advocate_id", "side", name="uq_case_advocates_item_adv_side"),
    )


class CauseListApplication(Base):
    """
    Interlocutory applications parsed under each case item.
    """
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_item_id = Column(UUID(as_uuid=True), ForeignKey("case_items.id", ondelete="CASCADE"), nullable=False, index=True)
    ia_number_raw = Column(String(120), nullable=False)
    ia_type = Column(String(50), nullable=True)
    ia_number = Column(String(30), nullable=True)
    ia_year = Column(Integer, nullable=True)
    ia_purpose = Column(Text, nullable=True)
    ia_status = Column(String(50), nullable=True)
    ia_advocates = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("case_item_id", "ia_number_raw", name="uq_applications_item_ia"),
    )


class CauseListEnrichmentQueue(Base):
    """
    Deferred queue for LLM enrichment of ambiguous cause-list rows.
    """
    __tablename__ = "cause_list_enrichment_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_run_id = Column(UUID(as_uuid=True), ForeignKey("cause_list_ingestion_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    case_item_id = Column(UUID(as_uuid=True), ForeignKey("case_items.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    listing_date = Column(Date, nullable=False, index=True)
    source = Column(SQLEnum(CauseListSource), nullable=False, index=True)
    court_number = Column(String(30), nullable=True)
    serial_number = Column(String(30), nullable=True)
    page_number = Column(Integer, nullable=True)
    row_snippet = Column(Text, nullable=True)
    row_text = Column(Text, nullable=True)
    status = Column(SQLEnum(CauseListEnrichmentStatus), nullable=False, default=CauseListEnrichmentStatus.pending, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    enriched_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index("ix_cause_enrich_status_created", "status", "created_at"),
        Index("ix_cause_enrich_run_status", "ingestion_run_id", "status"),
    )


class DailyCauseList(Base):
    """
    Precomputed daily cause-list result per advocate.
    """
    __tablename__ = "daily_cause_lists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advocate_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    total_listings = Column(Integer, nullable=False, default=0)
    result_json = Column(JSONB, nullable=False, default=dict)
    parse_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("advocate_id", "date", name="uq_daily_cause_lists_adv_date"),
    )


class LegalInsightJobStatus(str, enum.Enum):
    """Status lifecycle for a legal insight (judgment summarizer) job."""
    queued = "queued"
    extracting = "extracting"
    ocr = "ocr"
    summarizing = "summarizing"
    validating = "validating"
    completed = "completed"
    failed = "failed"


class LegalInsightJob(Base):
    """
    One job per (user, document) summarization request.
    Results are cached by (pdf_sha256 + model_id + prompt_version).
    """
    __tablename__ = "legal_insight_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(SQLEnum(LegalInsightJobStatus), nullable=False, default=LegalInsightJobStatus.queued, index=True)
    progress = Column(Integer, nullable=False, default=0)
    model_id = Column(String(200), nullable=False)
    prompt_version = Column(String(20), nullable=False, default="v1")
    error = Column(Text, nullable=True)
    pdf_sha256 = Column(String(64), nullable=True, index=True)
    # For direct-upload jobs (no linked document): store the S3 location here.
    upload_s3_key = Column(String(500), nullable=True)
    upload_s3_bucket = Column(String(100), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(TIMESTAMP, nullable=True)

    chunks = relationship("LegalInsightChunk", back_populates="job", cascade="all, delete-orphan")
    result = relationship("LegalInsightResult", back_populates="job", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_legal_insight_jobs_user_doc", "user_id", "document_id"),
        Index("ix_legal_insight_jobs_sha_model_pv", "pdf_sha256", "model_id", "prompt_version"),
    )


class LegalInsightChunk(Base):
    """
    One row per text block extracted from the judgment PDF.
    ``chunk_id`` is a stable human-readable key (e.g. ``chunk_000123``) used
    in LLM prompts and citation maps so citations always resolve to a page+bbox.
    """
    __tablename__ = "legal_insight_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("legal_insight_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(50), nullable=False)          # "chunk_000123"
    page_number = Column(Integer, nullable=False)
    # Stored as percentage of page dimensions so PdfViewer can use directly.
    # Keys: x, y, width, height  (0–100 %)
    bbox = Column(JSONB, nullable=True)
    text = Column(Text, nullable=False)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    parent_chunk_id = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    job = relationship("LegalInsightJob", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("job_id", "chunk_id", name="uq_legal_insight_chunk_job_chunk"),
        Index("ix_legal_insight_chunks_job_chunk", "job_id", "chunk_id"),
    )


class LegalInsightResult(Base):
    """Validated JSON output for a completed legal insight job."""
    __tablename__ = "legal_insight_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("legal_insight_jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    result_json = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    job = relationship("LegalInsightJob", back_populates="result")


class MediationListCase(Base):
    """
    Mediation List cases extracted from the end of the daily cause-list PDF.
    Because advocate names are NOT printed in the Mediation List section, we
    store the raw case numbers here, then enrich them by fetching case details
    from the court portal so we can discover the Petitioner/Respondent Advocates.
    """
    __tablename__ = "mediation_list_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_date = Column(Date, nullable=False, index=True)
    serial_number = Column(String(30), nullable=False)
    case_number_raw = Column(String(120), nullable=False)
    court_number = Column(String(30), nullable=True)
    raw_text = Column(Text, nullable=True)

    # Enrichment lifecycle: pending → fetching → fetched | failed
    fetch_status = Column(String(20), nullable=False, default="pending", index=True)
    fetch_attempts = Column(Integer, nullable=False, default=0)
    last_fetch_error = Column(Text, nullable=True)
    fetched_at = Column(TIMESTAMP, nullable=True)

    # Populated after court portal fetch
    petitioner_names = Column(JSONB, nullable=True)      # list[str] – party names
    respondent_names = Column(JSONB, nullable=True)      # list[str] – party names
    petitioner_advocates = Column(JSONB, nullable=True)  # list[str] – advocate names
    respondent_advocates = Column(JSONB, nullable=True)  # list[str] – advocate names
    case_detail_raw = Column(JSONB, nullable=True)       # condensed enriched data

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("listing_date", "case_number_raw", name="uq_mediation_list_date_case"),
        Index("ix_mediation_list_date_status", "listing_date", "fetch_status"),
    )


class CalendarEvent(Base):
    """Calendar events for advocates."""
    __tablename__ = "calendar_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lawyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(SQLEnum(CalendarEventType), nullable=False, default=CalendarEventType.other)
    source = Column(SQLEnum(CalendarEventSource), nullable=False, default=CalendarEventSource.manual)
    start_datetime = Column(TIMESTAMP, nullable=False)
    end_datetime = Column(TIMESTAMP, nullable=True)
    all_day = Column(Boolean, nullable=False, default=False)
    location = Column(String(255), nullable=True)
    google_event_id = Column(String(255), nullable=True, index=True)
    google_synced_at = Column(TIMESTAMP, nullable=True)
    google_sync_error = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_calendar_events_lawyer_start", "lawyer_id", "start_datetime"),
        Index("ix_calendar_events_lawyer_type", "lawyer_id", "event_type", "is_active"),
        Index("ix_calendar_events_case", "case_id", "start_datetime"),
        Index("ix_calendar_events_sync_pending", "lawyer_id", "is_active", "google_synced_at"),
    )


class CalendarSyncToken(Base):
    """Google Calendar OAuth tokens per advocate."""
    __tablename__ = "calendar_sync_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lawyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    google_refresh_token_enc = Column(Text, nullable=False)
    google_access_token_enc = Column(Text, nullable=True)
    google_token_expiry = Column(TIMESTAMP, nullable=True)
    google_calendar_id = Column(String(255), nullable=False, default="primary")
    google_sync_token = Column(Text, nullable=True)
    last_synced_at = Column(TIMESTAMP, nullable=True)
    last_sync_error = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdvocateCauseList(Base):
    """
    Per-advocate cause-list entries fetched from hckinfo.keralacourts.in/digicourt
    via POST /index.php/Casedetailssearch/Casebyadv1.

    Each row = one case listed for the advocate on a given date.
    Unique constraint on (lawyer_id, advocate_name, date, case_no) makes
    upserts fully idempotent.
    """
    __tablename__ = "advocate_cause_lists"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lawyer_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    advocate_name     = Column(String(255), nullable=False)          # full name+enrollment string used in query
    advocate_code     = Column(String(20),  nullable=True)           # adv_cd used in query
    date              = Column(Date, nullable=False, index=True)

    # Cause-list entry fields
    item_no           = Column(Integer,      nullable=True)
    court_hall        = Column(String(255),  nullable=True)
    court_hall_number = Column(String(50),   nullable=True)
    bench             = Column(String(255),  nullable=True)
    list_type         = Column(String(100),  nullable=True)
    judge_name        = Column(String(255),  nullable=True)
    case_no           = Column(String(255),  nullable=True)
    petitioner        = Column(Text,         nullable=True)
    respondent        = Column(Text,         nullable=True)

    # Fetch metadata
    fetch_status      = Column(SQLEnum(AdvocateCauseListFetchStatus), nullable=False,
                               default=AdvocateCauseListFetchStatus.fetched)
    fetch_error       = Column(Text,         nullable=True)
    source_url        = Column(String(500),  nullable=True)
    fetched_at        = Column(TIMESTAMP,    nullable=True)

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    lawyer = relationship("User")

    __table_args__ = (
        Index("ix_advocate_cause_lists_lawyer_date", "lawyer_id", "date"),
        UniqueConstraint(
            "lawyer_id", "advocate_name", "date", "case_no",
            name="uq_advocate_cause_lists_lawyer_adv_date_case",
        ),
    )


class IdempotencyRecord(Base):
    """
    Stores the result of a side-effecting request keyed by (user_id, idempotency_key).
    If the same key is received again within the TTL, the cached response is returned
    instead of re-executing the operation — safe for multi-tab and retry scenarios.
    """
    __tablename__ = "idempotency_records"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String(255), nullable=False)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint       = Column(String(255), nullable=True)   # e.g. "POST /api/v1/sync/cases"
    status_code    = Column(Integer, nullable=False, default=200)
    response_body  = Column(JSONB, nullable=False, default=dict)
    created_at     = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    expires_at     = Column(TIMESTAMP, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("idempotency_key", "user_id", name="uq_idempotency_key_user"),
    )


class DocComparison(Base):
    """
    Persisted document comparison result — replaces the previous in-memory store.
    Rows are owned by a specific user and auto-expire after 2 hours so that
    the table stays small regardless of how many users run comparisons.
    Stored as JSONB so the full ComparisonResult dict can be round-tripped
    without a complex relational schema.
    """
    __tablename__ = "doc_comparisons"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)   # = comparison_id
    owner_id   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    doc_a_name = Column(String(500), nullable=False)
    doc_b_name = Column(String(500), nullable=False)
    result_json = Column(JSONB, nullable=False)   # full ComparisonResult.to_dict()
    created_at  = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    expires_at  = Column(TIMESTAMP, nullable=False, index=True)  # created_at + 2 h

    owner = relationship("User")


# ============================================================================
# Indexes (already created in schema.sql, these are for reference)
# ============================================================================

# Index(
#     'idx_user_login',
#     User.email, User.is_active
# )

# Index(
#     'idx_case_advocate_status',
#     Case.advocate_id, Case.status, Case.is_visible
# )

# """
# SQLAlchemy ORM Models

# Defines the database schema for Lawmate application.
# """
# """
# SQLAlchemy ORM models
# """
# from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, BigInteger, Enum as SQLEnum, ForeignKey
# from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
# from sqlalchemy.orm import relationship
# from sqlalchemy.sql import func
# import enum
# import uuid
# from sqlalchemy import Column, String, Index
# from datetime import datetime
# # CORRECT import - use relative or absolute
# from app.db.database import Base  # Absolute import
# # OR
# # from .database import Base  # Relative import



# # ============================================================================
# # Enums
# # ============================================================================

# class UserRole(str, enum.Enum):
#     """User roles in the system"""
#     ADVOCATE = "advocate"
#     ADMIN = "admin"

# class CaseStatus(str, enum.Enum):
#     """Case status enumeration"""
#     FILED = "filed"
#     REGISTERED = "registered"
#     PENDING = "pending"
#     DISPOSED = "disposed"
#     TRANSFERRED = "transferred"
#     WITHDRAWN = "withdrawn"

# class CasePartyRole(str, enum.Enum):
#     """Party role of the advocate"""
#     PETITIONER = "petitioner"
#     RESPONDENT = "respondent"

# class DocumentCategory(str, enum.Enum):
#     """Document category classification"""
#     AFFIRMATION = "affirmation"
#     RECEIPT = "receipt"
#     CASE_FILE = "case_file"
#     ANNEXURE = "annexure"
#     JUDGMENT = "judgment"
#     COURT_ORDER = "court_order"
#     COUNTER_AFFIDAVIT = "counter_affidavit"
#     VAKALATNAMA = "vakalatnama"
#     OTHER = "other"

# class CaseEventType(str, enum.Enum):
#     """Case history event types"""
#     FILED = "filed"
#     REGISTERED = "registered"
#     HEARING = "hearing"
#     ORDER_PASSED = "order_passed"
#     ADJOURNED = "adjourned"
#     INTERIM_STAY = "interim_stay"
#     COUNTER_FILED = "counter_filed"
#     DISPOSED = "disposed"
#     JUDGMENT = "judgment"
#     OTHER = "other"

# class AIAnalysisStatus(str, enum.Enum):
#     """AI analysis processing status"""
#     PENDING = "pending"
#     PROCESSING = "processing"
#     COMPLETED = "completed"
#     FAILED = "failed"

# class UrgencyLevel(str, enum.Enum):
#     """Case urgency level (determined by AI)"""
#     HIGH = "high"
#     MEDIUM = "medium"
#     LOW = "low"

# # ============================================================================
# # Models
# # ============================================================================

# class User(Base):
#     """
#     User model - Represents advocates using Lawmate.
#     """
#     __tablename__ = "users"
    
#     # Primary Key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
#     # Authentication (Lawmate credentials)
#     email = Column(String(255), unique=True, nullable=False, index=True)
#     mobile = Column(String(15), unique=True, nullable=True, index=True)
#     password_hash = Column(String(255), nullable=False)
    
#     # KHC Identity (The "Handshake" Key)
#     khc_advocate_id = Column(String(50), unique=True, nullable=False, index=True)
#     khc_advocate_name = Column(String(255), nullable=False)
#     khc_enrollment_number = Column(String(50), nullable=True)
    
#     # Profile
#     #role = Column(SQLEnum(UserRole), default=UserRole.ADVOCATE, nullable=False)
#     role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.advocate)

#     is_active = Column(Boolean, default=True, nullable=False)
#     is_verified = Column(Boolean, default=False, nullable=False)
    
#     # Timestamps
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
#     last_login_at = Column(DateTime, nullable=True)
#     last_sync_at = Column(DateTime, nullable=True)
    
#     # Preferences (JSONB for flexibility)
#     preferences = Column(JSONB, default={}, nullable=False)
#     # Example structure:
#     # {
#     #   "notification_email": true,
#     #   "auto_sync": true,
#     #   "theme": "light",
#     #   "language": "en"
#     # }
    
#     # Relationships
#     cases = relationship("Case", back_populates="advocate", cascade="all, delete-orphan")
#     ai_analyses = relationship("AIAnalysis", back_populates="advocate")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_user_login', 'email', 'is_active'),
#         Index('idx_user_khc', 'khc_advocate_id', 'is_active'),
#     )
    
#     def __repr__(self):
#         return f"<User {self.email} ({self.khc_advocate_id})>"


# class Case(Base):
#     """
#     Case model - Represents legal cases from KHC portal.
#     """
#     __tablename__ = "cases"
    
#     # Primary Key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
#     # Foreign Keys
#     advocate_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
#     # Case Identification
#     case_number = Column(String(100), nullable=True, index=True)  # Assigned after registration
#     efiling_number = Column(String(100), unique=True, nullable=False, index=True)
#     case_type = Column(String(50), nullable=False, index=True)  # WP(C), CRL.A, etc.
#     case_year = Column(Integer, nullable=False, index=True)
    
#     # Party Information
#     party_role = Column(SQLEnum(CasePartyRole), nullable=False, index=True)
#     petitioner_name = Column(Text, nullable=False)
#     respondent_name = Column(Text, nullable=False)
    
#     # Filing Details
#     efiling_date = Column(DateTime, nullable=False, index=True)
#     efiling_details = Column(Text, nullable=True)
    
#     # Court Assignment
#     bench_type = Column(String(50), nullable=True)  # "Single Bench", "Division Bench"
#     judge_name = Column(String(255), nullable=True)
#     court_number = Column(String(50), nullable=True)
    
#     # Status & Tracking
#     status = Column(SQLEnum(CaseStatus), default=CaseStatus.FILED, nullable=False, index=True)
#     next_hearing_date = Column(DateTime, nullable=True, index=True)
    
#     # Sync Metadata
#     khc_source_url = Column(Text, nullable=True)
#     last_synced_at = Column(DateTime, nullable=True)
#     sync_status = Column(String(50), default="pending", nullable=False)
    
#     # Full-Text Search (PostgreSQL specific)
#     search_vector = Column(TSVECTOR, nullable=True)
    
#     # Soft Delete (for Vakalath transfers)
#     is_visible = Column(Boolean, default=True, nullable=False)
#     transferred_reason = Column(Text, nullable=True)
#     transferred_at = Column(DateTime, nullable=True)
    
#     # Timestamps
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
#     # Relationships
#     advocate = relationship("User", back_populates="cases")
#     documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
#     history = relationship("CaseHistory", back_populates="case", cascade="all, delete-orphan")
#     ai_analysis = relationship("AIAnalysis", back_populates="case", uselist=False)
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_case_advocate_status', 'advocate_id', 'status', 'is_visible'),
#         Index('idx_case_advocate_hearing', 'advocate_id', 'next_hearing_date'),
#         Index('idx_case_advocate_year', 'advocate_id', 'case_year', 'case_type'),
#         Index('idx_case_search', 'search_vector', postgresql_using='gin'),
#         Index('idx_case_active', 'advocate_id', 'status', 
#               postgresql_where="status != 'disposed' AND is_visible = true"),
#     )
    
#     def __repr__(self):
#         return f"<Case {self.case_number or self.efiling_number}>"


# class Document(Base):
#     """
#     Document model - Represents PDF documents associated with cases.
#     """
#     __tablename__ = "documents"
    
#     # Primary Key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
#     # Foreign Keys
#     case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    
#     # Document Identity
#     khc_document_id = Column(String(100), nullable=False, index=True)
#     category = Column(SQLEnum(DocumentCategory), nullable=False, index=True)
#     title = Column(String(255), nullable=False)
#     description = Column(Text, nullable=True)
    
#     # S3 Storage
#     s3_key = Column(String(500), unique=True, nullable=False, index=True)
#     s3_bucket = Column(String(100), default="lawmate-case-pdfs", nullable=False)
#     s3_version_id = Column(String(100), nullable=True)
    
#     # File Metadata
#     file_size = Column(BigInteger, nullable=False)  # Bytes (supports files > 2GB)
#     content_type = Column(String(50), default="application/pdf", nullable=False)
#     checksum_md5 = Column(String(32), nullable=True)
    
#     # Upload Tracking
#     upload_status = Column(String(50), default="pending", nullable=False, index=True)
#     uploaded_at = Column(DateTime, nullable=True)
#     upload_error = Column(Text, nullable=True)
    
#     # Source URL
#     source_url = Column(Text, nullable=True)
    
#     # OCR Status
#     is_ocr_required = Column(Boolean, default=False, nullable=False)
#     ocr_status = Column(String(50), default="not_required", nullable=True)
#     ocr_job_id = Column(String(255), nullable=True)
    
#     # Legal Hold (Object Lock for compliance)
#     is_locked = Column(Boolean, default=False, nullable=False)
#     lock_reason = Column(String(255), nullable=True)
#     locked_at = Column(DateTime, nullable=True)
    
#     # Timestamps
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
#     # Relationships
#     case = relationship("Case", back_populates="documents")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_doc_case_category', 'case_id', 'category'),
#         Index('idx_doc_upload_status', 'upload_status', 'created_at'),
#         Index('idx_doc_s3_key', 's3_key'),
#     )
    
#     def __repr__(self):
#         return f"<Document {self.title} ({self.category})>"


# class CaseHistory(Base):
#     """
#     Case History model - Timeline of events in a case.
#     """
#     __tablename__ = "case_history"
    
#     # Primary Key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
#     # Foreign Keys
#     case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    
#     # Event Details
#     event_type = Column(SQLEnum(CaseEventType), nullable=False, index=True)
#     event_date = Column(DateTime, nullable=False, index=True)
#     business_recorded = Column(Text, nullable=False)
    
#     # Court Details
#     judge_name = Column(String(255), nullable=True)
#     bench_type = Column(String(50), nullable=True)
#     court_number = Column(String(50), nullable=True)
    
#     # Next Hearing
#     next_hearing_date = Column(DateTime, nullable=True)
    
#     # Associated Document (if order/judgment)
#     order_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    
#     # Metadata
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
#     # Relationships
#     case = relationship("Case", back_populates="history")
#     order_document = relationship("Document", foreign_keys=[order_document_id])
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_history_case_date', 'case_id', 'event_date'),
#         Index('idx_history_event_type', 'event_type', 'event_date'),
#     )
    
#     def __repr__(self):
#         return f"<CaseHistory {self.event_type} on {self.event_date}>"


# class AIAnalysis(Base):
#     """
#     AI Analysis model - Claude-generated case insights.
#     """
#     __tablename__ = "ai_analyses"
    
#     # Primary Key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
#     # Foreign Keys
#     case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), 
#                      unique=True, nullable=False, index=True)
#     advocate_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
#     # Analysis Metadata
#     status = Column(SQLEnum(AIAnalysisStatus), default=AIAnalysisStatus.PENDING, nullable=False, index=True)
#     model_version = Column(String(50), default="claude-3.5-sonnet", nullable=False)
    
#     # Analysis Results (JSONB for flexibility)
#     analysis = Column(JSONB, nullable=True)
#     # Structure:
#     # {
#     #   "case_type_classification": "Writ Petition (Civil)",
#     #   "key_legal_issues": ["..."],
#     #   "relevant_statutes": ["..."],
#     #   "precedent_cases": [{name, citation, relevance}],
#     #   "action_items": ["..."],
#     #   "urgency_level": "high",
#     #   "deadline_reminders": [{task, due_date, priority}],
#     #   "case_summary": "2-3 line summary"
#     # }
    
#     # Extracted Fields (for faster queries)
#     urgency_level = Column(SQLEnum(UrgencyLevel), nullable=True, index=True)
#     case_summary = Column(Text, nullable=True)
    
#     # Processing Metadata
#     processed_at = Column(DateTime, nullable=True)
#     processing_time_seconds = Column(Integer, nullable=True)
#     token_count = Column(Integer, nullable=True)
    
#     # Error Handling
#     error_message = Column(Text, nullable=True)
#     retry_count = Column(Integer, default=0, nullable=False)
    
#     # Timestamps
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
#     # Relationships
#     case = relationship("Case", back_populates="ai_analysis")
#     advocate = relationship("User", back_populates="ai_analyses")
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_ai_advocate_urgency', 'advocate_id', 'urgency_level'),
#         Index('idx_ai_status', 'status', 'created_at'),
#         Index('idx_ai_analysis_jsonb', 'analysis', postgresql_using='gin'),
#     )
    
#     def __repr__(self):
#         return f"<AIAnalysis for Case {self.case_id}>"


# class MultipartUploadSession(Base):
#     """
#     Multipart Upload Session model - Tracks active multipart uploads.
#     Used for recovery and monitoring.
#     """
#     __tablename__ = "multipart_upload_sessions"
    
#     # Primary Key
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
#     # Upload Details
#     upload_id = Column(String(255), unique=True, nullable=False, index=True)
#     s3_key = Column(String(500), nullable=False)
#     s3_bucket = Column(String(100), default="lawmate-case-pdfs", nullable=False)
    
#     # Associated Case
#     case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True)
#     advocate_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
#     # Upload Progress
#     total_parts = Column(Integer, nullable=False)
#     uploaded_parts = Column(JSONB, default=[], nullable=False)  # List of part numbers
#     failed_parts = Column(JSONB, default=[], nullable=False)
    
#     # Status
#     status = Column(String(50), default="in_progress", nullable=False, index=True)
#     # Status: in_progress, completed, aborted, failed
    
#     # File Metadata
#     file_size = Column(BigInteger, nullable=False)
#     content_type = Column(String(50), default="application/pdf", nullable=False)
    
#     # Timestamps
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
#     completed_at = Column(DateTime, nullable=True)
    
#     # TTL (for cleanup)
#     expires_at = Column(DateTime, nullable=True)  # Auto-delete after 7 days
    
#     # Indexes
#     __table_args__ = (
#         Index('idx_multipart_status', 'status', 'created_at'),
#         Index('idx_multipart_advocate', 'advocate_id', 'status'),
#     )
    
#     def __repr__(self):
#         return f"<MultipartUploadSession {self.upload_id}>"
