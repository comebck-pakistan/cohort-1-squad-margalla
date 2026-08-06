"""Response builder — creates grounded, traceable responses.

Every response includes source references. The LLM never invents data.
All customer-facing strings come from app.services.i18n so that English
and Urdu are both supported without scattered if/else blocks.
"""
from dataclasses import dataclass, field
from app.services.catalog_search import CatalogSearchResult, MatchedProduct
from app.services.policy_matcher import PolicyMatchResult
from app.services.entity_extractor import ExtractedEntities
from app.services.intent_detector import IntentResult
from app.services.i18n import t


@dataclass
class ProcessedResponse:
    """Complete response from the pipeline."""
    message: str
    intent: str
    confidence: float
    matched_product_id: str | None = None
    matched_variant_id: str | None = None
    image_url: str | None = None
    sources: list[str] = field(default_factory=list)
    extracted_entities: dict = field(default_factory=dict)
    clarification_options: list[dict] | None = None
    needs_clarification: bool = False
    needs_human: bool = False
    escalation_reason: str | None = None
    store_id: str = ""
    customer_number: str = ""

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "message": self.message,
            "intent": self.intent,
            "confidence": self.confidence,
            "matched_product_id": self.matched_product_id,
            "matched_variant_id": self.matched_variant_id,
            "image_url": self.image_url,
            "sources": self.sources,
            "extracted_entities": self.extracted_entities,
            "clarification_options": self.clarification_options,
            "needs_clarification": self.needs_clarification,
            "needs_human": self.needs_human,
            "escalation_reason": self.escalation_reason,
            "store_id": self.store_id,
        }


def _lang(store_language: str) -> str:
    """Normalise store_language to i18n lang code ('en' or 'ur')."""
    if store_language == "ur":
        return "ur"
    if store_language == "roman_urdu":
        return "ur"   # Roman Urdu input → Urdu-script response
    return "en"


