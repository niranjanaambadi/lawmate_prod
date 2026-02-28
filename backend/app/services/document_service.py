# app/services/document_service.py

from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from app.db.models import Document, Case, DocumentCategory
from app.core.logger import logger

class DocumentService:
    """
    Service layer for document management.
    """
    
    @staticmethod
    def create_document(db: Session, doc_data: Dict[str, Any]) -> Document:
        """
        Create a new document record.
        """
        try:
            document = Document(**doc_data)
            db.add(document)
            db.commit()
            db.refresh(document)
            
            logger.info(f"Document created: {document.s3_key}")
            return document
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create document: {str(e)}")
            raise
    
    @staticmethod
    def update_document(db: Session, document: Document, update_data: Dict[str, Any]) -> Document:
        """
        Update document metadata.
        """
        try:
            for key, value in update_data.items():
                if value is not None and hasattr(document, key):
                    setattr(document, key, value)
            
            document.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(document)
            
            logger.info(f"Document updated: {document.s3_key}")
            return document
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update document: {str(e)}")
            raise
    
    @staticmethod
    def get_document_by_id(db: Session, document_id: UUID) -> Optional[Document]:
        """
        Get document by ID.
        """
        return db.query(Document).filter(Document.id == document_id).first()
    
    @staticmethod
    def get_documents(
        db: Session,
        filters: Dict[str, Any],
        skip: int = 0,
        limit: int = 50
    ) -> List[Document]:
        """
        Get documents with filters.
        """
        query = db.query(Document)
        
        if filters.get('case_id'):
            query = query.filter(Document.case_id == filters['case_id'])
        
        if filters.get('category'):
            query = query.filter(Document.category == filters['category'])
        
        if filters.get('upload_status'):
            query = query.filter(Document.upload_status == filters['upload_status'])
        
        # Join with Case to filter by advocate
        if filters.get('advocate_id'):
            query = query.join(Case).filter(Case.advocate_id == filters['advocate_id'])
        
        return query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_documents_by_case(db: Session, case_id: UUID) -> List[Document]:
        """
        Get all documents for a specific case, grouped by category.
        """
        documents = db.query(Document).filter(
            Document.case_id == case_id
        ).order_by(Document.category, Document.created_at.desc()).all()
        
        # Group by category
        grouped = {}
        for doc in documents:
            if doc.category not in grouped:
                grouped[doc.category] = []
            grouped[doc.category].append(doc)
        
        return grouped
    
    @staticmethod
    def mark_document_uploaded(
        db: Session,
        document_id: UUID,
        s3_key: str,
        file_size: int
    ) -> Document:
        """
        Mark document as successfully uploaded.
        """
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            
            if not document:
                raise ValueError("Document not found")
            
            document.upload_status = "completed"
            document.uploaded_at = datetime.utcnow()
            document.s3_key = s3_key
            document.file_size = file_size
            
            db.commit()
            db.refresh(document)
            
            logger.info(f"Document upload completed: {s3_key}")
            return document
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark document as uploaded: {str(e)}")
            raise
    
    @staticmethod
    def mark_document_failed(
        db: Session,
        document_id: UUID,
        error_message: str
    ) -> Document:
        """
        Mark document upload as failed.
        """
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            
            if not document:
                raise ValueError("Document not found")
            
            document.upload_status = "failed"
            document.upload_error = error_message
            
            db.commit()
            db.refresh(document)
            
            logger.error(f"Document upload failed: {document.s3_key} - {error_message}")
            return document
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark document as failed: {str(e)}")
            raise
    
    @staticmethod
    def check_ocr_required(db: Session, document_id: UUID) -> bool:
        """
        Check if document needs OCR processing.
        This is determined after upload by checking if PDF has extractable text.
        """
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            return False
        
        return document.is_ocr_required and document.ocr_status in ["not_required", "pending"]
    
    @staticmethod
    def mark_ocr_completed(
        db: Session,
        document_id: UUID,
        textract_job_id: str
    ) -> Document:
        """
        Mark OCR processing as completed.
        """
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            
            if not document:
                raise ValueError("Document not found")
            
            document.ocr_status = "completed"
            document.ocr_job_id = textract_job_id
            
            db.commit()
            db.refresh(document)
            
            logger.info(f"OCR completed for document: {document.s3_key}")
            return document
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark OCR as completed: {str(e)}")
            raise
    
    @staticmethod
    def get_storage_stats(db: Session, advocate_id: str) -> Dict[str, Any]:
        """
        Get storage statistics for an advocate.
        """
        # Get all case IDs for the advocate
        case_ids = db.query(Case.id).filter(Case.advocate_id == advocate_id).all()
        case_ids = [c[0] for c in case_ids]
        
        # Total documents
        total_docs = db.query(func.count(Document.id)).filter(
            Document.case_id.in_(case_ids)
        ).scalar()
        
        # Total storage
        total_storage = db.query(func.sum(Document.file_size)).filter(
            Document.case_id.in_(case_ids)
        ).scalar() or 0
        
        # By category
        by_category = db.query(
            Document.category,
            func.count(Document.id).label('count'),
            func.sum(Document.file_size).label('size')
        ).filter(
            Document.case_id.in_(case_ids)
        ).group_by(Document.category).all()
        
        return {
            "total_documents": total_docs,
            "total_storage_bytes": total_storage,
            "total_storage_mb": round(total_storage / (1024 * 1024), 2),
            "by_category": {
                stat.category: {
                    "count": stat.count,
                    "size_mb": round(stat.size / (1024 * 1024), 2)
                }
                for stat in by_category
            }
        }