"""
Custom exception classes
"""
from fastapi import HTTPException


class IdentityMismatchError(HTTPException):
    """Raised when KHC ID doesn't match authenticated user"""
    def __init__(self):
        super().__init__(
            status_code=403,
            detail="KHC Advocate ID mismatch. Data does not belong to you."
        )


class CaseNotFoundError(HTTPException):
    """Raised when case doesn't exist"""
    def __init__(self, case_id: str):
        super().__init__(
            status_code=404,
            detail=f"Case {case_id} not found"
        )


class DocumentNotFoundError(HTTPException):
    """Raised when document doesn't exist"""
    def __init__(self, document_id: str):
        super().__init__(
            status_code=404,
            detail=f"Document {document_id} not found"
        )


class UnauthorizedError(HTTPException):
    """Raised when user doesn't own resource"""
    def __init__(self):
        super().__init__(
            status_code=403,
            detail="You don't have permission to access this resource"
        )


class UploadFailedError(HTTPException):
    """Raised when S3 upload fails"""
    def __init__(self, reason: str = "Unknown error"):
        super().__init__(
            status_code=500,
            detail=f"Upload failed: {reason}"
        )


class AIServiceError(HTTPException):
    """Raised when AI service fails"""
    def __init__(self, reason: str = "AI service unavailable"):
        super().__init__(
            status_code=503,
            detail=f"AI service error: {reason}"
        )