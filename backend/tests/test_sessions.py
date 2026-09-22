"""
Real sessions tests (Step 12, Batch 12.3).

Covers: signup/login now return a refresh_token alongside access_token;
/auth/refresh rotates it (old one stops working, new one works); reusing
an already-rotated token revokes the whole family (reuse detection);
/auth/logout revokes the specific session it's given, and only that
user's own; and a password reset revokes every refresh token for that
account.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_refresh_token
from app.db.session import get_db
from app.main import app
from app.models.refresh_token import RefreshToken


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    monkeypatch.setattr(
        "app.api.routes.auth.send_email", lambda to, subject, html: True
    )

    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _signup(client, email="session.test@example.com", password="testpassword123"):
    response = client.post("/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201
    return response.json()


def test_signup_returns_both_tokens(client):
    body = _signup(client)
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_login_also_returns_both_tokens(client):
    _signup(client, email="login.session@example.com")
    response = client.post(
        "/auth/login", json={"email": "login.session@example.com", "password": "testpassword123"}
    )
    assert response.status_code == 200
    assert response.json()["refresh_token"]


def test_refresh_token_is_stored_hashed_not_in_plain_text(client, db_session):
    body = _signup(client, email="hash.check@example.com")
    raw_refresh_token = body["refresh_token"]

    row = db_session.query(RefreshToken).filter(RefreshToken.user_id == body["user"]["id"]).first()
    assert row is not None
    assert row.token_hash == hash_refresh_token(raw_refresh_token)
    assert row.token_hash != raw_refresh_token


def test_refresh_issues_a_new_pair_and_revokes_the_old_refresh_token(client):
    body = _signup(client, email="rotate@example.com")

    refreshed = client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    new_body = refreshed.json()
    assert new_body["access_token"] != body["access_token"]
    assert new_body["refresh_token"] != body["refresh_token"]

    # The old refresh token is now revoked; using it again must fail.
    reused = client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert reused.status_code == 401

    # But the new one from the rotation works.
    again = client.post("/auth/refresh", json={"refresh_token": new_body["refresh_token"]})
    assert again.status_code == 200


def test_reusing_a_rotated_token_revokes_the_whole_family(client):
    """Reuse detection: once token A has been rotated into token B, using
    A again is treated as theft and B (the legitimate, currently-active
    token) is revoked too -- not just A."""
    body = _signup(client, email="reuse@example.com")
    token_a = body["refresh_token"]

    rotated = client.post("/auth/refresh", json={"refresh_token": token_a})
    assert rotated.status_code == 200
    token_b = rotated.json()["refresh_token"]

    # Replay the old token.
    replay = client.post("/auth/refresh", json={"refresh_token": token_a})
    assert replay.status_code == 401

    # The legitimate successor is now revoked too, forcing a real re-login.
    use_b = client.post("/auth/refresh", json={"refresh_token": token_b})
    assert use_b.status_code == 401


def test_an_unknown_refresh_token_is_rejected(client):
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


def test_logout_revokes_the_given_session(client):
    body = _signup(client, email="logout.session@example.com")

    logout = client.post(
        "/auth/logout",
        json={"refresh_token": body["refresh_token"]},
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert logout.status_code == 200

    # That refresh token no longer works.
    response = client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 401


def test_logout_with_no_body_still_succeeds(client):
    """Backward compatibility: a client that calls /auth/logout the old
    way (access token only, no refresh_token) must not get a hard error."""
    body = _signup(client, email="logout.no.body@example.com")
    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 200


def test_logout_cannot_revoke_someone_elses_session(client, db_session):
    victim = _signup(client, email="victim@example.com")
    attacker = _signup(client, email="attacker@example.com")

    # The attacker is logged in (valid access token of their own) but
    # tries to revoke the victim's refresh token.
    response = client.post(
        "/auth/logout",
        json={"refresh_token": victim["refresh_token"]},
        headers={"Authorization": f"Bearer {attacker['access_token']}"},
    )
    assert response.status_code == 200  # silently does nothing -- no error leaks whether it existed

    # The victim's session is untouched.
    still_works = client.post("/auth/refresh", json={"refresh_token": victim["refresh_token"]})
    assert still_works.status_code == 200


def test_password_reset_revokes_every_session(client, db_session):
    from app.core.security import create_password_reset_token

    body = _signup(client, email="reset.sessions@example.com")
    # A second session for the same account (e.g. a second device).
    second_login = client.post(
        "/auth/login", json={"email": "reset.sessions@example.com", "password": "testpassword123"}
    )
    assert second_login.status_code == 200

    user_id = body["user"]["id"]
    reset_token = create_password_reset_token(user_id)
    reset = client.post(
        "/auth/reset-password", json={"token": reset_token, "new_password": "brandnewpassword456"}
    )
    assert reset.status_code == 200

    # Both sessions are dead.
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    assert (
        client.post(
            "/auth/refresh", json={"refresh_token": second_login.json()["refresh_token"]}
        ).status_code
        == 401
    )

    # But logging in fresh with the new password works.
    fresh = client.post(
        "/auth/login", json={"email": "reset.sessions@example.com", "password": "brandnewpassword456"}
    )
    assert fresh.status_code == 200
