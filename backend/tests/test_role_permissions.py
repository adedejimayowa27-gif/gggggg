"""
Role-permission tests (Step 12, Batch 12.4).

Two layers, deliberately separate:

1. POLICY (no database): every route nested under /businesses/{business_id}
   must declare a minimum team role, and that role must match the table
   below. The table is the single readable statement of "who can do what".
   A new route added without a matching row here fails the build, and so
   does any write route that is left open to read-only Viewers -- the
   original gap this batch closed (a Viewer could import data, save
   simulations, connect Google, and so on).

2. BEHAVIOR (real HTTP requests, real Postgres like the other tests): for
   each role -- outsider, viewer, member, admin, owner -- fire a
   representative request at every permission level and check it is either
   stopped by the role check or lets the request through.

How "stopped" is detected: a role failure answers 404 "Business not found."
(deliberate -- see app.api.deps; it never confirms a business exists to
someone without the right access). A request that passes the check may then
fail for some other reason (bad body -> 422, nothing connected -> 404 with a
different message, Stripe not configured -> 503). Those all count as
"let through"; this file tests the permission gate, not the features behind
it, which is why the "allowed" requests can use deliberately empty bodies.
"""
import io
import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import get_owned_business, require_business_role
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.team_member import ROLE_ORDER, TeamMember

# --------------------------------------------------------------------------
# The permission table. Keep this readable -- it is the documentation too
# (mirrored in docs/API.md, "Roles and permissions").
#
#   viewer  read everything the business shows, plus tools that change nothing
#           (what-if preview, AI assistant, chat history)
#   member  + day-to-day work: import data, run syncs, manage alerts, save or
#           delete simulations, add or edit branches
#   admin   + set up integrations, manage the team, delete branches, audit
#           log, start a plan upgrade
#   owner   (the business's creator; nothing is owner-only yet, the role
#           exists so it can be, e.g. deleting the business)
# --------------------------------------------------------------------------
B = "/businesses/{business_id}"

EXPECTED_MINIMUM_ROLE: dict[tuple[str, str], str] = {}


def _declare(role: str, *routes: tuple[str, str]) -> None:
    for method, path in routes:
        EXPECTED_MINIMUM_ROLE[(method, path)] = role


_declare(
    "viewer",
    ("GET", B),
    ("GET", f"{B}/subscription"),
    ("GET", f"{B}/analytics/summary"),
    ("GET", f"{B}/analytics/timeseries"),
    ("GET", f"{B}/analytics/products"),
    ("GET", f"{B}/analytics/breakdown"),
    ("GET", f"{B}/analytics/customer-loyalty"),
    ("GET", f"{B}/transactions"),
    ("GET", f"{B}/transactions/export"),
    ("GET", f"{B}/transactions/field-values"),
    ("GET", f"{B}/alerts"),
    ("GET", f"{B}/alerts/{{alert_id}}"),
    ("GET", f"{B}/imports"),
    ("GET", f"{B}/imports/{{import_id}}"),
    ("GET", f"{B}/branches"),
    ("GET", f"{B}/team"),
    ("GET", f"{B}/simulations"),
    ("GET", f"{B}/simulations/{{simulation_id}}"),
    # Tools that read data and save nothing about the business:
    ("POST", f"{B}/simulate"),
    ("POST", f"{B}/assistant/messages"),
    ("POST", f"{B}/conversations"),
    ("GET", f"{B}/conversations"),
    ("POST", f"{B}/conversations/{{conversation_id}}/messages"),
    ("GET", f"{B}/conversations/{{conversation_id}}/messages"),
    # Connection status only (who is connected, when it last synced):
    ("GET", f"{B}/google/status"),
    ("GET", f"{B}/microsoft/status"),
)

_declare(
    "member",
    ("POST", f"{B}/imports/upload"),
    ("POST", f"{B}/imports/{{import_id}}/confirm"),
    ("POST", f"{B}/alerts/run"),
    ("PATCH", f"{B}/alerts/{{alert_id}}"),
    ("POST", f"{B}/simulations"),
    ("DELETE", f"{B}/simulations/{{simulation_id}}"),
    ("POST", f"{B}/branches"),
    ("PATCH", f"{B}/branches/{{branch_id}}"),
    ("POST", f"{B}/google/sync"),
    ("POST", f"{B}/microsoft/sync"),
)

_declare(
    "admin",
    ("DELETE", f"{B}/branches/{{branch_id}}"),
    ("POST", f"{B}/team"),
    ("PATCH", f"{B}/team/{{member_id}}"),
    ("DELETE", f"{B}/team/{{member_id}}"),
    ("GET", f"{B}/audit-logs"),
    ("POST", f"{B}/billing/checkout"),
    # Integration setup: connecting an account, choosing which of its files
    # to read, and mapping columns. Listing spreadsheets/workbooks exposes
    # the connected account's file names, so it is admin-only too.
    ("GET", f"{B}/google/connect"),
    ("DELETE", f"{B}/google"),
    ("GET", f"{B}/google/spreadsheets"),
    ("GET", f"{B}/google/spreadsheets/{{spreadsheet_id}}/worksheets"),
    ("PUT", f"{B}/google/selection"),
    ("GET", f"{B}/google/preview"),
    ("PUT", f"{B}/google/mapping"),
    ("GET", f"{B}/microsoft/connect"),
    ("DELETE", f"{B}/microsoft"),
    ("GET", f"{B}/microsoft/workbooks"),
    ("GET", f"{B}/microsoft/workbooks/{{workbook_item_id}}/worksheets"),
    ("PUT", f"{B}/microsoft/selection"),
    ("GET", f"{B}/microsoft/preview"),
    ("PUT", f"{B}/microsoft/mapping"),
)

