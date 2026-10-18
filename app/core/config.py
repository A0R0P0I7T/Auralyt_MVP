"""Core configuration for Auralyt MVP — Engine 1."""
from typing import Optional, Dict
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

    # Crawler Settings & Safety Limits (10 Explicit Configurable Limits)
    DEFAULT_PAGE_LIMIT: int = Field(default=25, description="1. Default max pages to crawl per run")
    CRAWL_MAX_PAGES_PER_RUN: int = Field(default=25, description="1. Default max pages to crawl per run")
    HARD_MAX_PAGE_LIMIT: int = Field(default=50, description="1. Hard maximum allowed pages per run")
    MAX_CRAWL_DEPTH: int = Field(default=3, description="2. Maximum internal link recursion depth")
    CRAWL_MAX_DEPTH: int = Field(default=3, description="2. Alias for max internal link recursion depth")
    CRAWL_MAX_PAGES_PER_DOMAIN: int = Field(default=25, description="3. Maximum pages per domain per profiling run")
    CRAWL_CATEGORY_QUOTAS: Dict[str, int] = Field(
        default_factory=lambda: {
            "homepage": 1,
            "pricing": 3,
            "about": 3,
            "product_service": 6,
            "docs": 3,
            "blog": 2,
            "legal": 1,
            "faq": 3,
            "contact": 2,
            "other": 3,
        },
        description="3. Maximum page quotas per category to prevent any single category from crowding out others"
    )
    PER_HOST_CONCURRENCY: int = Field(default=3, description="4. Max concurrent requests to the same host")
    CRAWL_MAX_CONCURRENCY: int = Field(default=3, description="4. Alias for max concurrent page fetches")
    PER_HOST_DELAY_SECONDS: float = Field(default=0.5, description="Politeness delay between requests")
    REQUEST_TIMEOUT_SECONDS: int = Field(default=15, description="5. Network timeout per request in seconds")
    CRAWL_RUN_TIMEOUT_SECONDS: int = Field(default=60, description="5. Total run deadline in seconds")
    MAX_RESPONSE_SIZE_BYTES: int = Field(default=5 * 1024 * 1024, description="6. Max response body size (5MB)")
    CRAWL_MAX_DECOMPRESSED_BYTES: int = Field(default=5 * 1024 * 1024, description="6. Max decompressed content size (5MB)")
    CRAWL_MAX_AGGREGATE_BYTES: int = Field(default=20 * 1024 * 1024, description="7. Max aggregate content processed per run (20MB)")
    CRAWL_MAX_RETRIES: int = Field(default=2, description="8. Max retries for transient HTTP errors")
    CRAWL_RETRY_BACKOFF_SECONDS: float = Field(default=1.0, description="8. Initial retry backoff delay in seconds")
    CRAWL_MAX_SITEMAP_ENTRIES: int = Field(default=100, description="9. Maximum sitemap URLs to parse and consider")
    CRAWL_MAX_PAGES_PER_SECTION: int = Field(default=4, description="10. Maximum pages from any single section prefix (e.g. /docs/, /blog/)")
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

    # Authentication & Multi-Tenancy
    AUTH_ENABLED: bool = True
    AUTH_SECRET_KEY: str = Field(
        default="auralyt-auth-jwt-secret-key-32-bytes-prod-safe",
        description="Secret key for JWT token signing"
    )
    AUTH_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    AUTH_COOKIE_NAME: str = "auralyt_token"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"

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
            if not self.AUTH_ENABLED:
                raise ValueError("Production environment strictly requires AUTH_ENABLED=true.")
            if self.AUTH_SECRET_KEY == "auralyt-auth-jwt-secret-key-32-bytes-prod-safe":
                raise ValueError("Production environment requires an explicitly configured, non-default AUTH_SECRET_KEY.")


settings = Settings()
settings.validate_security_configuration()

