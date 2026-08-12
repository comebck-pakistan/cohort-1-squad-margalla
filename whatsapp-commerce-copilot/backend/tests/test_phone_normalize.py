"""Unit tests for phone-number normalization (WhatsApp linking)."""
import pytest
from app.utils.phone import normalize_phone_number, PHONE_HELP_MESSAGE


@pytest.mark.parametrize("raw,expected", [
    ("+92 300-1234567", "923001234567"),
    ("(+92) 300 1234567", "923001234567"),
    ("923001234567", "923001234567"),
    ("  923001234567  ", "923001234567"),
    ("12345678", "12345678"),          # 8 digits (min)
    ("123456789012345", "123456789012345"),  # 15 digits (max)
])
def test_valid_numbers_normalize_to_digits(raw, expected):
    assert normalize_phone_number(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_returns_none(raw):
    assert normalize_phone_number(raw) is None


@pytest.mark.parametrize("raw", [
    "92abc1234567",     # letters
    "92300$1234",       # symbol
    "92.300.1234567",   # dots not an allowed separator
    "1234567",          # 7 digits (too short)
    "1234567890123456", # 16 digits (too long)
])
def test_invalid_numbers_raise(raw):
    with pytest.raises(ValueError) as exc:
        normalize_phone_number(raw)
    assert exc.value.args[0] == PHONE_HELP_MESSAGE
