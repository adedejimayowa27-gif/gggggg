"""
Application-wide error handling.

Defines a small hierarchy of domain exceptions and registers handlers that
convert them (and unhandled errors) into a consistent JSON error shape:

    { "error": { "code": "...", "message": "..." } }
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import monitoring

logger = logging.getLogger("app")


class AppError(Exception):
    """Base class for expected, handled application errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "app_error"

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


def _error_body(code: str, message: str, request_id: str | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if request_id:
        # Included on every error response (not just 500s) so a user/
        # support agent can hand back one ID for *any* failed request --
        # a 404 from a mistyped ID is just as worth tracing as a 500.
        body["error"]["request_id"] = request_id
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code, content=_error_body(exc.code, exc.message, req_id)
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("validation_error", "Invalid request data.", req_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", str(exc.detail), req_id),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", None)
        # Structured log first (never skipped, regardless of whether
        # Sentry is configured) -- then, additionally, report to Sentry
        # if SENTRY_DSN is set. Order matters: logging must never be
        # skipped just because monitoring.capture_exception raises.
        # request_id is stamped onto this record automatically by
        # ContextFilter (app.core.logging_config) -- no need to pass it
        # via `extra` here.
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        monitoring.capture_exception(exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "An unexpected error occurred.", req_id),
        )
