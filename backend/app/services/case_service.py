# # app/services/case_service.py
"""
Case service - helper functions (optional)
Direct queries in endpoints for now
"""
# This file can be empty or deleted
# All case logic is in app/api/v1/endpoints/cases.py
pass
# from sqlalchemy.orm import Session
# from sqlalchemy import and_, or_, func, text
# from typing import List, Optional, Dict, Any
# from datetime import datetime, timedelta
# from uuid import UUID

# from app.db.models import Case, CaseHistory, AIAnalysis, CaseStatus, CaseEventType
# from app.core.logger import logger

# class CaseService:
#     """
#     Service layer for case-related business logic.
#     """
    
#     @staticmethod
#     def create_case(db: Session, case_data: Dict[str, Any]) -> Case:
#         """
#         Create a new case.
#         """
#         try:
#             case = Case(**case_data)
#             db.add(case)
#             db.commit()
#             db.refresh(case)
            
#             logger.info(f"Case created: {case.efiling_number}")
            
#             # Create initial history entry
#             history = CaseHistory(
#                 case_id=case.id,
#                 event_type=CaseEventType.FILED,
#                 event_date=case.efiling_date,
#                 business_recorded=f"Case filed electronically as {case.efiling_number}"
#             )
#             db.add(history)
#             db.commit()
            
#             return case
            
#         except Exception as e:
#             db.rollback()
#             logger.error(f"Failed to create case: {str(e)}")
#             raise
    
#     @staticmethod
#     def update_case(db: Session, case: Case, update_data: Dict[str, Any]) -> Case:
#         """
#         Update an existing case.
#         """
#         try:
#             # Track what changed for history
#             changes = []
            
#             for key, value in update_data.items():
#                 if key in ['pdf_links', 'khc_id']:
#                     continue
                    
#                 old_value = getattr(case, key, None)
#                 if old_value != value and value is not None:
#                     setattr(case, key, value)
#                     changes.append(f"{key}: {old_value} → {value}")
            
#             case.updated_at = datetime.utcnow()
#             db.commit()
#             db.refresh(case)
            
#             # Log changes in history if significant
#             if changes and ('status' in update_data or 'next_hearing_date' in update_data):
#                 history = CaseHistory(
#                     case_id=case.id,
#                     event_type=CaseEventType.OTHER,
#                     event_date=datetime.utcnow(),
#                     business_recorded=f"Case updated: {'; '.join(changes[:3])}"
#                 )
#                 db.add(history)
#                 db.commit()
            
#             logger.info(f"Case updated: {case.efiling_number}")
#             return case
            
#         except Exception as e:
#             db.rollback()
#             logger.error(f"Failed to update case: {str(e)}")
#             raise
    
#     @staticmethod
#     def get_case_by_id(db: Session, case_id: UUID) -> Optional[Case]:
#         """
#         Get case by ID.
#         """
#         return db.query(Case).filter(Case.id == case_id).first()
    
#     @staticmethod
#     def get_cases(
#         db: Session,
#         filters: Dict[str, Any],
#         skip: int = 0,
#         limit: int = 50
#     ) -> List[Case]:
#         """
#         Get cases with filters and pagination.
#         Uses optimized indexes for fast queries.
#         """
#         query = db.query(Case)
        
#         # Apply filters
#         if filters.get('advocate_id'):
#             query = query.filter(Case.advocate_id == filters['advocate_id'])
        
#         if filters.get('status'):
#             query = query.filter(Case.status == filters['status'])
        
#         if filters.get('case_type'):
#             query = query.filter(Case.case_type == filters['case_type'])
        
#         if filters.get('year'):
#             query = query.filter(Case.case_year == filters['year'])
        
#         if filters.get('is_visible') is not None:
#             query = query.filter(Case.is_visible == filters['is_visible'])
#         else:
#             query = query.filter(Case.is_visible == True)
        
#         # Full-text search
#         if filters.get('search'):
#             search_query = filters['search']
#             ts_query = func.plainto_tsquery('english', search_query)
#             query = query.filter(Case.search_vector.op('@@')(ts_query))
#             query = query.order_by(func.ts_rank(Case.search_vector, ts_query).desc())
#         else:
#             query = query.order_by(Case.created_at.desc())
        
#         return query.offset(skip).limit(limit).all()
    
#     @staticmethod
#     def count_cases(db: Session, filters: Dict[str, Any]) -> int:
#         """
#         Count cases matching filters.
#         """
#         query = db.query(func.count(Case.id))
        
