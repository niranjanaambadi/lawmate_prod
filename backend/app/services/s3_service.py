# app/services/s3_service.py

import boto3
from botocore.exceptions import ClientError
from typing import Optional
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.logger import logger

class S3Service:
    """
    Service layer for AWS S3 operations.
    """
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.bucket = settings.S3_BUCKET_NAME
    def generate_presigned_url(
        self,
        s3_key: str,
        content_type: str = "application/pdf",
        expires_in: int = 900
    ) -> str:
        """
        Generate pre-signed URL for PUT operation (upload).
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': s3_key,
                    'ContentType': content_type
                },
                ExpiresIn=expires_in
            )
            
            logger.info(f"Generated presigned URL for: {s3_key}")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            raise
    
    def generate_download_url(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
        expires_in: int = 3600
    ) -> str:
        """
        Generate pre-signed URL for GET operation (download).
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket or self.bucket,
                    'Key': s3_key
                },
                ExpiresIn=expires_in
            )
            
            logger.info(f"Generated download URL for: {s3_key}")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate download URL: {str(e)}")
            raise
    
    def initiate_multipart_upload(
        self,
        s3_key: str,
        content_type: str = "application/pdf",
        metadata: dict = None
    ) -> str:
        """
        Initiate multipart upload and return upload_id.
        """
        try:
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                ContentType=content_type,
                Metadata=metadata or {}
            )
            
            upload_id = response['UploadId']
            logger.info(f"Multipart upload initiated: {upload_id} for {s3_key}")
            
            return upload_id
            
        except ClientError as e:
            logger.error(f"Failed to initiate multipart upload: {str(e)}")
            raise
    
    def generate_multipart_presigned_urls(
        self,
        s3_key: str,
        upload_id: str,
        num_parts: int,
        expires_in: int = 3600
    ) -> list:
        """
        Generate pre-signed URLs for each part in multipart upload.
        """
        urls = []
        
        try:
            for part_number in range(1, num_parts + 1):
                url = self.s3_client.generate_presigned_url(
                    'upload_part',
                    Params={
                        'Bucket': self.bucket,
                        'Key': s3_key,
                        'UploadId': upload_id,
                        'PartNumber': part_number
                    },
                    ExpiresIn=expires_in
                )
                urls.append(url)
            
            logger.info(f"Generated {num_parts} part URLs for upload {upload_id}")
            return urls
            
        except ClientError as e:
            logger.error(f"Failed to generate multipart URLs: {str(e)}")
            raise
    
    def complete_multipart_upload(
        self,
        s3_key: str,
        upload_id: str,
        parts: list
    ) -> dict:
        """
        Complete multipart upload.
        Parts format: [{"PartNumber": 1, "ETag": "..."}, ...]
        """
        try:
            response = self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            logger.info(f"Multipart upload completed: {s3_key}")
            return response
            
        except ClientError as e:
            logger.error(f"Failed to complete multipart upload: {str(e)}")
            raise
    
    def abort_multipart_upload(self, s3_key: str, upload_id: str):
        """
        Abort a multipart upload.
        """
        try:
            self.s3_client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=s3_key,
                UploadId=upload_id
            )
            
            logger.info(f"Multipart upload aborted: {upload_id}")
            
        except ClientError as e:
            logger.error(f"Failed to abort multipart upload: {str(e)}")
            raise
    
    def delete_object(self, s3_key: str, bucket: Optional[str] = None):
        """
        Delete an object from S3.
        """
        try:
            self.s3_client.delete_object(
                Bucket=bucket or self.bucket,
                Key=s3_key
            )
            
            logger.info(f"Object deleted: {s3_key}")
            
        except ClientError as e:
            logger.error(f"Failed to delete object: {str(e)}")
            raise
    
    def apply_object_lock(
        self,
        s3_key: str,
        retain_until: datetime,
        bucket: Optional[str] = None
    ):
        """
        Apply object lock (legal hold) to prevent deletion.
        """
        try:
            self.s3_client.put_object_retention(
                Bucket=bucket or self.bucket,
                Key=s3_key,
                Retention={
                    'Mode': 'COMPLIANCE',
                    'RetainUntilDate': retain_until
                }
            )
            
            logger.info(f"Object lock applied: {s3_key} until {retain_until}")
            
        except ClientError as e:
            logger.error(f"Failed to apply object lock: {str(e)}")
            raise
    
    def get_object_metadata(self, s3_key: str, bucket: Optional[str] = None) -> dict:
        """
        Get object metadata from S3.
        """
        try:
            response = self.s3_client.head_object(
                Bucket=bucket or self.bucket,
                Key=s3_key
            )
            
            return {
                "content_length": response['ContentLength'],
                "content_type": response['ContentType'],
                "last_modified": response['LastModified'],
                "metadata": response.get('Metadata', {})
            }
            
        except ClientError as e:
            logger.error(f"Failed to get object metadata: {str(e)}")
            raise

# Singleton instance
s3_service = S3Service()
