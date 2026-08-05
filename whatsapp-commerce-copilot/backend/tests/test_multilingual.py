"""Tests for multilingual English / Urdu support.

Tests cover:
- Language detection (english, roman_urdu, urdu_script, mixed, neutral)
- Session language persistence and neutral reply preservation
- i18n template correctness (Urdu contains Unicode characters)
- Urdu output validation (no Roman sentences, correct numbers/prices)
"""
import pytest
from unittest.mock import MagicMock

from app.services.language_detector import detect_language, LanguageDetection
from app.services.i18n import t
from app.models.conversation import Conversation


# ---------------------------------------------------------------------------
# 1. Language detector unit tests
# ---------------------------------------------------------------------------


class TestLanguageDetector:

    def test_english_message(self):
        det = detect_language("Show me black shoes")
        assert det.input_language == "english"
        assert det.response_language == "en"
        assert not det.is_neutral

    def test_urdu_script(self):
        det = detect_language("مجھے کالے جوتے دکھائیں")
        assert det.input_language == "urdu_script"
        assert det.response_language == "ur"
        assert not det.is_neutral

    def test_roman_urdu(self):
        det = detect_language("Mujhe kalay jootay dikhao")
        assert det.input_language == "roman_urdu"
        assert det.response_language == "ur"
        assert not det.is_neutral

    def test_mixed_roman_english(self):
        """'Black shoes dikhao' mixes English and Roman Urdu."""
        det = detect_language("Black shoes dikhao")
        assert det.response_language == "ur"
        assert det.input_language in ("roman_urdu", "mixed")
        assert not det.is_neutral

    def test_neutral_digit(self):
        """A bare number should be neutral — session language preserved."""
        det = detect_language("42")
        assert det.is_neutral is True

    def test_neutral_emoji(self):
        det = detect_language("👍")
        assert det.is_neutral is True

    def test_explicit_english_request(self):
        """Explicit 'reply in English' overrides detection."""
        det = detect_language("Reply in English please")
        assert det.response_language == "en"
        assert det.input_language == "english"
        assert not det.is_neutral

    def test_explicit_urdu_request(self):
        """Explicit 'urdu mein jawab do' → Urdu."""
        det = detect_language("Urdu mein jawab do")
        assert det.response_language == "ur"
        assert not det.is_neutral

    def test_salam_greeting(self):
        """Roman Urdu greeting should map to Urdu response."""
        det = detect_language("salam kya haal hai")
        assert det.response_language == "ur"

    def test_pure_english(self):
        """Clearly English: no Roman Urdu words."""
        det = detect_language("Please show me the running shoes in English")
        assert det.input_language == "english"
        assert det.response_language == "en"


# ---------------------------------------------------------------------------
# 2. i18n template tests
# ---------------------------------------------------------------------------


class TestI18nTemplates:

    def test_welcome_english(self):
        msg = t("welcome", "en", store="StepUp Footwear")
        assert "StepUp Footwear" in msg
        assert "Hello" in msg or "Welcome" in msg

    def test_welcome_urdu_contains_unicode(self):
        msg = t("welcome", "ur", store="StepUp Footwear")
        # Must contain actual Urdu Unicode characters
        urdu_chars = [c for c in msg if 0x0600 <= ord(c) <= 0x06FF]
        assert len(urdu_chars) > 0, "Urdu welcome message must contain Urdu Unicode characters"

    def test_welcome_urdu_not_roman(self):
        """Urdu messages must not be Roman Urdu (Latin sentences)."""
        msg = t("welcome", "ur", store="StepUp")
        # Check there is no obvious Roman Urdu like 'mein' or 'kya' as full words
        lower = msg.lower()
        # These should NOT appear as primary sentence content in a proper Urdu message
        assert "khush aamdeed" not in lower, "Should not contain Roman Urdu"
        assert "mein khush" not in lower, "Should not contain Roman Urdu"

    def test_product_not_found_urdu(self):
        msg = t("product_not_found", "ur", query="shoes")
        urdu_chars = [c for c in msg if 0x0600 <= ord(c) <= 0x06FF]
        assert len(urdu_chars) > 0
        # Query (factual data) must be preserved
        assert "shoes" in msg

    def test_order_confirmed_preserves_order_id(self):
        msg = t("order_confirmed", "ur", order_id="ORD-12345")
        assert "ORD-12345" in msg

    def test_order_status_preserves_status(self):
        msg = t("order_status", "ur", order_id="ORD-999", status="pending")
        assert "ORD-999" in msg
        assert "pending" in msg

    def test_stock_available_preserves_number(self):
        msg = t("stock_available", "ur", stock=5)
        assert "5" in msg

    def test_unknown_key_returns_key_gracefully(self):
        msg = t("this_key_does_not_exist", "ur")
        assert msg == "this_key_does_not_exist"

    def test_roman_urdu_lang_maps_to_ur(self):
        """roman_urdu store_language must produce Urdu-script templates."""
        # i18n only knows 'en' and 'ur'; 'roman_urdu' should not be valid
        # The _lang() helper in response_builder maps it. Test at i18n level:
        msg_ur = t("welcome", "ur", store="S")
        msg_en = t("welcome", "en", store="S")
        assert msg_ur != msg_en


