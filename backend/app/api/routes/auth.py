"""
Authentication routes.

Two-token auth (Step 12, Batch 12.3):
- signup/login/refresh all return an access_token (short-lived, stateless
  JWT -- app.core.security.create_access_token) AND a refresh_token
  (long-lived, revocable, stored hashed -- app.models.refresh_token).
- POST /auth/refresh exchanges a refresh token for a new pair, rotating
  the refresh token each time; POST /auth/logout revokes it for real.
- A password reset revokes every refresh token for that account (see
  reset_password below), so a compromised session can't outlive the
  password that was reset because of it.
Before this batch, auth was pure stateless JWT with no server-side way
to end a session early; see app/models/refresh_token.py for the full
design rationale.

Email verification (Step 12, Batch 12.2): tracked, not enforced. An
unverified user can log in and use every feature exactly as before --
this batch only adds a flag, a dismissible frontend banner, and a way to
confirm the address. The alternative (blocking access until verified)
would double as an access-control feature and needs its own design
decisions (which routes stay open so a legitimately-locked-out person can
still get the verification email re-sent, what happens to existing
unverified accounts, etc.) -- deliberately out of scope here so as not to
lock anyone out as a side effect of this batch. Still not enforced as of
Batch 12.3 (sessions) below -- if it's ever added, it belongs in
get_current_user (app/api/deps.py), not here.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationError
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    decode_email_verification_token,
    decode_password_reset_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import (
    DeleteAccountRequest,
    ForgotPasswordRequest,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
    VerifyEmailRequest,
)
from app.services.audit import client_ip, log_action
from app.services.email import render_password_reset_email, render_verification_email, send_email
from app.services.team import link_pending_invites
from app.services.user import delete_account, export_account_data

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
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

    # Batch 12.2: best-effort, same as every other email this app sends --
    # send_email logs and returns False on any failure (missing config,
    # Resend down) rather than raising, so signup itself never fails
    # because of the verification email.
    _send_verification_email(user)

    return _issue_tokens(db, user)


def _send_verification_email(user: User) -> None:
    verify_token = create_email_verification_token(str(user.id))
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={verify_token}"
    subject, html = render_verification_email(verify_url)
    send_email(user.email, subject, html)


def _issue_tokens(db: Session, user: User, family_id: uuid.UUID | None = None) -> Token:
    """
    Creates a new access token (stateless, short-lived) and a new
    refresh-token row (stateful, revocable -- see
    app/models/refresh_token.py), and returns both in the shape the
    client stores.

    `family_id` is only passed by /auth/refresh, continuing an existing
    rotation chain; signup/login omit it, starting a brand-new family
    (this new token's own id becomes the family_id, exactly matching
    the pattern flush()-ing once and using the generated id).
    """
    access_token = create_access_token(subject=str(user.id))
    raw_refresh_token, token_hash = generate_refresh_token()

    refresh_token_row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    # A brand-new family uses this row's own id as family_id, so the
    # family always exists even for a session that's never been
    # refreshed. Needs an id up front, hence flush() before using it --
    # cheaper than a second query, and everything here commits together
    # in one transaction regardless.
    if family_id is None:
        db.add(refresh_token_row)
        db.flush()
        refresh_token_row.family_id = refresh_token_row.id
    else:
        db.add(refresh_token_row)
    db.commit()

    return Token(access_token=access_token, refresh_token=raw_refresh_token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
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

    return _issue_tokens(db, user)


@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
def refresh(payload: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)):
    """
    Exchanges a refresh token for a new access token AND a new refresh
    token (rotation -- see app/models/refresh_token.py's module
    docstring). The old refresh token is revoked in the same call, so
    it can never be used again.

    Reuse detection: if the presented token matches a row that's
    already revoked, that's not a normal "expired, log in again" case --
    a legitimate client only ever holds the single newest token in its
    family, so a *revoked* token being replayed means it was copied
    somewhere (a stolen token, a client that crashed mid-rotation and
    retried with a token it no longer should have, etc.). Rather than
    guess which, every token in that family is revoked, which forces a
    real re-login and cuts off whoever else is holding a copy.
    """
    token_hash = hash_refresh_token(payload.refresh_token)
    token_row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not token_row:
        raise UnauthorizedError("This session is no longer valid. Please log in again.")

    if token_row.revoked_at is not None:
        db.query(RefreshToken).filter(
            RefreshToken.family_id == token_row.family_id, RefreshToken.revoked_at.is_(None)
        ).update({"revoked_at": datetime.now(timezone.utc), "revoked_reason": "reuse_detected"})
        db.commit()
        log_action(
            db, "auth.refresh_reuse_detected", actor_user_id=token_row.user_id,
            target_type="user", target_id=str(token_row.user_id), ip_address=client_ip(request),
        )
        raise UnauthorizedError("This session is no longer valid. Please log in again.")

    if token_row.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("This session is no longer valid. Please log in again.")

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if not user or not user.is_active:
        raise UnauthorizedError("This session is no longer valid. Please log in again.")

    token_row.revoked_at = datetime.now(timezone.utc)
    token_row.revoked_reason = "rotated"
    db.commit()

    return _issue_tokens(db, user, family_id=token_row.family_id)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    payload: RefreshTokenRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Batch 12.3: now revokes the refresh token for real (previously this
    endpoint required a valid access token but had nothing to actually
    invalidate -- the access token itself kept working until it expired
    on its own). `payload` is optional so an older/other client that
    still calls this with no body -- or with only its access token, the
    way the pre-12.3 frontend did -- doesn't get a hard error; it just
    revokes nothing server-side and the client is still responsible for
    discarding its tokens, same as before.

    Scoped to `user_id == current_user.id`: a valid access token only
    lets you revoke your own sessions, never an arbitrary refresh token
    someone else's client happens to send here.
    """
    if payload and payload.refresh_token:
        token_row = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == hash_refresh_token(payload.refresh_token),
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .first()
        )
        if token_row:
            token_row.revoked_at = datetime.now(timezone.utc)
            token_row.revoked_reason = "logout"
            db.commit()

    return {"message": "Logged out successfully."}


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.get("/me/export")
@limiter.limit("5/minute")
def export_my_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Batch 12.5. Downloads everything about this account as a single JSON
    file -- see app/services/user.py's export_account_data for exactly
    what's included (and, deliberately, what isn't: raw transaction rows,
    which stay behind each business's own existing CSV export endpoint
    instead of ballooning this payload; and anything secret -- password
    hash, refresh tokens, integration OAuth tokens -- which never leaves
    its own table at all).
    """
    data = export_account_data(db, current_user)
    log_action(
        db, "auth.data_exported", actor_user_id=current_user.id,
        target_type="user", target_id=str(current_user.id), ip_address=client_ip(request),
    )
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="account-data-export.json"'},
    )


@router.delete("/me", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
def delete_my_account(
    payload: DeleteAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Batch 12.5. Permanently deletes the account and everything under it.
    Re-checks the password even though the request is already
    authenticated (see DeleteAccountRequest's docstring), and blocks --
    with a 409, via app.services.user's ConflictError -- when the account
    owns a business other people are still actively using; see
    app/services/user.py's businesses_blocking_deletion for why and what
    to do about it.

    No confirmation-email step: this app has no async
    "click here to confirm" flow for anything else destructive either
    (password reset, verify-email are the only token-based ones, and
    both are opt-in actions the person initiates from a link, not a
    same-session irreversible action like this one) -- the password
    re-check plus the frontend's own "are you sure" is the same bar as
    every other destructive action in this app (e.g. removing a team
    member).
    """
    if not verify_password(payload.password, current_user.hashed_password):
        raise UnauthorizedError("Incorrect password.")

    delete_account(db, current_user)
    return {"message": "Your account has been permanently deleted."}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """
    Always returns the same generic message, whether or not the email
    matches an account -- this is the standard defense against account
    enumeration (an attacker learning which emails are registered by
    comparing responses). The actual reset email is only ever sent when
    a matching, active account exists; a non-matching email silently
    does nothing beyond returning the same response.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if user and user.is_active:
        reset_token = create_password_reset_token(str(user.id))
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        subject, html = render_password_reset_email(reset_url)
        send_email(user.email, subject, html)
        log_action(
            db, "auth.password_reset_requested", actor_user_id=user.id,
            target_type="user", target_id=str(user.id), ip_address=client_ip(request),
        )

    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    user_id = decode_password_reset_token(payload.token)
    if not user_id:
        raise ValidationError("This reset link is invalid or has expired.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise ValidationError("This reset link is invalid or has expired.")

    user.hashed_password = hash_password(payload.new_password)

    # Batch 12.3: if the password was reset because it (or the account)
    # was compromised, an attacker's still-valid refresh token would
    # otherwise keep their session alive indefinitely -- resetting the
    # password alone wouldn't log them out. Revoking every one of this
    # user's sessions closes that gap; the person who just reset the
    # password logs back in and gets a fresh one.
    revoked_count = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .update({"revoked_at": datetime.now(timezone.utc), "revoked_reason": "password_reset"})
    )
    db.commit()

    log_action(
        db, "auth.password_reset_completed", actor_user_id=user.id,
        target_type="user", target_id=str(user.id),
        details={"sessions_revoked": revoked_count}, ip_address=client_ip(request),
    )

    return {"message": "Password updated. You can now log in with your new password."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def verify_email(payload: VerifyEmailRequest, request: Request, db: Session = Depends(get_db)):
    user_id = decode_email_verification_token(payload.token)
    if not user_id:
        raise ValidationError("This verification link is invalid or has expired.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValidationError("This verification link is invalid or has expired.")

    if not user.is_email_verified:
        user.is_email_verified = True
        db.commit()
        log_action(
            db, "auth.email_verified", actor_user_id=user.id,
            target_type="user", target_id=str(user.id), ip_address=client_ip(request),
        )

    return {"message": "Email address confirmed."}


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
def resend_verification(payload: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)):
    """
    Same account-enumeration defense as /forgot-password above: always
    the same generic response, and the email only actually goes out when
    a matching, active, not-yet-verified account exists.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if user and user.is_active and not user.is_email_verified:
        _send_verification_email(user)
        log_action(
            db, "auth.verification_resent", actor_user_id=user.id,
            target_type="user", target_id=str(user.id), ip_address=client_ip(request),
        )

    return {"message": "If an unverified account exists for that email, a confirmation link has been sent."}
