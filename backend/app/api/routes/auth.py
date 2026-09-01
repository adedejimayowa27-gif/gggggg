"""
Authentication routes.

Auth is stateless JWT-based for this step:
- signup/login both return a bearer token.
- logout is a client-side action (discard the token); the endpoint exists
  for a consistent API shape and to leave room for future server-side
  token revocation (e.g. a blacklist table) without breaking the contract.
"""
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserOut
from app.services.audit import client_ip, log_action
from app.services.team import link_pending_invites

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Batch 10.2: activates any team invite(s) made to this email before
    # the account existed. Safe/cheap even when there are none.
    link_pending_invites(db, user)

    log_action(
        db, "auth.signup", actor_user_id=user.id,
        target_type="user", target_id=str(user.id),
        details={"email": user.email}, ip_address=client_ip(request),
    )

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        # Logged with no actor_user_id when the email doesn't match any
        # account, since there's no real user to attribute it to -- the
        # email attempted still shows up in `details` for security review.
        log_action(
            db, "auth.login_failed", actor_user_id=user.id if user else None,
            details={"email": payload.email}, ip_address=client_ip(request),
        )
        raise UnauthorizedError("Incorrect email or password.")
    if not user.is_active:
        raise UnauthorizedError("User account is inactive.")

    log_action(
        db, "auth.login", actor_user_id=user.id,
        target_type="user", target_id=str(user.id), ip_address=client_ip(request),
    )

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(current_user: User = Depends(get_current_user)):
    # Stateless JWT: nothing to invalidate server-side yet. The client is
    # responsible for discarding the token. Requiring a valid token here
    # ensures the endpoint can't be spammed by unauthenticated clients.
    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
