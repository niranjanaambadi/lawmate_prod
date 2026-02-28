# # app/api/v1/endpoints/sync.py
"""
Sync endpoints for Chrome extension
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
import re

from app.db.database import get_db
from app.db.models import Case, Document, User, DocumentCategory
from app.db.schemas import CaseSyncRequest, DocumentSyncRequest, CaseResponse
from app.api.deps import get_current_user
from app.core.config import settings

router = APIRouter()


def normalize_name(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            return datetime.strptime(raw, "%Y-%m-%d")
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_status(value: str | None) -> str:
    v = (value or "").strip().lower()
    allowed = {"filed", "registered", "pending", "disposed", "transferred"}
    return v if v in allowed else "pending"


def normalize_party_role(value: str | None) -> str:
    v = (value or "").strip().lower()
    allowed = {"petitioner", "respondent", "appellant", "defendant"}
    return v if v in allowed else "petitioner"


def normalize_case_type(case_type: str | None, case_number: str | None) -> str:
    """
    Normalize case type from incoming value or derive from case number.
    Prevent single-letter artifacts like "M".
    """
    raw = (case_type or "").strip()
    if len(raw) > 1:
        return raw

    num = (case_number or "").strip().upper()
    if num:
        match = re.match(r"^([A-Z][A-Z\.\s\(\)\/\-&]+?)\s+\d+\s*/\s*\d{4}\b", num)
        if match:
            derived = re.sub(r"\s+", " ", match.group(1)).strip()
            if len(derived) > 1:
                return derived

    return "UNKNOWN"


def normalize_document_category(value: str | None) -> str:
    """
    Map extension-side categories to DB enum categories.
    """
    v = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if v == "case_bundle":
        return "case_file"
    allowed = {e.value for e in DocumentCategory}
    return v if v in allowed else "misc"


@router.post("/cases", response_model=CaseResponse)
def sync_case(
    sync_data: CaseSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sync case data from extension
    Upsert logic: create if new, update if exists
    """
    # Verify advocate name matches
    scraped_name = normalize_name(sync_data.khc_name or "")
    expected_name = normalize_name(current_user.khc_advocate_name or "")
    if not scraped_name or scraped_name != expected_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Advocate name mismatch"
        )
    
    case_type = normalize_case_type(sync_data.case_type, sync_data.case_number)
    case_year = sync_data.case_year or datetime.utcnow().year
    party_role = normalize_party_role(sync_data.party_role)
    petitioner_name = (sync_data.petitioner_name or "Unknown").strip() or "Unknown"
    respondent_name = (sync_data.respondent_name or "Unknown").strip() or "Unknown"
    efiling_date = parse_dt(sync_data.efiling_date) or datetime.utcnow()
    next_hearing_date = parse_dt(sync_data.next_hearing_date)
    status_value = normalize_status(sync_data.status)

    # Check if case exists
    existing_case = db.query(Case).filter(
        Case.efiling_number == sync_data.efiling_number,
        Case.advocate_id == current_user.id
    ).first()
    
    if existing_case:
        # Update existing case
        existing_case.case_number = sync_data.case_number
        existing_case.case_type = case_type
        existing_case.case_year = case_year
        existing_case.party_role = party_role
        existing_case.petitioner_name = petitioner_name
        existing_case.respondent_name = respondent_name
        existing_case.efiling_date = efiling_date
        existing_case.efiling_details = sync_data.efiling_details
        existing_case.next_hearing_date = next_hearing_date
        existing_case.status = status_value
        existing_case.bench_type = sync_data.bench_type
        existing_case.judge_name = sync_data.judge_name
        existing_case.khc_source_url = sync_data.khc_source_url
        
        existing_case.last_synced_at = datetime.utcnow()
        existing_case.sync_status = "completed"
        existing_case.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing_case)
        
        return existing_case
    
    else:
        # Create new case
        new_case = Case(
            advocate_id=current_user.id,
            efiling_number=sync_data.efiling_number,
            case_number=sync_data.case_number,
            case_type=case_type,
            case_year=case_year,
            party_role=party_role,
            petitioner_name=petitioner_name,
            respondent_name=respondent_name,
            efiling_date=efiling_date,
            efiling_details=sync_data.efiling_details,
            next_hearing_date=next_hearing_date,
            status=status_value,
            bench_type=sync_data.bench_type,
            judge_name=sync_data.judge_name,
            khc_source_url=sync_data.khc_source_url,
            last_synced_at=datetime.utcnow(),
            sync_status="completed"
        )
        
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
        
        return new_case