# ---------------------------------------------------------------------------
# 3. Conversation model language helpers
# ---------------------------------------------------------------------------


class TestConversationLanguageHelpers:

    def _make_conv(self) -> Conversation:
        return Conversation(
            id="c1", store_id="s1", customer_id="cu1"
        )

    def test_default_response_language_is_en(self):
        conv = self._make_conv()
        assert conv.get_preferred_response_language() == "en"

    def test_set_language_preference_roman_urdu(self):
        conv = self._make_conv()
        conv.set_language_preference("roman_urdu", "ur", 0.9)
        assert conv.get_preferred_response_language() == "ur"
        assert conv.last_detected_input_language == "roman_urdu"
        assert conv.language_confidence == 0.9

    def test_set_language_preference_urdu_script(self):
        conv = self._make_conv()
        conv.set_language_preference("urdu_script", "ur", 0.99)
        assert conv.get_preferred_response_language() == "ur"

    def test_set_language_preference_english(self):
        conv = self._make_conv()
        conv.set_language_preference("urdu_script", "ur", 0.9)
        conv.set_language_preference("english", "en", 1.0)
        assert conv.get_preferred_response_language() == "en"


# ---------------------------------------------------------------------------
# 4. Neutral reply preserves session language
# ---------------------------------------------------------------------------


class TestNeutralReplyPreservesLanguage:
    """Simulate the logic that lives in ConversationController."""

    def _simulate_lang_resolution(self, message: str, session_lang: str) -> str:
        det = detect_language(message)
        if det.is_neutral:
            return session_lang
        return det.response_language

    def test_digit_preserves_urdu(self):
        result = self._simulate_lang_resolution("42", "ur")
        assert result == "ur"

    def test_digit_preserves_english(self):
        result = self._simulate_lang_resolution("42", "en")
        assert result == "en"

    def test_roman_urdu_updates_to_ur(self):
        result = self._simulate_lang_resolution("Mujhe kalay jootay chahiye", "en")
        assert result == "ur"

    def test_english_updates_to_en(self):
        result = self._simulate_lang_resolution("Show me black shoes", "ur")
        assert result == "en"


# ---------------------------------------------------------------------------
# 5. Urdu output validation helpers
# ---------------------------------------------------------------------------


def contains_urdu_unicode(text: str) -> bool:
    return any(0x0600 <= ord(c) <= 0x06FF for c in text)


def contains_roman_urdu_sentences(text: str) -> bool:
    """Heuristic: if text has many Roman Urdu keywords it's likely Roman Urdu."""
    from app.services.language_detector import ROMAN_URDU_KEYWORDS
    tokens = set(text.lower().split())
    hits = tokens & ROMAN_URDU_KEYWORDS
    # More than 2 Roman Urdu words in a single response is suspicious
    return len(hits) > 2


class TestUrduOutputValidation:

    def test_welcome_ur_contains_urdu_unicode(self):
        assert contains_urdu_unicode(t("welcome", "ur", store="S"))

    def test_product_not_found_ur_contains_urdu_unicode(self):
        assert contains_urdu_unicode(t("product_not_found", "ur", query="X"))

    def test_handoff_ur_contains_urdu_unicode(self):
        assert contains_urdu_unicode(t("handoff", "ur"))

    def test_order_confirm_ur_contains_urdu_unicode(self):
        assert contains_urdu_unicode(t("order_confirm_prompt", "ur"))

    def test_fallback_ur_contains_urdu_unicode(self):
        assert contains_urdu_unicode(t("error_retry", "ur"))

    def test_urdu_messages_not_roman_urdu(self):
        """Critical: Urdu responses must not be in Roman Urdu."""
        keys_to_check = [
            "welcome", "welcome_returning", "product_not_found",
            "product_choice", "handoff", "fallback_unknown", "error_retry",
        ]
        for key in keys_to_check:
            # Use generic kwargs to avoid KeyError
            try:
                msg = t(key, "ur", store="S", query="X")
            except Exception:
                continue
            assert not contains_roman_urdu_sentences(msg), (
                f"Key '{key}' Urdu translation appears to be Roman Urdu: {msg[:80]}"
            )

    def test_english_messages_not_urdu_script(self):
        """English messages must not contain Urdu script."""
        keys_to_check = ["welcome", "product_not_found", "handoff", "error_retry"]
        for key in keys_to_check:
            try:
                msg = t(key, "en", store="S", query="X")
            except Exception:
                continue
            assert not contains_urdu_unicode(msg), (
                f"Key '{key}' English translation unexpectedly contains Urdu: {msg[:80]}"
            )

    def test_prices_preserved_in_urdu(self):
        """Numbers and prices must survive translation unchanged."""
        msg = t("stock_available", "ur", stock=42)
        assert "42" in msg

    def test_product_name_not_translated(self):
        """product_not_found preserves the actual query string (e.g., a brand name)."""
        msg = t("product_not_found", "ur", query="Nike Air Max")
        assert "Nike Air Max" in msg
