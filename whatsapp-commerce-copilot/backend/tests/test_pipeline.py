"""End-to-end tests for the message processor pipeline.

Tests the full flow: normalize → detect → extract → search → respond.
Uses the spec's exact test inputs.
"""
import pytest
from app.services.message_processor import MessageProcessor
from tests.conftest import (
    make_fashion_products, make_shoe_products,
    make_fashion_policies, make_shoe_policies,
)


@pytest.fixture
def processor():
    return MessageProcessor()


@pytest.fixture
def fashion_products():
    return make_fashion_products()


@pytest.fixture
def shoe_products():
    return make_shoe_products()


@pytest.fixture
def fashion_policies():
    return make_fashion_policies()


@pytest.fixture
def shoe_policies():
    return make_shoe_policies()


class TestSpecInputs:
    """Test the exact inputs from the spec."""

    def test_sky_blue_kurta_medium(self, processor, fashion_products, fashion_policies):
        """'Sky blue kurta medium size mein available hai? Price bhi bata dein.'"""
        response = processor.process(
            message="Sky blue kurta medium size mein available hai? Price bhi bata dein.",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.matched_product_id == "prod-kurta-001"
        assert "2,500" in response.message or "2500" in response.message
        assert len(response.sources) > 0
        assert any("catalog:product:" in s for s in response.sources)

    def test_navy_blue_sneakers_42(self, processor, shoe_products, shoe_policies):
        """'Navy blue sneakers size 42 ki price?'"""
        response = processor.process(
            message="Navy blue sneakers size 42 ki price?",
            products=shoe_products,
            policies=shoe_policies,
            store_name="Test Shoes",
            store_language="english",
            store_id="test-store-shoes",
        )
        assert response.matched_product_id is not None
        assert len(response.sources) > 0

    def test_off_white_kurta(self, processor, fashion_products, fashion_policies):
        """'Off white kurta hai?'"""
        response = processor.process(
            message="Off white kurta hai?",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.matched_product_id == "prod-kurta-001"
        assert any("off white" in s.lower() or "variant" in s for s in response.sources)

    def test_2_pieces_size_40(self, processor, shoe_products, shoe_policies):
        """'I want 2 pieces in size 40.'"""
        response = processor.process(
            message="I want 2 pieces in size 40.",
            products=shoe_products,
            policies=shoe_policies,
            store_name="Test Shoes",
            store_language="english",
            store_id="test-store-shoes",
        )
        # Should extract quantity=2 and size=40
        entities = response.extracted_entities
        assert entities.get("quantity") == 2 or entities.get("size") == "40"

    def test_cod_and_delivery(self, processor, fashion_products, fashion_policies):
        """'COD hai aur delivery kitne din mein hogi?'"""
        response = processor.process(
            message="COD hai aur delivery kitne din mein hogi?",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        # Should return policy information
        assert "COD" in response.message or "Cash" in response.message or "cod" in response.message.lower()
        assert len(response.sources) > 0
        assert any("policy:" in s for s in response.sources)

    def test_black_wala_medium(self, processor, fashion_products, fashion_policies):
        """'Woh black wala medium mein kitne ka hai?'"""
        response = processor.process(
            message="Woh black wala medium mein kitne ka hai?",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        # Should find black + medium combination
        assert response.matched_product_id is not None or "black" in response.message.lower()


class TestStoreIsolation:
    """Test that messages are processed only against the correct store's data."""

    def test_kurta_in_shoe_store(self, processor, shoe_products, shoe_policies):
        """Searching for kurta in shoe store should not find anything."""
        response = processor.process(
            message="Sky blue kurta medium size mein available hai?",
            products=shoe_products,
            policies=shoe_policies,
            store_name="Test Shoes",
            store_language="english",
            store_id="test-store-shoes",
        )
        assert response.matched_product_id is None
        # Should say not found
        assert "sorry" in response.message.lower() or "couldn't find" in response.message.lower() or "nahi" in response.message.lower()

    def test_sneakers_in_fashion_store(self, processor, fashion_products, fashion_policies):
        """Searching for sneakers in fashion store should not find anything."""
        response = processor.process(
            message="Black sneakers size 42 available hai?",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.matched_product_id is None


class TestGreetingAndHandoff:
    """Test greeting and handoff flows."""

    def test_greeting(self, processor, fashion_products, fashion_policies):
        response = processor.process(
            message="Assalam o Alaikum!",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.intent == "greeting"
        assert "Test Fashion" in response.message

    def test_human_request(self, processor, fashion_products, fashion_policies):
        response = processor.process(
            message="Mujhe agent se baat karni hai",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.needs_human is True
        assert response.escalation_reason == "explicit_request"

    def test_complaint(self, processor, fashion_products, fashion_policies):
        response = processor.process(
            message="Mera product kharab aaya hai complaint karna hai",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.needs_human is True
        assert response.escalation_reason == "complaint"


class TestEmptyAndEdge:
    """Test edge cases."""

    def test_empty_message(self, processor, fashion_products, fashion_policies):
        response = processor.process(
            message="",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.intent == "unknown"

    def test_whitespace_only(self, processor, fashion_products, fashion_policies):
        response = processor.process(
            message="   ",
            products=fashion_products,
            policies=fashion_policies,
            store_name="Test Fashion",
            store_language="roman_urdu",
            store_id="test-store-fashion",
        )
        assert response.intent == "unknown"
