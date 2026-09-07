"""
Import routes.

Nested under a specific business (/businesses/{business_id}/imports/...)
so every route here automatically inherits the ownership check from
get_owned_business -- there is no way to reach another business's data
through this router.
"""
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business
from app.core.exceptions import AppError, NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.import_session import ImportSession
from app.models.user import User
from app.services.billing import check_max_transactions_this_month
from app.services.jobs import enqueue_job, run_job_async
from app.schemas.import_session import (
    ImportConfirmIn,
    ImportConfirmOut,
    ImportPreviewOut,
    ImportSessionOut,
)
from app.services.import_pipeline import (
    MAX_FILE_SIZE_BYTES,
    parse_upload,
    suggest_mapping,
)

router = APIRouter(prefix="/businesses/{business_id}/imports", tags=["imports"])

PREVIEW_ROW_LIMIT = 10


def _get_owned_import_session(
    import_id: uuid.UUID, business: Business, db: Session
) -> ImportSession:
    import_session = (
        db.query(ImportSession)
        .filter(ImportSession.id == import_id, ImportSession.business_id == business.id)
        .first()
    )
    if not import_session:
        raise NotFoundError("Import not found.")
    return import_session


@router.post("/upload", response_model=ImportPreviewOut, status_code=status.HTTP_201_CREATED)
async def upload_import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    # Bounded read -- caps how much this handler ever holds in memory
    # regardless of how large the actual uploaded file is, rather than
    # buffering the whole thing first and only checking its size
    # afterward (that check still exists inside parse_upload as a second
    # layer; this is the first). Reading one byte past the limit is
    # enough to detect "too large" without needing the true size upfront.
    file_bytes = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise AppError(
            f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
            code="file_too_large",
        )
    headers, rows = parse_upload(file_bytes, file.filename or "upload")
    mapping = suggest_mapping(headers)

    import_session = ImportSession(
        business_id=business.id,
        filename=file.filename or "upload",
        status="pending_mapping",
        detected_columns=headers,
        raw_rows=rows,
        suggested_mapping=mapping,
        total_row_count=len(rows),
    )
    db.add(import_session)
    db.commit()
    db.refresh(import_session)

    return ImportPreviewOut(
        id=import_session.id,
        filename=import_session.filename,
        status=import_session.status,
        detected_columns=headers,
        suggested_mapping=mapping,
        preview_rows=rows[:PREVIEW_ROW_LIMIT],
        total_row_count=import_session.total_row_count,
    )


@router.post("/{import_id}/confirm", response_model=ImportConfirmOut, status_code=status.HTTP_202_ACCEPTED)
def confirm_import(
    import_id: uuid.UUID,
    payload: ImportConfirmIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_owned_business),
):
    """
    Batch 10.9: the actual row-by-row validation and insertion no longer
    happens in this request -- for a large file (up to MAX_ROWS=5000),
    doing that inline risked a slow response or an outright gateway
    timeout on some hosts. This route now only does the fast, must-be-
    synchronous parts (ownership/state checks, the plan's usage-limit
    check) and hands the actual work to a background job; the response
    comes back immediately with status="queued", and the caller polls
    GET /imports/{import_id} until status is "completed" or "failed".
    """
    import_session = _get_owned_import_session(import_id, business, db)

    if import_session.status != "pending_mapping":
        raise AppError(
            f"This import has already been {import_session.status} and cannot be confirmed again.",
            code="already_processed",
        )

    # Checked here, synchronously, so a plan-limit rejection is immediate
    # and visible to the user -- not something that only surfaces later
    # as a failed background job they'd have to go looking for.
    check_max_transactions_this_month(db, business)

    import_session.status = "queued"
    db.commit()
    db.refresh(import_session)

    job = enqueue_job(
        db, business, job_type="import_confirm",
        payload={"import_session_id": str(import_session.id), "mapping": payload.mapping},
        actor_user_id=current_user.id,
    )
    run_job_async(job.id)

    return ImportConfirmOut(
        id=import_session.id,
        status=import_session.status,
        total_row_count=import_session.total_row_count,
        imported_row_count=import_session.imported_row_count,
        failed_row_count=import_session.failed_row_count,
        row_errors=[],
    )


@router.get("/{import_id}", response_model=ImportConfirmOut)
def get_import_session(
    import_id: uuid.UUID,
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    """Batch 10.9: polling endpoint for the status of a queued/processing
    import -- the frontend calls this on an interval after `confirm`
    returns 202, until status is "completed" or "failed"."""
    import_session = _get_owned_import_session(import_id, business, db)
    return ImportConfirmOut(
        id=import_session.id,
        status=import_session.status,
        total_row_count=import_session.total_row_count,
        imported_row_count=import_session.imported_row_count,
        failed_row_count=import_session.failed_row_count,
        row_errors=[
            {"row_number": e["row_number"], "errors": e["errors"]} for e in (import_session.row_errors or [])
        ],
    )


@router.get("", response_model=list[ImportSessionOut])
def list_import_sessions(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    sessions = (
        db.query(ImportSession)
        .filter(ImportSession.business_id == business.id)
        .order_by(ImportSession.created_at.desc())
        .limit(limit)
        .all()
    )
    return [ImportSessionOut.model_validate(s) for s in sessions]
