# # app/core/config.py
"""
Application configuration using Pydantic Settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json
from pydantic import field_validator
from urllib.parse import urlparse


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    
    # Application
    APP_NAME: str = "Lawmate"
    DEBUG: bool = True
    
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
    CAPTCHA_ENABLED: bool = True
    TWOCAPTCHA_API_KEY: str = ""

    # Tavily web search (agent fallback)
    TAVILY_API_KEY: str = ""
    TAVILY_MAX_RESULTS: int = 5
    TAVILY_ALLOWED_DOMAINS: str = ""

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
    CORS_ORIGINS: str = '["http://localhost:3000"]'

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

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # KEY FIX: Ignore extra fields in .env
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from string to list"""
        try:
            if isinstance(self.CORS_ORIGINS, str):
                return json.loads(self.CORS_ORIGINS)
            return self.CORS_ORIGINS
        except:
            return ["http://localhost:3000"]

    @property
    def tavily_allowed_domains_list(self) -> List[str]:
        """
        Parse comma-separated allowed domains or URLs into normalized hostnames.
        Example env:
          TAVILY_ALLOWED_DOMAINS=barandbench.com,https://main.sci.gov.in/path
        """
        raw = (self.TAVILY_ALLOWED_DOMAINS or "").strip()
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
# from pydantic_settings import BaseSettings
# from typing import Optional

# class Settings(BaseSettings):
#     # App
#     APP_NAME: str = "Lawmate API"
#     VERSION: str = "1.0.0"
#     DEBUG: bool = False
    
#     # Database
#     DATABASE_URL: str
    
#     # JWT
#     JWT_SECRET_KEY: str
#     JWT_ALGORITHM: str = "HS256"
#     JWT_EXPIRATION_HOURS: int = 24
    
#     # AWS
#     AWS_REGION: str = "ap-south-1"
#     S3_BUCKET: str = "lawmate-case-pdfs"
#     AWS_ACCESS_KEY_ID: Optional[str] = None
#     AWS_SECRET_ACCESS_KEY: Optional[str] = None
#     ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
#     ENVIRONMENT: str = "development"
#     #S3
#     S3_BUCKET_NAME: str  # Add this line
    
#     # Bedrock
#     BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022"
    
#     # CORS
#     CORS_ORIGINS: list = ["https://lawmate.in", "chrome-extension://*"]
    
#     class Config:
#         env_file = ".env"
#         case_sensitive = True

# settings = Settings()

# from pydantic_settings import BaseSettings
# from typing import List
# import json

# class Settings(BaseSettings):
#     APP_NAME: str = "Lawmate"
#     DEBUG: bool = True
    
#     # Database
#     DATABASE_URL: str
    
#     # JWT
#     JWT_SECRET_KEY: str
#     JWT_ALGORITHM: str = "HS256"
#     ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
#     # AWS
#     AWS_ACCESS_KEY_ID: str
#     AWS_SECRET_ACCESS_KEY: str
#     AWS_REGION: str = "ap-south-2"
#     S3_BUCKET_NAME: str
    
#     # CORS
#     CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    
#     class Config:
#         env_file = ".env"
        
#     @property
#     def cors_origins_list(self) -> List[str]:
#         if isinstance(self.CORS_ORIGINS, str):
#             return json.loads(self.CORS_ORIGINS)
#         return self.CORS_ORIGINS

# settings = Settings()

# """
# Application configuration using Pydantic Settings
# """
# from pydantic_settings import BaseSettings, SettingsConfigDict
# from typing import List, Optional
# import json


# class Settings(BaseSettings):
#     """
#     Application settings loaded from environment variables
#     """
#     # Application
#     APP_NAME: str = "Lawmate"
#     ENVIRONMENT: str = "development"  # development, staging, production
#     DEBUG: bool = True
    
#     # Database
#     DATABASE_URL: str
    
#     # JWT Authentication
#     JWT_SECRET_KEY: str
#     JWT_ALGORITHM: str = "HS256"
#     ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
#     REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
#     # AWS Configuration
#     AWS_ACCESS_KEY_ID: str
#     AWS_SECRET_ACCESS_KEY: str
#     AWS_REGION: str = "ap-south-1"
#     S3_BUCKET_NAME: str
    
#     # AWS Bedrock (Claude)
#     BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    
#     # DynamoDB (Optional - for audit trail)
#     DYNAMODB_TABLE_NAME: Optional[str] = "lawmate-activity-trail"
    
#     # CORS
#     CORS_ORIGINS: str = '["http://localhost:3000"]'  # JSON string
    
#     # File Upload
#     MAX_UPLOAD_SIZE: int = 52428800  # 50MB in bytes
#     ALLOWED_EXTENSIONS: List[str] = [".pdf"]
    
#     # Logging
#     LOG_LEVEL: str = "INFO"
    
#     # Model configuration (Pydantic v2)
#     model_config = SettingsConfigDict(
#         env_file=".env",
#         env_file_encoding="utf-8",
#         case_sensitive=True,
#         extra="ignore"  # Ignore extra fields in .env
#     )
    
#     @property
#     def cors_origins_list(self) -> List[str]:
#         """Parse CORS_ORIGINS JSON string to list"""
#         try:
#             return json.loads(self.CORS_ORIGINS)
#         except json.JSONDecodeError:
#             # Fallback if not valid JSON
#             return self.CORS_ORIGINS.split(",") if isinstance(self.CORS_ORIGINS, str) else []
    
#     @property
#     def is_development(self) -> bool:
#         """Check if running in development mode"""
#         return self.ENVIRONMENT.lower() == "development"
    
#     @property
#     def is_production(self) -> bool:
#         """Check if running in production mode"""
#         return self.ENVIRONMENT.lower() == "production"
    
#     # Aliases for backward compatibility
#     @property
#     def S3_BUCKET(self) -> str:
#         """Alias for S3_BUCKET_NAME"""
#         return self.S3_BUCKET_NAME
    
#     class Config:
#         env_file = ".env"
#         case_sensitive = False


# # Create settings instance
# settings = Settings()
