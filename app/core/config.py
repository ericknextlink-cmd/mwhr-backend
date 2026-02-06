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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FRONTEND_URL: str = "http://localhost:3000"
    # Optional: owner password for certificate PDF encryption (restricts copy/text selection)
    CERTIFICATE_OWNER_PASSWORD: str | None = None
    
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
