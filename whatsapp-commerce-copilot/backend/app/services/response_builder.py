"""Response builder — creates grounded, traceable responses.

Every response includes source references. The LLM never invents data.
"""
from dataclasses import dataclass, field
from app.services.catalog_search import CatalogSearchResult, MatchedProduct
from app.services.policy_matcher import PolicyMatchResult
from app.services.entity_extractor import ExtractedEntities
from app.services.intent_detector import IntentResult


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
        product = match.product
        sources = [f"catalog:product:{product.id}"]
        parts: list[str] = []

        # Product info
        parts.append(f"*{product.name}*")

        # Variant info
        if match.matched_variants:
            for variant in match.matched_variants:
                sources.append(f"inventory:variant:{variant.id}")
                variant_desc = []
                if variant.color:
                    variant_desc.append(variant.color.title())
                if variant.size:
                    variant_desc.append(f"Size {variant.size}")

                desc = " | ".join(variant_desc) if variant_desc else "Default"

                # Stock status
                if variant.stock > 0:
                    if store_language == "roman_urdu":
                        stock_msg = f"Available hai (Stock: {variant.stock})"
                    else:
                        stock_msg = f"Available (Stock: {variant.stock})"
                else:
                    if store_language == "roman_urdu":
                        stock_msg = "Abhi stock mein nahi hai"
                    else:
                        stock_msg = "Currently out of stock"

                parts.append(f"  {desc}: Rs. {variant.price:,.0f} — {stock_msg}")

            # Use first matched variant as the selected one
            matched_variant = match.matched_variants[0] if match.matched_variants else None
        else:
            # No variants matched the filter — show all
            if product.variants:
                if store_language == "roman_urdu":
                    parts.append("Available variants:")
                else:
                    parts.append("Available variants:")
                for variant in product.variants:
                    if not variant.is_active:
                        continue
                    sources.append(f"inventory:variant:{variant.id}")
                    v_parts = []
                    if variant.color:
                        v_parts.append(variant.color.title())
                    if variant.size:
                        v_parts.append(f"Size {variant.size}")
                    desc = " | ".join(v_parts) if v_parts else "Default"
                    stock_str = f"Stock: {variant.stock}" if variant.stock > 0 else "Out of stock"
                    parts.append(f"  {desc}: Rs. {variant.price:,.0f} — {stock_str}")
            matched_variant = None

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
                "requested_fields": intent.requested_fields,
            },
        )

    def _ambiguous_products(
        self,
        search_result: CatalogSearchResult,
        entities: ExtractedEntities,
        store_language: str,
    ) -> ProcessedResponse:
        """Build clarification response for ambiguous matches."""
        if search_result.source_type == "generic":
            if store_language == "roman_urdu":
                header = "Hamare paas yeh products available hain:"
            else:
                header = "Here are some of our available products:"
        else:
            if store_language == "roman_urdu":
                header = "Aap kis product ki baat kar rahe hain?"
            else:
                header = "Which product are you referring to?"

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
        query = entities.product_query or entities.category or "this product"

        if store_language == "roman_urdu":
            message = f"Maaf kijiye, '{query}' hamare catalog mein nahi mila. Kya aap aur detail bata sakte hain?"
        else:
            message = f"Sorry, we couldn't find '{query}' in our catalog. Could you provide more details?"

        return ProcessedResponse(
            message=message,
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

        if store_language == "roman_urdu":
            msg = "Is baare mein filhaal information available nahi hai. Kya aap kuch aur poochna chahein ge?"
        else:
            msg = "We don't have information about that right now. Can I help with something else?"

        return ProcessedResponse(
            message=msg,
            intent=intent.intent,
            confidence=0.3,
        )

    def build_greeting_response(self, store_name: str, store_language: str = "roman_urdu") -> ProcessedResponse:
        """Build greeting response."""
        if store_language == "roman_urdu":
            message = f"Assalam o Alaikum! {store_name} mein khush aamdeed. Aap kya dhundh rahe hain?"
        else:
            message = f"Hello! Welcome to {store_name}. How can I help you today?"

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
        if store_language == "roman_urdu":
            message = "Aap ko humare team member se connect kiya ja raha hai. Thoda intezaar karein."
        else:
            message = "I'm connecting you with a team member. Please wait a moment."

        return ProcessedResponse(
            message=message,
            intent="human_agent_request",
            confidence=1.0,
            needs_human=True,
            escalation_reason=reason,
        )

    def build_error_response(self, store_language: str = "roman_urdu") -> ProcessedResponse:
        """Build error/fallback response."""
        if store_language == "roman_urdu":
            message = "Maaf kijiye, mujhe samajh nahi aaya. Kya aap dobara bata sakte hain?"
        else:
            message = "Sorry, I didn't understand that. Could you please rephrase?"

        return ProcessedResponse(
            message=message,
            intent="unknown",
            confidence=0.0,
        )
