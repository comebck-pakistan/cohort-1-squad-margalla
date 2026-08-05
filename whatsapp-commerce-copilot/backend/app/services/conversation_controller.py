"""Conversation-aware controller shared by demo and WhatsApp entry points.

This is the application layer that was previously missing: it resolves
follow-ups, runs grounded retrieval, advances orders, optionally asks the AI
provider to phrase ambiguous results, and persists state through the caller's
transaction.
"""
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.order import Order
from app.models.handoff import HumanHandoff
from app.models.product import Product, ProductVariant
from app.models.policy import StorePolicy
from app.services.ai_provider import AIRequestContext, get_ai_provider
from app.services.conversation_manager import ConversationManager
from app.services.entity_extractor import extract_entities
from app.services.i18n import t
from app.services.intent_detector import detect_intent
from app.services.language_detector import detect_language
from app.services.message_processor import MessageProcessor
from app.services.order_manager import OrderManager
from app.services.response_builder import ProcessedResponse
from app.services.text_normalizer import normalize_text


class ConversationController:
    def __init__(self):
        self.processor = MessageProcessor()
        self.conversations = ConversationManager()
        self.orders = OrderManager()

    async def process(
        self,
        db: AsyncSession,
        conversation: Conversation,
        message: str,
        products: list[Product],
        policies: list[StorePolicy],
        store_name: str,
        store_language: str,
        store_id: str,
        customer_number: str,
    ) -> ProcessedResponse:
        normalized = normalize_text(message)
        lang_detection = detect_language(message)
        language = lang_detection.input_language
        intent = detect_intent(normalized)
        entities = extract_entities(normalized, language)

        llm_classification = await get_ai_provider().classify_intent(message, store_language)
        if llm_classification:
            if llm_classification.intent and llm_classification.intent != "unknown":
                intent.intent = llm_classification.intent
                intent.confidence = llm_classification.confidence
            
            if intent.intent == "product_search":
                if llm_classification.product_query:
                    entities.product_query = llm_classification.product_query
                if llm_classification.reference:
                    # If they reference a product (e.g. "the black one", "the first one")
                    # but product_query is empty, use the reference to search context.
                    if not entities.product_query:
                        entities.product_query = llm_classification.reference
                
                # Merge AI extracted entities
                if llm_classification.entities.category:
                    entities.category = llm_classification.entities.category
                if llm_classification.entities.color:
                    entities.color = llm_classification.entities.color
                if llm_classification.entities.size:
                    entities.size = llm_classification.entities.size
                if llm_classification.entities.style:
                    # Stash style in product_query if empty, otherwise it's in preferences
                    if not entities.product_query:
                        entities.product_query = llm_classification.entities.style
                        
            elif intent.intent in {"greeting", "unknown", "acknowledgement"}:
                entities.product_query = None

        # --- Determine response language for this turn ---
        # Start with AI-detected language (most accurate for complex messages);
        # fall back to the heuristic detector; neutral replies keep session lang.
        ai_response_lang = None
        if llm_classification:
            ai_input_lang = llm_classification.input_language
            ai_response_lang = llm_classification.response_language
            ai_lang_conf = llm_classification.language_confidence
        else:
            ai_input_lang = lang_detection.input_language
            ai_response_lang = lang_detection.response_language
            ai_lang_conf = lang_detection.confidence

        if lang_detection.is_neutral:
            # Short / number / emoji reply → preserve session language
            response_lang = conversation.get_preferred_response_language()
        else:
            # Use AI decision; cross-check with heuristic for safety
            if ai_response_lang in ("en", "ur"):
                response_lang = ai_response_lang
            else:
                response_lang = lang_detection.response_language
            conversation.set_language_preference(
                input_language=ai_input_lang,
                response_language=response_lang,
                confidence=ai_lang_conf,
            )

        # Flush to prevent asyncpg MissingGreenlet on subsequent db queries (autoflush)
        await db.flush()

        entity_dict = {
            "product_query": entities.product_query,
            "sku": entities.sku,
            "category": entities.category,
            "color": entities.color,
            "size": entities.size,
            "quantity": entities.quantity,
        }
        resolved = self.conversations.resolve_followup(
            conversation, normalized, entity_dict
        )

        if (
            conversation.order_stage == "ORDER_CONFIRMATION"
            and re.fullmatch(r'(no|nope|nahi|nahin|na|نہیں|نا)', normalized)
        ):
            return await self._cancel_order(db, conversation, response_lang)
        if intent.intent == "order_status":
            return await self._order_status(
                db, conversation, store_id, customer_number, response_lang
            )
        if intent.intent == "order_cancel":
            return await self._cancel_order(db, conversation, response_lang)

        if intent.intent == "alternatives" and conversation.current_product_id:
            alternative = self._alternatives(
                products, conversation.current_product_id, response_lang
            )
            if alternative:
                return alternative

        response = self.processor.process(
            message=message,
            products=products,
            policies=policies,
            store_name=store_name,
            store_language=response_lang,
            store_id=store_id,
            customer_number=customer_number,
            contextual_product_id=resolved.get("product_id"),
            context_color=resolved.get("color"),
            context_size=resolved.get("size"),
            recently_shown_products=resolved.get("recently_shown_products"),
            preferences=resolved.get("preferences"),
        )
        self.conversations.apply_context(conversation, response)
        await db.flush()

        order_response = await self._advance_order(
            db, conversation, message, intent.intent, entities, response,
            products, response_lang, customer_number
        )
        if order_response:
            response = order_response

        response = await self._optional_ai_response(
            conversation, message, response, products, policies,
            store_name, response_lang
        )
        if response.needs_human:
            await self._create_handoff(db, conversation, response, message)
        return response

    async def _create_handoff(self, db, conversation, response, customer_message):
        result = await db.execute(
            select(HumanHandoff).where(
                HumanHandoff.conversation_id == conversation.id,
                HumanHandoff.status.in_(["pending", "active"]),
            ).limit(1)
        )
        if result.scalar_one_or_none():
            return
        db.add(HumanHandoff(
            conversation_id=conversation.id,
            store_id=conversation.store_id,
            reason=response.escalation_reason or "low_confidence",
            summary=f"Customer: {customer_message[:500]}",
            status="pending",
        ))
        conversation.is_ai_controlled = False

    async def _advance_order(
        self,
        db: AsyncSession,
        conversation: Conversation,
        message: str,
        intent: str,
        entities,
        response: ProcessedResponse,
        products: list[Product],
        store_language: str,
        customer_number: str,
    ) -> ProcessedResponse | None:
        active = conversation.order_stage not in {"BROWSING", "ORDER_CREATED"}
        if not active and intent not in {"order_request", "order_confirmation"}:
            return None

        product = self._product(products, conversation.current_product_id)
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        if not product:
            return self._order_message(
                t("select_product_first", lang),
                conversation, response,
            )

        # Start an order only from an explicit buying action.
        if conversation.order_stage in {"BROWSING", "ORDER_CREATED"}:
            conversation.order_stage = "BROWSING"
            self.orders.advance_stage(conversation, product=product)

        # Corrections can move variant selection backwards safely.
        if entities.color or entities.size:
            variant = self._matching_variant(product, entities.color, entities.size)
            if variant:
                conversation.order_stage = "PRODUCT_SELECTED"
                self.orders.advance_stage(conversation, variant=variant)
            elif conversation.order_stage == "PRODUCT_SELECTED":
                return self._order_message(
                    t("variant_unavailable", lang),
                    conversation, response,
                )

        if conversation.order_stage == "PRODUCT_SELECTED":
            # A uniquely filtered variant from catalogue retrieval is safe.
            variant = self._variant(product, response.matched_variant_id)
            if variant:
                self.orders.advance_stage(conversation, variant=variant)

        if conversation.order_stage == "VARIANT_SELECTED":
            quantity = entities.quantity
            if quantity is None and intent == "order_confirmation":
                quantity = 1
            if quantity:
                self.orders.advance_stage(conversation, quantity=quantity)

        if conversation.order_stage == "QUANTITY_SELECTED":
            name, phone = self._customer_details(message, customer_number)
            if name and phone:
                self.orders.advance_stage(
                    conversation, customer_name=name, customer_phone=phone
                )

        if conversation.order_stage == "CUSTOMER_DETAILS_REQUIRED":
            if self._looks_like_address(message, intent):
                conversation.requested_city = entities.delivery_city
                self.orders.advance_stage(
                    conversation, customer_address=message.strip()
                )

        if conversation.order_stage == "ADDRESS_REQUIRED":
            payment = self._payment_method(normalized=normalize_text(message))
            if payment:
                self.orders.advance_stage(conversation, payment_method=payment)

        variant = self._variant(product, conversation.current_variant_id)
        if conversation.order_stage == "PAYMENT_METHOD_REQUIRED" and variant:
            conversation.order_stage = "ORDER_CONFIRMATION"
            return self._order_message(
                self.orders.build_order_summary(
                    conversation, product, variant, store_language
                ),
                conversation, response,
            )

        if conversation.order_stage == "ORDER_CONFIRMATION":
            if intent == "order_confirmation" and variant:
                order = self.orders.create_order(conversation, product, variant)
                db.add(order)
                await db.flush()
                return self._order_message(
                    t("order_confirmed", lang, order_id=order.id),
                    conversation, response,
                )
            return self._order_message(
                t("order_confirm_or_cancel", lang),
                conversation, response,
            )

        prompt = self.orders.get_next_prompt(conversation, store_language)
        if prompt:
            return self._order_message(prompt, conversation, response)
        return None

    async def _order_status(
        self, db, conversation, store_id, customer_number, store_language
    ) -> ProcessedResponse:
        result = await db.execute(
            select(Order)
            .where(
                Order.store_id == store_id,
                Order.customer_id == conversation.customer_id,
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        order = result.scalar_one_or_none()
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        if not order:
            text = t("order_not_found", lang)
        else:
            text = t("order_status", lang, order_id=order.id, status=order.status)
        return ProcessedResponse(
            message=text, intent="order_status", confidence=1.0,
            sources=[f"order:{order.id}"] if order else [],
            store_id=store_id, customer_number=customer_number,
        )

    async def _cancel_order(
        self, db, conversation, store_language
    ) -> ProcessedResponse:
        result = await db.execute(
            select(Order)
            .where(
                Order.conversation_id == conversation.id,
                Order.status.in_(["pending", "confirmed"]),
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        order = result.scalar_one_or_none()
        if order:
            order.status = "cancelled"
        conversation.order_stage = "BROWSING"
        conversation.quantity = None
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        return ProcessedResponse(
            message=t("order_cancelled", lang), intent="order_cancel", confidence=1.0,
            sources=[f"order:{order.id}"] if order else [],
            store_id=conversation.store_id,
        )

    async def _optional_ai_response(
        self, conversation, message, response, products, policies,
        store_name, store_language
    ):
        provider = get_ai_provider()
        if provider.name() == "mock" or not provider.is_configured():
            return response
        if not (
            response.needs_clarification
            or response.intent == "unknown"
            or response.confidence < 0.45
        ):
            return response

        allowed_ids = {
            option["product_id"] for option in (response.clarification_options or [])
        }
        if response.matched_product_id:
            allowed_ids.add(response.matched_product_id)
        candidates = [
            self._product_payload(product)
            for product in products if product.id in allowed_ids
        ][:5]
        history = [
            {"direction": item.direction, "content": item.content}
            for item in conversation.messages[-6:]
        ]
        ai = await provider.process(AIRequestContext(
            customer_message=message,
            detected_intent=response.intent,
            extracted_entities=response.extracted_entities,
            candidate_products=candidates,
            candidate_policies=[
                {"type": p.policy_type, "value": p.policy_value}
                for p in policies
            ],
            conversation_history=history,
            store_language=store_language,
            store_name=store_name,
        ))
        # Reject hallucinated catalogue identifiers.
        if ai.selected_product_id and ai.selected_product_id not in allowed_ids:
            return response
        allowed_variants = {
            v["id"] for product in candidates for v in product["variants"]
        }
        if ai.selected_variant_id and ai.selected_variant_id not in allowed_variants:
            return response
        return ProcessedResponse(
            message=ai.response_message,
            intent=response.intent,
            confidence=ai.confidence,
            matched_product_id=ai.selected_product_id,
            matched_variant_id=ai.selected_variant_id,
            image_url=ai.image_url,
            sources=response.sources,
            extracted_entities=response.extracted_entities,
            needs_clarification=ai.clarification_needed,
            needs_human=ai.needs_human,
            escalation_reason=ai.escalation_reason,
            store_id=response.store_id,
            customer_number=response.customer_number,
        )

    @staticmethod
    def _product(products, product_id):
        return next((p for p in products if p.id == product_id), None)

    @staticmethod
    def _variant(product, variant_id):
        if not product or not variant_id:
            return None
        return next((v for v in product.variants if v.id == variant_id), None)

    @staticmethod
    def _matching_variant(product, color, size):
        matches = [
            variant for variant in product.variants
            if variant.is_active and variant.stock > 0
            and (not color or (variant.color or "").lower() == color.lower())
            and (not size or (variant.size or "").lower() == size.lower())
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _customer_details(message, fallback_phone):
        phone_match = re.search(r'\b(?:\+?92|0)?3\d{9}\b', message)
        phone = phone_match.group(0) if phone_match else fallback_phone
        name_text = re.sub(r'\b(?:\+?92|0)?3\d{9}\b', '', message)
        name_text = re.sub(r'\b(my name is|name|naam|phone|number|hai|is)\b', '', name_text, flags=re.I)
        name = " ".join(name_text.split()).strip(" ,-")
        if not name or len(name) > 80 or any(char.isdigit() for char in name):
            return None, None
        return name.title(), phone

    @staticmethod
    def _looks_like_address(message, intent):
        if intent in {"order_confirmation", "acknowledgement"}:
            return False
        return len(message.strip()) >= 8 and (
            bool(re.search(r'\d|street|road|block|phase|sector|house|gali|mohalla', message, re.I))
            or "," in message
        )

    @staticmethod
    def _payment_method(normalized):
        if re.search(r'\b(cod|cash|cash on delivery)\b', normalized):
            return "COD"
        if re.search(r'\b(online|bank|transfer|easypaisa|jazzcash|card)\b', normalized):
            return "Online"
        return None

    @staticmethod
    def _order_message(message, conversation, base):
        return ProcessedResponse(
            message=message,
            intent="order_request",
            confidence=1.0,
            matched_product_id=conversation.current_product_id,
            matched_variant_id=conversation.current_variant_id,
            sources=base.sources,
            extracted_entities=base.extracted_entities,
            store_id=base.store_id,
            customer_number=base.customer_number,
        )

    @staticmethod
    def _product_payload(product):
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "image_url": product.image_url,
            "variants": [
                {
                    "id": v.id, "color": v.color, "size": v.size,
                    "price": v.price, "stock": v.stock,
                }
                for v in product.variants if v.is_active
            ],
        }

    @staticmethod
    def _alternatives(products, current_product_id, store_language):
        current = next((p for p in products if p.id == current_product_id), None)
        if not current:
            return None
        options = [
            p for p in products
            if p.id != current.id and p.is_active
            and (not current.category or p.category == current.category)
        ][:5]
        if not options:
            text = (
                "Is category mein abhi koi aur option available nahi hai."
                if store_language == "roman_urdu"
                else "There are no other options in this category right now."
            )
            return ProcessedResponse(
                message=text, intent="alternatives", confidence=1.0,
                matched_product_id=current.id,
            )
        header = (
            "Yeh alternatives available hain:"
            if store_language == "roman_urdu"
            else "These alternatives are available:"
        )
        clarification = []
        for index, product in enumerate(options, 1):
            header += f"\n{index}. {product.name}"
            clarification.append({
                "number": index, "product_id": product.id, "name": product.name
            })
        return ProcessedResponse(
            message=header, intent="alternatives", confidence=0.8,
            sources=[f"catalog:product:{p.id}" for p in options],
            clarification_options=clarification,
            needs_clarification=True,
        )
