"""
Manual transaction entry, editing and deleting (Step 13, Batch 1).

Real HTTP requests against real Postgres, like the other route tests. The
last section covers the part most likely to go quietly wrong: an imported
sale that a person deletes or corrects in the app must not be brought back
by the next file import or sync.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.import_session import ImportSession
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.models.transaction_tombstone import TransactionTombstone
from app.services.import_pipeline import execute_confirmed_import
from app.services.transactions import existing_fingerprints


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    was_enabled = getattr(limiter, "enabled", True)
    limiter.enabled = False
    yield TestClient(app, raise_server_exceptions=False)
    limiter.enabled = was_enabled
    app.dependency_overrides.clear()


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


@pytest.fixture()
def owner_and_business(make_user, make_business):
    owner = make_user()
    return owner, make_business(owner=owner)


@pytest.fixture()
def add_member(db_session, make_user):
    def _add(business, role):
        user = make_user()
        db_session.add(
            TeamMember(
                business_id=business.id, user_id=user.id,
                invited_email=user.email, role=role, status="active",
            )
        )
        db_session.commit()
        return user

    return _add


def _payload(**overrides) -> dict:
    body = {
        "date": date.today().isoformat(),
        "product": "Bag of rice",
        "quantity": "2",
        "selling_price": "45000.00",
        "cost_price": "38000.00",
        "category": "Food",
        "customer": "Ada",
        "payment_method": "Transfer",
    }
    body.update(overrides)
    return body


def _url(business, suffix="") -> str:
    return f"/businesses/{business.id}/transactions{suffix}"


def _audit_actions(db_session, business) -> list[str]:
    return [a.action for a in db_session.query(AuditLog).filter(AuditLog.business_id == business.id)]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
class TestCreate:
    def test_creates_a_manual_sale_with_no_import_session(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        response = client.post(_url(business), json=_payload(), headers=_headers(owner))
        assert response.status_code == 201
        body = response.json()
        assert body["product"] == "Bag of rice"
        assert Decimal(body["quantity"]) == 2
        assert body["import_session_id"] is None

        stored = db_session.get(Transaction, body["id"])
        assert stored.business_id == business.id
        assert stored.fingerprint  # so a later import can recognise the same sale
        assert "transaction.created" in _audit_actions(db_session, business)

    def test_optional_fields_can_be_left_out_and_blank_text_becomes_null(self, client, owner_and_business):
        owner, business = owner_and_business
        body = {"date": date.today().isoformat(), "product": "  Pen  ", "quantity": "1",
                "selling_price": "150", "category": "   "}
        response = client.post(_url(business), json=body, headers=_headers(owner))
        assert response.status_code == 201
        data = response.json()
        assert data["product"] == "Pen"
        assert data["cost_price"] is None
        assert data["category"] is None

    def test_a_free_sale_is_allowed(self, client, owner_and_business):
        owner, business = owner_and_business
        response = client.post(_url(business), json=_payload(selling_price="0"), headers=_headers(owner))
        assert response.status_code == 201

    @pytest.mark.parametrize(
        "bad",
        [
            {"quantity": "0"},
            {"quantity": "-3"},
            {"selling_price": "-1"},
            {"cost_price": "-1"},
            {"product": "   "},
            {"date": (date.today() + timedelta(days=30)).isoformat()},
            {"date": "1999-12-31"},
            {"quantity": "1" * 20},
            {"payment_method": "x" * 101},
        ],
    )
    def test_invalid_values_are_rejected(self, client, db_session, owner_and_business, bad):
        owner, business = owner_and_business
        response = client.post(_url(business), json=_payload(**bad), headers=_headers(owner))
        assert response.status_code == 422
        assert db_session.query(Transaction).filter(Transaction.business_id == business.id).count() == 0

    def test_two_identical_sales_on_one_day_are_both_kept(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        for _ in range(2):
            assert client.post(_url(business), json=_payload(), headers=_headers(owner)).status_code == 201
        assert db_session.query(Transaction).filter(Transaction.business_id == business.id).count() == 2

    def test_a_branch_from_another_business_is_rejected(self, client, db_session, make_user, make_business, owner_and_business):
        owner, business = owner_and_business
        other_business = make_business(owner=make_user())
        foreign_branch = Branch(business_id=other_business.id, name="Elsewhere")
        db_session.add(foreign_branch)
        db_session.commit()

        response = client.post(
            _url(business), json=_payload(branch_id=str(foreign_branch.id)), headers=_headers(owner)
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_branch"

    def test_own_branch_is_accepted(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        response = client.post(_url(business), json=_payload(branch_id=str(branch.id)), headers=_headers(owner))
        assert response.status_code == 201
        assert response.json()["branch_id"] == str(branch.id)

    def test_the_monthly_plan_limit_applies(self, client, make_plan, make_business, make_user):
        owner = make_user()
        business = make_business(owner=owner, plan=make_plan(max_transactions_per_month=1))
        assert client.post(_url(business), json=_payload(), headers=_headers(owner)).status_code == 201
        second = client.post(_url(business), json=_payload(product="Another"), headers=_headers(owner))
        assert second.status_code == 422
        assert "transactions per month" in second.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
class TestUpdate:
    def _create(self, client, owner, business, **overrides) -> dict:
        response = client.post(_url(business), json=_payload(**overrides), headers=_headers(owner))
        assert response.status_code == 201
        return response.json()

    def test_only_the_sent_fields_change(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = self._create(client, owner, business)
        response = client.patch(
            _url(business, f"/{created['id']}"), json={"customer": "Bola", "quantity": "3"}, headers=_headers(owner)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["customer"] == "Bola"
        assert Decimal(body["quantity"]) == 3
        assert body["product"] == "Bag of rice"  # untouched
        assert body["category"] == "Food"  # untouched
        assert "transaction.updated" in _audit_actions(db_session, business)

    def test_optional_fields_can_be_cleared_with_null(self, client, owner_and_business):
        owner, business = owner_and_business
        created = self._create(client, owner, business)
        response = client.patch(
            _url(business, f"/{created['id']}"),
            json={"cost_price": None, "customer": None, "category": ""},
            headers=_headers(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["cost_price"] is None
        assert body["customer"] is None
        assert body["category"] is None

    @pytest.mark.parametrize("field", ["date", "product", "quantity", "selling_price"])
    def test_required_fields_cannot_be_cleared(self, client, owner_and_business, field):
        owner, business = owner_and_business
        created = self._create(client, owner, business)
        response = client.patch(_url(business, f"/{created['id']}"), json={field: None}, headers=_headers(owner))
        assert response.status_code == 422

    def test_an_edit_that_changes_the_sale_updates_its_fingerprint(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = self._create(client, owner, business)
        before = db_session.get(Transaction, created["id"]).fingerprint
        client.patch(_url(business, f"/{created['id']}"), json={"selling_price": "50000"}, headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(Transaction, created["id"]).fingerprint != before

    def test_a_metadata_only_edit_keeps_the_fingerprint(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = self._create(client, owner, business)
        before = db_session.get(Transaction, created["id"]).fingerprint
        client.patch(_url(business, f"/{created['id']}"), json={"customer": "Someone else"}, headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(Transaction, created["id"]).fingerprint == before

    def test_another_business_transaction_is_not_found(self, client, make_user, make_business, owner_and_business):
        owner, business = owner_and_business
        other_owner = make_user()
        other_business = make_business(owner=other_owner)
        theirs = self._create(client, other_owner, other_business)

        # Right business, someone else's transaction id.
        response = client.patch(_url(business, f"/{theirs['id']}"), json={"customer": "x"}, headers=_headers(owner))
        assert response.status_code == 404
        # Someone else's business entirely.
        response = client.patch(
            _url(other_business, f"/{theirs['id']}"), json={"customer": "x"}, headers=_headers(owner)
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
class TestDelete:
    def test_delete_removes_the_row_and_is_audited(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = client.post(_url(business), json=_payload(), headers=_headers(owner)).json()
        response = client.delete(_url(business, f"/{created['id']}"), headers=_headers(owner))
        assert response.status_code == 204
        assert db_session.get(Transaction, created["id"]) is None
        assert "transaction.deleted" in _audit_actions(db_session, business)

    def test_deleting_twice_is_a_404(self, client, owner_and_business):
        owner, business = owner_and_business
        created = client.post(_url(business), json=_payload(), headers=_headers(owner)).json()
        assert client.delete(_url(business, f"/{created['id']}"), headers=_headers(owner)).status_code == 204
        assert client.delete(_url(business, f"/{created['id']}"), headers=_headers(owner)).status_code == 404

    def test_deleting_a_manual_sale_leaves_no_tombstone(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = client.post(_url(business), json=_payload(), headers=_headers(owner)).json()
        client.delete(_url(business, f"/{created['id']}"), headers=_headers(owner))
        assert db_session.query(TransactionTombstone).filter_by(business_id=business.id).count() == 0


# ---------------------------------------------------------------------------
# Who may do what (the full matrix lives in test_role_permissions.py)
# ---------------------------------------------------------------------------
class TestRoles:
    def test_viewer_cannot_write(self, client, owner_and_business, add_member):
        owner, business = owner_and_business
        created = client.post(_url(business), json=_payload(), headers=_headers(owner)).json()
        viewer = add_member(business, "viewer")
        assert client.post(_url(business), json=_payload(), headers=_headers(viewer)).status_code == 404
        assert client.patch(_url(business, f"/{created['id']}"), json={"customer": "x"}, headers=_headers(viewer)).status_code == 404
        assert client.delete(_url(business, f"/{created['id']}"), headers=_headers(viewer)).status_code == 404

    def test_member_can_add_and_edit_but_not_delete(self, client, owner_and_business, add_member):
        owner, business = owner_and_business
        member = add_member(business, "member")
        created = client.post(_url(business), json=_payload(), headers=_headers(member))
        assert created.status_code == 201
        tid = created.json()["id"]
        assert client.patch(_url(business, f"/{tid}"), json={"customer": "x"}, headers=_headers(member)).status_code == 200
        assert client.delete(_url(business, f"/{tid}"), headers=_headers(member)).status_code == 404
        # ...and an admin can.
        admin = add_member(business, "admin")
        assert client.delete(_url(business, f"/{tid}"), headers=_headers(admin)).status_code == 204


# ---------------------------------------------------------------------------
# Imports must not resurrect what a person deleted or corrected
# ---------------------------------------------------------------------------
_MAPPING = {
    "date": "Date", "product": "Product", "quantity": "Qty", "selling_price": "Price",
    "cost_price": None, "category": None, "customer": None, "payment_method": None, "branch": None,
}
_RAW_ROWS = [
    {"Date": "2026-09-01", "Product": "Sugar", "Qty": "2", "Price": "1500"},
    {"Date": "2026-09-02", "Product": "Salt", "Qty": "1", "Price": "500"},
]


def _run_import(db_session, business) -> dict:
    session = ImportSession(
        business_id=business.id, filename="sales.csv", source="file", status="mapped",
        detected_columns=["Date", "Product", "Qty", "Price"], raw_rows=_RAW_ROWS,
        suggested_mapping=_MAPPING, total_row_count=len(_RAW_ROWS),
    )
    db_session.add(session)
    db_session.commit()
    return execute_confirmed_import(db_session, str(session.id), _MAPPING)


class TestImportsRespectManualChanges:
    def test_baseline_reimport_is_skipped_as_duplicates(self, db_session, owner_and_business):
        _, business = owner_and_business
        assert _run_import(db_session, business)["imported_row_count"] == 2
        again = _run_import(db_session, business)
        assert again["imported_row_count"] == 0
        assert again["skipped_duplicate_count"] == 2

    def test_a_deleted_imported_sale_is_not_brought_back(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _run_import(db_session, business)
        sugar = db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").one()

        assert client.delete(_url(business, f"/{sugar.id}"), headers=_headers(owner)).status_code == 204

        again = _run_import(db_session, business)
        assert again["imported_row_count"] == 0
        assert again["skipped_duplicate_count"] == 2
        assert db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").count() == 0

    def test_a_corrected_imported_sale_does_not_come_back_as_a_duplicate(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _run_import(db_session, business)
        sugar = db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").one()

        # Fix a typo in the price.
        assert client.patch(_url(business, f"/{sugar.id}"), json={"selling_price": "1800"}, headers=_headers(owner)).status_code == 200

        again = _run_import(db_session, business)
        assert again["imported_row_count"] == 0  # the original 1500 row is NOT re-inserted
        sugars = db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").all()
        assert len(sugars) == 1
        assert sugars[0].selling_price == Decimal("1800")

    def test_editing_only_notes_on_an_imported_sale_makes_no_tombstone(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _run_import(db_session, business)
        sugar = db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").one()
        client.patch(_url(business, f"/{sugar.id}"), json={"customer": "Tunde"}, headers=_headers(owner))
        assert db_session.query(TransactionTombstone).filter_by(business_id=business.id).count() == 0

    def test_existing_fingerprints_helper_covers_both_sources(self, db_session, owner_and_business, make_transaction):
        _, business = owner_and_business
        txn = make_transaction(business)
        db_session.add(TransactionTombstone(business_id=business.id, fingerprint="f" * 64))
        db_session.commit()
        found = existing_fingerprints(db_session, business.id, [txn.fingerprint, "f" * 64, "0" * 64])
        assert found == {txn.fingerprint, "f" * 64}
        assert existing_fingerprints(db_session, business.id, []) == set()

    def test_tombstones_are_per_business(self, client, db_session, make_user, make_business, owner_and_business):
        owner, business = owner_and_business
        other = make_business(owner=make_user())
        _run_import(db_session, business)
        sugar = db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").one()
        client.delete(_url(business, f"/{sugar.id}"), headers=_headers(owner))

        # The other business importing the same file is unaffected.
        assert _run_import(db_session, other)["imported_row_count"] == 2
