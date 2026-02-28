"""
Server-Sent Events for real-time updates
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
from datetime import datetime

from app.api.deps import get_db, get_current_user
from app.db.models import User, Case, Document



router = APIRouter()


@router.get("/updates")
async def subscribe_to_updates(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Subscribe to real-time updates via Server-Sent Events
    
    Events:
    - case_synced: New case added
    - document_uploaded: Document upload complete
    - ping: Keepalive
    """
    async def event_generator():
        last_check = datetime.now()
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            # Check if client disconnected
            if await request.is_disconnected():
                print(f"Client {current_user.email} disconnected")
                break
            
            try:
                # Check for new cases
                new_cases = db.query(Case).filter(
                    Case.advocate_id == current_user.id,
                    Case.created_at > last_check
                ).all()
                
                for case in new_cases:
                    yield {
                        "event": "case_synced",
                        "data": json.dumps({
                            "case_id": str(case.id),
                            "case_number": case.case_number or case.efiling_number,
                            "timestamp": datetime.now().isoformat()
                        })
                    }
                
                # Check for new documents
                new_documents = db.query(Document).join(Case).filter(
                    Case.advocate_id == current_user.id,
                    Document.created_at > last_check,
                    Document.upload_status == 'completed'
                ).all()
                
                for doc in new_documents:
                    yield {
                        "event": "document_uploaded",
                        "data": json.dumps({
                            "document_id": str(doc.id),
                            "case_id": str(doc.case_id),
                            "title": doc.title,
                            "timestamp": datetime.now().isoformat()
                        })
                    }
                
                last_check = datetime.now()
                
                # Send keepalive ping every 15 seconds
                yield {
                    "event": "ping",
                    "data": json.dumps({
                        "timestamp": datetime.now().isoformat()
                    })
                }
                
                retry_count = 0  # Reset on success
                
            except Exception as e:
                print(f"SSE Error for user {current_user.email}: {e}")
                retry_count += 1
                
                # Send error event
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "message": "Temporary error, retrying...",
                        "retry": retry_count
                    })
                }
            
            # Check every 5 seconds
            await asyncio.sleep(5)
        
        print(f"SSE stream ended for user {current_user.email}")
    
    return EventSourceResponse(event_generator())


# router = APIRouter()


# @router.get("/updates")
# async def subscribe_to_updates(
#     request: Request,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Subscribe to real-time updates via Server-Sent Events
    
#     Events:
#     - case_synced: New case added
#     - document_uploaded: Document upload complete
#     - analysis_completed: AI analysis finished
#     """
#     async def event_generator():
#         last_check = datetime.now()
        
#         while True:
#             # Check if client disconnected
#             if await request.is_disconnected():
#                 break
            
#             try:
#                 # Check for new cases (simplified - in production use Redis/pub-sub)
#                 new_cases = db.query(Case).filter(
#                     Case.advocate_id == current_user.id,
#                     Case.created_at > last_check
#                 ).all()
                
#                 for case in new_cases:
#                     yield {
#                         "event": "case_synced",
#                         "data": json.dumps({
#                             "case_id": str(case.id),
#                             "case_number": case.case_number or case.efiling_number,
#                             "timestamp": datetime.now().isoformat()
#                         })
#                     }
                
#                 # Check for new documents
#                 new_documents = db.query(Document).join(Case).filter(
#                     Case.advocate_id == current_user.id,
#                     Document.created_at > last_check,
#                     Document.upload_status == 'completed'
#                 ).all()
                
#                 for doc in new_documents:
#                     yield {
#                         "event": "document_uploaded",
#                         "data": json.dumps({
#                             "document_id": str(doc.id),
#                             "case_id": str(doc.case_id),
#                             "title": doc.title,
#                             "timestamp": datetime.now().isoformat()
#                         })
#                     }
                
#                 last_check = datetime.now()
                
#                 # Send keepalive every 15 seconds
#                 yield {
#                     "event": "ping",
#                     "data": json.dumps({"timestamp": datetime.now().isoformat()})
#                 }
                
#             except Exception as e:
#                 print(f"SSE Error: {e}")
#                 break
            
#             # Check every 5 seconds
#             await asyncio.sleep(5)
    
#     return EventSourceResponse(event_generator())