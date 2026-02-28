"""
AI Analysis endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.database import get_db
from app.db.models import AIAnalysis, Case, User
from app.db.schemas import AIAnalysisResponse
from app.api.deps import get_current_user
from app.services.ai_service import ai_service

router = APIRouter()


@router.get("/{case_id}", response_model=AIAnalysisResponse)
def get_analysis(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get AI analysis for a case
    """
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
            detail="Not authorized"
        )
    
    # Get analysis
    analysis = db.query(AIAnalysis).filter(
        AIAnalysis.case_id == case_id
    ).first()
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found. Trigger analysis first."
        )
    
    return analysis


@router.post("/{case_id}/trigger")
def trigger_analysis(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger AI analysis for a case
    """
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
            detail="Not authorized"
        )
    
    # Trigger analysis (synchronous for now, can be made async with Celery)
    try:
        analysis = ai_service.analyze_case(
            str(case_id),
            str(current_user.id),
            db
        )
        
        if analysis and analysis.status == "completed":
            return {
                "message": "Analysis completed",
                "analysis_id": str(analysis.id),
                "status": "completed"
            }
        else:
            return {
                "message": "Analysis in progress or failed",
                "status": analysis.status if analysis else "unknown"
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post("/chat")
def chat_with_document(
    document_id: str,
    message: str,
    conversation_history: list = [],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Chat with a document using Claude
    """
    try:
        response = ai_service.chat_with_document(
            document_id,
            message,
            conversation_history,
            db
        )
        
        return {
            "response": response,
            "timestamp": "2026-01-15T10:00:00Z"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )