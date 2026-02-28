"""
Document management endpoints
"""
from io import BytesIO
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from app.db.database import get_db
from app.db.models import Document, Case, User
from app.db.schemas import DocumentResponse, DocumentUpdate
from app.api.deps import get_current_user
from app.services.s3_service import S3Service

router = APIRouter()


class LockBody(BaseModel):
    reason: Optional[str] = None

# ============================================================================
# Endpoints
# ============================================================================

@router.get("/")
def get_documents(
    case_id: Optional[UUID] = Query(None, description="Filter by case ID"),
    category: Optional[str] = Query(None, description="Filter by category"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all documents for the authenticated user"""
    
    # Build query
    query = db.query(Document).join(Case).filter(
        Case.advocate_id == current_user.id
    )
    
    # Apply filters
    if case_id:
        query = query.filter(Document.case_id == case_id)
    
    if category:
        query = query.filter(Document.category == category)
    
    # Get documents
    documents = query.order_by(
        Document.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    # Webapp expects `{ data }` envelope for /api/v1/documents
    return {"data": documents}


@router.get("/{document_id}/view-url")
def get_document_view_url(
    document_id: UUID,
    expires_in: int = Query(3600, ge=60, le=86400),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return a short-lived signed URL to view/download the document. Do not store this URL."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if not case or case.advocate_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this document")
    from app.services.s3_service import S3Service
    s3 = S3Service()
    url = s3.generate_download_url(s3_key=document.s3_key, bucket=document.s3_bucket, expires_in=expires_in)
    return {"url": url, "expires_in": expires_in}


@router.get("/{document_id}/content")
def stream_document_content(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated PDF stream for same-origin in-app rendering."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if not case or case.advocate_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this document")

    s3 = S3Service()
    try:
        obj = s3.s3_client.get_object(Bucket=document.s3_bucket, Key=document.s3_key)
        blob = obj["Body"].read()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to read document: {exc}")

    filename = (document.title or "document").replace("\"", "")
    media_type = document.content_type or "application/pdf"
    headers = {"Content-Disposition": f'inline; filename="{filename}.pdf"'}
    return StreamingResponse(BytesIO(blob), media_type=media_type, headers=headers)


@router.get("/{document_id}")
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document details by ID"""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Verify ownership
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document"
        )
    
    return {"data": document}


@router.post("/presigned-url")
def get_presigned_url(
    s3_key: str,
    operation: str = "get",
    expires_in: int = Query(3600, ge=60, le=86400),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate pre-signed URL for S3 operations
    Used by frontend to view/download PDFs
    """
    
    # Verify document ownership
    document = db.query(Document).filter(Document.s3_key == s3_key).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document"
        )
    
    # Generate presigned URL (simplified - implement S3Service.generate_presigned_url)
    # For now, return mock URL
    presigned_url = f"https://{document.s3_bucket}.s3.amazonaws.com/{s3_key}?expires={expires_in}"
    
    return {"data": {"url": presigned_url, "expires_in": expires_in}}


@router.patch("/{document_id}")
def update_document(
    document_id: UUID,
    update_data: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update document metadata"""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Verify ownership
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this document"
        )
    
    # Update document
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(document, field, value)
    
    document.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(document)
    
    return {"data": document}


@router.delete("/{document_id}")
def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a document"""
    
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Verify ownership
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this document"
        )
    
    # Check if locked
    if document.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Document is locked and cannot be deleted"
        )
    
    # Delete from database
    db.delete(document)
    db.commit()
    
    return {"data": {"message": "Document deleted successfully", "document_id": str(document_id)}}


@router.post("/{document_id}/lock")
def lock_document(
    document_id: UUID,
    body: Optional[LockBody] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lock document. Webapp expects { data: document }."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if not case or case.advocate_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    reason = (body.reason if body and body.reason else None) or "Locked by user"
    document.is_locked = True
    document.lock_reason = reason
    document.locked_at = datetime.utcnow()
    document.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(document)
    return {"data": document}


@router.post("/{document_id}/unlock")
def unlock_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlock document. Webapp expects { data: document }."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if not case or case.advocate_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    document.is_locked = False
    document.lock_reason = None
    document.locked_at = None
    document.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(document)
    return {"data": document}


@router.post("/{document_id}/confirm")
def confirm_document_upload(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Confirm document upload completion
    Called after frontend uploads to S3
    """
    
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Verify ownership
    case = db.query(Case).filter(Case.id == document.case_id).first()
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    # Update status
    document.upload_status = "completed"
    document.uploaded_at = datetime.utcnow()
    
    db.commit()
    db.refresh(document)
    
    return {"data": document}


@router.get("/by-case/{case_id}", response_model=List[DocumentResponse])
def get_documents_by_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all documents for a specific case"""
    
    # Verify case ownership
    case = db.query(Case).filter(Case.id == case_id).first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this case"
        )
    
    # Get documents
    documents = db.query(Document).filter(
        Document.case_id == case_id
    ).order_by(Document.created_at.desc()).all()
    
    return documents


@router.get("/stats")
def get_document_stats(
    case_id: Optional[UUID] = Query(None, description="Filter by case ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document statistics (optionally for one case). Webapp expects { data }."""
    base_ids = db.query(Case.id).filter(Case.advocate_id == current_user.id)
    if case_id:
        base_ids = base_ids.filter(Case.id == case_id)
    case_ids = [c[0] for c in base_ids.all()]
    if not case_ids:
        out = {
            "by_category": {},
            "by_status": {},
            "total_documents": 0,
            "total_storage_bytes": 0,
            "total_storage_mb": 0,
        }
        return {"data": out}

    stats = db.query(
        Document.category,
        func.count(Document.id).label("count"),
        func.sum(Document.file_size).label("total_size"),
    ).filter(Document.case_id.in_(case_ids)).group_by(Document.category).all()
    status_counts = db.query(
        Document.upload_status,
        func.count(Document.id).label("count"),
    ).filter(Document.case_id.in_(case_ids)).group_by(Document.upload_status).all()
    total_storage = db.query(func.sum(Document.file_size)).filter(Document.case_id.in_(case_ids)).scalar() or 0

    out = {
        "by_category": {
            getattr(stat.category, "value", stat.category): {"count": stat.count, "size": stat.total_size or 0}
            for stat in stats
        },
        "by_status": {getattr(s.upload_status, "value", s.upload_status): s.count for s in status_counts},
        "total_documents": sum(s.count for s in stats),
        "total_storage_bytes": total_storage,
        "total_storage_mb": round(total_storage / (1024 * 1024), 2),
    }
    return {"data": out}
