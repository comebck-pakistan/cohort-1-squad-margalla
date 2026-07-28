"""Tests for AI provider abstraction."""
import pytest
import pytest_asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ai_provider import (
    MockAIProvider, OpenRouterProvider, AIRequestContext, AIResponseSchema,
    get_ai_provider, reset_ai_provider,
)


@pytest.fixture
def mock_provider():
    return MockAIProvider()


@pytest.fixture
def sample_context():
    return AIRequestContext(
        customer_message="Sky blue kurta hai?",
        detected_intent="product_search",
        extracted_entities={"product_query": "kurta", "color": "sky blue"},
        candidate_products=[{
            "id": "prod-001",
            "name": "Women's Embroidered Kurta",
            "variants": [
                {"id": "var-001", "color": "sky blue", "size": "medium", "price": 2500, "stock": 4},
                {"id": "var-002", "color": "sky blue", "size": "large", "price": 2500, "stock": 0},
            ],
        }],
        candidate_policies=[
            {"type": "cod", "value": "Haan, COD available hai."},
        ],
        store_language="roman_urdu",
        store_name="Test Fashion",
    )


@pytest.fixture
def empty_context():
    return AIRequestContext(
        customer_message="random gibberish",
        detected_intent="unknown",
        extracted_entities={},
        store_language="english",
        store_name="Test Store",
    )


class TestMockProvider:
    """Test MockAIProvider."""

    @pytest.mark.asyncio
    async def test_name(self, mock_provider):
        assert mock_provider.name() == "mock"

    @pytest.mark.asyncio
    async def test_with_products(self, mock_provider, sample_context):
        result = await mock_provider.process(sample_context)
        assert isinstance(result, AIResponseSchema)
        assert "Kurta" in result.response_message
        assert result.selected_product_id == "prod-001"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_with_policies_only(self, mock_provider):
        ctx = AIRequestContext(
            customer_message="COD hai?",
            detected_intent="cod_query",
            extracted_entities={},
            candidate_policies=[{"type": "cod", "value": "Yes, COD available."}],
            store_language="english",
            store_name="Test",
        )
        result = await mock_provider.process(ctx)
        assert "COD" in result.response_message
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_with_no_candidates(self, mock_provider, empty_context):
        result = await mock_provider.process(empty_context)
        assert result.confidence <= 0.5
        assert len(result.response_message) > 0


class TestMalformedAIJSON:
    """Test that malformed AI JSON falls back safely."""

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(self):
        """OpenRouter returns invalid JSON — should fall back to safe response."""
        provider = OpenRouterProvider()
        provider.api_key = "test-key"

        # Mock httpx response with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "This is not valid JSON {{{",
                }
            }]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            ctx = AIRequestContext(
                customer_message="test",
                detected_intent="unknown",
                extracted_entities={},
                store_language="english",
                store_name="Test",
            )
            result = await provider.process(ctx)

            # Should fall back to safe response with human handoff
            assert result.needs_human is True
            assert result.escalation_reason == "ai_error"
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_valid_json_from_openrouter(self):
        """OpenRouter returns valid JSON — should parse correctly."""
        provider = OpenRouterProvider()
        provider.api_key = "test-key"

        valid_response = {
            "response_message": "Here is the kurta info",
            "selected_product_id": "prod-001",
            "confidence": 0.9,
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps(valid_response),
                }
            }]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            ctx = AIRequestContext(
                customer_message="kurta hai?",
                detected_intent="product_search",
                extracted_entities={},
                store_language="roman_urdu",
                store_name="Test",
            )
            result = await provider.process(ctx)

            assert result.response_message == "Here is the kurta info"
            assert result.selected_product_id == "prod-001"
            assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_no_api_key_fallback(self):
        """No API key — should fall back safely."""
        provider = OpenRouterProvider()
        provider.api_key = None

        ctx = AIRequestContext(
            customer_message="test",
            detected_intent="unknown",
            extracted_entities={},
            store_language="english",
            store_name="Test",
        )
        result = await provider.process(ctx)
        assert result.needs_human is True


class TestProviderFactory:
    """Test provider factory."""

    def test_default_is_mock(self):
        reset_ai_provider()
        provider = get_ai_provider()
        assert provider.name() == "mock"
        reset_ai_provider()
