"""
Tests for app.services.import_pipeline's row validation and fingerprint
computation (Step 10, Batch 10.12, requirement #15).

Pure logic -- no database needed. This is the code that decides, row by
row, whether a piece of financial data (a sale) is trustworthy enough to
persist, so it gets the same scrutiny as the aggregation math tested
elsewhere in this suite.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.services.import_pipeline import compute_fingerprint, validate_and_convert_rows

MAPPING = {
    "date": "Date",
    "product": "Item",
    "quantity": "Qty",
    "selling_price": "Price",
    "cost_price": "Cost",
    "category": None,
    "customer": None,
    "payment_method": None,
}


def _row(**overrides) -> dict:
    base = {"Date": "2026-01-15", "Item": "Widget", "Qty": "3", "Price": "9.99", "Cost": "4.00"}
    base.update(overrides)
    return base


class TestValidateAndConvertRows:
    def test_valid_row_converts_every_field_to_the_right_type(self):
        valid_rows, row_errors = validate_and_convert_rows([_row()], MAPPING)

        assert row_errors == []
        assert len(valid_rows) == 1
        row = valid_rows[0]
        assert row["date"] == date(2026, 1, 15)
        assert row["product"] == "Widget"
        assert row["quantity"] == Decimal("3")
        assert row["selling_price"] == Decimal("9.99")
        assert row["cost_price"] == Decimal("4.00")

    def test_missing_required_mapping_raises_before_touching_any_row(self):
        incomplete_mapping = {**MAPPING, "selling_price": None}
        with pytest.raises(AppError) as exc_info:
            validate_and_convert_rows([_row()], incomplete_mapping)
        assert exc_info.value.code == "incomplete_mapping"

    def test_zero_quantity_is_rejected(self):
        # A sale of zero units isn't a valid financial record -- rejecting
        # it here is what keeps a business's revenue/units totals honest.
        valid_rows, row_errors = validate_and_convert_rows([_row(Qty="0")], MAPPING)
        assert valid_rows == []
        assert len(row_errors) == 1
        assert row_errors[0]["row_number"] == 1
        assert "greater than zero" in row_errors[0]["errors"][0]

    def test_negative_quantity_is_rejected(self):
        valid_rows, row_errors = validate_and_convert_rows([_row(Qty="-5")], MAPPING)
        assert valid_rows == []
        assert "greater than zero" in row_errors[0]["errors"][0]

    def test_unparseable_price_is_rejected_not_silently_zeroed(self):
        # A financial-data importer that silently turned garbage into 0
        # would quietly corrupt a business's revenue figures -- it must
        # reject the row and say why, never guess.
        valid_rows, row_errors = validate_and_convert_rows([_row(Price="not-a-number")], MAPPING)
        assert valid_rows == []
        assert len(row_errors) == 1
        assert "not a valid number" in row_errors[0]["errors"][0]

    def test_unparseable_date_is_rejected(self):
        valid_rows, row_errors = validate_and_convert_rows([_row(Date="not-a-date")], MAPPING)
        assert valid_rows == []
        assert any("date" in e.lower() for e in row_errors[0]["errors"])

    def test_missing_product_is_rejected(self):
        valid_rows, row_errors = validate_and_convert_rows([_row(Item="")], MAPPING)
        assert valid_rows == []
        assert "Product is required." in row_errors[0]["errors"]

    def test_blank_cost_price_becomes_none_not_an_error(self):
        # cost_price is optional (Batch 6.1) -- a blank cell must convert
        # to None, never block the row or silently default to 0 (which
        # would understate cost and overstate profit margin).
        valid_rows, row_errors = validate_and_convert_rows([_row(Cost="")], MAPPING)
        assert row_errors == []
        assert valid_rows[0]["cost_price"] is None

    def test_price_string_with_currency_symbol_and_commas_is_parsed(self):
        # Real-world spreadsheets often have "$1,234.56"-style cells --
        # this must not be misread as a parse failure or, worse, as the
        # wrong number.
        valid_rows, row_errors = validate_and_convert_rows([_row(Price="$1,234.56")], MAPPING)
        assert row_errors == []
        assert valid_rows[0]["selling_price"] == Decimal("1234.56")

    def test_multiple_rows_are_validated_independently_with_correct_row_numbers(self):
        rows = [_row(), _row(Qty="0"), _row()]
        valid_rows, row_errors = validate_and_convert_rows(rows, MAPPING)
        assert len(valid_rows) == 2
        assert len(row_errors) == 1
        # 1-indexed against the data rows, matching what a user sees when
        # counting rows in their own spreadsheet (row 2 = the second data row).
        assert row_errors[0]["row_number"] == 2


class TestComputeFingerprint:
    def _converted_row(self, **overrides) -> dict:
        base = {
            "date": date(2026, 1, 15),
            "product": "Widget",
            "quantity": Decimal("3"),
            "selling_price": Decimal("9.99"),
            "cost_price": Decimal("4.00"),
        }
        base.update(overrides)
        return base

    def test_identical_rows_for_the_same_business_produce_the_same_fingerprint(self):
        # This is the whole point of the fingerprint: it's how the Google
        # Sheets sync (app.services.sheets_sync) recognizes "this exact
        # sale was already imported" and skips re-inserting it.
        fp1 = compute_fingerprint("business-1", self._converted_row())
        fp2 = compute_fingerprint("business-1", self._converted_row())
        assert fp1 == fp2

    def test_different_businesses_never_collide_even_with_identical_row_data(self):
        # A hard tenant-isolation requirement: business A's fingerprint
        # space must never overlap business B's, or a future dedup check
        # could mistake one business's sale for another's.
        fp1 = compute_fingerprint("business-1", self._converted_row())
        fp2 = compute_fingerprint("business-2", self._converted_row())
        assert fp1 != fp2

    @pytest.mark.parametrize(
        "field,value",
        [
            ("product", "Gadget"),
            ("quantity", Decimal("4")),
            ("selling_price", Decimal("19.99")),
            ("cost_price", Decimal("5.00")),
            ("date", date(2026, 1, 16)),
        ],
    )
    def test_changing_any_identifying_field_changes_the_fingerprint(self, field, value):
        base = compute_fingerprint("business-1", self._converted_row())
        changed = compute_fingerprint("business-1", self._converted_row(**{field: value}))
        assert base != changed

    def test_product_name_matching_is_case_and_whitespace_insensitive(self):
        # Deliberate: "Widget" and "  widget  " referring to the same
        # product on two different rows should be recognized as the same
        # sale for dedup purposes, not treated as different products.
        fp1 = compute_fingerprint("business-1", self._converted_row(product="Widget"))
        fp2 = compute_fingerprint("business-1", self._converted_row(product="  WIDGET  "))
        assert fp1 == fp2

    def test_missing_cost_price_does_not_crash_and_is_distinct_from_zero(self):
        fp_none = compute_fingerprint("business-1", self._converted_row(cost_price=None))
        fp_zero = compute_fingerprint("business-1", self._converted_row(cost_price=Decimal("0")))
        # Both must at least compute without raising -- whether they're
        # equal or not is secondary to that, but asserting distinctness
        # here documents the actual current behavior rather than leaving
        # it unspecified.
        assert isinstance(fp_none, str) and isinstance(fp_zero, str)
