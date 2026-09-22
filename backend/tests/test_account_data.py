"""
Account export/deletion tests (Step 12, Batch 12.5).

Uses the same client/_headers pattern as tests/test_role_permissions.py
and tests/test_team_invites.py (a dependency_overrides'd TestClient
against the real db_session fixture, real Postgres).
"""
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.business import Business
from app.models.subscription import Subscription
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.models.user import User


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_includes_owned_business_and_transaction_count(
    client, db_session, make_user, make_business, make_transaction
):
    owner = make_user(email="owner@example.com")
    business = make_business(owner=owner, name="Owner's Shop")
    make_transaction(business)
    make_transaction(business)

    response = client.get("/auth/me/export", headers=_headers(owner))
    assert response.status_code == 200

    body = response.json()
    assert body["account"]["email"] == "owner@example.com"
    assert len(body["businesses_you_own"]) == 1
    assert body["businesses_you_own"][0]["name"] == "Owner's Shop"
    assert body["businesses_you_own"][0]["transaction_count"] == 2
    # Raw rows are never inlined -- just a pointer to the existing
    # per-business CSV export.
    assert body["businesses_you_own"][0]["transactions_export_url"] == f"/businesses/{business.id}/transactions/export"


def test_export_never_includes_secrets(client, db_session, make_user, make_business):
    owner = make_user()
    make_business(owner=owner)

    response = client.get("/auth/me/export", headers=_headers(owner))
    text = response.text
    assert owner.hashed_password not in text
    assert "hashed_password" not in text
    assert "encrypted_access_token" not in text
    assert "encrypted_refresh_token" not in text


def test_export_lists_memberships_on_other_peoples_businesses(client, db_session, make_user, make_business):
    someone_elses = make_user(email="other.owner@example.com")
    business = make_business(owner=someone_elses, name="Someone Else's Shop")
    member = make_user(email="member@example.com")
    db_session.add(
        TeamMember(
            business_id=business.id, user_id=member.id,
            invited_email=member.email, role="member", status="active",
        )
    )
    db_session.commit()

    response = client.get("/auth/me/export", headers=_headers(member))
    body = response.json()
    assert body["businesses_you_own"] == []
    assert len(body["team_memberships_on_other_businesses"]) == 1
    assert body["team_memberships_on_other_businesses"][0]["business_name"] == "Someone Else's Shop"


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_delete_requires_correct_password(client, db_session, make_user):
    user = make_user(password="correcthorsebattery")

    response = client.request(
        "DELETE", "/auth/me", json={"password": "wrongpassword"}, headers=_headers(user)
    )
    assert response.status_code == 401
    assert db_session.query(User).filter(User.id == user.id).first() is not None


def test_delete_removes_a_solo_owned_business_and_everything_under_it(
    client, db_session, make_user, make_business, make_transaction
):
    user = make_user(password="correcthorsebattery")
    business = make_business(owner=user)
    txn = make_transaction(business)

    response = client.request(
        "DELETE", "/auth/me", json={"password": "correcthorsebattery"}, headers=_headers(user)
    )
    assert response.status_code == 200

    assert db_session.query(User).filter(User.id == user.id).first() is None
    assert db_session.query(Business).filter(Business.id == business.id).first() is None
    assert db_session.query(Transaction).filter(Transaction.id == txn.id).first() is None
    assert db_session.query(Subscription).filter(Subscription.business_id == business.id).first() is None


def test_delete_blocked_when_owned_business_has_other_active_members(
    client, db_session, make_user, make_business
):
    owner = make_user(password="correcthorsebattery")
    business = make_business(owner=owner, name="Shared Shop")
    teammate = make_user(email="teammate@example.com")
    db_session.add(
        TeamMember(
            business_id=business.id, user_id=teammate.id,
            invited_email=teammate.email, role="member", status="active",
        )
    )
    db_session.commit()

    response = client.request(
        "DELETE", "/auth/me", json={"password": "correcthorsebattery"}, headers=_headers(owner)
    )
    assert response.status_code == 409
    assert "Shared Shop" in response.json()["error"]["message"]

    # Nothing was touched.
    assert db_session.query(User).filter(User.id == owner.id).first() is not None
    assert db_session.query(Business).filter(Business.id == business.id).first() is not None


def test_delete_allowed_once_the_other_member_is_removed(client, db_session, make_user, make_business):
    owner = make_user(password="correcthorsebattery")
    business = make_business(owner=owner)
    teammate = make_user(email="teammate2@example.com")
    member = TeamMember(
        business_id=business.id, user_id=teammate.id,
        invited_email=teammate.email, role="member", status="active",
    )
    db_session.add(member)
    db_session.commit()

    # Removed via the existing endpoint, same as a real admin would.
    remove_response = client.delete(f"/businesses/{business.id}/team/{member.id}", headers=_headers(owner))
    assert remove_response.status_code == 204

    response = client.request(
        "DELETE", "/auth/me", json={"password": "correcthorsebattery"}, headers=_headers(owner)
    )
    assert response.status_code == 200
    assert db_session.query(User).filter(User.id == owner.id).first() is None


def test_delete_not_blocked_by_a_pending_or_inactive_invite(client, db_session, make_user, make_business):
    """A *pending* invite (no account yet) or an inactive membership isn't
    an active collaborator using the business -- only status="active"
    should block deletion."""
    owner = make_user(password="correcthorsebattery")
    business = make_business(owner=owner)
    db_session.add(
        TeamMember(
            business_id=business.id, user_id=None,
            invited_email="not.signed.up.yet@example.com", role="member", status="pending",
        )
    )
    db_session.commit()

    response = client.request(
        "DELETE", "/auth/me", json={"password": "correcthorsebattery"}, headers=_headers(owner)
    )
    assert response.status_code == 200


def test_delete_removes_membership_on_someone_elses_business(client, db_session, make_user, make_business):
    """Deleting an account that's just a *member* elsewhere (not the
    owner) never blocks -- only owned businesses with other active
    members do."""
    someone_elses_owner = make_user()
    business = make_business(owner=someone_elses_owner)
    member = make_user(password="correcthorsebattery")
    row = TeamMember(
        business_id=business.id, user_id=member.id,
        invited_email=member.email, role="member", status="active",
    )
    db_session.add(row)
    db_session.commit()
    member_id = row.id

    response = client.request(
        "DELETE", "/auth/me", json={"password": "correcthorsebattery"}, headers=_headers(member)
    )
    assert response.status_code == 200
    assert db_session.query(User).filter(User.id == member.id).first() is None
    assert db_session.query(TeamMember).filter(TeamMember.id == member_id).first() is None
    # The other owner and their business are completely unaffected.
    assert db_session.query(Business).filter(Business.id == business.id).first() is not None
