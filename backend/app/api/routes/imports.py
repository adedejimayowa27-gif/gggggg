"""
Import routes.

Nested under a specific business (/businesses/{business_id}/imports/...)
so every route here automatically inherits the ownership check from
get_owned_business -- there is no way to reach another business's data
through this router.
"""
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_business
from app.db.session import get_db
from app.models.business import Business
from app.models.import_session import ImportSession
from app.schemas.import_session import ImportPreviewOut
from app.services.import_pipeline import parse_upload, suggest_mapping

router = APIRouter(prefix="/businesses/{business_id}/imports", tags=["imports"])

PREVIEW_ROW_LIMIT = 10


@router.post("/upload", response_model=ImportPreviewOut, status_code=status.HTTP_201_CREATED)
async def upload_import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    business: Business = Depends(get_owned_business),
):
    file_bytes = await file.read()
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
