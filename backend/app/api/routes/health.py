"""
Health-check endpoint. Verifies the API is up and can reach the database.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 -- intentionally broad for a health probe
        db_status = f"error: {exc}"

    return {
        "status": "ok",
        "database": db_status,
    }
