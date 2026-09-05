"""
Centralized application configuration.

All environment-driven settings live here. Never read os.environ directly
elsewhere in the app -- import `settings` from this module instead.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Mayorcity Bizintel"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # --- Database ---
    DATABASE_URL: str

    # --- Auth / JWT ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- AI assistant (Batch 5.3) ---
    # Empty by default so local/dev/test setups without an API key still
    # boot; app.services.ai_assistant raises a clear 503 if a request
    # actually reaches the assistant route with this unset.
    GROQ_API_KEY: str = ""
    # Pick a Groq-hosted model that supports tool calling -- check
    # https://console.groq.com/docs/models for the current list, since
    # Groq's lineup changes more often than a typical API. (llama-3.3-70b-
    # versatile and llama-3.1-8b-instant were moved to Enterprise-only
    # access as of Aug 2026, so a normal developer API key gets a 404
    # "model does not exist or you do not have access to it" on them --
    # openai/gpt-oss-120b is the current general-access production model
    # with tool-calling support.)
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # --- Google Sheets integration (Step 9) ---
    # Empty by default so local/dev/test setups without Google Cloud
    # credentials still boot; the /google/connect route raises a clear
    # 503 if a request reaches it with these unset. Get these from a
    # Google Cloud project's OAuth 2.0 Client (APIs & Services >
    # Credentials) with the Sheets API and Drive API enabled.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Must exactly match a redirect URI registered on the OAuth client in
    # Google Cloud Console, and must point at this backend's own
    # /google/callback route (not the frontend) -- Google redirects the
    # user's browser here directly with the auth code.
    GOOGLE_REDIRECT_URI: str = ""
    # Fernet key (32 url-safe base64-encoded bytes) used to encrypt
    # Google access/refresh tokens at rest -- never store them in plain
    # text. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Rotating this key invalidates every stored token (users would need
    # to reconnect), so treat it like SECRET_KEY: set once, keep it secret,
    # back it up.
    GOOGLE_TOKEN_ENCRYPTION_KEY: str = ""

    # Where to send the user's browser back to after the OAuth callback
    # finishes (success or failure) -- the frontend's settings/integration
    # page, not this backend.
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Billing (Step 10) ---
    # Empty by default so this app boots and runs fully without a Stripe
    # account -- every business is simply on the free plan (see
    # alembic/versions/0012_billing.py). Billing routes that need Stripe
    # raise a clear 503 if these are unset, same pattern as Groq/Google.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    # Verifies that a webhook request genuinely came from Stripe (not
    # forged) -- get this from the webhook endpoint's settings in the
    # Stripe dashboard once one is created.
    STRIPE_WEBHOOK_SECRET: str = ""

    # --- Background jobs (Step 10, Batch 10.7) ---
    # In-process scheduler (no separate worker/broker needed) -- correct
    # for this app's current single Render web service. If ever scaled to
    # multiple instances, each would run these jobs independently; the
    # dedupe_key (alerts) and fingerprint (transactions) mechanisms already
    # in place make redundant runs wasteful but not harmful.
    ENABLE_BACKGROUND_JOBS: bool = True
    ALERT_DETECTION_INTERVAL_HOURS: int = 24
    GOOGLE_SYNC_INTERVAL_HOURS: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance. Using a function (rather than a module-level
    singleton) makes it easy to override settings in tests via
    dependency_overrides or by clearing the lru_cache.
    """
    return Settings()


settings = get_settings()
