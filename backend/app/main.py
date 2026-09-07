"""
FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.monitoring import init_monitoring
from app.core.rate_limit import limiter
from app.core.security_headers import MaxBodySizeMiddleware, SecurityHeadersMiddleware
from app.core.tags_metadata import TAGS_METADATA
from app.services.jobs import shutdown_executor
from app.services.scheduler import shutdown_scheduler, start_scheduler

# Batch 10.8: configured before anything else (including init_monitoring
# and the FastAPI app itself) so every log line from every module --
# including ones imported below -- goes through this configuration
# rather than Python's default (which silently drops INFO and below).
configure_logging()
init_monitoring()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup (environment=%s).", settings.ENVIRONMENT)
    start_scheduler()
    yield
    shutdown_scheduler()
    # Batch 10.9: waits for any in-flight background job (e.g. a large
    # import mid-processing) to finish before the process actually exits,
    # so a deploy/restart can't abandon it partway through a DB write.
    shutdown_executor(wait=True)
    logger.info("Application shutdown.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    # Batch 10.11: shown at the top of /docs and /redoc. Kept short --
    # the full reference (auth flow, error shape, rate limits, tenant
    # model, pagination conventions) lives in docs/API.md so it doesn't
    # need to be duplicated/kept in sync in two places.
    description=(
        "See `docs/API.md` in the repository for the full developer guide "
        "(authentication flow, error response shape, rate limits, and the "
        "multi-tenant business/branch model every endpoint below is scoped to)."
    ),
    openapi_tags=TAGS_METADATA,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Order matters: middleware added last runs first on the way in. Body
# size and security headers should wrap everything, including CORS and
# rate limiting, so an oversized/malicious request is rejected as early
# as possible. RequestIDMiddleware must run before all of them (added
# last) so request_id is already set -- and therefore present on every
# log line -- for anything logged by the middleware below it, including
# a rejected-for-size or rate-limited request.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MaxBodySizeMiddleware)
app.add_middleware(RequestIDMiddleware)

register_exception_handlers(app)

app.include_router(api_router)
