"""AI provider abstraction — swappable interface for mock and OpenRouter.

Usage:
    provider = get_ai_provider()  # Returns mock or OpenRouter based on env
    result = await provider.process(context)

The AI provider is OPTIONAL. The rule-based pipeline handles most cases.
The AI is only called when: language is messy, multiple intents mixed,
indirect product reference, conversation context needed, or confidence is low.

The AI provider never queries the DB. It receives pre-fetched candidates
and formats responses over that closed set.
"""
import json
import httpx
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pydantic import BaseModel, ValidationError
from typing import Optional

from app.config import get_settings

logger = structlog.get_logger()


class AIRequestContext(BaseModel):
    """Context sent to the AI provider for response generation."""
    customer_message: str
    detected_intent: str
    extracted_entities: dict
    candidate_products: list[dict] = []  # Pre-fetched product data
    candidate_policies: list[dict] = []  # Pre-fetched policy data
    conversation_history: list[dict] = []  # Recent messages
    store_language: str = "roman_urdu"
    store_name: str = ""


class AIResponseSchema(BaseModel):
    """Expected structured output from the AI provider."""
    response_message: str
    selected_product_id: Optional[str] = None
    selected_variant_id: Optional[str] = None
    image_url: Optional[str] = None
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    confidence: float = 0.8
    needs_human: bool = False
    escalation_reason: Optional[str] = None


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def process(self, context: AIRequestContext) -> AIResponseSchema:
        """Process a message context and return structured response."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Return provider name."""
        ...


class MockAIProvider(AIProvider):
    """Mock AI provider for local dev and tests.

    Returns structured responses using the rule engine output directly,
    with simple formatting logic. No external API calls.
    """

    def name(self) -> str:
        return "mock"

    async def process(self, context: AIRequestContext) -> AIResponseSchema:
        """Mock processing — format response from candidates."""
        # If we have candidate products, describe the first one
        if context.candidate_products:
            product = context.candidate_products[0]
            product_name = product.get("name", "Unknown Product")
            variants = product.get("variants", [])

            parts = [f"*{product_name}*"]
            selected_variant_id = None

            for v in variants[:3]:  # Limit to 3 variants
                desc_parts = []
                if v.get("color"):
                    desc_parts.append(v["color"].title())
                if v.get("size"):
                    desc_parts.append(f"Size {v['size']}")
                desc = " | ".join(desc_parts) if desc_parts else "Default"

                stock = v.get("stock", 0)
                price = v.get("price", 0)
                stock_msg = f"Stock: {stock}" if stock > 0 else "Out of stock"
                parts.append(f"  {desc}: Rs. {price:,.0f} — {stock_msg}")

                if selected_variant_id is None and stock > 0:
                    selected_variant_id = v.get("id")

            # Add policy info
            for policy in context.candidate_policies:
                parts.append(f"\n{policy.get('value', '')}")

            return AIResponseSchema(
                response_message="\n".join(parts),
                selected_product_id=product.get("id"),
                selected_variant_id=selected_variant_id,
                image_url=product.get("image_url"),
                confidence=0.85,
            )

        # If only policies
        if context.candidate_policies:
            messages = [p.get("value", "") for p in context.candidate_policies]
            return AIResponseSchema(
                response_message="\n\n".join(messages),
                confidence=0.9,
            )

        # No candidates
        if context.store_language == "roman_urdu":
            msg = "Maaf kijiye, mujhe samajh nahi aaya. Kya aap dobara bata sakte hain?"
        else:
            msg = "Sorry, I didn't understand that. Could you please rephrase?"

        return AIResponseSchema(
            response_message=msg,
            confidence=0.3,
        )


class OpenRouterProvider(AIProvider):
    """OpenRouter-compatible AI provider.

    Calls OpenRouter API with structured JSON output.
    Validates response with Pydantic. Falls back safely on malformed JSON.
    """

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.OPENROUTER_MODEL
        self.base_url = settings.OPENROUTER_BASE_URL

    def name(self) -> str:
        return "openrouter"

    async def process(self, context: AIRequestContext) -> AIResponseSchema:
        """Call OpenRouter API with structured JSON output."""
        if not self.api_key:
            logger.warning("openrouter_no_api_key", msg="OPENROUTER_API_KEY not set, falling back to safe response")
            return self._fallback_response(context)

        system_prompt = self._build_system_prompt(context)
        user_prompt = self._build_user_prompt(context)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.3,
                        "max_tokens": 500,
                    },
                )
                response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Parse and validate JSON response
            try:
                parsed = json.loads(content)
                return AIResponseSchema(**parsed)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error("openrouter_malformed_json", error=str(e), raw_content=content[:200])
                return self._fallback_response(context)

        except httpx.HTTPError as e:
            logger.error("openrouter_http_error", error=str(e))
            return self._fallback_response(context)
        except Exception as e:
            logger.error("openrouter_unexpected_error", error=str(e))
            return self._fallback_response(context)

    def _build_system_prompt(self, context: AIRequestContext) -> str:
        return f"""You are a sales assistant for {context.store_name}. 
Respond in {'Roman Urdu' if context.store_language == 'roman_urdu' else 'English'}.

RULES:
1. Only use information from the provided product data and policies.
2. Never invent product names, prices, stock, sizes, colors, or policies.
3. Return a JSON object with these fields: response_message, selected_product_id, selected_variant_id, image_url, clarification_needed, clarification_question, confidence, needs_human, escalation_reason.
4. Be concise and helpful.

AVAILABLE PRODUCTS:
{json.dumps(context.candidate_products, indent=2)}

STORE POLICIES:
{json.dumps(context.candidate_policies, indent=2)}"""

    def _build_user_prompt(self, context: AIRequestContext) -> str:
        return f"""Customer message: "{context.customer_message}"
Detected intent: {context.detected_intent}
Extracted entities: {json.dumps(context.extracted_entities)}
Conversation history: {json.dumps(context.conversation_history[-5:])}

Generate a helpful response using ONLY the provided product data and policies. Return valid JSON."""

    def _fallback_response(self, context: AIRequestContext) -> AIResponseSchema:
        """Safe fallback when AI fails — trigger human handoff."""
        if context.store_language == "roman_urdu":
            msg = "Maaf kijiye, abhi jawab dene mein mushkil ho rahi hai. Aap ko humare team member se connect kiya ja raha hai."
        else:
            msg = "Sorry, I'm having trouble responding right now. Let me connect you with a team member."

        return AIResponseSchema(
            response_message=msg,
            confidence=0.0,
            needs_human=True,
            escalation_reason="ai_error",
        )


# --- Provider Factory ---

_provider_instance: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    """Get AI provider instance based on env config."""
    global _provider_instance
    if _provider_instance is None:
        settings = get_settings()
        if settings.AI_PROVIDER == "openrouter":
            _provider_instance = OpenRouterProvider()
        else:
            _provider_instance = MockAIProvider()
        logger.info("ai_provider_initialized", provider=_provider_instance.name())
    return _provider_instance


def reset_ai_provider():
    """Reset provider singleton (for testing)."""
    global _provider_instance
    _provider_instance = None
