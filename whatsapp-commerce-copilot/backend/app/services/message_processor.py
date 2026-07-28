"""Message processor — orchestrates the full deterministic pipeline.

Flow: normalize → detect language → detect intent → extract entities →
search catalog → match policies → build response.

All queries are store-scoped via the products/policies passed in.
"""
from app.services.text_normalizer import normalize_text
from app.services.language_detector import detect_language
from app.services.intent_detector import detect_intent
from app.services.entity_extractor import extract_entities
from app.services.catalog_search import CatalogSearchService
from app.services.policy_matcher import PolicyMatcher
from app.services.response_builder import ResponseBuilder, ProcessedResponse
from app.models.product import Product
from app.models.policy import StorePolicy


class MessageProcessor:
    """Orchestrate the full message processing pipeline."""

    def __init__(self):
        self.catalog_search = CatalogSearchService()
        self.policy_matcher = PolicyMatcher()
        self.response_builder = ResponseBuilder()

    def process(
        self,
        message: str,
        products: list[Product],
        policies: list[StorePolicy],
        store_name: str = "",
        store_language: str = "roman_urdu",
        store_id: str = "",
        customer_number: str = "",
    ) -> ProcessedResponse:
        """Process a customer message through the full pipeline.

        Args:
            message: Raw customer message
            products: Products from this store only
            policies: Policies from this store only
            store_name: Store's business name
            store_language: Store's preferred response language
            store_id: Store ID for traceability
            customer_number: Customer phone for traceability
        """
        # Step 1: Normalize
        normalized = normalize_text(message)

        if not normalized:
            response = self.response_builder.build_error_response(store_language)
            response.store_id = store_id
            response.customer_number = customer_number
            return response

        # Step 2: Detect language
        language = detect_language(message)

        # Step 3: Detect intent
        intent_result = detect_intent(normalized)

        # Step 4: Handle greeting
        if intent_result.intent == "greeting" and intent_result.confidence >= 0.8:
            response = self.response_builder.build_greeting_response(store_name, store_language)
            response.store_id = store_id
            response.customer_number = customer_number
            return response

        # Step 5: Handle human agent request
        if intent_result.intent == "human_agent_request":
            response = self.response_builder.build_human_handoff_response(
                "explicit_request", store_language
            )
            response.store_id = store_id
            response.customer_number = customer_number
            return response

        # Step 6: Handle complaint
        if intent_result.intent == "complaint":
            response = self.response_builder.build_human_handoff_response(
                "complaint", store_language
            )
            response.store_id = store_id
            response.customer_number = customer_number
            return response

        # Step 7: Extract entities
        entities = extract_entities(normalized, language)

        # Step 8: Pure policy query (no product reference)
        policy_intents = {'cod_query', 'delivery_query', 'returns_query', 'exchange_query'}
        product_intents = {'product_search', 'price_query', 'stock_query'}

        # Check if ALL detected sub-intents are policy-related
        has_product_sub_intent = any(si in product_intents for si in intent_result.sub_intents)
        all_policy = all(si in policy_intents for si in intent_result.sub_intents) if intent_result.sub_intents else False

        is_pure_policy = (
            (intent_result.intent in policy_intents or all_policy)
            and not has_product_sub_intent
            and not entities.product_query
            and not entities.sku
            and not entities.category
            and not entities.color
        )

        if is_pure_policy:
            # Map intent to requested fields — combine all policy sub-intents
            intent_to_field = {
                'cod_query': ['cod'],
                'delivery_query': ['delivery'],
                'returns_query': ['returns'],
                'exchange_query': ['exchange'],
            }
            fields = list(intent_result.requested_fields) if intent_result.requested_fields else []
            # Add fields from all sub-intents
            for si in intent_result.sub_intents:
                for f in intent_to_field.get(si, []):
                    if f not in fields:
                        fields.append(f)
            if not fields:
                fields = intent_to_field.get(intent_result.intent, [])
            policy_results = self.policy_matcher.match(policies, fields)
            response = self.response_builder.build_policy_response(
                policy_results, intent_result, store_language
            )
            response.store_id = store_id
            response.customer_number = customer_number
            return response

        # Step 9: Product search
        # If no product_query but we have color/size, search by those attributes
        search_query = entities.product_query
        search_category = entities.category
        if not search_query and not entities.sku and not search_category:
            if entities.color or entities.size:
                # Search by color/size across all products (context-dependent followup)
                search_query = None  # Will search all products, filter by color/size
            else:
                # No useful search criteria
                response = self.response_builder.build_error_response(store_language)
                response.store_id = store_id
                response.customer_number = customer_number
                return response

        search_result = self.catalog_search.search(
            products=products,
            query=search_query,
            sku=entities.sku,
            color=entities.color,
            size=entities.size,
            category=entities.category,
        )

        # Step 10: Match policies if requested
        policy_results = None
        if intent_result.requested_fields:
            policy_results = self.policy_matcher.match(policies, intent_result.requested_fields)

        # Step 11: Build response
        response = self.response_builder.build_product_response(
            search_result=search_result,
            entities=entities,
            intent=intent_result,
            policy_results=policy_results,
            store_language=store_language,
        )
        response.store_id = store_id
        response.customer_number = customer_number

        # Step 12: Check if confidence is too low for human handoff
        if response.confidence < 0.3 and intent_result.intent != "unknown":
            response.needs_human = True
            response.escalation_reason = "low_confidence"

        return response
