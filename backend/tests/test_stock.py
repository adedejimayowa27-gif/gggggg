"""
Inventory / stock (Step 13, Batch 3): CRUD for what's on hand, manual
restock/damage/correction adjustments with an audit trail, roles, the
auto-deduct-on-sale integration with transactions (manual and bulk
import), and the real stock_shortage alert detector.

Real HTTP requests against real Postgres, like the other route tests.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.import_session import ImportSession
from app.models.product_stock import ProductStock
from app.models.stock_adjustment import StockAdjustment
from app.models.transaction import Transaction
from app.services.alert_engine import detect_stock_shortage
from app.services.import_pipeline import execute_confirmed_import
from app.services.stock import (
    apply_manual_adjustment,
    auto_deduct_for_new_transactions,
    find_stock_for_sale,
    find_stock_record,
    reverse_linked_sale_adjustment,
)

TODAY = date.today()


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
        from app.models.team_member import TeamMember

        user = make_user()
        db_session.add(
            TeamMember(
                business_id=business.id, user_id=user.id, invited_email=user.email, role=role, status="active"
            )
        )
        db_session.commit()
        return user

    return _add


@pytest.fixture()
def make_stock(db_session):
    def _make(business, product="Rice", quantity="10", reorder="2", branch=None) -> ProductStock:
        stock = ProductStock(
            business_id=business.id, product=product, quantity_on_hand=Decimal(quantity),
            reorder_level=Decimal(reorder), branch_id=branch.id if branch else None,
        )
        db_session.add(stock)
        db_session.commit()
        db_session.refresh(stock)
        return stock

    return _make


def _url(business, suffix="") -> str:
    return f"/businesses/{business.id}/stock{suffix}"


def _audit_actions(db_session, business) -> list[str]:
    return [a.action for a in db_session.query(AuditLog).filter(AuditLog.business_id == business.id)]


def _enable_auto_deduct(client, owner, business) -> None:
    response = client.patch(
        f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": True}, headers=_headers(owner)
    )
    assert response.status_code == 200
    assert response.json()["auto_deduct_stock_on_sale"] is True


def _create_transaction(client, owner, business, **overrides) -> dict:
    body = {"date": TODAY.isoformat(), "product": "Rice", "quantity": "1", "selling_price": "1000"}
    body.update(overrides)
    response = client.post(f"/businesses/{business.id}/transactions", json=body, headers=_headers(owner))
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
class TestCreate:
    def test_create(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        response = client.post(
            _url(business), json={"product": "  Rice  ", "quantity_on_hand": "50", "reorder_level": "10"},
            headers=_headers(owner),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["product"] == "Rice"
        assert Decimal(body["quantity_on_hand"]) == 50
        assert body["is_low"] is False
        assert "stock.created" in _audit_actions(db_session, business)

    def test_creating_with_stock_at_zero_logs_no_initial_adjustment(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = client.post(_url(business), json={"product": "Salt"}, headers=_headers(owner)).json()
        assert db_session.query(StockAdjustment).filter_by(product_stock_id=created["id"]).count() == 0

    def test_creating_with_a_starting_quantity_logs_an_initial_adjustment(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        created = client.post(
            _url(business), json={"product": "Salt", "quantity_on_hand": "20"}, headers=_headers(owner)
        ).json()
        rows = db_session.query(StockAdjustment).filter_by(product_stock_id=created["id"]).all()
        assert len(rows) == 1
        assert rows[0].reason == "initial"
        assert rows[0].delta == Decimal("20")
        assert rows[0].resulting_quantity == Decimal("20")

    def test_duplicate_product_for_the_same_branch_is_rejected_case_insensitively(self, client, owner_and_business):
        owner, business = owner_and_business
        assert client.post(_url(business), json={"product": "Rice"}, headers=_headers(owner)).status_code == 201
        again = client.post(_url(business), json={"product": "  rice "}, headers=_headers(owner))
        assert again.status_code == 422
        assert again.json()["error"]["code"] == "already_tracked"

    def test_the_same_product_is_allowed_at_a_different_branch(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        assert client.post(_url(business), json={"product": "Rice"}, headers=_headers(owner)).status_code == 201
        response = client.post(
            _url(business), json={"product": "Rice", "branch_id": str(branch.id)}, headers=_headers(owner)
        )
        assert response.status_code == 201

    def test_a_branch_from_another_business_is_rejected(self, client, db_session, make_user, make_business, owner_and_business):
        owner, business = owner_and_business
        foreign = Branch(business_id=make_business(owner=make_user()).id, name="Elsewhere")
        db_session.add(foreign)
        db_session.commit()
        response = client.post(
            _url(business), json={"product": "Rice", "branch_id": str(foreign.id)}, headers=_headers(owner)
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_branch"

    @pytest.mark.parametrize(
        "bad", [{"product": "   "}, {"quantity_on_hand": "-1"}, {"reorder_level": "-1"}, {"product": "x" * 256}]
    )
    def test_invalid_values_are_rejected(self, client, db_session, owner_and_business, bad):
        owner, business = owner_and_business
        body = {"product": "Rice"}
        body.update(bad)
        assert client.post(_url(business), json=body, headers=_headers(owner)).status_code == 422
        assert db_session.query(ProductStock).filter_by(business_id=business.id).count() == 0


# ---------------------------------------------------------------------------
# List / filters
# ---------------------------------------------------------------------------
class TestList:
    def test_list_is_alphabetical_with_a_low_stock_count_over_the_whole_filtered_set(self, client, owner_and_business, make_stock):
        owner, business = owner_and_business
        make_stock(business, "Sugar", quantity="1", reorder="5")  # low
        make_stock(business, "Rice", quantity="50", reorder="5")  # not low
        make_stock(business, "Oil", quantity="0", reorder="0")  # reorder 0 -- never low
        body = client.get(_url(business), params={"page_size": 2}, headers=_headers(owner)).json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert [i["product"] for i in body["items"]] == ["Oil", "Rice"]  # alphabetical
        assert body["low_stock_count"] == 1  # counted over all 3, not just this page

    def test_low_stock_only_filter(self, client, owner_and_business, make_stock):
        owner, business = owner_and_business
        make_stock(business, "Sugar", quantity="1", reorder="5")
        make_stock(business, "Rice", quantity="50", reorder="5")
        body = client.get(_url(business), params={"low_stock_only": "true"}, headers=_headers(owner)).json()
        assert body["total"] == 1
        assert body["items"][0]["product"] == "Sugar"
        assert body["items"][0]["is_low"] is True

    def test_search_and_branch_filters(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        make_stock(business, "Rice")
        make_stock(business, "Cooking oil", branch=branch)

        def total(**params):
            return client.get(_url(business), params=params, headers=_headers(owner)).json()["total"]

        assert total(q="oil") == 1
        assert total(branch_id=str(branch.id)) == 1
        assert total(q="%") == 0  # literal percent sign, matches nothing here
        assert total() == 2

    def test_scoped_to_the_business(self, client, make_user, make_business, owner_and_business, make_stock):
        owner, business = owner_and_business
        make_stock(make_business(owner=make_user()), "Somebody else's product")
        assert client.get(_url(business), headers=_headers(owner)).json()["total"] == 0


# ---------------------------------------------------------------------------
# Update / delete
# ---------------------------------------------------------------------------
class TestUpdateDelete:
    def test_update_changes_only_reorder_level(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10", reorder="2")
        response = client.patch(_url(business, f"/{stock.id}"), json={"reorder_level": "5"}, headers=_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["reorder_level"]) == 5
        assert Decimal(body["quantity_on_hand"]) == 10  # untouched
        assert "stock.updated" in _audit_actions(db_session, business)

    def test_moving_to_a_branch_that_already_tracks_the_product_is_rejected(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        make_stock(business, "Rice", branch=branch)
        shared = make_stock(business, "Rice")  # same product, no branch
        response = client.patch(
            _url(business, f"/{shared.id}"), json={"branch_id": str(branch.id)}, headers=_headers(owner)
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "already_tracked"

    def test_moving_to_shared_by_sending_null(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        stock = make_stock(business, "Rice", branch=branch)
        response = client.patch(_url(business, f"/{stock.id}"), json={"branch_id": None}, headers=_headers(owner))
        assert response.status_code == 200
        assert response.json()["branch_id"] is None

    def test_delete_removes_the_record_and_its_history(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business)
        client.post(_url(business, f"/{stock.id}/adjustments"), json={"reason": "restock", "quantity": "5"}, headers=_headers(owner))
        response = client.delete(_url(business, f"/{stock.id}"), headers=_headers(owner))
        assert response.status_code == 204
        assert db_session.get(ProductStock, stock.id) is None
        assert db_session.query(StockAdjustment).filter_by(product_stock_id=stock.id).count() == 0
        assert "stock.deleted" in _audit_actions(db_session, business)

    def test_roles(self, client, owner_and_business, add_member, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business)
        viewer, member, admin = add_member(business, "viewer"), add_member(business, "member"), add_member(business, "admin")

        assert client.get(_url(business), headers=_headers(viewer)).status_code == 200
        assert client.post(_url(business), json={"product": "X"}, headers=_headers(viewer)).status_code == 404
        assert client.post(_url(business), json={"product": "X"}, headers=_headers(member)).status_code == 201
        assert client.patch(_url(business, f"/{stock.id}"), json={"reorder_level": "9"}, headers=_headers(member)).status_code == 200
        assert client.delete(_url(business, f"/{stock.id}"), headers=_headers(member)).status_code == 404
        assert client.delete(_url(business, f"/{stock.id}"), headers=_headers(admin)).status_code == 204


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------
class TestAdjustments:
    def test_restock_increases_quantity_and_is_audited(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, quantity="10")
        response = client.post(
            _url(business, f"/{stock.id}/adjustments"), json={"reason": "restock", "quantity": "5", "note": "Delivery"},
            headers=_headers(owner),
        )
        assert response.status_code == 201
        body = response.json()
        assert Decimal(body["stock"]["quantity_on_hand"]) == 15
        assert body["adjustment"]["delta"] == "5.000" or Decimal(body["adjustment"]["delta"]) == 5
        assert "stock.adjusted" in _audit_actions(db_session, business)

    def test_damage_decreases_quantity(self, client, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, quantity="10")
        body = client.post(
            _url(business, f"/{stock.id}/adjustments"), json={"reason": "damage", "quantity": "3"}, headers=_headers(owner)
        ).json()
        assert Decimal(body["stock"]["quantity_on_hand"]) == 7
        assert Decimal(body["adjustment"]["delta"]) == -3

    def test_correction_sets_the_absolute_quantity(self, client, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, quantity="10")
        body = client.post(
            _url(business, f"/{stock.id}/adjustments"), json={"reason": "correction", "quantity": "4"}, headers=_headers(owner)
        ).json()
        assert Decimal(body["stock"]["quantity_on_hand"]) == 4
        assert Decimal(body["adjustment"]["delta"]) == -6  # 4 - 10

    @pytest.mark.parametrize(
        "payload", [{"reason": "restock", "quantity": "0"}, {"reason": "damage", "quantity": "-1"}, {"reason": "correction", "quantity": "-1"}]
    )
    def test_invalid_adjustments_are_rejected(self, client, owner_and_business, make_stock, payload):
        owner, business = owner_and_business
        stock = make_stock(business, quantity="10")
        response = client.post(_url(business, f"/{stock.id}/adjustments"), json=payload, headers=_headers(owner))
        assert response.status_code == 422

    def test_history_is_newest_first_and_respects_limit(self, client, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, quantity="10")
        for i in range(3):
            client.post(
                _url(business, f"/{stock.id}/adjustments"), json={"reason": "restock", "quantity": str(i + 1)},
                headers=_headers(owner),
            )
        history = client.get(_url(business, f"/{stock.id}/adjustments"), params={"limit": 2}, headers=_headers(owner)).json()
        assert len(history) == 2
        assert [Decimal(h["delta"]) for h in history] == [Decimal(3), Decimal(2)]


# ---------------------------------------------------------------------------
# Business setting: auto_deduct_stock_on_sale
# ---------------------------------------------------------------------------
class TestBusinessSetting:
    def test_off_by_default(self, client, owner_and_business):
        owner, business = owner_and_business
        assert client.get(f"/businesses/{business.id}", headers=_headers(owner)).json()["auto_deduct_stock_on_sale"] is False

    def test_only_admin_can_change_it(self, client, owner_and_business, add_member):
        owner, business = owner_and_business
        member = add_member(business, "member")
        assert client.patch(f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": True}, headers=_headers(member)).status_code == 404
        assert client.patch(f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": True}, headers=_headers(owner)).status_code == 200

    def test_only_sent_fields_change_and_it_is_audited(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        response = client.patch(f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": True}, headers=_headers(owner))
        assert response.status_code == 200
        assert response.json()["name"] == business.name  # untouched
        assert "business.updated" in _audit_actions(db_session, business)


# ---------------------------------------------------------------------------
# Auto-deduction: manual transactions
# ---------------------------------------------------------------------------
class TestAutoDeductManual:
    def test_off_by_default_a_sale_does_not_touch_stock(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10")
        _create_transaction(client, owner, business, product="Rice", quantity="3")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 10

    def test_when_on_a_sale_deducts_the_matching_stock_record(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="rice", quantity="3")  # case-insensitive match

        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 7
        adjustment = db_session.query(StockAdjustment).filter_by(product_stock_id=stock.id, reason="sale").one()
        assert adjustment.delta == -3
        assert str(adjustment.related_transaction_id) == created["id"]

    def test_a_sale_of_an_untracked_product_does_nothing_and_creates_no_stock_record(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _enable_auto_deduct(client, owner, business)
        _create_transaction(client, owner, business, product="Untracked thing")
        assert db_session.query(ProductStock).filter_by(business_id=business.id).count() == 0

    def test_editing_the_quantity_reverses_and_rededucts(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="Rice", quantity="3")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 7

        response = client.patch(
            f"/businesses/{business.id}/transactions/{created['id']}", json={"quantity": "5"}, headers=_headers(owner)
        )
        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 5  # 10 - 5, not 7 - 5

        adjustments = (
            db_session.query(StockAdjustment)
            .filter_by(product_stock_id=stock.id)
            .order_by(StockAdjustment.created_at)
            .all()
        )
        assert [a.reason for a in adjustments] == ["sale", "sale_reversal", "sale"]

    def test_editing_the_quantity_twice_reverses_only_the_current_amount(self, client, db_session, owner_and_business, make_stock):
        """
        Regression test: a naive "find any sale adjustment for this
        transaction" reversal can pick a STALE row once a transaction has
        been edited more than once, under-restoring the stock. The fix
        must always reverse the most recent (current) deduction --
        ordering by StockAdjustment.seq (a database-generated, strictly-
        increasing sequence), not by created_at: two rows made within the
        SAME edit (a reversal immediately followed by a fresh deduction)
        land in the same database transaction, and Postgres's now()
        returns that transaction's start time for every statement in it,
        so both rows can get an identical created_at -- seq is what
        actually disambiguates them, both here and in the real app.
        """
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="30")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="Rice", quantity="5")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 25

        # First edit: 5 -> 10 (reverses -5, deducts -10; net so far -10).
        client.patch(f"/businesses/{business.id}/transactions/{created['id']}", json={"quantity": "10"}, headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 20

        # Second edit: 10 -> 3. Must reverse the -10 (not the stale -5),
        # then deduct -3, landing on 30 - 3 = 27.
        client.patch(f"/businesses/{business.id}/transactions/{created['id']}", json={"quantity": "3"}, headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 27

        # Deleting it afterward must restore the full 30, not a partial amount.
        client.delete(f"/businesses/{business.id}/transactions/{created['id']}", headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 30

    def test_an_edit_while_off_does_not_get_double_reversed_by_a_later_edit(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="30")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="Rice", quantity="5")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 25

        # Turn auto-deduct off, then edit -- reverses the -5 but does not re-deduct.
        client.patch(f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": False}, headers=_headers(owner))
        client.patch(f"/businesses/{business.id}/transactions/{created['id']}", json={"quantity": "8"}, headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 30

        # Turn back on and edit again -- must NOT re-reverse the already-
        # reversed sale; should simply deduct the new quantity fresh.
        client.patch(f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": True}, headers=_headers(owner))
        client.patch(f"/businesses/{business.id}/transactions/{created['id']}", json={"quantity": "6"}, headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 24

    def test_editing_an_unrelated_field_does_not_touch_stock(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="Rice", quantity="3")
        client.patch(
            f"/businesses/{business.id}/transactions/{created['id']}", json={"customer": "Ada"}, headers=_headers(owner)
        )
        adjustments = db_session.query(StockAdjustment).filter_by(product_stock_id=stock.id).all()
        assert len(adjustments) == 1  # only the original sale -- no reversal, no re-deduction

    def test_deleting_the_transaction_restores_the_stock(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="Rice", quantity="3")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 7

        response = client.delete(f"/businesses/{business.id}/transactions/{created['id']}", headers=_headers(owner))
        assert response.status_code == 204
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 10

    def test_turning_the_setting_off_still_reverses_an_already_deducted_sale(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="10")
        _enable_auto_deduct(client, owner, business)
        created = _create_transaction(client, owner, business, product="Rice", quantity="3")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 7

        client.patch(f"/businesses/{business.id}", json={"auto_deduct_stock_on_sale": False}, headers=_headers(owner))
        client.delete(f"/businesses/{business.id}/transactions/{created['id']}", headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 10  # restored despite the toggle now being off

    def test_branch_specific_stock_is_preferred_over_shared(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        shared = make_stock(business, "Rice", quantity="100")
        branch_stock = make_stock(business, "Rice", quantity="20", branch=branch)
        _enable_auto_deduct(client, owner, business)

        _create_transaction(client, owner, business, product="Rice", quantity="5", branch_id=str(branch.id))
        db_session.expire_all()
        assert db_session.get(ProductStock, branch_stock.id).quantity_on_hand == 15
        assert db_session.get(ProductStock, shared.id).quantity_on_hand == 100  # untouched

    def test_a_sale_with_no_branch_only_matches_the_shared_record(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        branch_stock = make_stock(business, "Rice", quantity="20", branch=branch)
        _enable_auto_deduct(client, owner, business)
        _create_transaction(client, owner, business, product="Rice", quantity="5")  # no branch_id
        db_session.expire_all()
        assert db_session.get(ProductStock, branch_stock.id).quantity_on_hand == 20  # untouched -- no shared record exists

    def test_deduction_is_allowed_to_go_negative(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="2")
        _enable_auto_deduct(client, owner, business)
        _create_transaction(client, owner, business, product="Rice", quantity="5")
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == -3


# ---------------------------------------------------------------------------
# Auto-deduction: bulk import
# ---------------------------------------------------------------------------
_MAPPING = {"date": "Date", "product": "Product", "quantity": "Qty", "selling_price": "Price"}


def _run_import(db_session, business, rows) -> dict:
    session = ImportSession(
        business_id=business.id, filename="sales.csv", source="file", status="mapped",
        detected_columns=["Date", "Product", "Qty", "Price"], raw_rows=rows,
        suggested_mapping=_MAPPING, total_row_count=len(rows),
    )
    db_session.add(session)
    db_session.commit()
    return execute_confirmed_import(db_session, str(session.id), _MAPPING)


class TestAutoDeductBulkImport:
    def test_import_deducts_matching_stock_in_one_pass(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        rice = make_stock(business, "Sugar", quantity="100")
        _enable_auto_deduct(client, owner, business)
        rows = [
            {"Date": "2026-09-01", "Product": "Sugar", "Qty": "2", "Price": "1500"},
            {"Date": "2026-09-02", "Product": "Sugar", "Qty": "3", "Price": "1500"},
            {"Date": "2026-09-03", "Product": "Untracked", "Qty": "1", "Price": "500"},
        ]
        result = _run_import(db_session, business, rows)
        assert result["imported_row_count"] == 3
        db_session.expire_all()
        assert db_session.get(ProductStock, rice.id).quantity_on_hand == 95  # 100 - 2 - 3

    def test_import_respects_the_off_setting(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Sugar", quantity="100")
        rows = [{"Date": "2026-09-01", "Product": "Sugar", "Qty": "2", "Price": "1500"}]
        _run_import(db_session, business, rows)
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 100

    def test_deleting_an_imported_transaction_reverses_its_deduction(self, client, db_session, owner_and_business, make_stock):
        owner, business = owner_and_business
        stock = make_stock(business, "Sugar", quantity="100")
        _enable_auto_deduct(client, owner, business)
        rows = [{"Date": "2026-09-01", "Product": "Sugar", "Qty": "2", "Price": "1500"}]
        _run_import(db_session, business, rows)
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 98

        sugar_txn = db_session.query(Transaction).filter_by(business_id=business.id, product="Sugar").one()
        client.delete(f"/businesses/{business.id}/transactions/{sugar_txn.id}", headers=_headers(owner))
        db_session.expire_all()
        assert db_session.get(ProductStock, stock.id).quantity_on_hand == 100


# ---------------------------------------------------------------------------
# Service-level unit checks (small pieces not already covered end-to-end above)
# ---------------------------------------------------------------------------
class TestServiceHelpers:
    def test_find_stock_record_matches_case_insensitively(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        stock = make_stock(business, "Rice")
        assert find_stock_record(db_session, business.id, "RICE", None).id == stock.id
        assert find_stock_record(db_session, business.id, "Beans", None) is None

    def test_find_stock_for_sale_falls_back_to_shared(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        shared = make_stock(business, "Rice")
        assert find_stock_for_sale(db_session, business.id, "Rice", branch.id).id == shared.id

    def test_reversing_when_nothing_to_reverse_is_a_no_op(self, db_session, owner_and_business):
        import uuid

        reverse_linked_sale_adjustment(db_session, uuid.uuid4())  # should not raise
        db_session.commit()

    def test_apply_manual_adjustment_rejects_unknown_reason(self, db_session, owner_and_business, make_stock):
        from app.core.exceptions import ValidationError

        _, business = owner_and_business
        stock = make_stock(business)
        with pytest.raises(ValidationError):
            apply_manual_adjustment(db_session, stock, reason="bogus", quantity=Decimal(1), note=None, user_id=None)


# ---------------------------------------------------------------------------
# Alert detector: stock_shortage
# ---------------------------------------------------------------------------
class TestStockShortageDetector:
    def test_nothing_low_gives_no_candidates(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        make_stock(business, "Rice", quantity="50", reorder="5")
        assert detect_stock_shortage(db_session, business, today=TODAY) == []

    def test_reorder_level_zero_is_never_flagged(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        make_stock(business, "Rice", quantity="0", reorder="0")
        assert detect_stock_shortage(db_session, business, today=TODAY) == []

    @pytest.mark.parametrize(
        "quantity, reorder, expected_severity",
        [("-1", "10", "CRITICAL"), ("0", "10", "CRITICAL"), ("2", "10", "HIGH"), ("2.5", "10", "HIGH"),
         ("4", "10", "MEDIUM"), ("5", "10", "MEDIUM"), ("9", "10", "LOW"), ("10", "10", "LOW")],
    )
    def test_severity_bands(self, db_session, owner_and_business, make_stock, quantity, reorder, expected_severity):
        _, business = owner_and_business
        make_stock(business, "Rice", quantity=quantity, reorder=reorder)
        candidates = detect_stock_shortage(db_session, business, today=TODAY)
        assert len(candidates) == 1
        assert candidates[0].severity == expected_severity
        assert candidates[0].affected_product == "Rice"

    def test_dedupe_key_includes_a_week_bucket_and_the_record_id(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        stock = make_stock(business, "Rice", quantity="1", reorder="10")
        candidates = detect_stock_shortage(db_session, business, today=TODAY)
        assert candidates[0].dedupe_key == f"stock_shortage:{stock.id}:{TODAY.strftime('%G-W%V')}"

    def test_a_branch_name_is_included_when_the_record_has_one(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        make_stock(business, "Rice", quantity="1", reorder="10", branch=branch)
        candidates = detect_stock_shortage(db_session, business, today=TODAY)
        assert "Ibadan" in candidates[0].title

    def test_multiple_low_records_each_get_their_own_candidate(self, db_session, owner_and_business, make_stock):
        _, business = owner_and_business
        make_stock(business, "Rice", quantity="1", reorder="10")
        make_stock(business, "Beans", quantity="2", reorder="20")
        assert len(detect_stock_shortage(db_session, business, today=TODAY)) == 2

    def test_scoped_to_the_business(self, db_session, make_user, make_business, owner_and_business, make_stock):
        _, business = owner_and_business
        other = make_business(owner=make_user())
        make_stock(other, "Rice", quantity="0", reorder="10")
        assert detect_stock_shortage(db_session, business, today=TODAY) == []
