"""
Import routes.

Nested under a specific business (/businesses/{business_id}/imports/...)
so every route here automatically inherits the ownership check from
get_owned_business -- there is no way to reach another business's data
through this router.
"""
import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_business
from app.core.exceptions import AppError, NotFoundError
from app.db.session import get_db
from app.models.business import Business
from app.models.import_session import ImportSession
from app.models.transaction import Transaction
from app.models.user import User
from app.services.audit import client_ip, log_action
from app.services.billing import check_max_transactions_this_month
from app.schemas.import_session import (
    ImportConfirmIn,
    ImportConfirmOut,
    ImportPreviewOut,
    ImportSessionOut,
)
from app.services.import_pipeline import (
    MAX_FILE_SIZE_BYTES,
    compute_fingerprint,
    parse_upload,
    suggest_mapping,
    validate_and_convert_rows,
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


@router.post("/{import_id}/confirm", response_model=ImportConfirmOut)
def confirm_import(
    import_id: uuid.UUID,
    payload: ImportConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_owned_business),
):
    import_session = _get_owned_import_session(import_id, business, db)

    if import_session.status != "pending_mapping":
        raise AppError(
            f"This import has already been {import_session.status} and cannot be confirmed again.",
            code="already_processed",
        )

    check_max_transactions_this_month(db, business)

    valid_rows, row_errors = validate_and_convert_rows(
        import_session.raw_rows, payload.mapping
    )

    # valid_rows' keys are exactly Transaction's data columns (see
    # validate_and_convert_rows' docstring) -- unpacking directly, rather
    # than re-listing every field here, is what makes this pipeline
    # reusable: a future Google Sheets sync or POS sync that produces the
    # same (headers, rows) shape and calls the same validate_and_convert_rows
    # can persist through this exact same shape with no route-level
    # changes when new optional fields are added later.
    for row in valid_rows:
        db.add(
            Transaction(
                business_id=business.id,
                import_session_id=import_session.id,
                fingerprint=compute_fingerprint(str(business.id), row),
                **row,
            )
        )

    import_session.confirmed_mapping = payload.mapping
    import_session.imported_row_count = len(valid_rows)
    import_session.failed_row_count = len(row_errors)
    import_session.row_errors = row_errors
    import_session.status = "completed" if valid_rows else "failed"

    db.commit()
    db.refresh(import_session)

    log_action(
        db, "import.completed", business_id=business.id, actor_user_id=current_user.id,
        target_type="import_session", target_id=str(import_session.id),
        details={
            "imported_row_count": import_session.imported_row_count,
            "failed_row_count": import_session.failed_row_count,
        },
        ip_address=client_ip(request),
    )

    return ImportConfirmOut(
        id=import_session.id,
        status=import_session.status,
        total_row_count=import_session.total_row_count,
        imported_row_count=import_session.imported_row_count,
        failed_row_count=import_session.failed_row_count,
        row_errors=row_errors,
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