#         if filters.get('advocate_id'):
#             query = query.filter(Case.advocate_id == filters['advocate_id'])
        
#         if filters.get('status'):
#             query = query.filter(Case.status == filters['status'])
        
#         if filters.get('case_type'):
#             query = query.filter(Case.case_type == filters['case_type'])
        
#         if filters.get('year'):
#             query = query.filter(Case.case_year == filters['year'])
        
#         if filters.get('is_visible') is not None:
#             query = query.filter(Case.is_visible == filters['is_visible'])
        
#         if filters.get('search'):
#             search_query = filters['search']
#             ts_query = func.plainto_tsquery('english', search_query)
#             query = query.filter(Case.search_vector.op('@@')(ts_query))
        
#         return query.scalar()
    
#     @staticmethod
#     def get_upcoming_hearings(db: Session, advocate_id: str, days: int = 7) -> List[Case]:
#         """
#         Get cases with hearings in the next N days.
#         Uses idx_case_advocate_hearing compound index.
#         """
#         cutoff_date = datetime.utcnow() + timedelta(days=days)
        
#         return db.query(Case).filter(
#             and_(
#                 Case.advocate_id == advocate_id,
#                 Case.next_hearing_date.isnot(None),
#                 Case.next_hearing_date <= cutoff_date,
#                 Case.next_hearing_date >= datetime.utcnow(),
#                 Case.is_visible == True
#             )
#         ).order_by(Case.next_hearing_date.asc()).all()
    
#     @staticmethod
#     def get_high_urgency_cases(db: Session, advocate_id: str) -> List[Case]:
#         """
#         Get all cases marked as high urgency by AI.
#         Uses idx_ai_advocate_urgency compound index.
#         """
#         return db.query(Case).join(AIAnalysis).filter(
#             and_(
#                 AIAnalysis.advocate_id == advocate_id,
#                 AIAnalysis.urgency_level == 'high',
#                 AIAnalysis.status == 'completed',
#                 Case.is_visible == True
#             )
#         ).order_by(Case.next_hearing_date.asc()).all()
    
#     @staticmethod
#     def get_case_timeline(db: Session, case_id: UUID) -> List[CaseHistory]:
#         """
#         Get chronological timeline of case events.
#         Uses idx_history_case_date compound index.
#         """
#         return db.query(CaseHistory).filter(
#             CaseHistory.case_id == case_id
#         ).order_by(CaseHistory.event_date.desc()).all()
    
#     @staticmethod
#     def add_case_event(
#         db: Session,
#         case_id: UUID,
#         event_type: CaseEventType,
#         business_recorded: str,
#         event_date: datetime = None,
#         **kwargs
#     ) -> CaseHistory:
#         """
#         Add a new event to case history.
#         """
#         try:
#             history = CaseHistory(
#                 case_id=case_id,
#                 event_type=event_type,
#                 event_date=event_date or datetime.utcnow(),
#                 business_recorded=business_recorded,
#                 **kwargs
#             )
#             db.add(history)
#             db.commit()
#             db.refresh(history)
            
#             logger.info(f"Case event added: {event_type} for case {case_id}")
#             return history
            
#         except Exception as e:
#             db.rollback()
#             logger.error(f"Failed to add case event: {str(e)}")
#             raise
    
#     @staticmethod
#     def search_by_party_name(db: Session, advocate_id: str, party_name: str) -> List[Case]:
#         """
#         Search cases by party name (petitioner or respondent).
#         Uses trigram similarity for fuzzy matching.
#         """
#         return db.query(Case).filter(
#             and_(
#                 Case.advocate_id == advocate_id,
#                 or_(
#                     Case.petitioner_name.ilike(f'%{party_name}%'),
#                     Case.respondent_name.ilike(f'%{party_name}%')
#                 ),
#                 Case.is_visible == True
#             )
#         ).limit(50).all()
    
#     @staticmethod
#     def get_yearly_statistics(db: Session, advocate_id: str, year: int) -> Dict[str, Any]:
#         """
#         Get case statistics for a specific year.
#         Uses idx_case_advocate_year compound index.
#         """
#         stats = db.query(
#             Case.case_type,
#             Case.status,
#             func.count(Case.id).label('count')
#         ).filter(
#             and_(
#                 Case.advocate_id == advocate_id,
#                 Case.case_year == year
#             )
#         ).group_by(Case.case_type, Case.status).all()
        
#         # Format results
#         result = {}
#         for stat in stats:
#             if stat.case_type not in result:
#                 result[stat.case_type] = {}
#             result[stat.case_type][stat.status] = stat.count
        
#         return result