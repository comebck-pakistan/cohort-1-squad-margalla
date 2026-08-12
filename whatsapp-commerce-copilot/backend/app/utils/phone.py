"""Phone-number normalization and validation for WhatsApp linking.

Shared rules (kept identical in the gateway and dashboard implementations):
  - Trim whitespace.
  - Remove a single optional leading "+".
  - Remove spaces, hyphens, and parentheses.
  - The remaining value must be digits only (letters/other chars are rejected).
  - Require 8-15 digits (an international number with country code).
  - Never auto-add a country code.

The message is deliberately generic and safe to show a user; it never echoes
the raw input back (avoids leaking a full phone number in error surfaces).
"""
import re

PHONE_HELP_MESSAGE = (
    "Enter an international phone number with country code, for example 923001234567."
)

_SEPARATORS = re.compile(r"[\s()\-]")
_DIGITS_ONLY = re.compile(r"^[0-9]+$")


def normalize_phone_number(raw: str | None) -> str | None:
    """Normalize a user-entered phone number to digits only.

    Returns:
        - ``None`` when no phone number was provided (empty / ``None``); this is
          the QR path and must not be treated as an error.
        - The normalized digits string when the input is a valid number.

    Raises:
        ValueError(PHONE_HELP_MESSAGE): when a value is present but invalid.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    # Remove separators first, then a single leading "+" (handles "(+92) 300...").
    stripped = _SEPARATORS.sub("", s)
    if stripped.startswith("+"):
        stripped = stripped[1:]
    if not _DIGITS_ONLY.match(stripped) or not (8 <= len(stripped) <= 15):
        raise ValueError(PHONE_HELP_MESSAGE)
    return stripped
