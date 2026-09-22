"""
Team invite email tests (Step 12, Batch 12.2 fix).

The invite endpoint always creates the TeamMember row regardless of
whether the email goes out (see app/services/team.py's invite_member) --
this file covers the part that was silently broken: the caller had no
way to tell a delivered invite from one where send_email failed (e.g.
Resend rejecting the recipient because the sender is an unverified
domain/sandbox address). `email_sent` on the response is how that's
surfaced now.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.team_member import TeamMember


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    sent = []

    def _fake_send_email(to, subject, html):
        sent.append({"to": to, "subject": subject, "html": html})
        return True

    import app.services.email as email_service

    monkeypatch.setattr(email_service, "send_email", _fake_send_email)

    test_client = TestClient(app)
    test_client.sent_emails = sent  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def _invite(client, business, actor, email, role="member"):
    return client.post(
        f"/businesses/{business.id}/team",
        json={"email": email, "role": role},
        headers=_headers(actor),
    )


def test_inviting_someone_new_sends_an_email_to_signup(client, db_session, make_user, make_business):
    owner = make_user()
    business = make_business(owner=owner)

    response = _invite(client, business, owner, "new.teammate@example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["email_sent"] is True

    assert len(client.sent_emails) == 1
    assert client.sent_emails[0]["to"] == "new.teammate@example.com"
    assert "invited" in client.sent_emails[0]["subject"].lower()


def test_inviting_an_existing_user_sends_an_email_to_login(client, db_session, make_user, make_business):
    owner = make_user()
    business = make_business(owner=owner)
    existing = make_user(email="already.has.an.account@example.com")

    response = _invite(client, business, owner, existing.email)
    assert response.status_code == 201
    assert response.json()["email_sent"] is True
    assert client.sent_emails[0]["to"] == existing.email


def test_a_failed_send_still_creates_the_membership_but_reports_it(
    client, db_session, make_user, make_business, monkeypatch
):
    """This is the bug this batch fixes: previously a failed send was only
    visible in server logs, so an admin who invited someone whose email
    provider rejected the message (e.g. Resend's sandbox restrictions) had
    no way to know the invitee never got anything."""
    owner = make_user()
    business = make_business(owner=owner)

    import app.services.email as email_service

    monkeypatch.setattr(email_service, "send_email", lambda to, subject, html: False)

    response = _invite(client, business, owner, "unreachable@example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["email_sent"] is False

    # The membership itself is unaffected by the email failure.
    member = db_session.query(TeamMember).filter(TeamMember.id == body["id"]).one()
    assert member.invited_email == "unreachable@example.com"
    assert member.status == "pending"


def test_listing_team_members_does_not_claim_an_email_was_sent(client, db_session, make_user, make_business):
    """email_sent only describes the invite that was just made -- a GET on
    the team list (which sends no email) must not imply otherwise."""
    owner = make_user()
    business = make_business(owner=owner)
    _invite(client, business, owner, "someone@example.com")

    response = client.get(f"/businesses/{business.id}/team", headers=_headers(owner))
    assert response.status_code == 200
    for member in response.json():
        assert member["email_sent"] is None
