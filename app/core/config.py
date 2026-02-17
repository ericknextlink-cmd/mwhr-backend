import json
from typing import List, Union
from pathlib import Path
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Ministry App API"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str
    
    # Supabase Storage
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_BUCKET_NAME: str | None = None
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour
    FRONTEND_URL: str = "http://localhost:3000"
    # Certificate PDF: no open password (anyone can view). Edit/copy is protected by owner password.
    # Set this in .env to a strong random value (e.g. openssl rand -base64 32). Used when the
    # user does not supply their account password at download; if unset, a default is used.
    CERTIFICATE_OWNER_PASSWORD: str | None = None

    # Invoice PDF (post-payment letter + invoice)
    INVOICE_APPLICATION_FEE_GHS: float = 1000.0
    INVOICE_PROCESSING_FEE_GHS: float = 500.0
    INVOICE_PAYMENT_DAYS_DUE: int = 7
    MINISTRY_NAME: str = "Ministry of Works, Housing & Water Resources"
    MINISTRY_ADDRESS: str = "Ministries Area, Off Starlets 91 Road, Accra, Ghana, P.O. Box M43, Ministries - Accra, Digital Address: GA-144-0550"
    MINISTRY_PHONE: str = "+233 (0)577 902 988 / +233 (0)577 902 933"
    MINISTRY_EMAIL: str = "info@mwhwr.gov.gh"
    # Optional path to ministry logo image for invoice PDF (PNG/JPEG). If not set, looks for assets/ministry_logo.png in project root.
    INVOICE_LOGO_PATH: str | None = None
    
    # Email
    EMAILS_ENABLED: bool = False
    RESEND_API_KEY: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: str | None = "noreply@mail.nexlinktechnologies.com"
    EMAILS_FROM_NAME: str | None = "Ministry Portal"
    
    # AI & Document Processing
    OPENAI_API_KEY: str | None = None
    UNSTRUCTURED_API_KEY: str | None = None
    UNSTRUCTURED_API_URL: str | None = "https://api.unstructured.io"
    
    # AI Microservice (External)
    AI_SERVICE_URL: str | None = None
    AI_SERVICE_API_KEY: str | None = None

    # CORS
    BACKEND_CORS_ORIGINS: List[Union[AnyHttpUrl, str]] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip().strip("'\"")
            if v.startswith("["):
                try:
                    v = json.loads(v)
                except json.JSONDecodeError:
                    v = [x.strip() for x in v.strip("[]").split(",")]
            else:
                v = [x.strip() for x in v.split(",")]
        if isinstance(v, list):
            return [str(x).strip().rstrip("/") for x in v if x]
        return []

    # Use .env file if it exists, otherwise rely on environment variables
    _env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    model_config = SettingsConfigDict(
        env_file=_env_file if _env_file.exists() else None,
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
