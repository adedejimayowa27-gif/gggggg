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
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"

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
