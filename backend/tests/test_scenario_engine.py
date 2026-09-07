"""
Tests for app.services.scenario_engine -- the business-decision simulator's
math (Step 10, Batch 10.12, requirement #15).

Two layers tested separately, matching how the module itself is
structured: the pure aggregation/scaling functions (no DB, exact
hand-computed expected values) and run_scenario() end-to-end against
real seeded transactions (needs a DB session).
"""
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.schemas.simulation import ScenarioParameters, ScenarioType, ScopeType
from app.services.scenario_engine import (
    _Row,
    _aggregate,
    _apply_price_change,
    _apply_volume_change,
    _matches_scope,
    run_scenario,
)


def _row(product="Widget", category=None, quantity="1", selling_price="10.00", cost_price="4.00") -> _Row:
    return _Row(
        product=product,
        category=category,
        quantity=Decimal(quantity),
        selling_price=Decimal(selling_price),
        cost_price=Decimal(cost_price),
    )


class TestAggregate:
    def test_revenue_cost_profit_and_margin_are_computed_correctly(self):
        rows = [
            _row(quantity="2", selling_price="10.00", cost_price="4.00"),  # revenue 20, cost 8
            _row(quantity="3", selling_price="5.00", cost_price="2.00"),  # revenue 15, cost 6
        ]
        metrics = _aggregate(rows)
        assert metrics.revenue == Decimal("35.00")
        assert metrics.total_cost == Decimal("14.00")
        assert metrics.gross_profit == Decimal("21.00")
        assert metrics.units_sold == Decimal("5")
        # 21/35 * 100 = 60%
        assert metrics.profit_margin == Decimal("60")

    def test_empty_row_list_yields_all_zeros_not_a_division_error(self):
        metrics = _aggregate([])
        assert metrics.revenue == 0
        assert metrics.total_cost == 0
        assert metrics.gross_profit == 0
        assert metrics.units_sold == 0
        # Zero revenue must short-circuit to a 0% margin rather than
        # attempting a division by zero.
        assert metrics.profit_margin == 0


class TestMatchesScope:
    def test_business_scope_matches_every_row_regardless_of_product_or_category(self):
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(10))
        assert _matches_scope(_row(product="Anything", category="Any"), params) is True

    def test_product_scope_matches_only_the_named_product_case_insensitively(self):
        params = ScenarioParameters(
            scope_type=ScopeType.PRODUCT, scope_value="Widget", change_percentage=Decimal(10)
        )
        assert _matches_scope(_row(product="widget"), params) is True
        assert _matches_scope(_row(product="  WIDGET  "), params) is True
        assert _matches_scope(_row(product="Gadget"), params) is False

    def test_category_scope_matches_only_the_named_category(self):
        params = ScenarioParameters(
            scope_type=ScopeType.CATEGORY, scope_value="Toys", change_percentage=Decimal(10)
        )
        assert _matches_scope(_row(category="Toys"), params) is True
        assert _matches_scope(_row(category="Electronics"), params) is False
        assert _matches_scope(_row(category=None), params) is False


class TestApplyPriceChange:
    def test_price_increase_scales_selling_price_and_leaves_quantity_and_cost_untouched(self):
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(10))
        rows = [_row(quantity="5", selling_price="10.00", cost_price="4.00")]
        adjusted = _apply_price_change(rows, params, "selling_price")
        assert adjusted[0].selling_price == Decimal("11.000")
        assert adjusted[0].quantity == Decimal("5")
        assert adjusted[0].cost_price == Decimal("4.00")

    def test_price_decrease_scales_down(self):
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(-20))
        rows = [_row(selling_price="10.00")]
        adjusted = _apply_price_change(rows, params, "selling_price")
        assert adjusted[0].selling_price == Decimal("8.000")

    def test_cost_price_field_selector_scales_cost_not_selling_price(self):
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(10))
        rows = [_row(selling_price="10.00", cost_price="4.00")]
        adjusted = _apply_price_change(rows, params, "cost_price")
        assert adjusted[0].cost_price == Decimal("4.400")
        assert adjusted[0].selling_price == Decimal("10.00")

    def test_rows_outside_scope_are_returned_completely_unchanged(self):
        params = ScenarioParameters(
            scope_type=ScopeType.PRODUCT, scope_value="Widget", change_percentage=Decimal(50)
        )
        rows = [_row(product="Gadget", selling_price="10.00")]
        adjusted = _apply_price_change(rows, params, "selling_price")
        assert adjusted[0].selling_price == Decimal("10.00")


