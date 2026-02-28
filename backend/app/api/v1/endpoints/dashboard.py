"""
Dashboard statistics endpoints for webapp
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from typing import Dict, List

from app.api.deps import get_db, get_current_user
from app.db.models import User, Case, Document
from app.db import schemas

router = APIRouter()


@router.get("/stats", response_model=schemas.DashboardStats)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive dashboard statistics
    """
    # Total cases
    total_cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    ).count()

    # Cases by status
    pending_cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.status == 'pending',
        Case.is_visible == True
    ).count()

    disposed_cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.status == 'disposed',
        Case.is_visible == True
    ).count()

    # Upcoming hearings (next 7 days)
    now = datetime.now()
    upcoming_hearings = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.next_hearing_date.between(now, now + timedelta(days=7)),
        Case.is_visible == True
    ).count()

    # Total documents
    total_documents = db.query(Document).join(Case).filter(
        Case.advocate_id == current_user.id
    ).count()

    # Cases by status (detailed)
    cases_by_status = db.query(
        Case.status,
        func.count(Case.id)
    ).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    ).group_by(Case.status).all()

    cases_by_status_dict = {status: count for status, count in cases_by_status}

    # Cases by type
    cases_by_type = db.query(
        Case.case_type,
        func.count(Case.id)
    ).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    ).group_by(Case.case_type).all()

    cases_by_type_dict = {case_type: count for case_type, count in cases_by_type}

    # Monthly trend (last 6 months)
    six_months_ago = now - timedelta(days=180)
    monthly_cases = db.query(
        extract('year', Case.created_at).label('year'),
        extract('month', Case.created_at).label('month'),
        func.count(Case.id).label('count')
    ).filter(
        Case.advocate_id == current_user.id,
        Case.created_at >= six_months_ago
    ).group_by('year', 'month').order_by('year', 'month').all()

    monthly_trend = []
    for year, month, count in monthly_cases:
        month_name = datetime(int(year), int(month), 1).strftime('%b')
        monthly_trend.append({
            "month": month_name,
            "count": count
        })

    return {
        "total_cases": total_cases,
        "pending_cases": pending_cases,
        "disposed_cases": disposed_cases,
        "upcoming_hearings": upcoming_hearings,
        "total_documents": total_documents,
        "cases_by_status": cases_by_status_dict,
        "cases_by_type": cases_by_type_dict,
        "monthly_trend": monthly_trend
    }