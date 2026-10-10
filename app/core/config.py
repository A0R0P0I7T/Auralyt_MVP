"""Core configuration for Auralyt MVP — Engine 1."""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application
    APP_NAME: str = "Auralyt MVP — Brand & Website Profiler"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./auralyt.db"

    # Crawler Settings & Safety Limits
    DEFAULT_PAGE_LIMIT: int = Field(default=30, description="Default max pages to crawl")
    HARD_MAX_PAGE_LIMIT: int = Field(default=50, description="Hard maximum allowed pages per run")
    MAX_CRAWL_DEPTH: int = Field(default=3, description="Maximum internal link recursion depth")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=15, description="Network timeout per request")
    MAX_RESPONSE_SIZE_BYTES: int = Field(default=5 * 1024 * 1024, description="Max response size (5MB)")
    PER_HOST_CONCURRENCY: int = Field(default=3, description="Max concurrent requests to the same host")
    PER_HOST_DELAY_SECONDS: float = Field(default=0.5, description="Politeness delay between requests")
    USER_AGENT: str = "AuralytBot/1.0 (+https://auralyt.ai/bot)"

    # Browser Fallback
    ALLOW_BROWSER_FALLBACK: bool = False
    MIN_TEXT_CHARS_FOR_STATIC: int = 120

    # Network Egress & SSRF Protection
    EGRESS_PROXY_URL: Optional[str] = Field(default=None, description="External egress proxy URL (e.g. http://egress-proxy:4750)")
    ENFORCE_EGRESS_PROXY: bool = Field(default=False, description="Enforce that all outbound traffic passes through the egress proxy")
    BROWSER_ISOLATION_MODE: str = Field(default="none", description="Isolation mode for browser execution: none, egress_proxy, container_sandbox")
    BROWSER_PROXY_URL: Optional[str] = Field(default=None, description="Dedicated proxy for browser requests (defaults to EGRESS_PROXY_URL)")

    # Optional LLM Enhancement (Off by default)
    LLM_ENABLED: bool = False
    LLM_PROVIDER: str = "gemini"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-1.5-flash"

    def validate_security_configuration(self) -> None:
        """Validate security boundaries for the current environment."""
        env = self.ENVIRONMENT.lower()
        if env == "production":
            if not self.EGRESS_PROXY_URL:
                raise ValueError(
                    "Production environment requires an explicitly configured EGRESS_PROXY_URL "
                    "for connection-time SSRF and DNS-rebinding protection."
                )
            if self.ALLOW_BROWSER_FALLBACK and self.BROWSER_ISOLATION_MODE not in ("egress_proxy", "container_sandbox"):
                raise ValueError(
                    "Browser fallback cannot be enabled in production without a validated "
                    "isolated execution mode ('egress_proxy' or 'container_sandbox')."
                )


settings = Settings()
settings.validate_security_configuration()

