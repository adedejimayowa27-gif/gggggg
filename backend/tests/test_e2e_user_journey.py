"""
End-to-end tests for the main user journey (Step 10, Batch 10.13,
requirement #16): sign up, create a business, import transactions, view
analytics, run a simulation, and see it all reflected in the audit log
-- driven through real HTTP requests against the actual FastAPI app,
not by calling service functions directly (that's what Batch 10.12's
unit tests already do). Also covers the one thing that must never work:
one business reading another business's data.

Background jobs (Batch 10.9): app.services.jobs' real executor opens its
own DB connection to the live database, which can never see this test's
not-yet-committed transaction (see conftest.py's db_session fixture).
The `client` fixture below monkeypatches the import route's
`run_job_async` to instead run the job's handler synchronously against
this same test session -- so import confirmation completes
deterministically within the test, with no polling/sleeping needed,
while still exercising the exact same handler code
(app.services.import_pipeline's registered "import_confirm" handler)
that production's background thread would run.
"""
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.background_job import BackgroundJob
from app.services.jobs import JOB_HANDLERS


def _d(value) -> Decimal:
    """Normalizes a JSON-decoded numeric field to Decimal for comparison.
    Whether FastAPI/Pydantic serializes a Decimal response field as a
    JSON string (`"150.00"`) or a number (`150.0`) is a detail of the
    serialization path, not something these tests should be coupled to
    -- Decimal(str(x)) compares correctly either way, since Decimal
    equality is by numeric value regardless of trailing-zero formatting."""
    return Decimal(str(value))


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
        try:
            result = handler(db_session, job)
        except Exception as exc:  # noqa: BLE001 -- mirrors app.services.jobs._execute's own handling
            job.status = "failed"
            job.error = str(exc)
            db_session.commit()
            raise
        job.status = "completed"
        job.result = result
        db_session.commit()

    monkeypatch.setattr(imports_route, "run_job_async", _run_job_sync)

    # Not used as `with TestClient(app) as c:` -- entering the context
    # manager runs the app's lifespan, which would start the real
    # APScheduler (app.services.scheduler) and background job executor
    # for no benefit here (their intervals are hours; nothing they do
    # would fire during a test run) and an extra thing to clean up per
    # test. Requests are still dispatched through the full real
    # middleware stack either way.
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def free_plan(make_plan):
    # POST /businesses always attaches a free-tier Subscription (see
    # app.services.billing.create_free_subscription), which looks up a
    # Plan row with key="free" -- this test DB is built via create_all
    # (see conftest.py), not the Alembic migration chain that seeds one
    # in a real deployment, so it must be created explicitly here.
    return make_plan(key="free")


def _signup(client, email: str) -> str:
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "correct-horse-battery-staple", "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _sample_csv() -> bytes:
    return (
        b"date,product,quantity,selling_price,cost_price\n"
        b"2026-01-05,Widget,10,10.00,4.00\n"
        b"2026-01-06,Widget,5,10.00,4.00\n"
        b"not-a-date,Widget,1,5.00,2.00\n"  # invalid date -> deliberately bad row
    )


