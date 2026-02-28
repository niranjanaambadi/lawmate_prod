# app/services/audit_service.py

import boto3
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger

class AuditService:
    """
    Service for audit trail logging (DPDPA compliance).
    Uses DynamoDB for high-velocity audit logs.
    """
    
    def __init__(self):
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.table = self.dynamodb.Table('lawmate-activity-trail')
    
    async def log_identity_mismatch(
        self,
        user_id: str,
        scraped_khc_id: str,
        registered_khc_id: str,
        db: Session
    ):
        """
        Log identity mismatch event (CRITICAL security event).
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'IDENTITY_MISMATCH',
                'severity': 'CRITICAL',
                'metadata': {
                    'scraped_khc_id': scraped_khc_id,
                    'registered_khc_id': registered_khc_id,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (3 * 365 * 24 * 3600)  # 3 years
            })
            
            logger.warning(f"Identity mismatch logged for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to log identity mismatch: {str(e)}")
    
    async def log_identity_verified(
        self,
        user_id: str,
        khc_id: str,
        db: Session
    ):
        """
        Log successful identity verification.
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'IDENTITY_VERIFIED',
                'severity': 'INFO',
                'metadata': {
                    'khc_id': khc_id,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (90 * 24 * 3600)  # 90 days
            })
            
        except Exception as e:
            logger.error(f"Failed to log identity verification: {str(e)}")
    
    async def log_case_sync(
        self,
        user_id: str,
        case_id: str,
        action: str,
        db: Session
    ):
        """
        Log case sync activity.
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'CASE_SYNC',
                'resource_type': 'Case',
                'resource_id': case_id,
                'metadata': {
                    'action': action,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (365 * 24 * 3600)  # 1 year
            })
            
        except Exception as e:
            logger.error(f"Failed to log case sync: {str(e)}")
    
    async def log_document_sync(
        self,
        user_id: str,
        document_id: str,
        action: str,
        db: Session
    ):
        """
        Log document sync activity.
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'DOCUMENT_SYNC',
                'resource_type': 'Document',
                'resource_id': document_id,
                'metadata': {
                    'action': action,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (365 * 24 * 3600)
            })
            
        except Exception as e:
            logger.error(f"Failed to log document sync: {str(e)}")
    
    async def log_document_access(
        self,
        user_id: str,
        document_id: str,
        action: str,
        db: Session
    ):
        """
        Log document access (viewed/downloaded).
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'DOCUMENT_ACCESS',
                'resource_type': 'Document',
                'resource_id': document_id,
                'metadata': {
                    'action': action,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (365 * 24 * 3600)
            })
            
        except Exception as e:
            logger.error(f"Failed to log document access: {str(e)}")
    
    async def log_analysis_access(
        self,
        user_id: str,
        analysis_id: str,
        db: Session
    ):
        """
        Log AI analysis access.
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'ANALYSIS_ACCESS',
                'resource_type': 'AIAnalysis',
                'resource_id': analysis_id,
                'metadata': {
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (365 * 24 * 3600)
            })
            
        except Exception as e:
            logger.error(f"Failed to log analysis access: {str(e)}")
    
    async def log_batch_sync(
        self,
        user_id: str,
        sync_id: str,
        synced_cases: int,
        failed_cases: int,
        db: Session
    ):
        """
        Log batch sync operation.
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'BATCH_SYNC',
                'metadata': {
                    'sync_id': sync_id,
                    'synced_cases': synced_cases,
                    'failed_cases': failed_cases,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (365 * 24 * 3600)
            })
            
        except Exception as e:
            logger.error(f"Failed to log batch sync: {str(e)}")

    async def log_document_deletion(
        self,
        user_id: str,
        document_id: str,
        permanent: bool,
        db: Session
    ):
        """
        Log document deletion (critical for compliance).
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'DOCUMENT_DELETION',
                'severity': 'HIGH',
                'resource_type': 'Document',
                'resource_id': document_id,
                'metadata': {
                    'permanent': permanent,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (3 * 365 * 24 * 3600)  # 3 years
            })
            
        except Exception as e:
            logger.error(f"Failed to log document deletion: {str(e)}")
    
    async def log_case_transfer(
        self,
        user_id: str,
        case_id: str,
        reason: str,
        db: Session
    ):
        """
        Log case transfer (vakalath change).
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'CASE_TRANSFER',
                'resource_type': 'Case',
                'resource_id': case_id,
                'metadata': {
                    'reason': reason,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (3 * 365 * 24 * 3600)  # 3 years
            })
            
        except Exception as e:
            logger.error(f"Failed to log case transfer: {str(e)}")
    
    async def log_analysis_feedback(
        self,
        user_id: str,
        analysis_id: str,
        rating: int,
        db: Session
    ):
        """
        Log AI analysis feedback (for quality improvement).
        """
        try:
            self.table.put_item(Item={
                'user_id': user_id,
                'timestamp': int(datetime.utcnow().timestamp()),
                'action_type': 'ANALYSIS_FEEDBACK',
                'resource_type': 'AIAnalysis',
                'resource_id': analysis_id,
                'metadata': {
                    'rating': rating,
                    'timestamp_iso': datetime.utcnow().isoformat()
                },
                'ttl': int(datetime.utcnow().timestamp()) + (365 * 24 * 3600)
            })
            
        except Exception as e:
            logger.error(f"Failed to log analysis feedback: {str(e)}")

# Singleton instance
audit_service = AuditService()