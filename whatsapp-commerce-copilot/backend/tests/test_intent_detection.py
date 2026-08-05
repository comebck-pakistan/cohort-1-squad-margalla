"""Tests for intent detection."""
import pytest
from app.services.intent_detector import detect_intent


class TestGreetings:
    def test_hello(self):
        result = detect_intent("hello")
        assert result.intent == "greeting"
        assert result.confidence >= 0.8

    def test_salam(self):
        result = detect_intent("assalam o alaikum")
        assert result.intent == "greeting"

    def test_hi(self):
        result = detect_intent("hi")
        assert result.intent == "greeting"

    def test_greeting_does_not_hide_product_question(self):
        result = detect_intent("hi black kurta price")
        assert result.intent == "price_query"


class TestProductSearch:
    def test_product_with_availability(self):
        result = detect_intent("sky blue kurta medium size mein available hai")
        assert result.intent in ("stock_query", "product_search")
        assert "availability" in result.requested_fields or result.intent == "stock_query"

    def test_price_query(self):
        result = detect_intent("navy blue sneakers size 42 ki price")
        assert "price" in result.requested_fields or result.intent == "price_query"


class TestPolicyQueries:
    def test_cod_query(self):
        result = detect_intent("cod hai kya")
        assert result.intent == "cod_query" or "cod" in result.requested_fields

    def test_delivery_query(self):
        result = detect_intent("delivery kitne din mein hogi")
        assert result.intent == "delivery_query" or "delivery" in result.requested_fields

    def test_return_query(self):
        result = detect_intent("return policy kya hai")
        assert result.intent == "returns_query" or "returns" in result.requested_fields


class TestMultipleFields:
    def test_availability_price_cod(self):
        """Test: 'Sky blue kurta available hai? Price aur COD bhi bata dein.'"""
        result = detect_intent("sky blue kurta medium mein available hai price aur cod bhi bata dein")
        # Should detect multiple requested fields
        assert len(result.requested_fields) >= 2 or len(result.sub_intents) >= 2

    def test_cod_and_delivery(self):
        result = detect_intent("cod hai aur delivery kitne din mein hogi")
        assert len(result.requested_fields) >= 1 or len(result.sub_intents) >= 2


class TestHumanRequest:
    def test_human_request(self):
        result = detect_intent("mujhe agent se baat karni hai")
        assert result.intent == "human_agent_request"

    def test_complaint(self):
        result = detect_intent("mera product kharab aaya hai complaint karna hai")
        assert result.intent == "complaint"


class TestUnknown:
    def test_empty(self):
        result = detect_intent("")
        assert result.intent == "unknown"

    def test_gibberish(self):
        result = detect_intent("asdfghjkl")
        # Should be product_search with low confidence or unknown
        assert result.confidence < 0.7

    def test_link_is_not_a_product(self):
        result = detect_intent("https://meet.google.com/example")
        assert result.intent == "unsupported"
