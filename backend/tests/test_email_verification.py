"""
Email verification tests (Step 12, Batch 12.2).

Covers: a new signup starts unverified and gets a verification email;
a valid token verifies the account exactly once; an invalid/expired/
wrong-purpose token is rejected; resend is a no-op (but still returns
the same generic message) for a nonexistent or already-verified email;
and, most importantly, that none of this blocks login or any other
route -- verification is tracked, not enforced (see
app/api/routes/auth.py's module docstring).
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, create_email_verification_token
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # This file cares about verification, not rate limiting; the shared
    # limiter is process-wide, so other test files running first could
    # otherwise make a 5/minute or 10/minute route here flake.
    sent = []

    def _fake_send_email(to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})
        return True

    import app.api.routes.auth as auth_route

    monkeypatch.setattr(auth_route, "send_email", _fake_send_email)

    test_client = TestClient(app)
    test_client.sent_emails = sent  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def test_signup_starts_unverified_and_sends_a_verification_email(client):
    response = client.post(
        "/auth/signup",
        json={"email": "new.user@example.com", "password": "testpassword123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["is_email_verified"] is False

    assert len(client.sent_emails) == 1
    assert client.sent_emails[0]["to"] == "new.user@example.com"
    assert "confirm" in client.sent_emails[0]["subject"].lower()


def test_a_valid_token_verifies_the_account(client, make_user):
    user = make_user()
    assert user.is_email_verified is False
    token = create_email_verification_token(str(user.id))

    response = client.post("/auth/verify-email", json={"token": token})
    assert response.status_code == 200

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"})
    assert me.json()["is_email_verified"] is True


def test_verifying_twice_is_harmless(client, make_user):
    user = make_user()
    token = create_email_verification_token(str(user.id))
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    # The same token used again: still valid (nothing invalidates it),
    # still succeeds, still just leaves is_email_verified True.
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200


def test_an_invalid_token_is_rejected(client):
    response = client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 422


def test_a_password_reset_token_does_not_verify_email(client, make_user):
    """The "purpose" claim must stop a token issued for one thing from
    being replayed for the other -- see create_email_verification_token's
    docstring."""
    from app.core.security import create_password_reset_token

    user = make_user()
    reset_token = create_password_reset_token(str(user.id))

    response = client.post("/auth/verify-email", json={"token": reset_token})
    assert response.status_code == 422
    assert user.is_email_verified is False


def test_an_expired_token_is_rejected(client, make_user):
    user = make_user()
    # Build an already-expired token directly instead of waiting out the
    # real ~24h expiry.
    from datetime import datetime, timezone
    from jose import jwt
    from app.core.config import settings

    expired = jwt.encode(
        {
            "sub": str(user.id),
            "purpose": "email_verification",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    response = client.post("/auth/verify-email", json={"token": expired})
    assert response.status_code == 422


def test_resend_sends_a_new_email_for_an_unverified_account(client, make_user):
    user = make_user()
    response = client.post("/auth/resend-verification", json={"email": user.email})
    assert response.status_code == 200
    assert len(client.sent_emails) == 1
    assert client.sent_emails[0]["to"] == user.email


def test_resend_is_a_silent_no_op_for_an_unknown_email(client):
    """Same account-enumeration defense as /forgot-password: the response
    text must not reveal whether the email is registered."""
    response = client.post("/auth/resend-verification", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert "if an unverified account exists" in response.json()["message"].lower()
    assert len(client.sent_emails) == 0


def test_resend_is_a_silent_no_op_for_an_already_verified_account(client, make_user):
    user = make_user()
    client.post("/auth/verify-email", json={"token": create_email_verification_token(str(user.id))})
    client.sent_emails.clear()

    response = client.post("/auth/resend-verification", json={"email": user.email})
    assert response.status_code == 200
    assert len(client.sent_emails) == 0


def test_an_unverified_user_can_still_log_in_and_use_the_app(client, make_user):
    """The core guarantee of this batch: verification is informational
    only. An unverified account is fully functional."""
    user = make_user(password="testpassword123")
    login = client.post("/auth/login", json={"email": user.email, "password": "testpassword123"})
    assert login.status_code == 200
    assert login.json()["user"]["is_email_verified"] is False

    token = login.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["is_email_verified"] is False
