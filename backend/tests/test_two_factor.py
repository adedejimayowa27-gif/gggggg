"""
Two-factor login tests (Step 12, Batch 12.6).

Same client/_headers pattern as test_account_data.py and
test_team_invites.py. settings.TOTP_ENCRYPTION_KEY is monkeypatched to a
fresh Fernet key per test (see the `configured` fixture) rather than
relying on a real .env value, since nothing else in this test suite
depends on one being set.
"""
import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def _enroll(client, user, db_session) -> tuple[str, list[str]]:
    """Runs setup + enable for `user`, returning (raw_totp_secret, recovery_codes)."""
    setup = client.post("/auth/2fa/setup", headers=_headers(user))
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    code = pyotp.TOTP(secret).now()
    enable = client.post("/auth/2fa/enable", json={"code": code}, headers=_headers(user))
    assert enable.status_code == 200
    recovery_codes = enable.json()["recovery_codes"]

    db_session.refresh(user)
    assert user.is_2fa_enabled is True
    return secret, recovery_codes


# ---------------------------------------------------------------------------
# Setup / enable
# ---------------------------------------------------------------------------


def test_setup_returns_a_scannable_secret_and_qr(client, make_user):
    user = make_user()
    response = client.post("/auth/2fa/setup", headers=_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert len(body["secret"]) >= 16
    assert body["otpauth_url"].startswith("otpauth://totp/")
    assert "<svg" in body["qr_code_svg"]


def test_enable_rejects_a_wrong_code(client, db_session, make_user):
    user = make_user()
    client.post("/auth/2fa/setup", headers=_headers(user))

    response = client.post("/auth/2fa/enable", json={"code": "000000"}, headers=_headers(user))
    assert response.status_code == 401

    db_session.refresh(user)
    assert user.is_2fa_enabled is False


def test_enable_with_the_right_code_turns_on_2fa_and_issues_recovery_codes(client, db_session, make_user):
    user = make_user()
    _, recovery_codes = _enroll(client, user, db_session)
    assert len(recovery_codes) == 8
    assert len(set(recovery_codes)) == 8  # all distinct


def test_setup_cannot_be_restarted_once_enabled(client, db_session, make_user):
    user = make_user()
    _enroll(client, user, db_session)

    response = client.post("/auth/2fa/setup", headers=_headers(user))
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------


def test_login_without_2fa_enabled_returns_tokens_directly(client, make_user):
    user = make_user(password="correcthorsebattery")
    response = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_2fa_enabled_returns_a_challenge_not_tokens(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    _enroll(client, user, db_session)

    response = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    assert response.status_code == 200
    body = response.json()
    assert body["two_factor_required"] is True
    assert "challenge_token" in body
    assert "access_token" not in body


def test_verify_login_with_correct_totp_code_issues_tokens(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    secret, _ = _enroll(client, user, db_session)

    login = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    challenge_token = login.json()["challenge_token"]

    code = pyotp.TOTP(secret).now()
    response = client.post("/auth/2fa/verify-login", json={"challenge_token": challenge_token, "code": code})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_verify_login_with_wrong_code_is_rejected(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    _enroll(client, user, db_session)

    login = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    challenge_token = login.json()["challenge_token"]

    response = client.post(
        "/auth/2fa/verify-login", json={"challenge_token": challenge_token, "code": "000000"}
    )
    assert response.status_code == 401


def test_verify_login_with_a_recovery_code_works_and_consumes_it(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    _, recovery_codes = _enroll(client, user, db_session)
    a_code = recovery_codes[0]

    login = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    challenge_token = login.json()["challenge_token"]

    first_use = client.post(
        "/auth/2fa/verify-login", json={"challenge_token": challenge_token, "code": a_code}
    )
    assert first_use.status_code == 200

    # The same code must not work a second time, even against a fresh challenge.
    login2 = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    second_use = client.post(
        "/auth/2fa/verify-login", json={"challenge_token": challenge_token, "code": a_code}
    )
    assert second_use.status_code == 401
    second_use_fresh_challenge = client.post(
        "/auth/2fa/verify-login",
        json={"challenge_token": login2.json()["challenge_token"], "code": a_code},
    )
    assert second_use_fresh_challenge.status_code == 401


# ---------------------------------------------------------------------------
# Disable / regenerate
# ---------------------------------------------------------------------------


def test_disable_requires_correct_password(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    secret, _ = _enroll(client, user, db_session)
    code = pyotp.TOTP(secret).now()

    response = client.post(
        "/auth/2fa/disable", json={"password": "wrongpassword", "code": code}, headers=_headers(user)
    )
    assert response.status_code == 401

    db_session.refresh(user)
    assert user.is_2fa_enabled is True


def test_disable_requires_correct_code(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    _enroll(client, user, db_session)

    response = client.post(
        "/auth/2fa/disable",
        json={"password": "correcthorsebattery", "code": "000000"},
        headers=_headers(user),
    )
    assert response.status_code == 401


def test_disable_with_password_and_code_clears_everything(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    secret, _ = _enroll(client, user, db_session)
    code = pyotp.TOTP(secret).now()

    response = client.post(
        "/auth/2fa/disable", json={"password": "correcthorsebattery", "code": code}, headers=_headers(user)
    )
    assert response.status_code == 200

    db_session.refresh(user)
    assert user.is_2fa_enabled is False
    assert user.totp_secret_encrypted is None
    assert user.totp_recovery_codes_hashed is None

    # Logging in now goes straight through, no challenge.
    login = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    assert "access_token" in login.json()


def test_disable_accepts_a_recovery_code_instead_of_a_totp_code(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    _, recovery_codes = _enroll(client, user, db_session)

    response = client.post(
        "/auth/2fa/disable",
        json={"password": "correcthorsebattery", "code": recovery_codes[0]},
        headers=_headers(user),
    )
    assert response.status_code == 200


def test_regenerate_recovery_codes_invalidates_the_old_set(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")
    secret, old_codes = _enroll(client, user, db_session)
    code = pyotp.TOTP(secret).now()

    response = client.post(
        "/auth/2fa/recovery-codes",
        json={"password": "correcthorsebattery", "code": code},
        headers=_headers(user),
    )
    assert response.status_code == 200
    new_codes = response.json()["recovery_codes"]
    assert set(new_codes).isdisjoint(set(old_codes))

    # An old code no longer works at login.
    login = client.post("/auth/login", json={"email": user.email, "password": "correcthorsebattery"})
    challenge_token = login.json()["challenge_token"]
    old_code_attempt = client.post(
        "/auth/2fa/verify-login", json={"challenge_token": challenge_token, "code": old_codes[0]}
    )
    assert old_code_attempt.status_code == 401

    # A new one does.
    new_code_attempt = client.post(
        "/auth/2fa/verify-login", json={"challenge_token": challenge_token, "code": new_codes[0]}
    )
    assert new_code_attempt.status_code == 200
