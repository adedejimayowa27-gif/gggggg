"""
Bulk expense import, and stock value (Step 13, Batch 3.1).

Expense import reuses the transaction-import pipeline's upload -> map
columns -> confirm flow (app.services.import_pipeline), pointed at a
different target and schema. These tests drive it through real HTTP
requests, the same way test_e2e_user_journey.py exercises the
transaction import path, including the same background-job-runs-
synchronously monkeypatch (see that file's module docstring for why).
"""
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.background_job import BackgroundJob
from app.models.branch import Branch
from app.models.expense import Expense
from app.models.import_session import ImportSession
from app.services.jobs import JOB_HANDLERS


@pytest.fixture()
def client(db_session, monkeypatch):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    import app.api.routes.imports as imports_route

    def _run_job_sync(job_id):
        job = db_session.get(BackgroundJob, job_id)
        handler = JOB_HANDLERS[job.job_type]
        job.status = "running"
        db_session.commit()
        result = handler(db_session, job)
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


def _csv(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8"))


def _upload_and_confirm(client, owner, business, csv_text, mapping_overrides=None) -> dict:
    upload = client.post(
        f"/businesses/{business.id}/imports/upload",
        params={"target": "expenses"},
        files={"file": ("expenses.csv", _csv(csv_text), "text/csv")},
        headers=_headers(owner),
    )
    assert upload.status_code == 201, upload.text
    preview = upload.json()
    mapping = preview["suggested_mapping"]
    if mapping_overrides:
        mapping.update(mapping_overrides)
    confirm = client.post(
        f"/businesses/{business.id}/imports/{preview['id']}/confirm",
        json={"mapping": mapping},
        headers=_headers(owner),
    )
    assert confirm.status_code == 202, confirm.text
    return client.get(f"/businesses/{business.id}/imports/{preview['id']}", headers=_headers(owner)).json()


class TestUpload:
    def test_upload_suggests_the_expense_mapping_not_the_transaction_one(self, client, owner_and_business):
        owner, business = owner_and_business
        csv_text = "Date,Category,Amount,Note\n2026-09-01,Rent,150000,September rent\n"
        response = client.post(
            f"/businesses/{business.id}/imports/upload",
            params={"target": "expenses"},
            files={"file": ("e.csv", _csv(csv_text), "text/csv")},
            headers=_headers(owner),
        )
        assert response.status_code == 201
        mapping = response.json()["suggested_mapping"]
        assert set(mapping) == {"date", "category", "amount", "description", "branch"}
        assert mapping["date"] == "Date"
        assert mapping["category"] == "Category"
        assert mapping["amount"] == "Amount"

    def test_the_session_remembers_its_target(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        csv_text = "Date,Category,Amount\n2026-09-01,Rent,150000\n"
        response = client.post(
            f"/businesses/{business.id}/imports/upload",
            params={"target": "expenses"},
            files={"file": ("e.csv", _csv(csv_text), "text/csv")},
            headers=_headers(owner),
        )
        session_id = response.json()["id"]
        assert db_session.get(ImportSession, session_id).target == "expenses"

    def test_default_target_is_still_transactions(self, client, db_session, owner_and_business):
        """Unchanged behaviour for every existing caller that doesn't pass `target`."""
        owner, business = owner_and_business
        csv_text = "Date,Product,Qty,Price\n2026-09-01,Rice,1,1000\n"
        response = client.post(
            f"/businesses/{business.id}/imports/upload",
            files={"file": ("t.csv", _csv(csv_text), "text/csv")},
            headers=_headers(owner),
        )
        session_id = response.json()["id"]
        assert db_session.get(ImportSession, session_id).target == "transactions"

    def test_an_unsupported_target_is_rejected(self, client, owner_and_business):
        owner, business = owner_and_business
        response = client.post(
            f"/businesses/{business.id}/imports/upload",
            params={"target": "bogus"},
            files={"file": ("e.csv", _csv("a,b\n1,2\n"), "text/csv")},
            headers=_headers(owner),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_target"


class TestConfirm:
    def test_valid_rows_become_expenses(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        csv_text = (
            "Date,Category,Amount,Note\n"
            "2026-09-01,Rent,150000,September rent\n"
            "2026-09-05,Transport,5000,\n"
        )
        result = _upload_and_confirm(client, owner, business, csv_text)
        assert result["status"] == "completed"
        assert result["imported_row_count"] == 2
        assert result["failed_row_count"] == 0

        expenses = db_session.query(Expense).filter_by(business_id=business.id).order_by(Expense.date).all()
        assert len(expenses) == 2
        assert expenses[0].category == "Rent"
        assert expenses[0].amount == Decimal("150000")
        assert expenses[0].description == "September rent"
        assert expenses[1].description is None  # blank cell -> null, not ""

    def test_invalid_rows_are_reported_and_skipped(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        csv_text = (
            "Date,Category,Amount\n"
            "2026-09-01,Rent,150000\n"
            "2026-09-02,,5000\n"          # missing category
            "2026-09-03,Transport,-100\n"  # non-positive amount
            "not-a-date,Fuel,1000\n"       # bad date
        )
        result = _upload_and_confirm(client, owner, business, csv_text)
        assert result["imported_row_count"] == 1
        assert result["failed_row_count"] == 3
        row_numbers = {e["row_number"] for e in result["row_errors"]}
        assert row_numbers == {2, 3, 4}
        assert db_session.query(Expense).filter_by(business_id=business.id).count() == 1

    def test_branch_names_are_resolved_case_insensitively(self, client, db_session, owner_and_business):
        owner, business = owner_and_business
        branch = Branch(business_id=business.id, name="Ibadan")
        db_session.add(branch)
        db_session.commit()

        csv_text = "Date,Category,Amount,Branch\n2026-09-01,Transport,2000,ibadan\n2026-09-02,Rent,1000,Nowhere\n"
        _upload_and_confirm(client, owner, business, csv_text)

        rows = {e.category: e.branch_id for e in db_session.query(Expense).filter_by(business_id=business.id)}
        assert rows["Transport"] == branch.id
        assert rows["Rent"] is None  # unrecognized branch name -> left unassigned, not rejected or auto-created

    def test_reimporting_the_same_file_creates_duplicates(self, client, db_session, owner_and_business):
        """Documents the known, deliberate limitation noted in
        execute_confirmed_expense_import's docstring: unlike transactions,
        there is no fingerprint/duplicate check for expenses yet."""
        owner, business = owner_and_business
        csv_text = "Date,Category,Amount\n2026-09-01,Rent,150000\n"
        _upload_and_confirm(client, owner, business, csv_text)
        _upload_and_confirm(client, owner, business, csv_text)
        assert db_session.query(Expense).filter_by(business_id=business.id).count() == 2

    def test_a_file_with_only_invalid_rows_is_marked_failed(self, client, owner_and_business):
        owner, business = owner_and_business
        csv_text = "Date,Category,Amount\nnot-a-date,,0\n"
        result = _upload_and_confirm(client, owner, business, csv_text)
        assert result["status"] == "failed"
        assert result["imported_row_count"] == 0

    def test_missing_required_mapping_is_rejected(self, client, owner_and_business):
        owner, business = owner_and_business
        upload = client.post(
            f"/businesses/{business.id}/imports/upload",
            params={"target": "expenses"},
            files={"file": ("e.csv", _csv("Date,Amount\n2026-09-01,100\n"), "text/csv")},
            headers=_headers(owner),
        )
        preview = upload.json()
        mapping = dict(preview["suggested_mapping"])
        mapping["category"] = None  # not present in this file at all
        confirm = client.post(
            f"/businesses/{business.id}/imports/{preview['id']}/confirm",
            json={"mapping": mapping},
            headers=_headers(owner),
        )
        # A confirm with a required field left unmapped never reaches the
        # background job -- the mapping is only known once the person
        # confirms it, so this is caught synchronously, same as the
        # transaction-import path.
        assert confirm.status_code == 400
        assert confirm.json()["error"]["code"] == "incomplete_mapping"

    def test_the_transaction_monthly_limit_does_not_apply_to_an_expense_import(
        self, client, make_business, make_user
    ):
        owner = make_user()
        business = make_business(owner=owner, plan=None)  # default/free plan, whatever its transaction limit is
        # A free plan's transaction limit is small; expenses must not be
        # bounded by it at all.
        csv_text = "\n".join(
            ["Date,Category,Amount"] + [f"2026-09-{d:02d},Rent,1000" for d in range(1, 29)]
        )
        result = _upload_and_confirm(client, owner, business, csv_text)
        assert result["imported_row_count"] == 28

    def test_viewers_cannot_upload_an_expense_import(self, client, db_session, owner_and_business, make_user):
        from app.models.team_member import TeamMember

        owner, business = owner_and_business
        viewer = make_user()
        db_session.add(
            TeamMember(business_id=business.id, user_id=viewer.id, invited_email=viewer.email, role="viewer", status="active")
        )
        db_session.commit()

        response = client.post(
            f"/businesses/{business.id}/imports/upload",
            params={"target": "expenses"},
            files={"file": ("e.csv", _csv("Date,Category,Amount\n2026-09-01,Rent,1000\n"), "text/csv")},
            headers=_headers(viewer),
        )
        assert response.status_code == 404
