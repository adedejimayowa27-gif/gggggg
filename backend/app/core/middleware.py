"""
Request-ID middleware (Step 10, Batch 10.8, requirement #6).

Generates (or forwards) a unique ID for every request, makes it available
to route/service code via `request.state.request_id`, stamps it onto every
log line emitted during the request (via the contextvar in
app.core.logging_config), and echoes it back as an `X-Request-ID` response
header -- so a user/support agent reporting "I got an error" can hand back
one ID that a developer can grep straight out of the structured logs (and,
if configured, look up in Sentry -- see app.core.monitoring), no
timestamp-matching guesswork required.

If the incoming request already carries an X-Request-ID (e.g. set by a
load balancer, or by the frontend for its own tracing), that value is
reused rather than replaced, so a single request keeps one consistent ID
across every layer that touches it.

This middleware must run first on the way in (added last in app.main, per
that module's existing middleware-ordering comment) so the ID is set
before any other middleware, exception handler, or route code logs
anything.
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging_config import (
    business_id_var,
    new_request_id,
    request_id_var,
    user_id_var,
)

logger = logging.getLogger("app.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        req_id = incoming if incoming else new_request_id()

        request_id_token = request_id_var.set(req_id)
        # user_id/business_id aren't known yet at this point (auth hasn't
        # run) -- get_current_user/get_owned_business set them once
        # resolved. Reset to None here first so a value left over from a
        # previous request handled on the same worker thread can never
        # leak into this one.
        user_id_token = user_id_var.set(None)
        business_id_token = business_id_var.set(None)

        request.state.request_id = req_id
        start = time.monotonic()
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Unhandled exceptions are logged with full context here too,
                # in addition to the app-level handler in app.core.exceptions
                # -- this line guarantees at least one structured log entry
                # exists even in the (should-be-impossible) case an exception
                # somehow bypasses that handler. Logged *before* the finally
                # block below resets the contextvars, so request_id/user_id/
                # business_id are still attached to this line.
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.exception(
                    "Unhandled exception during request",
                    extra={"method": request.method, "path": request.url.path, "duration_ms": duration_ms},
                )
                raise

            duration_ms = round((time.monotonic() - start) * 1000, 2)
            response.headers["X-Request-ID"] = req_id
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            # Reset only after all logging for this request is done, so
            # every log line -- including the completion/error lines just
            # above -- carries this request's context, never the next
            # request's (on a reused worker thread).
            request_id_var.reset(request_id_token)
            user_id_var.reset(user_id_token)
            business_id_var.reset(business_id_token)
