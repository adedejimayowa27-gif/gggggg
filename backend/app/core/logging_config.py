"""
Production-grade logging configuration (Step 10, Batch 10.8, requirement #6).

Before this batch, every module did `logger = logging.getLogger(__name__)`
but nothing ever called `logging.config.dictConfig`/`basicConfig` -- so
with no handler attached anywhere, Python's root logger silently
swallowed everything below WARNING (the "handler of last resort" only
prints WARNING+ to stderr). That meant every `logger.info(...)` call
already in the codebase (scheduler completions, sync results, etc.) was
invisible in production. This module is the one place logging is
configured; import-and-call `configure_logging()` once, from
app.main, before anything else runs.

Two concerns, kept deliberately separate:

1. Structured (JSON) output -- one JSON object per line, so a log
   aggregator (Render's own log viewer, Datadog, CloudWatch, whatever)
   can parse and filter/search fields instead of grepping free text.
   Plain-text is used instead when settings.LOG_FORMAT == "text", which
   is friendlier for local `uvicorn --reload` development.

2. Request context propagation via contextvars -- request_id (always),
   plus user_id/business_id when the route has authenticated/resolved
   them. Contextvars (not thread-locals) are used because FastAPI runs
   sync route code in a threadpool but async code on the event loop;
   contextvars are the one mechanism that correctly follows a single
   request through both. A logging.Filter reads these vars and stamps
   them onto every LogRecord automatically -- no call site anywhere else
   in the app needs to remember to pass request_id explicitly.
"""
import contextvars
import logging
import logging.config
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

# --- Request-scoped context ---------------------------------------------
# Set by RequestIDMiddleware (app.core.middleware) at the start of every
# request and reset at the end. Read by JsonFormatter/ContextFilter below.
# Defaults ensure logging never breaks for code that runs outside an HTTP
# request (the scheduler's background jobs, CLI scripts, etc.) -- those
# just log with request_id=None, which is correct: there is no request.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id", default=None
)
business_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "business_id", default=None
)


def new_request_id() -> str:
    return uuid.uuid4().hex


class ContextFilter(logging.Filter):
    """Stamps request_id/user_id/business_id onto every LogRecord, from
    whatever the current contextvars happen to be. Attached to the root
    logger's handler (not to individual loggers) so it applies uniformly,
    including to third-party loggers (uvicorn, sqlalchemy, etc.)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.business_id = business_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Deliberately hand-rolled (no extra
    dependency) -- the field set is small and stable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
            "business_id": getattr(record, "business_id", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Anything passed via logger.info("...", extra={...}) that isn't
        # already a standard LogRecord attribute -- lets call sites add
        # ad-hoc structured fields (e.g. duration_ms) without this
        # formatter needing to know about them in advance.
        standard_keys = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id", "user_id", "business_id",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_keys:
                payload[key] = value
        return __import__("json").dumps(payload, default=str)


def configure_logging() -> None:
    """Called once from app.main, before the FastAPI app is constructed,
    so every log line from every module (including ones imported by
    app.main itself) goes through this configuration."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(ContextFilter())

    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # Quiet down noisy third-party loggers unless we're actually debugging
    # at that level -- otherwise SQLAlchemy's engine logger in particular
    # logs every single SQL statement at INFO, which drowns out
    # everything else.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.LOG_LEVEL == "DEBUG" else logging.WARNING
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
