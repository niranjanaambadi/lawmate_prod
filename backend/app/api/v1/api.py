"""
Main API router aggregator
"""
from fastapi import APIRouter
from sqlalchemy.dialects.postgresql import UUID
# ✅ Import all endpoint routers
from app.api.v1.endpoints import (
    auth,
    user,
    identity,
    cases,
    documents,
    upload,
    sync,
    analysis,
    ocr,
    ai_insights,
    health,
    hearing_day,
    roster,
    notebooks,
)

# Import new endpoints (create these if they don't exist)
try:
    from app.api.v1.endpoints import dashboard, sse, subscription
    HAS_NEW_ENDPOINTS = True
except ImportError:
    HAS_NEW_ENDPOINTS = False

try:
    from app.api.v1.endpoints import live_status_worker
    HAS_LIVE_STATUS_WORKER = True
except ImportError:
    HAS_LIVE_STATUS_WORKER = False

api_router = APIRouter()

# Include routers
api_router.include_router(ocr.router, prefix="/ocr", tags=["OCR"])  
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(user.router, prefix="/user", tags=["User"])
api_router.include_router(identity.router, prefix="/identity", tags=["Identity"])
api_router.include_router(cases.router, prefix="/cases", tags=["Cases"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(upload.router, prefix="/upload", tags=["Upload"])
api_router.include_router(sync.router, prefix="/sync", tags=["Sync"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["AI Analysis"])
api_router.include_router(ai_insights.router, prefix="/ai-insights", tags=["AI Insights"])
api_router.include_router(hearing_day.router, prefix="/hearing-day", tags=["Hearing Day"])
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(roster.router, prefix="/roster", tags=["Roster"])
api_router.include_router(notebooks.router, prefix="/notebooks", tags=["Case Notebooks"])

# Include new endpoints if available
if HAS_NEW_ENDPOINTS:
    api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
    api_router.include_router(sse.router, prefix="/sse", tags=["Real-time"])
    api_router.include_router(subscription.router, prefix="/subscription", tags=["Subscription"])

# Lambda worker endpoint: POST /api/v1/live-status-worker/run-due
if HAS_LIVE_STATUS_WORKER:
    api_router.include_router(
        live_status_worker.router,
        prefix="/live-status-worker",
        tags=["Live Status Worker"],
    )

# Legal translation
try:
    from app.api.v1.endpoints import translate as translate_endpoint
    HAS_TRANSLATE = True
except ImportError:
    HAS_TRANSLATE = False

if HAS_TRANSLATE:
    api_router.include_router(
        translate_endpoint.router,
        prefix="/translate",
        tags=["Translation"],
    )

# Legal Insight (Judgment Summarizer)
try:
    from app.api.v1.endpoints import legal_insight as legal_insight_endpoint
    HAS_LEGAL_INSIGHT = True
except ImportError:
    HAS_LEGAL_INSIGHT = False

if HAS_LEGAL_INSIGHT:
    api_router.include_router(
        legal_insight_endpoint.router,
        prefix="/legal-insight",
        tags=["Legal Insight"],
    )

# Case Prep AI
try:
    from app.api.v1.endpoints import prep_session as prep_session_endpoint
    HAS_PREP_SESSION = True
except ImportError:
    HAS_PREP_SESSION = False

if HAS_PREP_SESSION:
    api_router.include_router(
        prep_session_endpoint.router,
        prefix="/prep-sessions",
        tags=["Case Prep AI"],
    )

# Advocate Cause List (hckinfo.keralacourts.in/digicourt)
try:
    from app.api.v1.endpoints import advocate_cause_list as advocate_cause_list_endpoint
    HAS_ADVOCATE_CAUSE_LIST = True
except ImportError:
    HAS_ADVOCATE_CAUSE_LIST = False

if HAS_ADVOCATE_CAUSE_LIST:
    api_router.include_router(
        advocate_cause_list_endpoint.router,
        prefix="/advocate-cause-list",
        tags=["Advocate Cause List"],
    )

# Document Comparison
try:
    from app.api.v1.endpoints import doc_compare as doc_compare_endpoint
    HAS_DOC_COMPARE = True
except ImportError:
    HAS_DOC_COMPARE = False

if HAS_DOC_COMPARE:
    api_router.include_router(
        doc_compare_endpoint.router,
        prefix="/doc-compare",
        tags=["Document Comparison"],
    )
