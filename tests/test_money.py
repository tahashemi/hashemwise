"""Parsing and formatting money. Nothing here may involve a float."""

import pytest

from src.money import (
    AmountTooLarge,
    InvalidAmount,
    NonPositiveAmount,
    TooManyDecimals,
    format_amount,
    normalize_digits,
    parse_amount,
)


class TestNormalizeDigits:
    def test_persian_digits(self):
        assert normalize_digits("۱۲۳۴۵۶۷۸۹۰") == "1234567890"

    def test_arabic_indic_digits(self):
        assert normalize_digits("١٢٣٤٥٦٧٨٩٠") == "1234567890"

    def test_persian_decimal_and_thousands_marks(self):
        # U+066B arabic decimal separator, U+066C arabic thousands separator
        assert normalize_digits("۱٬۲۳۴٫۵۶") == "1,234.56"

    def test_ascii_passthrough(self):
        assert normalize_digits("1,234.56") == "1,234.56"


class TestParseZeroDecimalCurrency:
    def test_plain_integer(self):
        assert parse_amount("1250000", "IRT") == 1250000

    def test_thousands_separators_stripped(self):
        assert parse_amount("1,250,000", "IRT") == 1250000

    def test_spaces_stripped(self):
        assert parse_amount(" 1 250 000 ", "IRT") == 1250000

    def test_persian_digits(self):
        assert parse_amount("۱۲۵۰۰۰۰", "IRT") == 1250000

    def test_persian_digits_with_persian_separator(self):
        assert parse_amount("۱٬۲۵۰٬۰۰۰", "IRT") == 1250000

    def test_trailing_zero_decimal_is_accepted(self):
        # "1250.0" is exactly representable in a 0-decimal currency.
        assert parse_amount("1250.0", "IRT") == 1250

    def test_real_fraction_is_rejected(self):
        # Toman has no sub-unit; 12.5 T is not a thing.
        with pytest.raises(TooManyDecimals):
            parse_amount("12.5", "IRT")


class TestParseTwoDecimalCurrency:
    def test_whole_number(self):
        assert parse_amount("12", "USD") == 1200

    def test_one_decimal(self):
        assert parse_amount("12.5", "USD") == 1250

    def test_two_decimals(self):
        assert parse_amount("12.34", "USD") == 1234

    def test_three_decimals_rejected(self):
        with pytest.raises(TooManyDecimals):
            parse_amount("12.345", "USD")

    def test_the_classic_float_trap(self):
        # 0.1 + 0.2 != 0.3 in binary floating point. Integer minor units make
        # this exact, which is the entire reason this module exists.
        assert parse_amount("0.1", "USD") + parse_amount("0.2", "USD") == parse_amount("0.3", "USD")

    def test_no_float_rounding_on_awkward_values(self):
        # int(float("1.15") * 100) == 114 on CPython. We must get 115.
        assert parse_amount("1.15", "USD") == 115
        assert parse_amount("8.20", "USD") == 820

    def test_leading_decimal_point(self):
        assert parse_amount(".5", "USD") == 50


class TestParseRejections:
    @pytest.mark.parametrize("text", ["", "   ", "abc", "12abc", "1.2.3", "--5", "1e5", "٫"])
    def test_garbage_rejected(self, text):
        with pytest.raises(InvalidAmount):
            parse_amount(text, "USD")

    @pytest.mark.parametrize("text", ["0", "0.00", "-5", "-0.01"])
    def test_non_positive_rejected(self, text):
        with pytest.raises(NonPositiveAmount):
            parse_amount(text, "USD")

    def test_absurdly_large_rejected(self):
        with pytest.raises(AmountTooLarge):
            parse_amount("9" * 30, "IRT")

    def test_none_rejected(self):
        with pytest.raises(InvalidAmount):
            parse_amount(None, "USD")  # type: ignore[arg-type]


class TestFormat:
    def test_toman_suffix_english(self):
        assert format_amount(1250000, "IRT", "en") == "1,250,000 T"

    def test_usd_prefix_english(self):
        assert format_amount(1234, "USD", "en") == "$12.34"

    def test_usd_pads_fraction(self):
        assert format_amount(1200, "USD", "en") == "$12.00"
        assert format_amount(5, "USD", "en") == "$0.05"

    def test_negative_sign_leads(self):
        assert format_amount(-1234, "USD", "en") == "-$12.34"
        assert format_amount(-1250000, "IRT", "en") == "-1,250,000 T"

    def test_zero(self):
        assert format_amount(0, "USD", "en") == "$0.00"
        assert format_amount(0, "IRT", "en") == "0 T"

    def test_persian_suffixes_regardless_of_currency(self):
        assert format_amount(1234, "USD", "fa").endswith("دلار")
        assert format_amount(1250000, "IRT", "fa").endswith("تومان")

    def test_persian_uses_western_digits_for_legibility(self):
        assert "1,250,000" in format_amount(1250000, "IRT", "fa")


class TestRoundTrip:
    @pytest.mark.parametrize("code", ["IRT", "USD", "EUR", "GBP"])
    @pytest.mark.parametrize("minor", [1, 5, 99, 100, 1234, 999999, 1250000])
    def test_format_then_parse_is_identity(self, code, minor):
        # Strip the currency symbol, re-parse, and we must land on the same int.
        text = format_amount(minor, code, "en").replace("$", "").replace("€", "")
        text = text.replace("£", "").replace("T", "").strip()
        assert parse_amount(text, code) == minor
