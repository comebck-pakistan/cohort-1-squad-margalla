"""Tests for conversation memory and follow-up resolution."""
import pytest
from app.services.conversation_manager import ConversationManager
from app.models.conversation import Conversation


@pytest.fixture
def manager():
    return ConversationManager()


@pytest.fixture
def conversation_with_product():
    """Conversation where customer asked about a black kurta."""
    conv = Conversation(
        id="conv-001",
        store_id="test-store",
        customer_id="cust-001",
        current_product_id="prod-kurta-001",
        current_variant_id=None,
        selected_color="black",
        selected_size=None,
        is_ai_controlled=True,
    )
    return conv


@pytest.fixture
def conversation_with_clarification():
    """Conversation where customer was presented numbered choices."""
    conv = Conversation(
        id="conv-002",
        store_id="test-store",
        customer_id="cust-001",
        pending_clarification="product_selection",
        is_ai_controlled=True,
    )
    conv.set_clarification_candidates_list([
        "prod-snk-casual-001",
        "prod-snk-run-001",
        "prod-snk-leather-001",
    ])
    return conv


class TestFollowupResolution:
    """Test follow-up message resolution from context."""

    def test_followup_uses_current_product(self, manager, conversation_with_product):
        """'Medium ki price?' should resolve to the current product (black kurta)."""
        resolved = manager.resolve_followup(
            conversation_with_product,
            "medium ki price?",
            {"size": "medium"},
        )
        assert resolved.get("product_id") == "prod-kurta-001"
        assert resolved.get("from_context") is True
        assert resolved.get("color") == "black"  # From context

    def test_followup_new_product_overrides_context(self, manager, conversation_with_product):
        """If message has a new product query, don't use context."""
        resolved = manager.resolve_followup(
            conversation_with_product,
            "sneakers dikhao",
            {"product_query": "sneakers", "category": "sneakers"},
        )
        assert "product_id" not in resolved  # Should not use context

    def test_followup_fills_missing_color(self, manager, conversation_with_product):
        """Follow-up with just size should fill color from context."""
        resolved = manager.resolve_followup(
            conversation_with_product,
            "large size hai?",
            {"size": "large"},
        )
        assert resolved.get("color") == "black"

    def test_followup_with_explicit_color_overrides(self, manager, conversation_with_product):
        """Follow-up with explicit color should use the new color, not context."""
        resolved = manager.resolve_followup(
            conversation_with_product,
            "white mein hai?",
            {"color": "white"},
        )
        assert resolved.get("product_id") == "prod-kurta-001"
        # Color should NOT be from context because entity has explicit color
        assert "color" not in resolved


class TestClarificationResolution:
    """Test numbered choice disambiguation."""

    def test_select_first(self, manager, conversation_with_clarification):
        resolved = manager.resolve_followup(
            conversation_with_clarification,
            "1",
            {},
        )
        assert resolved.get("product_id") == "prod-snk-casual-001"

    def test_select_second(self, manager, conversation_with_clarification):
        resolved = manager.resolve_followup(
            conversation_with_clarification,
            "2",
            {},
        )
        assert resolved.get("product_id") == "prod-snk-run-001"

    def test_select_third(self, manager, conversation_with_clarification):
        resolved = manager.resolve_followup(
            conversation_with_clarification,
            "3",
            {},
        )
        assert resolved.get("product_id") == "prod-snk-leather-001"

    def test_select_by_word_second(self, manager, conversation_with_clarification):
        resolved = manager.resolve_followup(
            conversation_with_clarification,
            "second one",
            {},
        )
        assert resolved.get("product_id") == "prod-snk-run-001"

    def test_select_by_roman_urdu_pehla(self, manager, conversation_with_clarification):
        resolved = manager.resolve_followup(
            conversation_with_clarification,
            "pehla wala",
            {},
        )
        assert resolved.get("product_id") == "prod-snk-casual-001"

    def test_select_by_roman_urdu_doosra(self, manager, conversation_with_clarification):
        resolved = manager.resolve_followup(
            conversation_with_clarification,
            "doosra dikhao",
            {},
        )
        assert resolved.get("product_id") == "prod-snk-run-001"


class TestContextUpdate:
    """Test that apply_context updates conversation state."""

    def test_updates_product(self, manager):
        from app.services.response_builder import ProcessedResponse
        conv = Conversation(id="test", store_id="s", customer_id="c")
        response = ProcessedResponse(
            message="test",
            intent="product_search",
            confidence=0.9,
            matched_product_id="prod-001",
            matched_variant_id="var-001",
            extracted_entities={"color": "red", "size": "L"},
        )
        manager.apply_context(conv, response)
        assert conv.current_product_id == "prod-001"
        assert conv.current_variant_id == "var-001"
        assert conv.selected_color == "red"
        assert conv.selected_size == "L"

    def test_stores_clarification_candidates(self, manager):
        from app.services.response_builder import ProcessedResponse
        conv = Conversation(id="test", store_id="s", customer_id="c")
        response = ProcessedResponse(
            message="Which one?",
            intent="product_search",
            confidence=0.5,
            clarification_options=[
                {"number": 1, "product_id": "prod-a", "name": "A"},
                {"number": 2, "product_id": "prod-b", "name": "B"},
            ],
            needs_clarification=True,
        )
        manager.apply_context(conv, response)
        assert conv.pending_clarification == "product_selection"
        candidates = conv.get_clarification_candidates_list()
        assert candidates == ["prod-a", "prod-b"]

    def test_clears_clarification_on_match(self, manager):
        from app.services.response_builder import ProcessedResponse
        conv = Conversation(
            id="test", store_id="s", customer_id="c",
            pending_clarification="product_selection",
        )
        response = ProcessedResponse(
            message="Found it",
            intent="product_search",
            confidence=0.9,
            matched_product_id="prod-001",
        )
        manager.apply_context(conv, response)
        assert conv.pending_clarification is None
        assert conv.clarification_candidates is None