class TestApplyVolumeChange:
    def test_volume_increase_scales_quantity_and_leaves_prices_untouched(self):
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(25))
        rows = [_row(quantity="4", selling_price="10.00", cost_price="4.00")]
        adjusted = _apply_volume_change(rows, params)
        assert adjusted[0].quantity == Decimal("5.00")
        assert adjusted[0].selling_price == Decimal("10.00")
        assert adjusted[0].cost_price == Decimal("4.00")

    def test_volume_decrease_of_exactly_100_percent_zeroes_out_quantity(self):
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(-100))
        rows = [_row(quantity="4")]
        adjusted = _apply_volume_change(rows, params)
        assert adjusted[0].quantity == Decimal("0.00")


class TestRunScenarioEndToEnd:
    """Seeds real transactions and runs the actual entry point every
    route/AI tool calls -- these are the numbers a business owner sees
    on screen, so they're checked against hand-computed expected values,
    not just "does it run without raising"."""

    def test_selling_price_increase_matches_hand_computed_revenue_and_profit(
        self, db_session, make_business, make_transaction
    ):
        business = make_business()
        make_transaction(business, quantity="10", selling_price="10.00", cost_price="4.00")
        # current: revenue 100, cost 40, profit 60
        # simulated (+10% price): revenue 110, cost 40 (unchanged), profit 70

        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(10))
        results, assumptions = run_scenario(
            db_session, business, ScenarioType.SELLING_PRICE_CHANGE, params,
            date.today(), date.today(),
        )

        assert results.current.revenue == Decimal("100.00")
        assert results.current.gross_profit == Decimal("60.00")
        assert results.simulated.revenue == Decimal("110.000")
        assert results.simulated.total_cost == Decimal("40.00")
        assert results.simulated.gross_profit == Decimal("70.000")
        assert len(assumptions) > 0

    def test_sales_volume_decrease_matches_hand_computed_units_and_revenue(
        self, db_session, make_business, make_transaction
    ):
        business = make_business()
        make_transaction(business, quantity="20", selling_price="5.00", cost_price="2.00")
        # current: revenue 100, units 20
        # simulated (-25% volume): units 15, revenue 75, cost 30

        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(-25))
        results, _ = run_scenario(
            db_session, business, ScenarioType.SALES_VOLUME_CHANGE, params,
            date.today(), date.today(),
        )

        assert results.current.units_sold == Decimal("20")
        assert results.simulated.units_sold == Decimal("15.00")
        assert results.simulated.revenue == Decimal("75.000")
        assert results.simulated.total_cost == Decimal("30.000")

    def test_product_scoped_change_leaves_other_products_untouched(
        self, db_session, make_business, make_transaction
    ):
        business = make_business()
        make_transaction(business, product="Widget", quantity="10", selling_price="10.00", cost_price="4.00")
        make_transaction(business, product="Gadget", quantity="10", selling_price="10.00", cost_price="4.00")
        # current combined revenue: 200. Only Widget's price rises 10%
        # (+10 on its 100) -> simulated combined revenue should be 210,
        # not 220 (which is what a business-wide scope would produce).

        params = ScenarioParameters(
            scope_type=ScopeType.PRODUCT, scope_value="Widget", change_percentage=Decimal(10)
        )
        results, _ = run_scenario(
            db_session, business, ScenarioType.SELLING_PRICE_CHANGE, params,
            date.today(), date.today(),
        )

        assert results.current.revenue == Decimal("200.00")
        assert results.simulated.revenue == Decimal("210.000")

    def test_end_date_before_start_date_is_rejected(self, db_session, make_business):
        business = make_business()
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(10))
        with pytest.raises(ValidationError):
            run_scenario(
                db_session, business, ScenarioType.SELLING_PRICE_CHANGE, params,
                date(2026, 2, 1), date(2026, 1, 1),
            )

    def test_change_percentage_of_negative_100_or_less_is_rejected(self, db_session, make_business):
        # A -100% or worse change would drive a price or quantity
        # negative, which has no business meaning.
        business = make_business()
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(-150))
        with pytest.raises(ValidationError):
            run_scenario(
                db_session, business, ScenarioType.SELLING_PRICE_CHANGE, params,
                date.today(), date.today(),
            )

    def test_no_transactions_in_range_yields_zero_metrics_not_an_error(
        self, db_session, make_business
    ):
        business = make_business()
        params = ScenarioParameters(scope_type=ScopeType.BUSINESS, change_percentage=Decimal(10))
        results, assumptions = run_scenario(
            db_session, business, ScenarioType.SELLING_PRICE_CHANGE, params,
            date.today(), date.today(),
        )
        assert results.current.revenue == 0
        assert results.simulated.revenue == 0
        assert any("no transactions" in a.lower() for a in assumptions)
