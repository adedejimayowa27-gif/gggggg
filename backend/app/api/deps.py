"""
Shared FastAPI dependencies.

`get_current_user` is the single choke point for route protection: any
route that takes it as a dependency requires a valid bearer token and an
active user. Later steps (business routes, AI assistant, etc.) reuse this
same dependency rather than re-implementing auth checks.
"""
import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# tokenUrl is only used by the OpenAPI docs UI to know where to fetch a token from.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise UnauthorizedError("Not authenticated.")

    subject = decode_access_token(token)
    if not subject:
        raise UnauthorizedError("Invalid or expired token.")

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise UnauthorizedError("Invalid token subject.")

    user = db.get(User, user_id)
    if not user:
        raise UnauthorizedError("User not found.")
    if not user.is_active:
        raise UnauthorizedError("User account is inactive.")

    return user
