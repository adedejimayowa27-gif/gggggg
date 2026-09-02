"""
Security headers + request-body-size middleware (Step 10, Batch 10.5,
requirement #12).
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Generously above import_pipeline.MAX_FILE_SIZE_BYTES (5MB) so a
# legitimate transaction file upload always fits under this ceiling too
# -- this is a blunt, whole-request guard, not the file-size business
# rule itself (that stays in import_pipeline.py).
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Standard defensive headers on every response. This is an API-only
    backend (no HTML pages rendered here), so there's no Content-Security-
    Policy here -- that belongs on the frontend (Next.js/Netlify), which
    is what actually renders pages a browser executes script in.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """
    Rejects a request outright, before FastAPI/Starlette parses its body
    at all, if its declared Content-Length exceeds MAX_REQUEST_BODY_BYTES
    -- a first line of defense against large-payload DoS, in addition to
    (not instead of) import_pipeline's own file-size check, which only
    runs after a file has already been read into this application.

    Content-Length isn't always present (e.g. chunked transfer encoding),
    so this is a best-effort early rejection, not the only guard --
    that's exactly why the bounded read in app.api.routes.imports (see
    that module) still exists as a second layer.
    """

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large."})
            except ValueError:
                pass  # malformed header -- let normal request processing reject it downstream
        return await call_next(request)
