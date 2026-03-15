# # app/core/config.py
"""
Application configuration using Pydantic Settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json
import logging
from pydantic import field_validator
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    
    # Application
    APP_NAME: str = "Lawmate"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str
    
    # JWT Authentication
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # AWS Configuration
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "ap-south-1"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    # Model used exclusively by the LawMate AI chat agent (ChatWidget).
    # Use a Bedrock cross-region inference profile ARN for Claude 4.x models.
    # Example: us.anthropic.claude-sonnet-4-5-20250514-v1:0
    # Falls back to BEDROCK_MODEL_ID if not set.
    CHAT_AGENT_MODEL_ID: str = "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
    HEARING_DAY_BEDROCK_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    CAUSELIST_BEDROCK_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    ANTHROPIC_API_KEY: str = ""
    CAUSELIST_ANTHROPIC_MODEL: str = "claude-haiku-4-5-20251001"

    @field_validator("BEDROCK_MODEL_ID", mode="before")
    @classmethod
    def strip_bedrock_model_id(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    # S3
    S3_BUCKET_NAME: str = "lawmate-case-pdfs"
    ROSTER_S3_BUCKET_NAME: str = "lawmate-khc-prod"
    ROSTER_S3_PREFIX: str = "roster"
    ROSTER_SOURCE_URL: str = "https://highcourt.kerala.gov.in/"
    CAUSELIST_S3_BUCKET_NAME: str = "lawmate-khc-prod"
    CAUSELIST_S3_PREFIX: str = "causelist"
    CAUSELIST_DAILY_URL: str = "https://hckinfo.keralacourts.in/digicourt/Casedetailssearch/viewCauselist"
    CAUSELIST_WEEKLY_URL: str = ""
    CAUSELIST_ADVANCED_URL: str = ""
    CAUSELIST_MONTHLY_URL: str = ""
    CAUSELIST_SCHEMA_PATH: str = "backend/database/cause_list_schema.json"
    CAUSELIST_LLM_DISAMBIGUATION_ENABLED: bool = True
    CAUSELIST_LLM_MAX_ROWS_PER_PDF: int = 20
    CAUSELIST_ENRICHMENT_QUEUE_ENABLED: bool = True
    CAUSELIST_ENRICHMENT_MAX_ATTEMPTS: int = 5
    CAUSELIST_ENRICHMENT_BATCH_SIZE: int = 20
    CAUSELIST_ENRICHMENT_BASE_DELAY_SECONDS: float = 1.5
    CAUSELIST_ENRICHMENT_WORKER_ENABLED: bool = True
    CAUSELIST_ENRICHMENT_WORKER_INTERVAL_MINUTES: int = 10
    CAUSELIST_ENRICHMENT_WORKER_PROCESS_LIMIT: int = 50
    CAUSELIST_ENABLE_SCHEDULED_SYNC: bool = True
    CAUSELIST_DAILY_SYNC_HOUR_IST: int = 18
    CAUSELIST_DAILY_SYNC_MINUTE_IST: int = 50
    CAUSELIST_RETENTION_ENABLED: bool = True
    CAUSELIST_RETENTION_DAYS: int = 60
    CASES_RECYCLE_BIN_PURGE_ENABLED: bool = True
    CASES_RECYCLE_BIN_RETENTION_DAYS: int = 90

    # Oracle VM Scraper Service
    # Set SCRAPER_SERVICE_URL to route on-demand scraping calls to the Oracle
    # Cloud VM (Indian IP) instead of running Playwright locally on Railway.
    # Leave empty to fall back to local Playwright.
    SCRAPER_SERVICE_URL: str = ""          # e.g. http://129.154.254.110:8001
    SCRAPER_SERVICE_SECRET: str = ""       # shared x-scraper-secret header
    SCRAPER_SERVICE_TIMEOUT: int = 120     # seconds per request

    # MCP live-status integration
    MCP_LIVE_STATUS_URL: str = ""
    MCP_LIVE_STATUS_TOKEN: str = ""
    MCP_WORKER_TOKEN: str = ""
    LIVE_STATUS_REFRESH_WINDOW_HOURS: int = 24
    LIVE_STATUS_SESSION_TTL_HOURS: int = 24
    LIVE_STATUS_COURT_BASE_URL: str = "https://hckinfo.keralacourts.in/digicourt"
    LIVE_STATUS_STATUSADVNAME_PATH: str = "/Casedetailssearch/Statusadvname"
    LIVE_STATUS_STATUSCASENO_PATH: str = "/Casedetailssearch/Statuscasenovoice"
    LIVE_STATUS_FIND_ADVOCATE_PATH: str = "/index.php/Casedetailssearch/findAdvocate"
    LIVE_STATUS_SEARCH_BY_ADV_PATH: str = "/index.php/Casedetailssearch/Stausbyadvname2"
    LIVE_STATUS_ARCHIVE_HTML_TO_S3: bool = False
    LIVE_STATUS_ARCHIVE_BUCKET: str = ""
    LIVE_STATUS_ARCHIVE_PREFIX: str = "live-status/raw-html"
    LIVE_STATUS_REQUEST_DELAY_SECONDS: float = 1.2
    COURT_SESSION_ENCRYPTION_KEY: str = ""

    # External case sync API
    COURT_API_BASE_URL: str = "https://court-api.kleopatra.io"
    COURT_API_KEY: str = ""
    COURT_API_TIMEOUT_SECONDS: int = 45
    CASE_SYNC_REQUEST_DELAY_SECONDS: float = 2.0
    CASE_SYNC_BEDROCK_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    COURT_PLAYWRIGHT_STATUS_URL: str = "https://hckinfo.keralacourts.in/digicourt/Casedetailssearch/Statuscasenovoice"
    COURT_PLAYWRIGHT_SEARCH_URL: str = "https://hckinfo.keralacourts.in/digicourt/index.php/Casedetailssearch/Stausbycaseno"
    COURT_PLAYWRIGHT_VIEW_URL: str = "https://hckinfo.keralacourts.in/digicourt/index.php/Casedetailssearch/Viewcasestatus"
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_EXECUTABLE_PATH: str = ""
    PLAYWRIGHT_LAUNCH_ARGS: str = "--no-sandbox,--disable-setuid-sandbox"
    CAPTCHA_ENABLED: bool = True
    TWOCAPTCHA_API_KEY: str = ""

    # Tavily web search (legacy — replaced by Firecrawl for agent search)
    TAVILY_API_KEY: str = ""
    TAVILY_MAX_RESULTS: int = 5

    # Firecrawl — agent web search (replaces Tavily) and URL reading tool
    FIRECRAWL_API_KEY: str = ""
    # Max chars returned from a single URL scrape (keeps context window manageable)
    FIRECRAWL_MAX_CONTENT_CHARS: int = 12000
    # Max results returned by firecrawl search
    FIRECRAWL_SEARCH_MAX_RESULTS: int = 5
    # Comma-separated list of domains search_web and read_url are restricted to.
    # Example: livelaw.in,barandbench.com,indiankanoon.org,sci.gov.in
    FIRECRAWL_ALLOWED_DOMAINS: str = ""

    # OTP delivery
    OTP_SMS_PROVIDER: str = "dev"   # dev | twilio
    OTP_EMAIL_PROVIDER: str = "dev" # dev | resend
    OTP_SMS_FROM: str = ""
    OTP_EMAIL_FROM: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    RESEND_API_KEY: str = ""
    
    # DynamoDB (optional)
    DYNAMODB_TABLE_NAME: str = "lawmate-activity-trail"
    
    # CORS
    CORS_ORIGINS: str = '["https://lawmate-prod.vercel.app","https://www.lawmatekerala.com","https://lawmatekerala.com","http://localhost:3000"]'
    # Matches all Vercel preview deployments (lawmate-prod-xxxx.vercel.app), production domains, and chrome extensions
    CORS_ORIGIN_REGEX: str = r"https://lawmate-prod[^.]*\.vercel\.app|https://www\.lawmatekerala\.com|https://lawmatekerala\.com|chrome-extension://.*"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string or comma-separated string to list."""
        raw = (self.CORS_ORIGINS or "").strip()

        # Strip surrounding quotes that Railway/shell may add
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1].strip()

        if not raw:
            return ["http://localhost:3000"]

        # Try JSON array first (handles both ["a","b"] and [\"a\",\"b\"] forms)
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                result = [str(x).strip() for x in parsed if str(x).strip()]
                if result:
                    return result
            except (json.JSONDecodeError, ValueError):
                pass
            # Fallback: strip brackets and split
            raw = raw.lstrip("[").rstrip("]").replace('"', '').replace("'", "")

        # Comma-separated (most reliable Railway format)
        return [x.strip() for x in raw.split(",") if x.strip()]

    # Legal translation
    LEGAL_TRANSLATE_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    LEGAL_TRANSLATE_MAX_TOKENS: int = 4096
    LEGAL_TRANSLATE_TEMPERATURE: float = 0.1
    LEGAL_TRANSLATE_MAX_SUBSET_TERMS: int = 30
    LEGAL_GLOSSARY_PATH: str = ""  # leave blank to auto-resolve from backend root

    # Legal Insight — Judgment Summarizer
    LEGAL_INSIGHT_MODEL_ID: str = ""          # required; falls back to BEDROCK_MODEL_ID
    LEGAL_INSIGHT_MAX_CHARS_PER_CHUNK: int = 3000
    LEGAL_INSIGHT_JOB_TIMEOUT_SEC: int = 600
    LEGAL_INSIGHT_PROMPT_VERSION: str = "v1"
    LEGAL_INSIGHT_ENABLE_OCR_FALLBACK: bool = True

    # Case Prep AI
    # Model used for the sustained hearing-prep chat and brief generation.
    # ap-south-1 supports Haiku on-demand. To use Sonnet, set a cross-region
    # inference profile ARN (e.g. us.anthropic.claude-3-5-sonnet-20241022-v2:0)
    CASE_PREP_MODEL_ID: str = "anthropic.claude-3-haiku-20240307-v1:0"
    CASE_PREP_MAX_TOKENS: int = 8192
    CASE_PREP_TEMPERATURE: float = 0.3

    # BDA document extraction — set profile ARN to enable; falls back to PyMuPDF
    BDA_PROFILE_ARN:      str = ""
    BDA_OUTPUT_S3_PREFIX: str = "bda-output"

    # Feature flags
    HEARING_DAY_ENABLED: bool = True

    # ── Razorpay Payment Gateway ──────────────────────────────────────────────
    # Set these in your environment / Railway / App Runner secrets.
    RAZORPAY_KEY_ID: str = ""           # rzp_live_... or rzp_test_...
    RAZORPAY_KEY_SECRET: str = ""       # secret key (never expose to frontend)
    RAZORPAY_WEBHOOK_SECRET: str = ""   # from Razorpay Dashboard > Webhooks

    # Razorpay Plan IDs — create once in Razorpay Dashboard > Subscriptions > Plans
    RAZORPAY_EARLY_BIRD_PLAN_ID: str = ""   # monthly plan at EARLY_BIRD_PLAN_AMOUNT_PAISE
    RAZORPAY_STANDARD_PLAN_ID: str = ""     # monthly plan at STANDARD_PLAN_AMOUNT_PAISE

    # ── Pricing (stored in paise; INR amount × 100) ───────────────────────────
    EARLY_BIRD_PLAN_AMOUNT_PAISE: int = 120000   # ₹1,200 / month
    STANDARD_PLAN_AMOUNT_PAISE: int = 150000     # ₹1,500 / month
    TOPUP_AMOUNT_PAISE: int = 20000              # ₹200 per top-up

    # ── Top-up & slot config ──────────────────────────────────────────────────
    TOPUP_AI_ANALYSES: int = 20     # AI analyses credited per top-up purchase
    EARLY_BIRD_SLOTS: int = 100     # max users eligible for early-bird pricing
    TRIAL_DAYS: int = 60            # free trial length on new sign-up

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # KEY FIX: Ignore extra fields in .env
    )
   

    @property
    def firecrawl_allowed_domains_list(self) -> List[str]:
        """
        Parse comma-separated allowed domains or URLs into normalized hostnames.
        Example env:
          FIRECRAWL_ALLOWED_DOMAINS=barandbench.com,https://main.sci.gov.in/path
        """
        raw = (self.FIRECRAWL_ALLOWED_DOMAINS or "").strip()
        if not raw:
            return []

        items = [part.strip() for part in raw.split(",") if part.strip()]
        out: List[str] = []

        for item in items:
            candidate = item
            if "://" not in candidate:
                candidate = f"https://{candidate}"
            parsed = urlparse(candidate)
            host = (parsed.netloc or parsed.path or "").strip().lower()
            if not host:
                continue
            if "@" in host:
                host = host.split("@", 1)[1]
            if ":" in host:
                host = host.split(":", 1)[0]
            host = host.lstrip(".")
            if host.startswith("www."):
                host = host[4:]
            if host and host not in out:
                out.append(host)

        return out


# Create settings instance
settings = Settings()