@router.post("/documents")
def sync_document(
    sync_data: DocumentSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sync document metadata after S3 upload
    Links uploaded document to case
    """
    # Find case by case_number
    case = db.query(Case).filter(
        Case.case_number == sync_data.case_number,
        Case.advocate_id == current_user.id
    ).first()
    
    if not case:
        # Try by efiling_number
        case = db.query(Case).filter(
            Case.efiling_number == sync_data.case_number,
            Case.advocate_id == current_user.id
        ).first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    normalized_category = normalize_document_category(sync_data.category)

    # Check if document already exists
    existing_doc = db.query(Document).filter(
        Document.case_id == case.id,
        Document.khc_document_id == sync_data.khc_document_id
    ).first()
    
    if existing_doc:
        # Update existing
        existing_doc.category = normalized_category
        existing_doc.title = sync_data.title
        existing_doc.s3_key = sync_data.s3_key
        existing_doc.file_size = sync_data.file_size
        existing_doc.upload_status = "completed"
        existing_doc.uploaded_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing_doc)
        
        return {
            "message": "Document updated",
            "document_id": str(existing_doc.id)
        }
    
    else:
        # Create new document
        new_doc = Document(
            case_id=case.id,
            khc_document_id=sync_data.khc_document_id,
            category=normalized_category,
            title=sync_data.title,
            s3_key=sync_data.s3_key,
            s3_bucket=settings.S3_BUCKET_NAME,
            file_size=sync_data.file_size,
            source_url=sync_data.source_url,
            upload_status="completed",
            uploaded_at=datetime.utcnow()
        )
        
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        return {
            "message": "Document created",
            "document_id": str(new_doc.id)
        }
# from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
# from sqlalchemy.orm import Session
# from pydantic import BaseModel, validator
# from typing import List, Optional
# from datetime import datetime
# from uuid import UUID
# import asyncio

# from app.db.database import get_db
# from app.db.models import Case, User, Document, CaseHistory
# from app.db.schemas import CaseCreate, DocumentCreate
# from app.api.v1.deps import get_current_user, verify_sync_token
# from app.services.case_service import CaseService
# from app.services.document_service import DocumentService
# from app.services.audit_service import AuditService
# from app.services.ai_service import AIService

# router = APIRouter(prefix="/sync", tags=["sync"])

# # ============================================================================
# # Request Models
# # ============================================================================

# class PDFLinkSchema(BaseModel):
#     url: str
#     document_id: str
#     label: str
#     category: str

# class CaseSyncRequest(BaseModel):
#     efiling_number: str
#     case_number: Optional[str] = None
#     case_type: str
#     case_year: int
#     party_role: str  # 'petitioner' or 'respondent'
#     petitioner_name: str
#     respondent_name: str
#     efiling_date: str  # ISO format
#     efiling_details: Optional[str] = None
#     next_hearing_date: Optional[str] = None
#     status: str
#     bench_type: Optional[str] = None
#     judge_name: Optional[str] = None
#     khc_source_url: Optional[str] = None
#     pdf_links: List[PDFLinkSchema] = []
#     khc_id: str
    
#     @validator('efiling_date', 'next_hearing_date')
#     def validate_date(cls, v):
#         if v:
#             try:
#                 datetime.fromisoformat(v.replace('Z', '+00:00'))
#             except ValueError:
#                 raise ValueError('Invalid date format. Use ISO 8601.')
#         return v
    
#     @validator('party_role')
#     def validate_party_role(cls, v):
#         if v not in ['petitioner', 'respondent']:
#             raise ValueError('party_role must be "petitioner" or "respondent"')
#         return v

# class DocumentSyncRequest(BaseModel):
#     case_number: str
#     khc_document_id: str
#     category: str
#     title: str
#     s3_key: str
#     file_size: int
#     source_url: Optional[str] = None

# class BatchSyncResponse(BaseModel):
#     synced_cases: int
#     synced_documents: int
#     failed_cases: List[str]
#     failed_documents: List[str]
#     sync_id: str
#     timestamp: datetime

# # ============================================================================
# # Endpoints
# # ============================================================================

# @router.post("/cases", status_code=status.HTTP_201_CREATED)
# async def sync_case_metadata(
#     request: CaseSyncRequest,
#     background_tasks: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Sync case metadata from KHC portal.
#     This endpoint is idempotent - multiple calls with the same efiling_number will update existing case.
#     """
#     try:
#         # Verify KHC ID match
#         if current_user.khc_advocate_id != request.khc_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="KHC ID mismatch. Identity verification failed."
#             )
        
#         # Check if case already exists
#         existing_case = db.query(Case).filter(
#             Case.advocate_id == current_user.id,
#             Case.efiling_number == request.efiling_number
#         ).first()
        
#         if existing_case:
#             # Update existing case
#             case = CaseService.update_case(db, existing_case, request.dict())
#             action = "updated"
#         else:
#             # Create new case
#             case_data = {
#                 "advocate_id": current_user.id,
#                 **request.dict(exclude={'pdf_links', 'khc_id'})
#             }
#             case = CaseService.create_case(db, case_data)
#             action = "created"
        
#         # Update sync timestamp
#         case.last_synced_at = datetime.utcnow()
#         case.sync_status = "completed"
#         db.commit()
#         db.refresh(case)
        
#         # Log audit trail
#         await AuditService.log_case_sync(
#             user_id=str(current_user.id),
#             case_id=str(case.id),
#             action=action,
#             db=db
#         )
        
#         # Trigger AI analysis in background (if new case)
#         if action == "created":
#             background_tasks.add_task(
#                 trigger_ai_analysis,
#                 case_id=str(case.id),
#                 advocate_id=str(current_user.id)
#             )
        
#         return {
#             "case_id": str(case.id),
#             "action": action,
#             "efiling_number": case.efiling_number,
#             "case_number": case.case_number,
#             "status": "success"
#         }
        
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Case sync failed: {str(e)}"
#         )

# @router.post("/documents", status_code=status.HTTP_201_CREATED)
# async def sync_document_metadata(
#     request: DocumentSyncRequest,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Sync document metadata after S3 upload is complete.
#     This is called by the extension after Phase B (S3 upload).
#     """
#     try:
#         # Find the case
#         case = db.query(Case).filter(
#             Case.advocate_id == current_user.id,
#             Case.case_number == request.case_number
#         ).first()
        
#         if not case:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail=f"Case {request.case_number} not found"
#             )
        
#         # Check if document already exists
#         existing_doc = db.query(Document).filter(
#             Document.case_id == case.id,
#             Document.khc_document_id == request.khc_document_id
#         ).first()
        
#         if existing_doc:
#             # Update existing document
#             document = DocumentService.update_document(db, existing_doc, request.dict())
#             action = "updated"
#         else:
#             # Create new document record
#             doc_data = {
#                 "case_id": case.id,
#                 **request.dict()
#             }
#             document = DocumentService.create_document(db, doc_data)
#             action = "created"
        
#         # Mark upload as completed
#         document.upload_status = "completed"
#         document.uploaded_at = datetime.utcnow()
#         db.commit()
#         db.refresh(document)
        
#         # Log audit trail
#         await AuditService.log_document_sync(
#             user_id=str(current_user.id),
#             document_id=str(document.id),
#             action=action,
#             db=db
#         )
        
#         return {
#             "document_id": str(document.id),
#             "action": action,
#             "s3_key": document.s3_key,
#             "status": "success"
#         }
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Document sync failed: {str(e)}"
#         )

# @router.get("/status/{case_number}")
# async def get_sync_status(
#     case_number: str,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Get sync status for a specific case.
#     """
#     case = db.query(Case).filter(
#         Case.advocate_id == current_user.id,
#         Case.case_number == case_number
#     ).first()
    
#     if not case:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Case not found"
#         )
    
#     # Get document sync status
#     documents = db.query(Document).filter(Document.case_id == case.id).all()
    
#     doc_status = {
#         "total": len(documents),
#         "completed": sum(1 for d in documents if d.upload_status == "completed"),
#         "pending": sum(1 for d in documents if d.upload_status == "pending"),
#         "failed": sum(1 for d in documents if d.upload_status == "failed")
#     }
    
#     return {
#         "case_number": case.case_number,
#         "case_sync_status": case.sync_status,
#         "last_synced_at": case.last_synced_at.isoformat() if case.last_synced_at else None,
#         "document_status": doc_status
#     }

# @router.post("/batch")
# async def batch_sync(
#     cases: List[CaseSyncRequest],
#     background_tasks: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Batch sync multiple cases in one request.
#     Useful for bulk sync operations.
#     """
#     sync_id = str(UUID.uuid4())
#     synced_cases = 0
#     synced_documents = 0
#     failed_cases = []
#     failed_documents = []
    
#     for case_request in cases:
#         try:
#             # Sync case
#             case_result = await sync_case_metadata(
#                 request=case_request,
#                 background_tasks=background_tasks,
#                 current_user=current_user,
#                 db=db
#             )
#             synced_cases += 1
            
#         except Exception as e:
#             failed_cases.append(f"{case_request.efiling_number}: {str(e)}")
    
#     # Log batch sync
#     await AuditService.log_batch_sync(
#         user_id=str(current_user.id),
#         sync_id=sync_id,
#         synced_cases=synced_cases,
#         failed_cases=len(failed_cases),
#         db=db
#     )
    
#     return BatchSyncResponse(
#         synced_cases=synced_cases,
#         synced_documents=synced_documents,
#         failed_cases=failed_cases,
#         failed_documents=failed_documents,
#         sync_id=sync_id,
#         timestamp=datetime.utcnow()
#     )

# @router.delete("/cases/{case_number}")
# async def mark_case_transferred(
#     case_number: str,
#     reason: str = "Vakalath transferred",
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Mark a case as transferred (soft delete).
#     Called when a case no longer appears in the advocate's KHC portal.
#     """
#     case = db.query(Case).filter(
#         Case.advocate_id == current_user.id,
#         Case.case_number == case_number
#     ).first()
    
#     if not case:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Case not found"
#         )
    
#     # Soft delete
#     case.is_visible = False
#     case.transferred_reason = reason
#     case.transferred_at = datetime.utcnow()
#     case.status = "transferred"
    
#     db.commit()
    
#     # Log audit trail
#     await AuditService.log_case_transfer(
#         user_id=str(current_user.id),
#         case_id=str(case.id),
#         reason=reason,
#         db=db
#     )
    
#     return {
#         "case_number": case_number,
#         "status": "transferred",
#         "message": "Case marked as transferred"
#     }

# # ============================================================================
# # Background Tasks
# # ============================================================================

# async def trigger_ai_analysis(case_id: str, advocate_id: str):
#     """
#     Trigger AI analysis for a newly synced case.
#     This runs in the background to avoid blocking the sync response.
#     """
#     try:
#         # Wait for documents to be uploaded (max 5 minutes)
#         max_wait = 300  # 5 minutes
#         wait_interval = 10  # Check every 10 seconds
#         elapsed = 0
        
#         while elapsed < max_wait:
#             # Check if main case document is uploaded
#             from app.db.database import SessionLocal
#             db = SessionLocal()
            
#             documents = db.query(Document).filter(
#                 Document.case_id == UUID(case_id),
#                 Document.category.in_(['case_file', 'petition'])
#             ).all()
            
#             if documents and any(d.upload_status == 'completed' for d in documents):
#                 # Trigger AI analysis
#                 await AIService.analyze_case(case_id, advocate_id, db)
#                 db.close()
#                 break
            
#             db.close()
#             await asyncio.sleep(wait_interval)
#             elapsed += wait_interval
        
#     except Exception as e:
#         print(f"AI analysis trigger failed for case {case_id}: {str(e)}")