class TestMainUserJourney:
    def test_signup_create_business_import_analyze_and_simulate(self, client, free_plan):
        token = _signup(client, "owner@example.com")
        headers = _auth_headers(token)

        # --- create a business ---
        create_resp = client.post("/businesses", json={"name": "Acme Corp"}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        business_id = create_resp.json()["id"]

        list_resp = client.get("/businesses", headers=headers)
        assert list_resp.status_code == 200
        assert any(b["id"] == business_id for b in list_resp.json())

        # --- upload + confirm an import ---
        upload_resp = client.post(
            f"/businesses/{business_id}/imports/upload",
            files={"file": ("sales.csv", io.BytesIO(_sample_csv()), "text/csv")},
            headers=headers,
        )
        assert upload_resp.status_code == 201, upload_resp.text
        preview = upload_resp.json()
        import_id = preview["id"]
        assert preview["total_row_count"] == 3

        mapping = {
            "date": "date", "product": "product", "quantity": "quantity",
            "selling_price": "selling_price", "cost_price": "cost_price",
            "category": None, "customer": None, "payment_method": None,
        }
        confirm_resp = client.post(
            f"/businesses/{business_id}/imports/{import_id}/confirm",
            json={"mapping": mapping},
            headers=headers,
        )
        assert confirm_resp.status_code == 202, confirm_resp.text
        assert confirm_resp.json()["status"] == "queued"

        # The client fixture's monkeypatch runs the background job
        # synchronously as part of the confirm call above, so it's
        # already finished -- no polling loop needed in this test (a
        # real client does poll; that behavior is exercised implicitly
        # by every prior batch's manual testing of the actual route).
        poll_resp = client.get(f"/businesses/{business_id}/imports/{import_id}", headers=headers)
        assert poll_resp.status_code == 200
        result = poll_resp.json()
        assert result["status"] == "completed"
        assert result["imported_row_count"] == 2  # 2 valid rows
        assert result["failed_row_count"] == 1  # the "not-a-date" row
        assert len(result["row_errors"]) == 1
        assert result["row_errors"][0]["row_number"] == 3

        # --- analytics reflect exactly the imported data ---
        # 10*10.00 + 5*10.00 = 150.00 revenue; 10*4.00 + 5*4.00 = 60.00 cost
        summary_resp = client.get(
            f"/businesses/{business_id}/analytics/summary",
            params={"range": "custom", "start_date": "2026-01-01", "end_date": "2026-01-31"},
            headers=headers,
        )
        assert summary_resp.status_code == 200, summary_resp.text
        summary = summary_resp.json()
        assert _d(summary["revenue"]) == Decimal("150.00")
        assert _d(summary["total_cost"]) == Decimal("60.00")
        assert _d(summary["gross_profit"]) == Decimal("90.00")
        assert summary["transaction_count"] == 2

        # --- run a simulation against the imported data ---
        simulate_resp = client.post(
            f"/businesses/{business_id}/simulate",
            json={
                "scenario_type": "selling_price_change",
                "parameters": {"scope_type": "business", "change_percentage": "10"},
                "baseline_start_date": "2026-01-01",
                "baseline_end_date": "2026-01-31",
            },
            headers=headers,
        )
        assert simulate_resp.status_code == 200, simulate_resp.text
        sim = simulate_resp.json()
        assert _d(sim["results"]["current"]["revenue"]) == Decimal("150.00")
        assert _d(sim["results"]["simulated"]["revenue"]) == Decimal("165.00")  # +10%

        # --- the audit trail recorded the key actions along the way ---
        audit_resp = client.get(f"/businesses/{business_id}/audit-logs", headers=headers)
        assert audit_resp.status_code == 200, audit_resp.text
        actions = {entry["action"] for entry in audit_resp.json()}
        assert "business.created" in actions
        assert "import.completed" in actions

    def test_signup_rejects_a_duplicate_email(self, client, free_plan):
        _signup(client, "dupe@example.com")
        response = client.post(
            "/auth/signup",
            json={"email": "dupe@example.com", "password": "correct-horse-battery-staple"},
        )
        assert response.status_code == 409

    def test_login_with_wrong_password_is_rejected(self, client, free_plan):
        _signup(client, "wrongpass@example.com")
        response = client.post(
            "/auth/login",
            json={"email": "wrongpass@example.com", "password": "definitely-not-it"},
        )
        assert response.status_code == 401

    def test_unauthenticated_request_is_rejected(self, client):
        response = client.get("/businesses")
        assert response.status_code == 401


class TestTenantIsolation:
    """The one thing that must never work, checked at the HTTP layer
    (not just the service layer, which Batch 10.12 and the deps.py
    docstrings already cover) -- a business must never be reachable by
    anyone other than its owner/team members, and a wrong/foreign
    business_id must 404, never 403 (which would confirm the business's
    existence to someone not authorized to see it)."""

    def _create_business_for(self, client, email: str, free_plan) -> tuple[str, str]:
        token = _signup(client, email)
        resp = client.post(
            "/businesses", json={"name": f"{email}'s business"}, headers=_auth_headers(token)
        )
        assert resp.status_code == 201
        return token, resp.json()["id"]

    def test_a_user_cannot_read_another_users_business(self, client, free_plan):
        _, business_a_id = self._create_business_for(client, "alice@example.com", free_plan)
        token_b, _ = self._create_business_for(client, "bob@example.com", free_plan)

        response = client.get(f"/businesses/{business_a_id}", headers=_auth_headers(token_b))
        assert response.status_code == 404  # never 403 -- see class docstring

    def test_a_user_cannot_list_another_users_transactions(self, client, free_plan):
        _, business_a_id = self._create_business_for(client, "carol@example.com", free_plan)
        token_b, _ = self._create_business_for(client, "dave@example.com", free_plan)

        response = client.get(
            f"/businesses/{business_a_id}/transactions", headers=_auth_headers(token_b)
        )
        assert response.status_code == 404

    def test_a_user_cannot_view_another_users_analytics(self, client, free_plan):
        _, business_a_id = self._create_business_for(client, "erin@example.com", free_plan)
        token_b, _ = self._create_business_for(client, "frank@example.com", free_plan)

        response = client.get(
            f"/businesses/{business_a_id}/analytics/summary", headers=_auth_headers(token_b)
        )
        assert response.status_code == 404

    def test_a_user_cannot_confirm_an_import_belonging_to_another_business(
        self, client, free_plan
    ):
        token_a, business_a_id = self._create_business_for(client, "grace@example.com", free_plan)
        token_b, _ = self._create_business_for(client, "heidi@example.com", free_plan)

        upload_resp = client.post(
            f"/businesses/{business_a_id}/imports/upload",
            files={"file": ("sales.csv", io.BytesIO(_sample_csv()), "text/csv")},
            headers=_auth_headers(token_a),
        )
        import_id = upload_resp.json()["id"]

        confirm_resp = client.post(
            f"/businesses/{business_a_id}/imports/{import_id}/confirm",
            json={"mapping": {"date": "date", "product": "product", "quantity": "quantity", "selling_price": "selling_price"}},
            headers=_auth_headers(token_b),  # business_b's owner, not business_a's
        )
        assert confirm_resp.status_code == 404

    def test_a_non_owner_cannot_view_the_audit_log(self, client, free_plan, db_session):
        # audit-logs requires "admin"+ role (see app.api.routes.audit_logs)
        # -- a plain "member"/"viewer" team role must be rejected too, not
        # just a completely unrelated outsider.
        from app.models.team_member import TeamMember

        token_a, business_a_id = self._create_business_for(client, "ivan@example.com", free_plan)
        token_b, _ = self._create_business_for(client, "judy@example.com", free_plan)

        # Add business B's owner as a low-privilege "viewer" on business A.
        from app.models.user import User

        member_user = db_session.query(User).filter(User.email == "judy@example.com").first()
        db_session.add(
            TeamMember(
                business_id=business_a_id, user_id=member_user.id,
                invited_email=member_user.email, role="viewer", status="active",
            )
        )
        db_session.commit()

        response = client.get(f"/businesses/{business_a_id}/audit-logs", headers=_auth_headers(token_b))
        assert response.status_code == 404