# Not in this table on purpose: the OAuth redirects at /google/callback and
# /microsoft/callback. They live outside /businesses/{business_id}/..., because
# the providers send the user's browser there with no Authorization header;
# they authenticate through the signed `state` value that only an admin's
# /connect call can produce.

# POST/PUT/PATCH/DELETE routes that a read-only Viewer may still call, because
# they change nothing about the business's data: a calculation that saves
# nothing, and questions to the AI assistant.
VIEWER_MAY_USE_WRITE_METHODS = {
    ("POST", f"{B}/simulate"),
    ("POST", f"{B}/assistant/messages"),
    ("POST", f"{B}/conversations"),
    ("POST", f"{B}/conversations/{{conversation_id}}/messages"),
}

_ROLE_BY_RANK = {rank: name for name, rank in ROLE_ORDER.items()}


def _business_routes():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "{business_id}" not in route.path:
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            yield method, route.path, route


def _actual_minimum_role(route: APIRoute) -> str | None:
    """The strictest role any of this route's dependencies demands, or None
    when it has no business-role check at all."""
    ranks: list[int] = []

    def walk(dependant):
        for sub in dependant.dependencies:
            if sub.call is get_owned_business:
                ranks.append(ROLE_ORDER["viewer"])
            declared = getattr(sub.call, "minimum_role", None)
            if declared is not None:
                ranks.append(ROLE_ORDER[declared])
            walk(sub)

    walk(route.dependant)
    return _ROLE_BY_RANK[max(ranks)] if ranks else None


# ---------------------------------------------------------------------------
# Layer 1: policy
# ---------------------------------------------------------------------------
class TestRoutePolicy:
    def test_every_business_route_declares_a_minimum_role(self):
        undeclared = [
            f"{method} {path}"
            for method, path, _ in _business_routes()
            if (method, path) not in EXPECTED_MINIMUM_ROLE
        ]
        assert not undeclared, (
            "These routes have no row in EXPECTED_MINIMUM_ROLE. Decide who may call each one "
            "(see the table at the top of this file), gate it with get_owned_business (read-only) "
            "or require_business_role(...), and add it:\n  " + "\n  ".join(undeclared)
        )

    def test_each_route_requires_exactly_its_declared_role(self):
        wrong = []
        for method, path, route in _business_routes():
            expected = EXPECTED_MINIMUM_ROLE.get((method, path))
            if expected is None:
                continue
            actual = _actual_minimum_role(route)
            if actual != expected:
                wrong.append(f"{method} {path}: expected {expected}, route enforces {actual}")
        assert not wrong, "\n".join(wrong)

    def test_the_table_has_no_stale_rows(self):
        live = {(method, path) for method, path, _ in _business_routes()}
        stale = [f"{m} {p}" for (m, p) in EXPECTED_MINIMUM_ROLE if (m, p) not in live]
        assert not stale, "Rows for routes that no longer exist:\n  " + "\n  ".join(stale)

    def test_no_business_route_is_left_without_a_role_check(self):
        ungated = [
            f"{method} {path}" for method, path, route in _business_routes() if _actual_minimum_role(route) is None
        ]
        assert not ungated, "Routes under /businesses/{business_id} with no role check:\n  " + "\n  ".join(ungated)

    def test_no_state_changing_route_is_open_to_viewers_unless_allow_listed(self):
        """The safety net for the future: a new POST/PUT/PATCH/DELETE route that is
        only behind get_owned_business would be writable by a read-only
        Viewer. Fail unless it was deliberately added to the allow-list."""
        open_writes = []
        for method, path, route in _business_routes():
            if method == "GET":
                continue
            if _actual_minimum_role(route) == "viewer" and (method, path) not in VIEWER_MAY_USE_WRITE_METHODS:
                open_writes.append(f"{method} {path}")
        assert not open_writes, (
            "State-changing routes that a read-only Viewer can call. Gate them with "
            'require_business_role("member") or higher, or, if they truly change nothing, '
            "add them to VIEWER_MAY_USE_WRITE_METHODS:\n  " + "\n  ".join(open_writes)
        )

    def test_a_misspelled_role_fails_immediately_instead_of_letting_everyone_in(self):
        with pytest.raises(ValueError):
            require_business_role("admn")

    def test_the_factory_records_the_role_it_enforces(self):
        assert require_business_role("member").minimum_role == "member"


