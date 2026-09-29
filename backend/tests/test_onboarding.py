"""
Onboarding (Step 13, Batch 4): the getting-started checklist, the sample
data load/remove actions, and the downloadable import templates.

Real HTTP requests against real Postgres, like the other route tests.
"""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.background_job import BackgroundJob
from app.models.expense import Expense
from app.models.product_stock import ProductStock
from app.models.stock_adjustment import StockAdjustment
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.services.billing import check_max_transactions_this_month
from app.services.import_pipeline import (
    EXPENSE_FIELD_SYNONYMS,
    EXPENSE_STANDARD_FIELDS,
    STANDARD_FIELDS,
    build_import_template,
    parse_upload,
    suggest_mapping,
)
from app.services.jobs import JOB_HANDLERS
from app.services.sample_data import SAMPLE_PRODUCT_NAMES

TODAY = date.today()


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    import app.api.routes.imports as imports_route

    def _run_job_sync(job_id):
        job = db_session.get(BackgroundJob, job_id)
        job.status = "running"
        db_session.commit()
        result = JOB_HANDLERS[job.job_type](db_session, job)
        job.status = "completed"
        job.result = result
        db_session.commit()

    monkeypatch.setattr(imports_route, "run_job_async", _run_job_sync)
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
            TeamMember(business_id=business.id, user_id=user.id, invited_email=user.email, role=role, status="active")
        )
        db_session.commit()
        return user

    return _add


def _url(business, suffix) -> str:
    return f"/businesses/{business.id}{suffix}"


def _load(client, owner, business):
    return client.post(_url(business, "/sample-data"), headers=_headers(owner))


def _count(db_session, model, business, sample=None) -> int:
    query = db_session.query(model).filter(model.business_id == business.id)
    if sample is not None:
        query = query.filter(model.is_sample.is_(sample))
    return query.count()


