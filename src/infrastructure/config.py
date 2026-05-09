"""Configuration module — centralised settings management.

Uses ``pydantic_settings.BaseSettings`` which automatically reads values from
environment variables (and from a ``.env`` file if present).  All type
coercions (bool, int, float) are handled by Pydantic.
"""

from __future__ import annotations


from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — all values can be overridden via environment
    variables or a ``.env`` file placed in the working directory."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── AI Provider ────────────────────────────────────────────────────────
    # Options: "gemini" | "openai" | "vertexai"
    AI_PROVIDER: str = "gemini"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash-latest"

    # Vertex AI
    VERTEXAI_PROJECT_ID: str = ""
    VERTEXAI_LOCATION: str = "us-central1"
    VERTEXAI_MODEL: str = "gemini-1.5-pro"
    VERTEXAI_CLIENT_EMAIL: str = ""
    VERTEXAI_PRIVATE_KEY: str = ""

    # Generic OpenAI-compatible (Groq, Ollama, …)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    OPENAI_MODEL: str = "llama3-8b-8192"

    # ── API ────────────────────────────────────────────────────────────────

    # ── Application ────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Microsoft 365 / SharePoint ─────────────────────────────────────────
    TENANT_ID: str = ""
    CLIENT_ID: str = ""
    CLIENT_SECRET: str = ""
    SITE_ID: str = ""
    SHAREPOINT_SITE_URL: str = ""
    APP_CATALOG_SITE_ID: str = ""
    # Auth mode: Always uses OBO (On-Behalf-Of) with user tokens.
    # OBO is configured in Azure AD and enforces user permissions.

    # ── Deprecated ─────────────────────────────────────────────────────────
    # API_KEY is no longer supported.  This field exists solely so that the
    # validator can detect leftover .env values and fail loudly instead of
    # silently ignoring them or raising AttributeError.
    API_KEY: str = ""

    # ── Redis ──────────────────────────────────────────────────────────────
    # Redis is always attempted for distributed state. If the connection
    # fails the application falls back to in-memory storage automatically.
    REDIS_URL: str = "redis://redis:6379/0"

    # ── CORS ───────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:4321,"
        "https://*.sharepoint.com,https://*.sharepoint-df.com"
    )
    # Comma-separated SharePoint tenant names for strict CORS validation.
    # Example: "optimumpartnersjo,contoso"  →  only
    # https://optimumpartnersjo.sharepoint.com and
    # https://contoso.sharepoint.com will be accepted.
    # Leave empty to allow all *.sharepoint.com subdomains (with a warning).
    ALLOWED_SHAREPOINT_TENANTS: str = ""

    # ── OBO Cache ──────────────────────────────────────────────────────────
    OBO_CACHE_TTL_SECONDS: int = 900  # 15 minutes (was 45 min)

    # ── User Status Revalidation ──────────────────────────────────────────
    USER_STATUS_CHECK_TTL_SECONDS: int = 120  # 2 minutes

    # ── Smart Resource Discovery ───────────────────────────────────────────
    MAX_DISCOVERY_SITES: int = 10
    CANDIDATE_SCORE_THRESHOLD: float = 0.5
    SEARCH_FALLBACK_THRESHOLD: float = 0.2

    # ── Validators ─────────────────────────────────────────────────────────

    @field_validator("LOG_LEVEL")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got '{v}'")
        return v.upper()

    @model_validator(mode='after')
    def _validate_all(self):
        if self.AI_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required when AI_PROVIDER='gemini'")
        if self.AI_PROVIDER == "vertexai":
            if not self.VERTEXAI_PROJECT_ID:
                raise ValueError("VERTEXAI_PROJECT_ID is required when AI_PROVIDER='vertexai'")
            if not self.VERTEXAI_CLIENT_EMAIL or not self.VERTEXAI_PRIVATE_KEY:
                raise ValueError("VERTEXAI_CLIENT_EMAIL and VERTEXAI_PRIVATE_KEY are required when AI_PROVIDER='vertexai'")
        if self.AI_PROVIDER == "openai":
            if not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER='openai'")
            if not self.OPENAI_BASE_URL:
                raise ValueError("OPENAI_BASE_URL is required when AI_PROVIDER='openai'")
        if not self.TENANT_ID:
            raise ValueError("TENANT_ID is required")
        if not self.CLIENT_ID:
            raise ValueError("CLIENT_ID is required")
        if not self.CLIENT_SECRET:
            raise ValueError("CLIENT_SECRET is required")
        if not self.SITE_ID:
            raise ValueError("SITE_ID is required")
        if self.API_KEY:
            raise ValueError(
                "API_KEY is no longer supported. Production requires Azure AD JWT tokens only. "
                "Please remove API_KEY from your .env file."
            )
        # Ensure tenant allowlist is configured
        if not self.ALLOWED_SHAREPOINT_TENANTS:
            raise ValueError(
                "ALLOWED_SHAREPOINT_TENANTS is not set. You must explicitly configure "
                "your SharePoint tenant name(s) for secure CORS validation."
            )
        return self

    def validate(self) -> None:
        pass


settings = Settings()
