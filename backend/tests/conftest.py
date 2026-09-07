"""
Shared pytest fixtures (Step 10, Batch 10.12, requirement #15).

Runs against a real Postgres database, not SQLite -- this app's models
use Postgres-specific types (JSONB, native UUID) that don't behave the
same (or don't exist at all) on SQLite, and the whole point of these
tests is confidence that the actual production dialect's behavior is
correct. Uses the same database docker-compose.yml already provides for
local dev, under a separate `_test`-suffixed database name so tests
never touch (and can never corrupt) real development data.

Setup (one-time): docker compose up -d postgres, then just run `pytest`
-- the test database itself is created automatically on first run if it
doesn't exist yet (see _ensure_test_database_exists). Override entirely
with a TEST_DATABASE_URL env var if you'd rather point at a different
Postgres instance (e.g. in CI).

Isolation: each test runs inside its own transaction (see db_session)
that's rolled back at the end, regardless of whether the test passed,
failed, or raised -- so tests never leak data into each other and don't
need to clean up after themselves.
"""
import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base  # imports every model so create_all sees them all
from app.models.business import Business
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.user import User
from app.services.import_pipeline import compute_fingerprint


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = settings.DATABASE_URL
    root, _, dbname = base.rpartition("/")
    if dbname.endswith("_test"):
        return base
    return f"{root}/{dbname}_test"


TEST_DATABASE_URL = _test_database_url()


def _ensure_test_database_exists() -> None:
    """Postgres has no `CREATE DATABASE IF NOT EXISTS` -- existence is
    checked first, via a connection to the always-present `postgres`
    maintenance database, rather than just attempting creation and
    swallowing a "already exists" error (which would also swallow a
    genuine connection failure to the wrong host/credentials)."""
    root, _, dbname = TEST_DATABASE_URL.rpartition("/")
    maintenance_engine = create_engine(f"{root}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with maintenance_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": dbname}
            ).first()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        maintenance_engine.dispose()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database_exists()
    test_engine = create_engine(TEST_DATABASE_URL)
    # create_all (not the Alembic migration chain) -- faster for a test
    # suite and sufficient here, since these tests exercise business
    # logic against the current schema, not the migration history
    # itself. If a test ever needs to assert something about a specific
    # migration's behavior, that test should run Alembic directly rather
    # than relying on this fixture.
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    trans = connection.begin()
    # join_transaction_mode="create_savepoint": each session.commit() the
    # test code (or the fixtures below) calls only releases a SAVEPOINT,
    # never the outer `trans` -- without this, a plain Session bound to
    # this connection would commit (and end) the outer transaction on the
    # test's very first session.commit(), making the final trans.rollback()
    # below a no-op and defeating the whole point of per-test isolation.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture()
def make_user(db_session):
    """Factory fixture (not a single fixed object) so a test can create
    as many distinct users as its scenario needs -- e.g. an owner and a
    separately-invited team member."""

    def _make(email: str | None = None, full_name: str = "Test User", password: str = "testpassword123") -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:10]}@example.com",
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture()
def make_plan(db_session):
    """Every limit defaults to None (unlimited) -- a test that cares about
    a specific limit passes it explicitly (e.g. make_plan(max_transactions_per_month=5)),
    keeping each test's actual constraint visible in the test itself
    rather than hidden in shared fixture defaults."""

    def _make(
        key: str | None = None,
        max_businesses_per_user: int | None = None,
        max_branches_per_business: int | None = None,
        max_team_members_per_business: int | None = None,
        max_transactions_per_month: int | None = None,
    ) -> Plan:
        plan = Plan(
            key=key or f"plan-{uuid.uuid4().hex[:10]}",
            name="Test Plan",
            price_ngn=Decimal("0"),
            max_businesses_per_user=max_businesses_per_user,
            max_branches_per_business=max_branches_per_business,
            max_team_members_per_business=max_team_members_per_business,
            max_transactions_per_month=max_transactions_per_month,
        )
        db_session.add(plan)
        db_session.commit()
        db_session.refresh(plan)
        return plan

    return _make


@pytest.fixture()
def make_business(db_session, make_user, make_plan):
    """Always creates (and attaches) a Subscription too -- every real
    Business has one (see app.services.billing.get_subscription's
    defensive auto-create fallback for why), so a fixture that skipped
    it would let a test accidentally pass only because
    get_subscription's fallback silently created a free-plan one, not
    because the test's own setup was actually correct."""

    def _make(owner: User | None = None, plan: Plan | None = None, name: str = "Test Business") -> Business:
        owner = owner or make_user()
        business = Business(owner_id=owner.id, name=name)
        db_session.add(business)
        db_session.commit()
        db_session.refresh(business)

        subscription = Subscription(
            business_id=business.id, plan_id=(plan or make_plan()).id, status="active"
        )
        db_session.add(subscription)
        db_session.commit()
        return business

    return _make


@pytest.fixture()
def make_transaction(db_session):
    def _make(
        business: Business,
        product: str = "Widget",
        quantity: str = "1",
        selling_price: str = "10.00",
        cost_price: str | None = "5.00",
        txn_date: date | None = None,
        category: str | None = None,
    ) -> Transaction:
        row = {
            "date": txn_date or date.today(),
            "product": product,
            "quantity": Decimal(quantity),
            "selling_price": Decimal(selling_price),
            "cost_price": Decimal(cost_price) if cost_price is not None else None,
        }
        txn = Transaction(
            business_id=business.id,
            category=category,
            fingerprint=compute_fingerprint(str(business.id), row),
            **row,
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)
        return txn

    return _make