# ---------------------------------------------------------------------------
# Sample data: loading
# ---------------------------------------------------------------------------
class TestLoadSampleData:
    def test_loads_sales_expenses_and_stock_all_flagged_as_sample(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        response = _load(client, owner, business)
        assert response.status_code == 201
        body = response.json()
        assert body["transactions"] > 100
        assert body["expenses"] > 10
        assert body["stock_records"] == len(SAMPLE_PRODUCT_NAMES)

        assert _count(db_session, Transaction, business, sample=True) == body["transactions"]
        assert _count(db_session, Expense, business, sample=True) == body["expenses"]
        assert _count(db_session, ProductStock, business, sample=True) == body["stock_records"]
        # ...and nothing was inserted unflagged.
        assert _count(db_session, Transaction, business, sample=False) == 0
        assert _count(db_session, Expense, business, sample=False) == 0
        assert _count(db_session, ProductStock, business, sample=False) == 0

    def test_dates_are_recent_and_never_in_the_future(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        dates = [d for (d,) in db_session.query(Transaction.date).filter_by(business_id=business.id)]
        assert max(dates) == TODAY
        assert min(dates) >= TODAY - timedelta(days=60)
        expense_dates = [d for (d,) in db_session.query(Expense.date).filter_by(business_id=business.id)]
        assert max(expense_dates) <= TODAY

    def test_the_sample_set_is_deterministic(self, client, db_session, make_user, make_business):
        def shape(business, owner):
            _load(client, owner, business)
            rows = db_session.query(Transaction).filter_by(business_id=business.id).order_by(
                Transaction.date, Transaction.product, Transaction.quantity
            )
            return [(r.date, r.product, r.quantity) for r in rows]

        owner_a, owner_b = make_user(), make_user()
        assert shape(make_business(owner=owner_a), owner_a) == shape(make_business(owner=owner_b), owner_b)

    def test_stock_includes_a_low_and_an_out_of_stock_product_to_show_alerts(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        low = db_session.query(ProductStock).filter(
            ProductStock.business_id == business.id,
            ProductStock.reorder_level > 0,
            ProductStock.quantity_on_hand <= ProductStock.reorder_level,
        )
        assert low.count() == 2
        assert any(s.quantity_on_hand == 0 for s in low)

    def test_opening_quantities_are_logged_as_stock_history(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        rice = db_session.query(ProductStock).filter_by(business_id=business.id, product="Rice (50kg bag)").one()
        history = db_session.query(StockAdjustment).filter_by(product_stock_id=rice.id).all()
        assert [h.reason for h in history] == ["initial"]
        assert history[0].resulting_quantity == rice.quantity_on_hand

    def test_loading_twice_is_refused(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        assert _load(client, owner, business).status_code == 201
        before = _count(db_session, Transaction, business)
        again = _load(client, owner, business)
        assert again.status_code == 422
        assert again.json()["error"]["code"] == "sample_data_already_loaded"
        assert _count(db_session, Transaction, business) == before

    def test_it_never_uses_up_the_monthly_plan_limit(self, client, db_session, make_plan, make_business, make_user):
        owner = make_user()
        business = make_business(owner=owner, plan=make_plan(max_transactions_per_month=5))
        assert _load(client, owner, business).status_code == 201  # ~200 rows despite a limit of 5
        check_max_transactions_this_month(db_session, business)  # must not raise: sample rows don't count

    def test_real_rows_still_count_toward_the_limit_alongside_sample_rows(self, client, db_session, make_plan, make_business, make_user, make_transaction):
        from app.core.exceptions import ValidationError

        owner = make_user()
        business = make_business(owner=owner, plan=make_plan(max_transactions_per_month=2))
        _load(client, owner, business)
        make_transaction(business)
        make_transaction(business)
        with pytest.raises(ValidationError):
            check_max_transactions_this_month(db_session, business)

    def test_an_existing_product_with_a_sample_name_is_left_alone(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        mine = ProductStock(business_id=business.id, product="rice (50KG bag)", quantity_on_hand=Decimal("3"), reorder_level=Decimal("1"))
        db_session.add(mine)
        db_session.commit()
        body = _load(client, owner, business).json()
        assert body["stock_records"] == len(SAMPLE_PRODUCT_NAMES) - 1
        db_session.refresh(mine)
        assert mine.quantity_on_hand == 3 and mine.is_sample is False

    def test_the_load_is_audited(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        actions = [a.action for a in db_session.query(AuditLog).filter_by(business_id=business.id)]
        assert "sample_data.loaded" in actions

    def test_sample_data_feeds_the_real_analytics(self, client, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        summary = client.get(_url(business, "/analytics/summary"), headers=_headers(owner)).json()
        assert Decimal(summary["revenue"]) > 0
        assert Decimal(summary["operating_expenses"]) > 0
        assert Decimal(summary["net_profit"]) > 0  # a demo that shows a loss would be a bad demo


# ---------------------------------------------------------------------------
# Sample data: removing
# ---------------------------------------------------------------------------
class TestRemoveSampleData:
    def test_removes_only_sample_rows_and_leaves_real_data(self, client, db_session, owner_and_business, make_transaction):
        owner, business = owner_and_business
        make_transaction(business, product="My own product")
        db_session.add(Expense(business_id=business.id, date=TODAY, category="Rent", amount=Decimal("1000")))
        db_session.add(ProductStock(business_id=business.id, product="My own stock", quantity_on_hand=Decimal("4")))
        db_session.commit()
        loaded = _load(client, owner, business).json()

        response = client.delete(_url(business, "/sample-data"), headers=_headers(owner))
        assert response.status_code == 200
        removed = response.json()
        assert removed["transactions"] == loaded["transactions"]
        assert removed["expenses"] == loaded["expenses"]
        assert removed["stock_records"] == loaded["stock_records"]

        assert _count(db_session, Transaction, business) == 1
        assert _count(db_session, Expense, business) == 1
        assert _count(db_session, ProductStock, business) == 1
        assert db_session.query(Transaction).filter_by(business_id=business.id).one().product == "My own product"

    def test_removing_sample_stock_removes_its_history_too(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        client.delete(_url(business, "/sample-data"), headers=_headers(owner))
        assert db_session.query(StockAdjustment).filter_by(business_id=business.id).count() == 0

    def test_removing_when_nothing_is_loaded_is_a_harmless_no_op(self, client, owner_and_business):
        owner, business = owner_and_business
        response = client.delete(_url(business, "/sample-data"), headers=_headers(owner))
        assert response.status_code == 200
        assert response.json() == {"transactions": 0, "expenses": 0, "stock_records": 0, "alerts": 0}

    def test_it_can_be_loaded_again_after_removal(self, client, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        client.delete(_url(business, "/sample-data"), headers=_headers(owner))
        assert _load(client, owner, business).status_code == 201

    def test_all_alerts_go_when_no_real_transactions_remain(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        client.post(_url(business, "/alerts/run"), headers=_headers(owner))
        assert db_session.query(Alert).filter_by(business_id=business.id).count() > 0  # the low-stock alerts
        removed = client.delete(_url(business, "/sample-data"), headers=_headers(owner)).json()
        assert removed["alerts"] > 0
        assert db_session.query(Alert).filter_by(business_id=business.id).count() == 0

    def test_a_real_product_sharing_a_sample_name_keeps_its_alerts(self, client, db_session, owner_and_business, make_transaction):
        owner, business = owner_and_business
        make_transaction(business, product="Sugar (1kg)")  # a real product with a sample product's name
        _load(client, owner, business)
        db_session.add(
            Alert(
                business_id=business.id, alert_type="unusual_sales", severity="LOW", title="t", message="m",
                affected_product="Sugar (1kg)", period_start=TODAY, period_end=TODAY, dedupe_key="k1",
                supporting_values={},
            )
        )
        db_session.add(
            Alert(
                business_id=business.id, alert_type="unusual_sales", severity="LOW", title="t2", message="m2",
                affected_product="Garri (25kg bag)", period_start=TODAY, period_end=TODAY, dedupe_key="k2",
                supporting_values={},
            )
        )
        db_session.commit()
        client.delete(_url(business, "/sample-data"), headers=_headers(owner))
        remaining = {a.affected_product for a in db_session.query(Alert).filter_by(business_id=business.id)}
        assert remaining == {"Sugar (1kg)"}  # Garri was sample-only, Sugar is also a real product

    def test_the_removal_is_audited(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        client.delete(_url(business, "/sample-data"), headers=_headers(owner))
        actions = [a.action for a in db_session.query(AuditLog).filter_by(business_id=business.id)]
        assert "sample_data.removed" in actions


class TestSampleDataRoles:
    def test_only_an_admin_can_load_or_remove(self, client, owner_and_business, add_member):
        owner, business = owner_and_business
        viewer, member, admin = add_member(business, "viewer"), add_member(business, "member"), add_member(business, "admin")
        for user in (viewer, member):
            assert _load(client, user, business).status_code == 404
            assert client.delete(_url(business, "/sample-data"), headers=_headers(user)).status_code == 404
        assert _load(client, admin, business).status_code == 201
        assert client.delete(_url(business, "/sample-data"), headers=_headers(admin)).status_code == 200

    def test_another_business_cannot_be_touched(self, client, make_user, make_business, owner_and_business):
        owner, business = owner_and_business
        other = make_business(owner=make_user())
        assert _load(client, owner, other).status_code == 404


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------
class TestChecklist:
    def _status(self, client, user, business) -> dict:
        response = client.get(_url(business, "/onboarding"), headers=_headers(user))
        assert response.status_code == 200
        return response.json()

    def test_a_new_business_has_nothing_done(self, client, owner_and_business):
        owner, business = owner_and_business
        assert self._status(client, owner, business) == {
            "add_sales": False, "record_expense": False, "track_stock": False,
            "invite_team": False, "has_sample_data": False,
        }

    def test_each_step_completes_from_the_businesss_own_data(self, client, db_session, owner_and_business, make_transaction, add_member):
        owner, business = owner_and_business
        make_transaction(business)
        assert self._status(client, owner, business)["add_sales"] is True

        db_session.add(Expense(business_id=business.id, date=TODAY, category="Rent", amount=Decimal("1")))
        db_session.commit()
        assert self._status(client, owner, business)["record_expense"] is True

        db_session.add(ProductStock(business_id=business.id, product="X", quantity_on_hand=Decimal("1")))
        db_session.commit()
        assert self._status(client, owner, business)["track_stock"] is True

        add_member(business, "member")
        assert self._status(client, owner, business)["invite_team"] is True

    def test_a_pending_invite_counts_as_inviting_someone(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        db_session.add(TeamMember(business_id=business.id, invited_email="new@example.com", role="member", status="pending"))
        db_session.commit()
        assert self._status(client, owner, business)["invite_team"] is True

    def test_sample_data_never_completes_a_step_but_is_reported(self, client, owner_and_business):
        owner, business = owner_and_business
        _load(client, owner, business)
        status = self._status(client, owner, business)
        assert status["has_sample_data"] is True
        assert status["add_sales"] is False
        assert status["record_expense"] is False
        assert status["track_stock"] is False

    def test_any_role_can_read_it(self, client, owner_and_business, add_member):
        owner, business = owner_and_business
        viewer = add_member(business, "viewer")
        assert client.get(_url(business, "/onboarding"), headers=_headers(viewer)).status_code == 200

    def test_scoped_to_the_business(self, client, make_user, make_business, owner_and_business, make_transaction):
        owner, business = owner_and_business
        make_transaction(make_business(owner=make_user()))
        assert self._status(client, owner, business)["add_sales"] is False


# ---------------------------------------------------------------------------
# Import templates
# ---------------------------------------------------------------------------
class TestImportTemplates:
    @pytest.mark.parametrize("target", ["transactions", "expenses"])
    def test_downloads_as_a_csv_attachment(self, client, owner_and_business, target):
        owner, business = owner_and_business
        response = client.get(_url(business, "/imports/template"), params={"target": target}, headers=_headers(owner))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert f"{target}-template.csv" in response.headers["content-disposition"]

    def test_default_target_is_transactions(self, client, owner_and_business):
        owner, business = owner_and_business
        body = client.get(_url(business, "/imports/template"), headers=_headers(owner)).text
        assert body.splitlines()[0].startswith("Date,Product,Quantity")

    def test_an_unsupported_target_is_rejected(self, client, owner_and_business):
        owner, business = owner_and_business
        response = client.get(_url(business, "/imports/template"), params={"target": "bogus"}, headers=_headers(owner))
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_target"

    def test_template_has_a_column_for_every_field_the_importer_accepts(self):
        for target, fields in (("transactions", STANDARD_FIELDS), ("expenses", EXPENSE_STANDARD_FIELDS)):
            headers, rows = parse_upload(build_import_template(target).encode(), "t.csv")
            assert len(headers) == len(fields)
            assert len(rows) == 1

    def test_uploading_the_untouched_template_maps_every_column_automatically(self):
        headers, _ = parse_upload(build_import_template("transactions").encode(), "t.csv")
        mapping = suggest_mapping(headers)
        assert all(mapping[f] is not None for f in STANDARD_FIELDS), mapping
        assert len({v for v in mapping.values()}) == len(STANDARD_FIELDS)  # no column claimed twice

        headers, _ = parse_upload(build_import_template("expenses").encode(), "t.csv")
        mapping = suggest_mapping(headers, EXPENSE_STANDARD_FIELDS, EXPENSE_FIELD_SYNONYMS)
        assert all(mapping[f] is not None for f in EXPENSE_STANDARD_FIELDS), mapping

    def test_the_example_row_is_obviously_an_example(self):
        for target in ("transactions", "expenses"):
            assert "delete this row" in build_import_template(target).splitlines()[1]

    def test_a_filled_in_template_imports_end_to_end(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        template = client.get(_url(business, "/imports/template"), params={"target": "expenses"}, headers=_headers(owner)).text
        upload = client.post(
            _url(business, "/imports/upload"), params={"target": "expenses"},
            files={"file": ("expenses-template.csv", io.BytesIO(template.encode()), "text/csv")},
            headers=_headers(owner),
        )
        assert upload.status_code == 201
        preview = upload.json()
        confirm = client.post(
            _url(business, f"/imports/{preview['id']}/confirm"), json={"mapping": preview["suggested_mapping"]},
            headers=_headers(owner),
        )
        assert confirm.status_code == 202
        assert db_session.query(Expense).filter_by(business_id=business.id).count() == 1

    def test_any_role_can_download_a_template(self, client, owner_and_business, add_member):
        owner, business = owner_and_business
        viewer = add_member(business, "viewer")
        assert client.get(_url(business, "/imports/template"), headers=_headers(viewer)).status_code == 200
