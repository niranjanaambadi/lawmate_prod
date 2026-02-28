# # app/services/textract_service.py

# import boto3
# import time
# from botocore.exceptions import ClientError

# from app.core.config import settings
# from app.core.logger import logger

# class TextractService:
#     """
#     Service for AWS Textract OCR processing.
#     """
    
#     def __init__(self):
#         self.textract_client = boto3.client(
#             'textract',
#             region_name=settings.AWS_REGION,
#             aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#             aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
#         )
    
#     async def extract_text(self, bucket: str, key: str) -> str:
#         """
#         Extract text from a PDF using Textract.
#         This is asynchronous - it starts a job and polls for completion.
#         """
#         try:
#             # Start document text detection
#             response = self.textract_client.start_document_text_detection(
#                 DocumentLocation={
#                     'S3Object': {
#                         'Bucket': bucket,
#                         'Name': key
#                     }
#                 }
#             )
            
#             job_id = response['JobId']
#             logger.info(f"Textract job started: {job_id} for {key}")
            
#             # Poll for completion
#             max_attempts = 60  # 5 minutes max
#             attempt = 0
            
#             while attempt < max_attempts:
#                 status_response = self.textract_client.get_document_text_detection(
#                     JobId=job_id
#                 )
                
#                 status = status_response['JobStatus']
                
#                 if status == 'SUCCEEDED':
#                     logger.info(f"Textract job completed: {job_id}")
#                     return self._extract_text_from_response(status_response, job_id)
                
#                 elif status == 'FAILED':
#                     error = status_response.get('StatusMessage', 'Unknown error')
#                     logger.error(f"Textract job failed: {job_id} - {error}")
#                     raise Exception(f"Textract failed: {error}")
                
#                 # Still in progress, wait and retry
#                 time.sleep(5)
#                 attempt += 1
            
#             raise Exception(f"Textract job timed out: {job_id}")
            
#         except ClientError as e:
#             logger.error(f"Textract error: {str(e)}")
#             raise
    
#     def _extract_text_from_response(self, response: dict, job_id: str) -> str:
#         """
#         Extract text from Textract response.
#         Handles pagination for multi-page documents.
#         """
#         text = ""
        
#         # Extract text from first page
#         for block in response.get('Blocks', []):
#             if block['BlockType'] == 'LINE':
#                 text += block['Text'] + "\n"
        
#         # Handle pagination
#         next_token = response.get('NextToken')
        
#         while next_token:
#             try:
#                 next_response = self.textract_client.get_document_text_detection(
#                     JobId=job_id,
#                     NextToken=next_token
#                 )
                
#                 for block in next_response.get('Blocks', []):
#                     if block['BlockType'] == 'LINE':
#                         text += block['Text'] + "\n"
                
#                 next_token = next_response.get('NextToken')
                
#             except ClientError as e:
#                 logger.error(f"Textract pagination error: {str(e)}")
#                 break
        
#         return text