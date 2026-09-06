"""
Error monitoring (Step 10, Batch 10.8, requirement #6).

Same pattern already used for Stripe/Groq/Google elsewhere in this app:
empty setting = feature quietly disabled, so local/dev/test environments
boot and run fully with zero external accounts configured. Set
SENTRY_DSN in production to get exception tracking, release tracking,
and (at a low, cost-bounded sample rate) performance tracing.

Sentry is used here as the concrete provider since it has the most
mature FastAPI/SQLAlchemy integration and a generous free tier, but
nothing outside this module knows that -- `capture_exception` /
`set_request_context` are the only two functions the rest of the app
calls, so swapping providers later only means rewriting this file.
"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_enabled = False


def init_monitoring() -> None:
    """Called once from app.main's startup, after configure_logging().
    No-op if SENTRY_DSN is unset."""
    global _enabled
    if not settings.SENTRY_DSN:
        logger.info("SENTRY_DSN not set -- error monitoring disabled.")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        # sentry-sdk is in requirements.txt, so this should only happen
        # in an environment that installed a stale requirements set --
        # fail soft (log loudly, keep serving requests) rather than
        # crashing the whole app over what is, after all, an optional
        # add-on.
        logger.error(
            "SENTRY_DSN is set but sentry-sdk is not installed -- "
            "error monitoring disabled. Run `pip install -r requirements.txt`."
        )
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        # Traces (performance) sampled much lower than errors (always
        # captured) -- tracing is nice-to-have and Sentry's paid tiers
        # bill per-transaction, so keep this conservative by default.
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            # Mirrors this app's own logging: only ERROR+ becomes a
            # Sentry event, but breadcrumbs (for context leading up to
            # it) are recorded from INFO+.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Request bodies can contain financial transaction data -- never
        # send them to a third party by default. Headers are kept (useful
        # for request_id correlation) but bodies are not.
        send_default_pii=False,
        max_request_body_size="never",
    )
    _enabled = True
    logger.info("Error monitoring initialized (environment=%s).", settings.ENVIRONMENT)


def set_request_context(request_id: str, user_id: str | None, business_id: str | None) -> None:
    """Attaches the current request's identifiers to whatever Sentry event
    (if any) gets captured next on this thread/task. No-op if monitoring
    isn't enabled -- safe to call unconditionally from middleware."""
    if not _enabled:
        return
    import sentry_sdk

    sentry_sdk.set_tag("request_id", request_id)
    if user_id:
        sentry_sdk.set_user({"id": user_id})
    if business_id:
        sentry_sdk.set_tag("business_id", business_id)


def capture_exception(exc: BaseException) -> None:
    """Explicit capture point for the catch-all handler in
    app.core.exceptions -- called in addition to (never instead of) the
    structured `logger.exception(...)` already there, so an error is
    always at minimum in the logs even if this call itself no-ops or
    fails."""
    if not _enabled:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001 -- monitoring must never break error handling itself
        logger.exception("Failed to report exception to Sentry.")