class ResponseBuilder:
    """Build grounded responses from pipeline results."""

    def build_product_response(
        self,
        search_result: CatalogSearchResult,
        entities: ExtractedEntities,
        intent: IntentResult,
        policy_results: list[PolicyMatchResult] | None = None,
        store_language: str = "roman_urdu",
    ) -> ProcessedResponse:
        """Build response for product-related queries."""

        if not search_result.found:
            return self._product_not_found(entities, store_language)

        if search_result.is_ambiguous:
            return self._ambiguous_products(search_result, entities, store_language)

        best = search_result.best_match
        if not best:
            return self._product_not_found(entities, store_language)

        # Single product match
        return self._single_product_response(best, entities, intent, policy_results, store_language)

    def _single_product_response(
        self,
        match: MatchedProduct,
        entities: ExtractedEntities,
        intent: IntentResult,
        policy_results: list[PolicyMatchResult] | None,
        store_language: str,
    ) -> ProcessedResponse:
        """Build response for a single matched product."""
        lang = _lang(store_language)
        product = match.product
        sources = [f"catalog:product:{product.id}"]
        parts: list[str] = []

        # Product name (never translated — it's a catalogue identifier)
        parts.append(f"*{product.name}*")

        # Variant info
        available_sizes = []
        available_colors = []
        base_price = product.base_price or 0.0
        stock_status = "Available" if any(v.stock > 0 for v in product.variants) else "Out of stock"
        
        if match.matched_variants:
            for variant in match.matched_variants:
                sources.append(f"inventory:variant:{variant.id}")
                if variant.size and variant.size not in available_sizes:
                    available_sizes.append(variant.size)
                if variant.color and variant.color not in available_colors:
                    available_colors.append(variant.color)
            
            # Use price from first matched variant if base_price is not set or we want to be specific
            if match.matched_variants[0].price:
                base_price = match.matched_variants[0].price
                
            matched_variant = match.matched_variants[0] if len(match.matched_variants) == 1 else None
            stock_status = "Available" if any(v.stock > 0 for v in match.matched_variants) else "Out of stock"
        else:
            for variant in product.variants:
                if not variant.is_active:
                    continue
                sources.append(f"inventory:variant:{variant.id}")
                if variant.size and variant.size not in available_sizes:
                    available_sizes.append(variant.size)
                if variant.color and variant.color not in available_colors:
                    available_colors.append(variant.color)
            matched_variant = None
            
        parts.append(f"Price: Rs. {base_price:,.0f}")
        
        if available_sizes:
            parts.append(f"Available sizes: {', '.join(available_sizes)}")
        if available_colors:
            parts.append(f"Available colors: {', '.join(available_colors)}")
            
        parts.append(f"Stock: {stock_status}")
        
        # Next question
        if not matched_variant and available_sizes:
            next_q = t("ask_size", lang) if t("ask_size", lang) != "ask_size" else "Would you like to select a size?"
            parts.append(next_q)
        elif not matched_variant and available_colors:
            next_q = t("ask_color", lang) if t("ask_color", lang) != "ask_color" else "Which color would you prefer?"
            parts.append(next_q)

        # Policy info
        if policy_results:
            for pr in policy_results:
                if pr.matched:
                    parts.append(f"\n{pr.policy_value}")
                    sources.append(pr.source)

        message = "\n".join(parts)

        return ProcessedResponse(
            message=message,
            intent=intent.intent,
            confidence=match.score / 100.0,
            matched_product_id=product.id,
            matched_variant_id=matched_variant.id if matched_variant else None,
            image_url=product.image_url if hasattr(product, 'image_url') else None,
            sources=sources,
            extracted_entities={
                "product_query": entities.product_query,
                "color": entities.color,
                "size": entities.size,
                "quantity": entities.quantity,
                "budget_min": entities.budget_min,
                "budget_max": entities.budget_max,
                "excluded_colors": entities.excluded_colors,
                "requested_fields": intent.requested_fields,
            },
        )

    def build_contextual_fallback_response(
        self,
        intent: str,
        store_language: str,
    ) -> ProcessedResponse:
        """Respond to non-product turns without claiming a catalogue miss."""
        lang = _lang(store_language)
        key_map = {
            "acknowledgement": "fallback_ack",
            "unsupported": "fallback_unsupported",
            "unknown": "fallback_unknown",
        }
        key = key_map.get(intent, "fallback_unknown")
        return ProcessedResponse(
            message=t(key, lang),
            intent=intent,
            confidence=0.9 if intent != "unknown" else 0.2,
        )

    def _ambiguous_products(
        self,
        search_result: CatalogSearchResult,
        entities: ExtractedEntities,
        store_language: str,
    ) -> ProcessedResponse:
        """Build clarification response for ambiguous matches."""
        lang = _lang(store_language)
        if search_result.source_type == "generic":
            header = t("product_available_list", lang)
        else:
            header = t("product_choice", lang)

        options = []
        sources = []
        for i, match in enumerate(search_result.matches[:5], 1):
            options.append({
                "number": i,
                "product_id": match.product.id,
                "name": match.product.name,
            })
            sources.append(f"catalog:product:{match.product.id}")
            header += f"\n{i}. {match.product.name}"

        return ProcessedResponse(
            message=header,
            intent="product_search",
            confidence=0.5,
            sources=sources,
            extracted_entities={
                "product_query": entities.product_query,
                "color": entities.color,
                "size": entities.size,
            },
            clarification_options=options,
            needs_clarification=True,
        )

    def _product_not_found(
        self,
        entities: ExtractedEntities,
        store_language: str,
    ) -> ProcessedResponse:
        """Build not-found response."""
        lang = _lang(store_language)
        query = entities.product_query or entities.category or "this product"
        return ProcessedResponse(
            message=t("product_not_found", lang, query=query),
            intent="product_search",
            confidence=0.0,
            extracted_entities={
                "product_query": entities.product_query,
                "color": entities.color,
                "size": entities.size,
            },
        )

    def build_policy_response(
        self,
        policy_results: list[PolicyMatchResult],
        intent: IntentResult,
        store_language: str = "roman_urdu",
    ) -> ProcessedResponse:
        """Build response for pure policy queries."""
        lang = _lang(store_language)
        sources = []
        messages = []

        for pr in policy_results:
            if pr.matched:
                messages.append(pr.policy_value)
                sources.append(pr.source)

        if messages:
            return ProcessedResponse(
                message="\n\n".join(messages),
                intent=intent.intent,
                confidence=0.9,
                sources=sources,
            )

        return ProcessedResponse(
            message=t("policy_not_found", lang),
            intent=intent.intent,
            confidence=0.3,
        )

    def build_greeting_response(
        self, store_name: str, store_language: str = "roman_urdu", has_context: bool = False
    ) -> ProcessedResponse:
        """Build greeting response."""
        lang = _lang(store_language)
        if has_context:
            message = t("welcome_returning", lang)
        else:
            message = t("welcome", lang, store=store_name)

        return ProcessedResponse(
            message=message,
            intent="greeting",
            confidence=1.0,
        )

    def build_human_handoff_response(
        self,
        reason: str,
        store_language: str = "roman_urdu",
    ) -> ProcessedResponse:
        """Build human handoff response."""
        lang = _lang(store_language)
        return ProcessedResponse(
            message=t("handoff", lang),
            intent="human_agent_request",
            confidence=1.0,
            needs_human=True,
            escalation_reason=reason,
        )

    def build_error_response(self, store_language: str = "roman_urdu") -> ProcessedResponse:
        """Build error/fallback response."""
        lang = _lang(store_language)
        return ProcessedResponse(
            message=t("error_retry", lang),
            intent="unknown",
            confidence=0.0,
        )