# ---------------------------------------------------------------------------
# Layer 2: behavior
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # The default limit (120/minute per IP, in memory) is shared by the whole
    # test process; clear it so this file's requests can't trip a 429 and a
    # 429 can't be mistaken for a permission result.
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001 -- best effort; `enabled = False` below is the real switch
        pass
    was_enabled = getattr(limiter, "enabled", True)
    limiter.enabled = False

    # raise_server_exceptions=False: a request the gate lets through may fail
    # further down for unrelated reasons (nothing connected, empty body...).
    # That is a 4xx/5xx response here, not a crashed test.
    test_client = TestClient(app, raise_server_exceptions=False)
    yield test_client

    limiter.enabled = was_enabled
    app.dependency_overrides.clear()


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def _blocked_by_role(response) -> bool:
    if response.status_code != 404:
        return False
    try:
        return response.json().get("error", {}).get("message") == "Business not found."
    except ValueError:
        return False


_ANY_ID = str(uuid.uuid4())
_CSV = b"date,product,quantity,selling_price\n2026-01-05,Widget,1,10.00\n"

# (label, method, path under the business, minimum role, extra request kwargs)
# One representative request per permission level and kind of action. Bodies
# are deliberately empty/invalid for anything that would otherwise change
# data: getting past the gate then answers 422/404/503, never a real write.
BEHAVIOR_CASES = [
    ("view analytics", "GET", "/analytics/summary", "viewer", {}),
    ("list transactions", "GET", "/transactions", "viewer", {}),
    ("list alerts", "GET", "/alerts", "viewer", {}),
    ("list branches", "GET", "/branches", "viewer", {}),
    ("what-if preview", "POST", "/simulate", "viewer", {"json": {}}),
    ("ask the AI assistant", "POST", "/assistant/messages", "viewer", {"json": {}}),
    ("upload an import file", "POST", "/imports/upload", "member",
     {"files": {"file": ("sales.csv", io.BytesIO(_CSV), "text/csv")}}),
    ("run alert detection", "POST", "/alerts/run", "member", {}),
    ("update an alert", "PATCH", f"/alerts/{_ANY_ID}", "member", {"json": {"status": "read"}}),
    ("save a simulation", "POST", "/simulations", "member", {"json": {}}),
    ("delete a simulation", "DELETE", f"/simulations/{_ANY_ID}", "member", {}),
    ("add a branch", "POST", "/branches", "member", {"json": {}}),
    ("edit a branch", "PATCH", f"/branches/{_ANY_ID}", "member", {"json": {}}),
    ("sync Google Sheets", "POST", "/google/sync", "member", {}),
    ("sync Excel", "POST", "/microsoft/sync", "member", {}),
    ("delete a branch", "DELETE", f"/branches/{_ANY_ID}", "admin", {}),
    ("invite a teammate", "POST", "/team", "admin", {"json": {}}),
    ("read the audit log", "GET", "/audit-logs", "admin", {}),
    ("start a plan upgrade", "POST", "/billing/checkout", "admin", {"json": {}}),
    ("connect Google", "GET", "/google/connect", "admin", {}),
    ("list Google spreadsheets", "GET", "/google/spreadsheets", "admin", {}),
    ("save the Google column mapping", "PUT", "/google/mapping", "admin", {"json": {}}),
    ("connect Microsoft", "GET", "/microsoft/connect", "admin", {}),
    ("list Excel workbooks", "GET", "/microsoft/workbooks", "admin", {}),
    ("save the Excel column mapping", "PUT", "/microsoft/mapping", "admin", {"json": {}}),
]

# rank -1: someone with no access to this business at all.
ROLES_UNDER_TEST = ["outsider", "viewer", "member", "admin", "owner"]


def _rank(role: str) -> int:
    return -1 if role == "outsider" else ROLE_ORDER[role]


@pytest.mark.parametrize("role", ROLES_UNDER_TEST)
def test_each_role_can_do_exactly_what_it_should(client, db_session, make_user, make_business, role):
    owner = make_user()
    business = make_business(owner=owner)

    if role == "owner":
        actor = owner
    else:
        actor = make_user()
        if role != "outsider":
            db_session.add(
                TeamMember(
                    business_id=business.id, user_id=actor.id,
                    invited_email=actor.email, role=role, status="active",
                )
            )
            db_session.commit()

    problems = []
    for label, method, suffix, minimum, kwargs in BEHAVIOR_CASES:
        # File-like bodies are consumed by a request, so build a fresh one each time.
        if "files" in kwargs:
            kwargs = {"files": {"file": ("sales.csv", io.BytesIO(_CSV), "text/csv")}}
        response = client.request(
            method, f"/businesses/{business.id}{suffix}", headers=_headers(actor), **kwargs
        )
        should_be_allowed = _rank(role) >= ROLE_ORDER[minimum]
        was_blocked = _blocked_by_role(response)
        if should_be_allowed == was_blocked:
            problems.append(
                f"{role} / {label} ({method} {suffix}): "
                f"{'was blocked but should be allowed' if was_blocked else 'got through but should be blocked'} "
                f"(status {response.status_code})"
            )

    assert not problems, "\n".join(problems)
