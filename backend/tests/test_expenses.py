"""
Operating expenses (Step 13, Batch 2): CRUD, roles, filters, the category
summary, and how expenses feed net profit in the analytics summary and the
AI assistant's tools.

Real HTTP requests against real Postgres, like the other route tests.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ValidationError
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.expense import Expense
from app.models.team_member import TeamMember
from app.services import ai_assistant, ai_tools
from app.services.user import export_account_data

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


@pytest.fixture()
def make_expense(db_session):
    def _make(business, category="Rent", amount="1000.00", on=None, description=None, branch=None) -> Expense:
        expense = Expense(
            business_id=business.id, category=category, amount=Decimal(amount),
            date=on or TODAY, description=description, branch_id=branch.id if branch else None,
        )
        db_session.add(expense)
        db_session.commit()
        db_session.refresh(expense)
        return expense

    return _make


def _url(business, suffix="") -> str:
    return f"/businesses/{business.id}/expenses{suffix}"


def _payload(**overrides) -> dict:
    body = {"date": TODAY.isoformat(), "category": "Rent", "amount": "150000", "description": "Shop rent, September"}
    body.update(overrides)
    return body


def _audit_actions(db_session, business) -> list[str]:
    return [a.action for a in db_session.query(AuditLog).filter(AuditLog.business_id == business.id)]


# ---------------------------------------------------------------------------
# Create / update / delete
# ---------------------------------------------------------------------------
class TestWrite:
    def test_create(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        response = client.post(_url(business), json=_payload(), headers=_headers(owner))
        assert response.status_code == 201
        body = response.json()
        assert body["category"] == "Rent"
        assert Decimal(body["amount"]) == 150000
        assert body["description"] == "Shop rent, September"
        assert db_session.get(Expense, body["id"]).business_id == business.id
        assert "expense.created" in _audit_actions(db_session, business)

    def test_description_and_branch_are_optional_and_blank_text_is_dropped(self, client, owner_and_business):
        owner, business = owner_and_business
        response = client.post(
            _url(business), json={"date": TODAY.isoformat(), "category": "  Transport  ", "amount": "2500", "description": "  "},
            headers=_headers(owner),
        )
        assert response.status_code == 201
        assert response.json()["category"] == "Transport"
        assert response.json()["description"] is None

    @pytest.mark.parametrize(
        "bad",
        [
            {"amount": "0"},
            {"amount": "-100"},
            {"category": "   "},
            {"category": "x" * 101},
            {"date": (TODAY + timedelta(days=30)).isoformat()},
            {"date": "1999-01-01"},
            {"amount": "1" * 20},
            {"description": "x" * 256},
        ],
    )
    def test_invalid_values_are_rejected(self, client, db_session, owner_and_business, bad):
        owner, business = owner_and_business
        assert client.post(_url(business), json=_payload(**bad), headers=_headers(owner)).status_code == 422
        assert db_session.query(Expense).filter_by(business_id=business.id).count() == 0

    def test_a_branch_from_another_business_is_rejected(self, client, db_session, make_user, make_business, owner_and_business):
        owner, business = owner_and_business
        foreign = Branch(business_id=make_business(owner=make_user()).id, name="Elsewhere")
        db_session.add(foreign)
        db_session.commit()
        response = client.post(_url(business), json=_payload(branch_id=str(foreign.id)), headers=_headers(owner))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_branch"

    def test_update_changes_only_what_was_sent(self, client, db_session, owner_and_business, make_expense):
        owner, business = owner_and_business
        expense = make_expense(business, description="old note")
        response = client.patch(
            _url(business, f"/{expense.id}"), json={"amount": "2000", "description": None}, headers=_headers(owner)
        )
        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["amount"]) == 2000
        assert body["description"] is None  # cleared
        assert body["category"] == "Rent"  # untouched
        assert "expense.updated" in _audit_actions(db_session, business)

    @pytest.mark.parametrize("field", ["date", "category", "amount"])
    def test_required_fields_cannot_be_cleared(self, client, owner_and_business, make_expense, field):
        owner, business = owner_and_business
        expense = make_expense(business)
        assert client.patch(_url(business, f"/{expense.id}"), json={field: None}, headers=_headers(owner)).status_code == 422

    def test_delete(self, client, db_session, owner_and_business, make_expense):
        owner, business = owner_and_business
        expense = make_expense(business)
        assert client.delete(_url(business, f"/{expense.id}"), headers=_headers(owner)).status_code == 204
        assert db_session.get(Expense, expense.id) is None
        assert "expense.deleted" in _audit_actions(db_session, business)
        assert client.delete(_url(business, f"/{expense.id}"), headers=_headers(owner)).status_code == 404

    def test_another_business_expense_is_not_found(self, client, make_user, make_business, owner_and_business, make_expense):
        owner, business = owner_and_business
        theirs = make_expense(make_business(owner=make_user()))
        assert client.patch(_url(business, f"/{theirs.id}"), json={"amount": "5"}, headers=_headers(owner)).status_code == 404
        assert client.delete(_url(business, f"/{theirs.id}"), headers=_headers(owner)).status_code == 404

    def test_roles(self, client, owner_and_business, add_member, make_expense):
        owner, business = owner_and_business
        expense = make_expense(business)
        viewer = add_member(business, "viewer")
        member = add_member(business, "member")
        admin = add_member(business, "admin")

        # Viewers can read but not write.
        assert client.get(_url(business), headers=_headers(viewer)).status_code == 200
        assert client.post(_url(business), json=_payload(), headers=_headers(viewer)).status_code == 404
        # Members can add and edit, but not delete.
        assert client.post(_url(business), json=_payload(), headers=_headers(member)).status_code == 201
        assert client.patch(_url(business, f"/{expense.id}"), json={"amount": "9"}, headers=_headers(member)).status_code == 200
        assert client.delete(_url(business, f"/{expense.id}"), headers=_headers(member)).status_code == 404
        # Admins can delete.
        assert client.delete(_url(business, f"/{expense.id}"), headers=_headers(admin)).status_code == 204


# ---------------------------------------------------------------------------
# List, filters, summary, categories
# ---------------------------------------------------------------------------
class TestReading:
    def test_list_is_newest_first_with_a_total_over_the_whole_filtered_set(self, client, owner_and_business, make_expense):
        owner, business = owner_and_business
        for i in range(5):
            make_expense(business, amount="100.00", on=TODAY - timedelta(days=i))
        body = client.get(_url(business), params={"page_size": 2}, headers=_headers(owner)).json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert Decimal(body["total_amount"]) == 500  # all five, not just this page
        dates = [item["date"] for item in body["items"]]
        assert dates == sorted(dates, reverse=True)

    def test_filters(self, client, db_session, owner_and_business, make_expense):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        make_expense(business, "Rent", "5000", on=TODAY - timedelta(days=40))
        make_expense(business, "rent", "6000", on=TODAY - timedelta(days=2))
        make_expense(business, "Transport", "700", on=TODAY - timedelta(days=1), description="Fuel for 100% delivery run", branch=branch)

        def total(**params):
            return client.get(_url(business), params=params, headers=_headers(owner)).json()

        assert total()["total"] == 3
        assert total(category="RENT")["total"] == 2  # case-insensitive
        assert total(start_date=(TODAY - timedelta(days=10)).isoformat())["total"] == 2
        assert total(end_date=(TODAY - timedelta(days=10)).isoformat())["total"] == 1
        assert total(branch_id=str(branch.id))["total"] == 1
        assert total(q="fuel")["total"] == 1
        # A search for "%" must match a literal percent sign, not everything.
        assert total(q="%")["total"] == 1
        assert total(q="_")["total"] == 0

    def test_a_reversed_date_range_is_rejected(self, client, owner_and_business):
        owner, business = owner_and_business
        response = client.get(
            _url(business), params={"start_date": TODAY.isoformat(), "end_date": (TODAY - timedelta(days=3)).isoformat()},
            headers=_headers(owner),
        )
        assert response.status_code == 422

    def test_summary_groups_categories_case_insensitively_and_orders_by_size(self, client, owner_and_business, make_expense):
        owner, business = owner_and_business
        make_expense(business, "Rent", "6000")
        make_expense(business, "rent", "2000")
        make_expense(business, "Transport", "2000")
        body = client.get(_url(business, "/summary"), headers=_headers(owner)).json()
        assert Decimal(body["total"]) == 10000
        assert body["count"] == 3
        assert [c["category"].lower() for c in body["by_category"]] == ["rent", "transport"]
        rent, transport = body["by_category"]
        assert Decimal(rent["total"]) == 8000 and rent["count"] == 2
        assert Decimal(rent["share_percent"]) == Decimal("80.0")
        assert Decimal(transport["share_percent"]) == Decimal("20.0")

    def test_summary_with_no_expenses(self, client, owner_and_business):
        owner, business = owner_and_business
        body = client.get(_url(business, "/summary"), headers=_headers(owner)).json()
        assert Decimal(body["total"]) == 0
        assert body["count"] == 0
        assert body["by_category"] == []

    def test_categories_lists_used_first_then_unused_defaults(self, client, owner_and_business, make_expense):
        owner, business = owner_and_business
        make_expense(business, "Generator diesel", on=TODAY)
        make_expense(business, "rent", on=TODAY - timedelta(days=5))
        categories = client.get(_url(business, "/categories"), headers=_headers(owner)).json()
        assert categories[:2] == ["Generator diesel", "rent"]
        assert "Rent" not in categories  # already used, in its own spelling
        assert "Salaries & wages" in categories  # a default it hasn't used yet
        assert len({c.lower() for c in categories}) == len(categories)

    def test_reading_is_scoped_to_the_business(self, client, make_user, make_business, owner_and_business, make_expense):
        owner, business = owner_and_business
        other = make_business(owner=make_user())
        make_expense(other, amount="99999")
        assert client.get(_url(business), headers=_headers(owner)).json()["total"] == 0
        # ...and someone who isn't on the business can't read it at all.
        assert client.get(_url(other), headers=_headers(owner)).status_code == 404


# ---------------------------------------------------------------------------
# Net profit: analytics summary and the AI assistant's tools
# ---------------------------------------------------------------------------
class TestNetProfit:
    def _summary(self, client, owner, business, **extra) -> dict:
        params = {"range": "custom", "start_date": (TODAY - timedelta(days=30)).isoformat(), "end_date": TODAY.isoformat()}
        params.update(extra)
        response = client.get(f"/businesses/{business.id}/analytics/summary", params=params, headers=_headers(owner))
        assert response.status_code == 200
        return response.json()

    def test_summary_subtracts_expenses_from_gross_profit(self, client, owner_and_business, make_transaction, make_expense):
        owner, business = owner_and_business
        make_transaction(business, quantity="10", selling_price="1000", cost_price="600")  # revenue 10000, cost 6000
        make_expense(business, "Rent", "1500")
        make_expense(business, "Salaries & wages", "500")
        body = self._summary(client, owner, business)
        assert Decimal(body["gross_profit"]) == 4000  # unchanged meaning
        assert Decimal(body["operating_expenses"]) == 2000
        assert body["expense_count"] == 2
        assert Decimal(body["net_profit"]) == 2000
        assert Decimal(body["net_profit_margin"]) == 20

    def test_without_expenses_net_profit_equals_gross_profit(self, client, owner_and_business, make_transaction):
        owner, business = owner_and_business
        make_transaction(business, quantity="10", selling_price="1000", cost_price="600")
        body = self._summary(client, owner, business)
        assert Decimal(body["operating_expenses"]) == 0
        assert body["expense_count"] == 0
        assert Decimal(body["net_profit"]) == Decimal(body["gross_profit"]) == 4000

    def test_only_expenses_inside_the_window_count(self, client, owner_and_business, make_transaction, make_expense):
        owner, business = owner_and_business
        make_transaction(business, quantity="1", selling_price="1000", cost_price="0")
        make_expense(business, amount="100", on=TODAY - timedelta(days=5))
        make_expense(business, amount="9999", on=TODAY - timedelta(days=90))
        assert Decimal(self._summary(client, owner, business)["operating_expenses"]) == 100

    def test_a_branch_view_excludes_shared_overhead(self, client, db_session, owner_and_business, make_expense):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()
        make_expense(business, "Rent", "300")  # shared overhead, no branch
        make_expense(business, "Transport", "50", branch=branch)
        assert Decimal(self._summary(client, owner, business)["operating_expenses"]) == 350
        assert Decimal(self._summary(client, owner, business, branch_id=str(branch.id))["operating_expenses"]) == 50

    def test_ai_get_profit_includes_net_profit_and_flags_missing_expenses(self, db_session, owner_and_business, make_transaction, make_expense):
        _, business = owner_and_business
        make_transaction(business, quantity="10", selling_price="1000", cost_price="600")
        start, end = TODAY - timedelta(days=30), TODAY

        without = ai_tools.get_profit(db_session, business, start, end)
        assert without["net_profit"] == without["gross_profit"] == 4000
        assert without["has_expense_data"] is False
        assert "expense_note" in without

        make_expense(business, amount="1000")
        with_expenses = ai_tools.get_profit(db_session, business, start, end)
        assert with_expenses["operating_expenses"] == 1000
        assert with_expenses["net_profit"] == 3000
        assert with_expenses["has_expense_data"] is True
        assert "expense_note" not in with_expenses

    def test_ai_get_operating_expenses(self, db_session, owner_and_business, make_expense):
        _, business = owner_and_business
        start, end = TODAY - timedelta(days=30), TODAY

        empty = ai_tools.get_operating_expenses(db_session, business, start, end)
        assert empty["has_data"] is False and empty["total_operating_expenses"] == 0 and "note" in empty

        make_expense(business, "Rent", "7500")
        make_expense(business, "Transport", "2500")
        result = ai_tools.get_operating_expenses(db_session, business, start, end)
        assert result["has_data"] is True
        assert result["total_operating_expenses"] == 10000
        assert [c["category"] for c in result["categories"]] == ["Rent", "Transport"]
        assert result["categories"][0]["share_percent"] == 75.0

        with pytest.raises(ValidationError):
            ai_tools.get_operating_expenses(db_session, business, end, start)

    def test_ai_cost_of_goods_tool_is_unaffected_by_expenses(self, db_session, owner_and_business, make_transaction, make_expense):
        _, business = owner_and_business
        make_transaction(business, quantity="10", selling_price="1000", cost_price="600")
        make_expense(business, amount="5000")
        assert ai_tools.get_expenses(db_session, business, TODAY - timedelta(days=30), TODAY)["total_cost"] == 6000

    def test_every_assistant_tool_has_a_handler_and_the_new_tool_is_registered(self):
        declared = {t["function"]["name"] for t in ai_assistant.TOOLS}
        assert declared == set(ai_assistant.TOOL_HANDLERS)
        assert "get_operating_expenses" in declared

    def test_the_new_tool_runs_through_the_assistant_dispatcher(self, db_session, owner_and_business, make_expense):
        _, business = owner_and_business
        make_expense(business, "Rent", "1234")
        result = ai_assistant._execute_tool(
            db_session, business, "get_operating_expenses",
            f'{{"start_date": "{(TODAY - timedelta(days=30)).isoformat()}", "end_date": "{TODAY.isoformat()}"}}',
        )
        assert result["total_operating_expenses"] == 1234


# ---------------------------------------------------------------------------
# Account data export
# ---------------------------------------------------------------------------
def test_account_export_reports_the_expense_count(db_session, owner_and_business, make_expense):
    owner, business = owner_and_business
    make_expense(business)
    make_expense(business, "Transport")
    exported = export_account_data(db_session, owner)
    assert exported["businesses_you_own"][0]["expense_count"] == 2
