"""
Tests for app.services.microsoft_graph's Excel serial-date conversion
(Step 11, audit finding: Microsoft Graph's usedRange.values returns a
date-formatted cell as its raw underlying serial number, not a display
string -- confirmed against real-world reports of the same behavior in
other Graph-based integrations, e.g. Power Automate's Excel connector
needing an explicit opt-in for ISO-formatted dates). Passed straight to
import_pipeline._parse_date_value, a raw serial silently misparses as a
nanosecond-scale Unix timestamp and lands on 1970-01-01 with no error at
all -- a wrong date on every row, with nothing to signal it happened.

Pure logic -- no network, no database.
"""
from app.services.microsoft_graph import _convert_date_serials, _is_date_number_format


class TestIsDateNumberFormat:
    def test_general_and_text_formats_are_not_dates(self):
        assert _is_date_number_format("General") is False
        assert _is_date_number_format("@") is False
        assert _is_date_number_format("") is False
        assert _is_date_number_format(None) is False

    def test_plain_numeric_formats_are_not_dates(self):
        assert _is_date_number_format("0.00") is False
        assert _is_date_number_format("#,##0") is False
        assert _is_date_number_format("0%") is False
        assert _is_date_number_format("0.00E+00") is False

    def test_currency_format_is_not_a_date_even_though_it_has_no_date_tokens(self):
        # Regression check specifically for the false-positive direction:
        # a "$" currency format must never be mistaken for a date just
        # because it's a custom/complex format string.
        assert _is_date_number_format("$#,##0.00") is False

    def test_common_date_and_time_formats_are_recognized(self):
        assert _is_date_number_format("yyyy-mm-dd") is True
        assert _is_date_number_format("m/d/yyyy") is True
        assert _is_date_number_format("dd/mm/yyyy") is True
        assert _is_date_number_format("h:mm:ss AM/PM") is True
        assert _is_date_number_format("m/d/yyyy h:mm") is True

    def test_bracketed_locale_and_color_sections_are_ignored(self):
        # A conditional/locale bracket can contain letters that would
        # otherwise look like date tokens (or, here, doesn't) -- either
        # way the bracket's contents must not affect the result, only
        # the format tokens outside it.
        assert _is_date_number_format("[$-409]m/d/yyyy;@") is True
        assert _is_date_number_format("[Red]#,##0") is False

    def test_quoted_literal_text_is_ignored(self):
        # The quoted "units" text contains no date letters here, but the
        # point is that quoted literal text is stripped before checking
        # at all -- a format like '0.00" ml"' must not be misread just
        # because of what's inside the quotes.
        assert _is_date_number_format('0.00" ml"') is False


class TestConvertDateSerials:
    def test_date_formatted_serial_is_converted_to_the_correct_iso_date(self):
        # 46037 is 2026-01-15 under Excel's date-serial system.
        values = [[46037, "Widget", 10, 9.99]]
        number_formats = [["m/d/yyyy", "General", "General", "$#,##0.00"]]
        result = _convert_date_serials(values, number_formats)
        assert result[0][0] == "2026-01-15"

    def test_non_date_numeric_columns_are_never_touched(self):
        # The bug this guards against is specifically a false negative
        # (a real date column left as a raw serial) -- this test guards
        # the opposite direction: quantity/price columns must never be
        # reinterpreted as dates just because they're also numeric.
        values = [[46037, "Widget", 10, 9.99]]
        number_formats = [["m/d/yyyy", "General", "General", "$#,##0.00"]]
        result = _convert_date_serials(values, number_formats)
        assert result[0][2] == 10
        assert result[0][3] == 9.99

    def test_text_and_blank_cells_are_left_exactly_as_is(self):
        values = [["Widget", None, ""]]
        number_formats = [["General", "General", "General"]]
        result = _convert_date_serials(values, number_formats)
        assert result == values

    def test_multiple_rows_convert_independently(self):
        values = [[46037, 1], [46038, 2], [46039, 3]]
        number_formats = [["m/d/yyyy", "General"]] * 3
        result = _convert_date_serials(values, number_formats)
        assert [row[0] for row in result] == ["2026-01-15", "2026-01-16", "2026-01-17"]

    def test_a_date_formatted_cell_that_is_already_text_is_left_alone(self):
        # Someone typed a date as literal text into a cell that Excel
        # still happens to have formatted as a date -- Graph would
        # return that as a string, not a number, so the isinstance
        # check in _convert_date_serials must leave it untouched rather
        # than attempt (and fail) a numeric conversion.
        values = [["15 Jan 2026"]]
        number_formats = [["m/d/yyyy"]]
        result = _convert_date_serials(values, number_formats)
        assert result[0][0] == "15 Jan 2026"

    def test_boolean_values_are_never_mistaken_for_numeric_serials(self):
        # bool is a subclass of int in Python -- isinstance(True, int) is
        # True -- so this is a deliberate, explicit guard in
        # _convert_date_serials, not an incidental pass.
        values = [[True]]
        number_formats = [["m/d/yyyy"]]
        result = _convert_date_serials(values, number_formats)
        assert result[0][0] is True
