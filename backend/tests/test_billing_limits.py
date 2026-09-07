"""
Tests for app.services.billing's plan usage-limit enforcement (Step 10,
Batch 10.12, requirement #15). These are the checks that stand between a
user and exceeding what they're paying for -- getting the boundary
condition wrong (off-by-one on a limit) either lets a free user use more
than they should, or blocks a paying user who's still within their
limit, so both directions are tested explicitly at the exact boundary.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.services.billing import (
    check_max_branches,
    check_max_businesses,
    check_max_team_members,
    check_max_transactions_this_month,
    get_subscription,
)


class TestCheckMaxBusinesses:
    def test_new_user_with_no_businesses_yet_is_always_allowed(self, db_session, make_user):
        # A brand-new user has no existing business to check a limit
        # against yet -- this must never raise, or nobody could ever
        # create their first business.
        user = make_user()
        check_max_businesses(db_session, user)  # should not raise

    def test_at_the_limit_is_rejected(self, db_session, make_user, make_plan, make_business):
        plan = make_plan(max_businesses_per_user=2)
        user = make_user()
        make_business(owner=user, plan=plan)
        make_business(owner=user, plan=plan)

        with pytest.raises(ValidationError):
            check_max_businesses(db_session, user)

    def test_one_below_the_limit_is_allowed(self, db_session, make_user, make_plan, make_business):
        plan = make_plan(max_businesses_per_user=2)
        user = make_user()
        make_business(owner=user, plan=plan)

        check_max_businesses(db_session, user)  # should not raise

    def test_null_limit_means_unlimited(self, db_session, make_user, make_plan, make_business):
        plan = make_plan(max_businesses_per_user=None)
        user = make_user()
        for _ in range(5):
            make_business(owner=user, plan=plan)

        check_max_businesses(db_session, user)  # should not raise, no matter how many exist


class TestCheckMaxBranches:
    def test_at_the_limit_is_rejected(self, db_session, make_plan, make_business):
        from app.models.branch import Branch

        plan = make_plan(max_branches_per_business=1)
        business = make_business(plan=plan)
        db_session.add(Branch(business_id=business.id, name="Main Branch"))
        db_session.commit()

        with pytest.raises(ValidationError):
            check_max_branches(db_session, business)

    def test_below_the_limit_is_allowed(self, db_session, make_plan, make_business):
        plan = make_plan(max_branches_per_business=2)
        business = make_business(plan=plan)
        check_max_branches(db_session, business)  # should not raise -- zero branches so far


class TestCheckMaxTeamMembers:
    def test_at_the_limit_is_rejected(self, db_session, make_plan, make_business, make_user):
        from app.models.team_member import TeamMember

        plan = make_plan(max_team_members_per_business=1)
        business = make_business(plan=plan)
        member = make_user()
        db_session.add(
            TeamMember(
                business_id=business.id, user_id=member.id, invited_email=member.email,
                role="staff", status="active",
            )
        )
        db_session.commit()

        with pytest.raises(ValidationError):
            check_max_team_members(db_session, business)

    def test_inactive_team_members_do_not_count_toward_the_limit(
        self, db_session, make_plan, make_business, make_user
    ):
        from app.models.team_member import TeamMember

        plan = make_plan(max_team_members_per_business=1)
        business = make_business(plan=plan)
        member = make_user()
        db_session.add(
            TeamMember(
                business_id=business.id, user_id=member.id, invited_email=member.email,
                role="staff", status="removed",
            )
        )
        db_session.commit()

        check_max_team_members(db_session, business)  # should not raise -- the one row is inactive


class TestCheckMaxTransactionsThisMonth:
    def test_at_the_limit_is_rejected(self, db_session, make_plan, make_business, make_transaction):
        plan = make_plan(max_transactions_per_month=2)
        business = make_business(plan=plan)
        make_transaction(business)
        make_transaction(business)

        with pytest.raises(ValidationError):
            check_max_transactions_this_month(db_session, business)

    def test_below_the_limit_is_allowed(self, db_session, make_plan, make_business, make_transaction):
        plan = make_plan(max_transactions_per_month=2)
        business = make_business(plan=plan)
        make_transaction(business)

        check_max_transactions_this_month(db_session, business)  # should not raise

    def test_null_limit_means_unlimited(self, db_session, make_plan, make_business, make_transaction):
        plan = make_plan(max_transactions_per_month=None)
        business = make_business(plan=plan)
        for _ in range(10):
            make_transaction(business)

        check_max_transactions_this_month(db_session, business)  # should not raise

    def test_only_counts_transactions_created_this_calendar_month(
        self, db_session, make_plan, make_business, make_transaction
    ):
        # The cap is a *monthly* allowance, not a lifetime one -- a
        # transaction created (imported) in a previous month must not
        # count against this month's limit, even if the sale's own
        # `date` field falls in the current month.
        plan = make_plan(max_transactions_per_month=1)
        business = make_business(plan=plan)
        txn = make_transaction(business)
        # Backdate created_at (the import timestamp) into last month,
        # simulating a transaction actually imported previously --
        # `date` (the sale date) is left alone since it's a separate,
        # user-supplied field the cap does not key off of.
        last_month_end = date.today().replace(day=1) - timedelta(days=1)
        txn.created_at = datetime(
            last_month_end.year, last_month_end.month, last_month_end.day, tzinfo=timezone.utc
        )
        db_session.commit()

        check_max_transactions_this_month(db_session, business)  # should not raise


class TestGetSubscription:
    def test_business_with_no_subscription_row_gets_a_free_plan_auto_created(
        self, db_session, make_user, make_plan
    ):
        # Defensive fallback for a business that somehow has no
        # Subscription row (shouldn't happen via the normal create-business
        # flow, which always creates one -- but get_subscription must never
        # raise just because that invariant was somehow violated).
        from app.models.business import Business

        # This test's own DB is built via create_all (see conftest.py),
        # not the Alembic migration chain -- so the "free" plan that
        # migration 0012_billing seeds in a real deployment doesn't exist
        # here automatically; create it explicitly so get_subscription's
        # fallback (which looks up Plan.key == "free") has something to find.
        make_plan(key="free")
        user = make_user()
        business = Business(owner_id=user.id, name="No Subscription Yet")
        db_session.add(business)
        db_session.commit()
        db_session.refresh(business)

        subscription = get_subscription(db_session, business)
        assert subscription is not None
        assert subscription.plan.key == "free"
