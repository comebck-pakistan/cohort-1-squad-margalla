"""Conversation-aware controller shared by demo and WhatsApp entry points.

This is the application layer that was previously missing: it resolves
follow-ups, runs grounded retrieval, advances orders, optionally asks the AI
provider to phrase ambiguous results, and persists state through the caller's
transaction.
"""
import inspect
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.order import Order
from app.models.handoff import HumanHandoff
from app.models.product import Product, ProductVariant
from app.models.category import Category
from app.models.policy import StorePolicy

# Number of products shown per category page (bounded to avoid message spam).
CATEGORY_PAGE_SIZE = 5
# Number of product images sent in one gallery reply. WhatsApp treats a burst of
# media as spam, so a colour's designs are paged like any other menu.
MEDIA_PAGE_SIZE = 5
import structlog

from app.services import catalog_gallery
from app.services.ai_provider import AIRequestContext, KNOWN_INTENTS, get_ai_provider
from app.services.conversation_manager import ConversationManager
from app.services.entity_extractor import SIZE_NORMALIZE, extract_entities
from app.services.i18n import t
from app.services.intent_detector import detect_intent
from app.services.language_detector import detect_language
from app.services.message_processor import MessageProcessor
from app.services.order_manager import OrderManager
from app.services.response_builder import ProcessedResponse
from app.services.text_normalizer import normalize_color, normalize_text

logger = structlog.get_logger()


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
        vision: dict | None = None,
    ) -> ProcessedResponse:
        normalized = normalize_text(message)
        lang_detection = detect_language(message)
        language = lang_detection.input_language
        intent = detect_intent(normalized)
        entities = extract_entities(normalized, language)
        # Kept for the routing diagnostics below: once the LLM classification is
        # merged in, the original deterministic verdict is no longer recoverable,
        # and the two disagreeing is exactly what we need to see when a turn is
        # routed the wrong way.
        deterministic_intent = intent.intent
        deterministic_confidence = intent.confidence

        expected_order_field = {
            "QUANTITY_SELECTED": "customer_details",
            "CUSTOMER_DETAILS_REQUIRED": "address",
            "ADDRESS_REQUIRED": "payment_method",
        }.get(conversation.order_stage)
        provider = get_ai_provider()
        # A classification failure must degrade to the deterministic path, not
        # take the turn down with it: providers normally swallow their own
        # errors, but a transport-level fault (DNS, TLS, a hard timeout) escapes
        # and would otherwise turn every message into an error reply for as long
        # as the outage lasted.
        llm_classification = None
        try:
            classify_params = inspect.signature(provider.classify_intent).parameters
            if "expected_order_field" in classify_params:
                llm_classification = await provider.classify_intent(
                    message, store_language, expected_order_field
                )
            else:  # Compatibility for custom providers written against the old API.
                llm_classification = await provider.classify_intent(message, store_language)
        except Exception as exc:
            logger.warning(
                "intent_classification_failed",
                store_id=store_id, provider=type(provider).__name__,
                error=type(exc).__name__,
            )
        if llm_classification:
            # Only let the LLM override the deterministic intent when it names a
            # KNOWN intent AND is at least as confident as the deterministic
            # detector. A low-confidence or unknown LLM guess must never override
            # a higher-confidence deterministic result (Phase 9 grounding rule).
            if (
                llm_classification.intent
                and llm_classification.intent != "unknown"
                and llm_classification.intent in KNOWN_INTENTS
                and llm_classification.confidence >= intent.confidence
            ):
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

        # Seller-managed category browse flow: greeting → category menu, category
        # selection → product page, pagination, and "back". Only runs for idle
        # text conversations — never hijacks an active order or an image/vision
        # query, and falls through to normal search for specific product text.
        if vision is None and conversation.order_stage in ("BROWSING", "ORDER_CREATED"):
            cat_response = await self._handle_category_flow(
                db, conversation, message, normalized, intent, products,
                response_lang, store_id, store_name, customer_number,
            )
            if cat_response is not None:
                await db.flush()
                return cat_response

        # While an order is being completed, a plain "yes" is a confirmation and
        # nothing else. The LLM (and, for Urdu-script or emoji replies, the regex
        # table) can otherwise label it `acknowledgement`/`order_status`/
        # `alternatives`, which routes the turn away from the order state machine
        # and leaves the order unrecorded. Explicit cancels are never touched, and
        # this never applies while browsing, so ordinary chat is unaffected.
        is_affirmative = self._is_affirmative(message)
        if (
            intent.intent != "order_cancel"
            and is_affirmative
            and (
                # mid-order: a plain yes can only mean "go ahead"
                conversation.order_stage not in ("BROWSING", "ORDER_CREATED")
                # or they are looking at a product and answered the buy prompt
                or conversation.current_product_id
            )
        ):
            intent.intent = "order_confirmation"
            intent.confidence = max(intent.confidence, 0.9)

        # A "yes" is never a product name. Searching the catalogue for it produced
        # the nonsense reply "we couldn't find 'confirmed' in our catalogue" when a
        # customer answered a confirmation prompt.
        if is_affirmative:
            entities.product_query = None

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

        # Req 8: Explicit new-topic detection: clear old product context
        # ONLY clear context if this is a product search/inquiry, NOT an order/transaction command.
        # Never clear it mid-order: replies like a name or an address look like a
        # new topic, and dropping the product there strands the customer on
        # "select a product first" so the order can never be completed.
        if (
            resolved.get("is_new_topic")
            and intent.intent not in {"order_request", "order_confirmation", "order_status", "order_cancel", "greeting"}
            and conversation.order_stage in ("BROWSING", "ORDER_CREATED")
        ):
            self.conversations.clear_product_context(conversation)

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

        # When the accepted LLM classification is a product search with a rewritten
        # query (e.g. "lal wala" → "Red Kurta"), pass that query through so the
        # rewrite drives catalog search. In mock/deterministic operation the LLM
        # query equals the regex query, so this is a no-op; it only diverges when a
        # real LLM rewrites a phrase the regex could not resolve.
        product_query_override = None
        if (
            llm_classification
            and intent.intent == "product_search"
            and llm_classification.product_query
        ):
            product_query_override = llm_classification.product_query

        # For inbound image messages, the visual analysis is the strongest signal
        # (the LLM classification never sees the image). Build a bounded search
        # query from caption + visual attributes + OCR so catalog matching is
        # driven by what is actually in the picture, scoped to this store only.
        if vision:
            vision_query = self._build_vision_query(vision)
            if vision_query:
                product_query_override = vision_query

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
            product_query_override=product_query_override,
        )
        self.conversations.apply_context(conversation, response)
        await db.flush()

        # --- Intent precedence during an active checkout ---------------------
        # A customer part-way through an order is still a person having a
        # conversation: they ask for the picture, the price, whether medium is in
        # stock. Before this guard, EVERY message received during checkout fell
        # through _advance_order to get_next_prompt(), which replaced the real
        # answer with the current order prompt — so the assistant looked
        # hard-coded and simply repeated itself.
        #
        # An interrupt is answered from persisted catalogue rows, leaves every
        # piece of order state untouched, and ends with a reminder of what the
        # order is still waiting for.
        interrupt = await self._checkout_interrupt(
            db, conversation, message, intent.intent, entities, response,
            products, response_lang, llm_classification,
        )
        if interrupt is not None:
            self._log_order_routing(
                store_id, conversation, expected_order_field,
                deterministic_intent, deterministic_confidence,
                llm_classification, intent.intent, "interrupt",
            )
            await db.flush()
            if interrupt.needs_human:
                await self._create_handoff(db, conversation, interrupt, message)
            return interrupt

        order_response = await self._advance_order(
            db, conversation, message, intent.intent, entities, response,
            products, response_lang, customer_number, llm_classification
        )
        if order_response:
            response = order_response

        if conversation.order_stage not in ("BROWSING", "ORDER_CREATED") or order_response:
            self._log_order_routing(
                store_id, conversation, expected_order_field,
                deterministic_intent, deterministic_confidence,
                llm_classification, intent.intent,
                "order_field" if order_response else "normal",
            )

        # Image message with no catalog match: reply honestly with what was seen
        # instead of a generic "not found" or an AI rephrase that could imply
        # availability. Matches and clarifications keep the normal grounded flow.
        if (
            vision
            and not response.matched_product_id
            and not response.needs_clarification
        ):
            response.message = self._vision_no_match_message(vision, response_lang)
            response.intent = "product_search"
            return response

        response = await self._optional_ai_response(
            conversation, message, response, products, policies,
            store_name, response_lang
        )
        if response.needs_human:
            await self._create_handoff(db, conversation, response, message)
        return response

    # ------------------------------------------------------------------
    # Seller-managed category browse flow
    # ------------------------------------------------------------------

    async def _handle_category_flow(
        self, db, conversation, message, normalized, intent, products,
        response_lang, store_id, store_name, customer_number,
    ):
        """Greeting → category menu; selection → product page; pagination; back.

        Returns a ProcessedResponse to short-circuit, or None to fall through to
        normal catalog search (so specific product text keeps working).
        Categories always come from THIS store's active catalog — never hardcoded.
        """
        cats = (await db.execute(
            select(Category)
            .where(Category.store_id == store_id, Category.is_active == True)
            .order_by(Category.display_order, Category.name)
        )).scalars().all()

        text = (normalized or "").strip()
        snapshot = conversation.get_menu_snapshot()

        # "Back" steps up exactly one level of the guided flow:
        # colour's designs → colour menu → category menu.
        if self._is_back_command(text):
            if snapshot and snapshot.get("kind") == "color_products":
                colors = self._category_colors(products, snapshot.get("category_id"))
                if len(colors) > 1:
                    return self._category_colors_response(
                        conversation, snapshot.get("category_id"),
                        snapshot.get("category_name"), colors,
                        response_lang, store_id, customer_number)
            if cats:
                return self._category_menu_response(conversation, cats, store_name, response_lang, store_id, customer_number)
            return None

        # Browsing a product page → pagination + numbered product selection.
        # Pagination re-derives the source list from the snapshot scope so
        # "More"/"Previous" work for both category pages and all-catalogue browse.
        if snapshot and snapshot.get("kind") == "products":
            nav = self._nav_command(text)
            if nav in ("next", "prev"):
                delta = CATEGORY_PAGE_SIZE if nav == "next" else -CATEGORY_PAGE_SIZE
                source = self._snapshot_source(products, snapshot)
                return self._render_products_page(
                    conversation, source, snapshot.get("category_name", ""),
                    snapshot.get("scope", "category"), snapshot.get("category_id"),
                    max(0, snapshot.get("offset", 0) + delta),
                    response_lang, store_id, customer_number)
            sel = self._resolve_menu_selection(text, snapshot.get("items", []))
            if sel:
                detail = self._product_detail_response(products, sel["id"], conversation, response_lang, store_id, customer_number)
                if detail is not None:
                    return detail
            # else: fall through — customer may have typed a product name

        # A colour menu is showing → resolve "2" / "Black" into that colour's designs.
        if snapshot and snapshot.get("kind") == "category_colors":
            sel = self._resolve_menu_selection(text, snapshot.get("items", []))
            if sel:
                return self._color_products_response(
                    conversation, products, snapshot.get("category_id"),
                    snapshot.get("category_name"), sel.get("color"), 0,
                    response_lang, store_id, customer_number)

        # A colour's designs are showing → pagination + numbered design selection.
        # Same contract as the plain product page, so the number the customer
        # replies with resolves against exactly the images that were sent.
        if snapshot and snapshot.get("kind") == "color_products":
            nav = self._nav_command(text)
            if nav in ("next", "prev"):
                delta = MEDIA_PAGE_SIZE if nav == "next" else -MEDIA_PAGE_SIZE
                return self._render_color_products_page(
                    conversation, self._snapshot_source(products, snapshot),
                    snapshot.get("category_id"), snapshot.get("category_name"),
                    snapshot.get("color"),
                    max(0, snapshot.get("offset", 0) + delta),
                    response_lang, store_id, customer_number)
            sel = self._resolve_menu_selection(text, snapshot.get("items", []))
            if sel:
                detail = self._product_detail_response(
                    products, sel.get("product_id") or sel.get("id"), conversation,
                    response_lang, store_id, customer_number,
                    # The image was just sent in the gallery — repeating it here
                    # would be a second copy of the same picture.
                    include_image=False)
                if detail is not None:
                    return detail
            # else: fall through — customer may have typed a product name

        # Category selection against a shown category menu (number / ordinal / name)
        if snapshot and snapshot.get("kind") == "categories":
            sel = self._resolve_menu_selection(text, snapshot.get("items", []))
            if sel:
                return self._category_products_response(
                    conversation, products, sel["id"], sel["name"], 0,
                    response_lang, store_id, customer_number)

        # Category selection by near-exact name ("lawn", "show lawn", "lawn dikhao")
        cat = self._match_category_by_name(text, cats)
        if cat:
            return self._category_products_response(
                conversation, products, cat.id, cat.name, 0,
                response_lang, store_id, customer_number)

        # Browse / "show me options/designs" → retrieve real products immediately.
        # This is the fix for the questionnaire behaviour: once the customer asks
        # to see what's available, never keep asking clarification.
        if self._is_browse_request(text):
            return await self._browse_response(
                db, conversation, message, products, cats,
                response_lang, store_id, store_name, customer_number)

        # Greeting → show the store's category menu (only when categories exist)
        if intent.intent == "greeting" and cats:
            return self._category_menu_response(conversation, cats, store_name, response_lang, store_id, customer_number)

        return None

    @staticmethod
    def _is_back_command(text: str) -> bool:
        if text in {"back", "menu", "categories", "category", "go back", "wapas", "واپس"}:
            return True
        return "back to categor" in text or "categories dikha" in text

    @staticmethod
    def _nav_command(text: str) -> str | None:
        if text in {"more", "next", "aur", "agay", "aage", "next page", "زیادہ", "aur dikhao"}:
            return "next"
        if text in {"previous", "prev", "pichay", "peeche", "pichla"}:
            return "prev"
        return None

    @staticmethod
    def _clean_for_category(text: str) -> str:
        """Strip common lead/trail verbs so 'show lawn'/'lawn dikhao' → 'lawn'."""
        t = f" {text} "
        for w in (" show me ", " show ", " dikhao ", " dikha do ", " dikhaye ", " chahiye ",
                  " chaie ", " hai ", " available ", " do you have ", " mujhe ", " i want ",
                  " i need ", " please ", " ka ", " ke ", " ki "):
            t = t.replace(w, " ")
        return " ".join(t.split()).strip()

    def _match_category_by_name(self, text: str, cats) -> Category | None:
        """Match only on a near-exact category name so product queries fall through."""
        cleaned = self._clean_for_category(text)
        if not cleaned:
            return None
        for c in cats:
            if cleaned == c.name.lower().strip():
                return c
        return None

    _ORDINALS = {
        "first": 1, "1st": 1, "pehla": 1, "pehli": 1,
        "second": 2, "2nd": 2, "doosra": 2, "dusra": 2, "dosra": 2, "doosri": 2,
        "third": 3, "3rd": 3, "teesra": 3, "tesra": 3,
        "fourth": 4, "4th": 4, "chotha": 4, "chautha": 4,
        "fifth": 5, "5th": 5, "panchwa": 5, "paanchwa": 5,
    }

    def _resolve_menu_selection(self, text: str, items: list) -> dict | None:
        """Resolve a numbered/ordinal/name reply against the exact shown menu."""
        if not items:
            return None
        idx = None
        m = re.fullmatch(r"(\d+)", text)
        if m:
            idx = int(m.group(1))
        else:
            for word, n in self._ORDINALS.items():
                if re.search(rf"\b{re.escape(word)}\b", text):
                    idx = n
                    break
        if idx is not None:
            return next((it for it in items if it.get("n") == idx), None)
        # name equality (cleaned) against the shown item names
        cleaned = self._clean_for_category(text)
        if cleaned:
            for it in items:
                # Colour menus label their entries "color"; every other menu
                # uses "name". Both are matched on the exact shown label.
                label = (it.get("name") or it.get("color") or "").lower().strip()
                if cleaned == label:
                    return it
        return None

    def _category_menu_response(self, conversation, cats, store_name, response_lang, store_id, customer_number):
        items = [{"n": i, "id": c.id, "name": c.name} for i, c in enumerate(cats, 1)]
        conversation.set_menu_snapshot({"kind": "categories", "items": items})
        conversation.browse_category_id = None
        conversation.browse_offset = 0
        ur = response_lang in ("ur", "roman_urdu")
        header = (f"{store_name} mein khush aamdeed! Aap kya dhoond rahe hain?" if ur
                  else f"Welcome to {store_name}! What are you looking for?")
        footer = ("Category ka naam ya number bhejein." if ur
                  else "Reply with a category name or number.")
        lines = [header, ""] + [f"{it['n']}. {it['name']}" for it in items] + ["", footer]
        return ProcessedResponse(
            message="\n".join(lines), intent="category_menu", confidence=1.0,
            store_id=store_id, customer_number=customer_number,
        )

    @staticmethod
    def _display_price(product, color: str | None = None) -> float:
        """Lowest active variant price, optionally restricted to one colour."""
        if color:
            target = normalize_color(color)
            in_color = [
                v.price for v in product.variants
                if v.is_active and v.price and v.color
                and normalize_color(v.color) == target
            ]
            if in_color:
                return min(in_color)
        prices = [v.price for v in product.variants if v.is_active and v.price]
        return min(prices) if prices else (product.base_price or 0.0)

    # --- Browse / show-products intent -------------------------------------

    # Trigger words that mean "show me what you have". A message is a browse
    # request only when it is made up ENTIRELY of these triggers + filler words,
    # so specific product queries ("show me white cotton kurta") fall through.
    _BROWSE_TRIGGERS = {
        "available", "avail", "designs", "design", "dizain", "options", "option",
        "products", "product", "collection", "collections", "articles", "article",
        "dikhao", "dikhaen", "dikhaein", "dikha", "dekhao", "dekhna", "dikhado",
        "bhejo", "bhej", "bhejdo", "show", "stock", "more", "next", "cheezain", "cheezen",
    }
    _BROWSE_FILLER = {
        "kya", "kia", "koi", "kuch", "jo", "joh", "woh", "wo", "mujhe", "mjhe", "muje",
        "hai", "hain", "ha", "hn", "hon", "ho", "aapka", "aap", "apka", "ap", "apke",
        "aapke", "apkay", "pass", "paas", "pas", "k", "ka", "ke", "ki", "do", "dein",
        "den", "de", "dedo", "main", "mein", "me", "select", "karun", "karoon", "karne",
        "karna", "karo", "karein", "kar", "liye", "lie", "taake", "take", "please", "plz",
        "i", "want", "to", "what", "you", "have", "us", "some", "the", "a", "all", "sara",
        "saare", "saari", "sari", "poora", "poori", "batao", "bta", "bataen", "yr", "yaar",
        "aur", "zara", "zra", "thora", "thori", "abhi", "ne", "please",
    }
    _SCRIPT_BROWSE = ("دکھا", "ڈیزائن", "دیزائن", "آپشن", "دستیاب", "کلیکشن", "پروڈکٹ")

    @classmethod
    def _is_browse_request(cls, text: str) -> bool:
        if any(s in text for s in cls._SCRIPT_BROWSE):
            return True
        tokens = re.findall(r"[a-z]+", text.lower())
        if not tokens or not any(t in cls._BROWSE_TRIGGERS for t in tokens):
            return False
        residual = [t for t in tokens if t not in cls._BROWSE_TRIGGERS and t not in cls._BROWSE_FILLER]
        return len(residual) == 0

    @staticmethod
    def _available_products(products):
        """Active products, preferring those in stock; falls back to active-but-
        out-of-stock so we still show something truthfully (marked out of stock)."""
        active = [p for p in products if p.is_active]
        in_stock = [p for p in active if any(v.is_active and v.stock > 0 for v in p.variants)]
        return in_stock if in_stock else active

    def _snapshot_source(self, products, snapshot):
        """Reconstruct the product list a snapshot paginates over, by scope."""
        if snapshot.get("kind") == "color_products":
            return self._products_in_color(
                products, snapshot.get("category_id"), snapshot.get("color"))
        if snapshot.get("scope") == "all":
            return self._available_products(products)
        cid = snapshot.get("category_id")
        return [p for p in products if getattr(p, "category_id", None) == cid and p.is_active]

    async def _browse_response(self, db, conversation, message, products, cats,
                               response_lang, store_id, store_name, customer_number):
        """Deterministic response to a browse request: send real products.

        Empty catalogue → truthful message + owner notification. Large catalogue
        with categories → categories first (avoid flooding). Otherwise a bounded
        page of real, available products.
        """
        available = self._available_products(products)
        if not available:
            return await self._empty_catalog_response(db, conversation, message, response_lang, store_id, customer_number)
        if cats and len(available) > CATEGORY_PAGE_SIZE * 3:
            return self._category_menu_response(conversation, cats, store_name, response_lang, store_id, customer_number)
        return self._render_products_page(
            conversation, available, None, "all", None, 0,
            response_lang, store_id, customer_number)

    async def _empty_catalog_response(self, db, conversation, message, response_lang, store_id, customer_number):
        ur = response_lang in ("ur", "roman_urdu")
        msg = ("Mazrat, is waqt catalogue mein koi active product available nahi hai. "
               "Main shop owner ko notify kar raha hun." if ur else
               "Sorry, there are no active products in the catalogue right now. "
               "I'm notifying the shop owner.")
        # Notify the owner (pending handoff) WITHOUT disabling the AI, so the bot
        # keeps working once products are added.
        existing = await db.execute(
            select(HumanHandoff).where(
                HumanHandoff.conversation_id == conversation.id,
                HumanHandoff.status.in_(["pending", "active"]),
            ).limit(1)
        )
        if not existing.scalar_one_or_none():
            db.add(HumanHandoff(
                conversation_id=conversation.id, store_id=store_id,
                reason="empty_catalog",
                summary="Customer asked to browse but the catalogue is empty.",
                status="pending",
            ))
        return ProcessedResponse(
            message=msg, intent="browse_catalog", confidence=1.0,
            needs_human=True, escalation_reason="empty_catalog",
            store_id=store_id, customer_number=customer_number,
        )

    def _product_line(self, n, product, ur):
        """One grounded product entry — real DB values only."""
        price = self._display_price(product)
        sizes, colors = [], []
        for v in product.variants:
            if not v.is_active:
                continue
            if v.color and v.color not in colors:
                colors.append(v.color)
            if v.size and v.size not in sizes:
                sizes.append(v.size)
        in_stock = any(v.is_active and v.stock > 0 for v in product.variants)
        bits = []
        if price:
            bits.append(f"Rs. {price:,.0f}")
        if colors:
            bits.append("Colors: " + ", ".join(colors))
        if sizes:
            bits.append("Sizes: " + ", ".join(sizes))
        bits.append(("Stock mein" if in_stock else "Stock khatam") if ur else ("In stock" if in_stock else "Out of stock"))
        return f"{n}. {product.name}\n" + " | ".join(bits)

    def _render_products_page(self, conversation, source, label, scope, category_id,
                              offset, response_lang, store_id, customer_number):
        """Render one bounded page of real products and snapshot the exact menu.

        `scope` is "category" or "all"; the snapshot stores it so pagination and
        numbered replies resolve against precisely what was shown.
        """
        total = len(source)
        ur = response_lang in ("ur", "roman_urdu")

        if total == 0:
            conversation.set_menu_snapshot(None)
            conversation.browse_category_id = category_id
            name = label or ("this category" if not ur else "is category")
            msg = (f"Is waqt '{name}' mein koi product available nahi hai."
                   if ur else f"There are no products in '{name}' right now.")
            return ProcessedResponse(message=msg, intent="category_products", confidence=1.0,
                                     store_id=store_id, customer_number=customer_number)

        max_offset = ((total - 1) // CATEGORY_PAGE_SIZE) * CATEGORY_PAGE_SIZE
        offset = max(0, min(offset, max_offset))
        page = source[offset:offset + CATEGORY_PAGE_SIZE]
        items = [{"n": offset + i + 1, "id": p.id, "name": p.name} for i, p in enumerate(page)]
        conversation.set_menu_snapshot({
            "kind": "products", "scope": scope, "store_id": store_id,
            "category_id": category_id, "category_name": label,
            "page": offset // CATEGORY_PAGE_SIZE, "offset": offset, "total": total,
            "items": items, "ts": datetime.utcnow().isoformat(),
        })
        conversation.browse_category_id = category_id
        conversation.browse_offset = offset
        conversation.add_recently_shown_products([p.id for p in page])

        if scope == "all":
            intro = "Ye designs abhi available hain:" if ur else "Here's what's available right now:"
        else:
            intro = f"{label}:"
        lines = [intro, ""]
        for it, p in zip(items, page):
            lines.append(self._product_line(it["n"], p, ur))

        shown_upto = offset + len(page)
        nav = ["Number bhej kar product dekhein" if ur else "Reply with a number to view a product"]
        if shown_upto < total:
            nav.append("'More'")
        if offset > 0:
            nav.append("'Previous'")
        nav.append("'Back' categories ke liye" if ur else "'Back' for categories")
        lines += ["", ", ".join(nav) + "."]
        return ProcessedResponse(
            message="\n".join(lines),
            intent="browse_catalog" if scope == "all" else "category_products",
            confidence=1.0,
            sources=[f"catalog:category:{category_id}"] if category_id else ["catalog:browse"],
            store_id=store_id, customer_number=customer_number,
        )

    def _category_products_response(self, conversation, products, category_id, category_name,
                                    offset, response_lang, store_id, customer_number):
        """Open a category: ask for a colour first when that is a real choice.

        A shop owner answering "Cotton dikhao" asks which colour before pulling
        designs off the shelf. That only makes sense when the category actually
        holds several products in several colours — a single product, or a
        single colour, goes straight to the product page as before.
        """
        in_cat = [p for p in products if getattr(p, "category_id", None) == category_id and p.is_active]
        colors = self._category_colors(products, category_id)
        if len(colors) > 1 and len(self._available_products(in_cat)) > 1:
            return self._category_colors_response(
                conversation, category_id, category_name, colors,
                response_lang, store_id, customer_number)
        return self._render_products_page(
            conversation, in_cat, category_name, "category", category_id,
            offset, response_lang, store_id, customer_number)

    # --- Colour menu inside a category -------------------------------------

    @staticmethod
    def _category_colors(products, category_id) -> list[str]:
        """Distinct sellable colours in one category, in catalogue order.

        Only active, in-stock variants count, so the menu never offers a colour
        the customer cannot actually buy. Labels keep the seller's own casing;
        de-duplication is done on the normalised form so "Blk"/"black" collapse.
        """
        colors, seen = [], set()
        for p in products:
            if not p.is_active or getattr(p, "category_id", None) != category_id:
                continue
            for v in p.variants:
                if not (v.is_active and v.stock > 0 and v.color):
                    continue
                key = normalize_color(v.color)
                if key in seen:
                    continue
                seen.add(key)
                colors.append(v.color.strip())
        return colors

    @staticmethod
    def _products_in_color(products, category_id, color):
        """Active products in a category with a sellable variant in `color`.

        Scoped to the category the customer opened — the caller only ever passes
        this store's products, so a colour never reaches across stores.
        """
        if not color:
            return []
        target = normalize_color(color)
        return [
            p for p in products
            if p.is_active and getattr(p, "category_id", None) == category_id
            and any(
                v.is_active and v.stock > 0 and v.color
                and normalize_color(v.color) == target
                for v in p.variants
            )
        ]

    def _category_colors_response(self, conversation, category_id, category_name, colors,
                                  response_lang, store_id, customer_number):
        """Show the colours stocked in a category and snapshot the exact menu."""
        items = [{"n": i, "color": c} for i, c in enumerate(colors, 1)]
        conversation.set_menu_snapshot({
            "kind": "category_colors", "store_id": store_id,
            "category_id": category_id, "category_name": category_name,
            "items": items, "ts": datetime.utcnow().isoformat(),
        })
        conversation.browse_category_id = category_id
        conversation.browse_offset = 0
        ur = response_lang in ("ur", "roman_urdu")
        header = (f"{category_name} mein available colors:" if ur
                  else f"Colors available in {category_name}:")
        footer = ("Color ka naam ya number bhejein." if ur
                  else "Reply with a color name or number.")
        lines = [header, ""] + [f"{it['n']}. {it['color']}" for it in items] + ["", footer]
        return ProcessedResponse(
            message="\n".join(lines), intent="category_colors", confidence=1.0,
            sources=[f"catalog:category:{category_id}"],
            store_id=store_id, customer_number=customer_number,
        )

    def _color_products_response(self, conversation, products, category_id, category_name,
                                 color, offset, response_lang, store_id, customer_number):
        """Thin wrapper: render one colour's designs inside a category."""
        return self._render_color_products_page(
            conversation, self._products_in_color(products, category_id, color),
            category_id, category_name, color, offset,
            response_lang, store_id, customer_number)

    def _render_color_products_page(self, conversation, source, category_id, category_name,
                                    color, offset, response_lang, store_id, customer_number):
        """Send one bounded gallery of a colour's designs, numbered for selection.

        Products that have a picture become `media_items` (image + numbered
        caption); products without one stay as text lines so nothing is dropped
        and the numbering stays continuous either way.
        """
        ur = response_lang in ("ur", "roman_urdu")
        label = " ".join(x for x in (color, category_name) if x)
        total = len(source)

        if total == 0:
            conversation.set_menu_snapshot(None)
            conversation.browse_category_id = category_id
            msg = (f"Is waqt '{label}' mein koi design available nahi hai."
                   if ur else f"There are no designs in '{label}' right now.")
            return ProcessedResponse(
                message=msg, intent="color_products", confidence=1.0,
                sources=[f"catalog:category:{category_id}"],
                store_id=store_id, customer_number=customer_number)

        max_offset = ((total - 1) // MEDIA_PAGE_SIZE) * MEDIA_PAGE_SIZE
        offset = max(0, min(offset, max_offset))
        page = source[offset:offset + MEDIA_PAGE_SIZE]
        items = [{"n": offset + i + 1, "product_id": p.id, "name": p.name}
                 for i, p in enumerate(page)]
        conversation.set_menu_snapshot({
            "kind": "color_products", "store_id": store_id,
            "category_id": category_id, "category_name": category_name,
            "color": color, "offset": offset, "total": total,
            "items": items, "ts": datetime.utcnow().isoformat(),
        })
        conversation.browse_category_id = category_id
        conversation.browse_offset = offset
        conversation.add_recently_shown_products([p.id for p in page])

        media_items, text_lines = [], []
        skipped = 0
        for it, prod in zip(items, page):
            price = catalog_gallery.gallery_price(prod, color)
            blockers = catalog_gallery.gallery_blockers(prod, color)
            image_url = catalog_gallery.resolve_media_url(prod.image_url)
            caption = catalog_gallery.build_caption(
                it["n"], prod.name, category_name, color, price)

            if blockers or not image_url or not caption:
                # Not gallery-ready: never send a half-filled caption or a
                # `PKR 0` price. The design still gets its number as a text
                # line, so one incomplete row cannot hide the valid ones or
                # break the numbering the customer replies with.
                skipped += 1
                logger.info(
                    "gallery_product_skipped",
                    store_id=store_id, category_id=category_id,
                    color=normalize_color(color) if color else None,
                    product_id=prod.id,
                    reasons=sorted(blockers.keys()) or ["caption_incomplete"],
                )
                text_lines.append(
                    f"{it['n']}. {prod.name}" + (f" — PKR {price:,.0f}" if price else ""))
                continue

            variant = next(iter(catalog_gallery.sellable_variants(prod, color)), None)
            media_items.append({
                "product_id": prod.id,
                "variant_id": variant.id if variant else None,
                "image_url": image_url,
                "caption": caption,
                "selection_number": it["n"],
            })

        logger.info(
            "gallery_page_built",
            store_id=store_id, category_id=category_id,
            color=normalize_color(color) if color else None,
            matched=total, on_page=len(page),
            gallery_ready=len(media_items), skipped=skipped,
        )

        header = (f"{label} mein {total} designs available hain:" if ur
                  else f"{total} designs available in {label}:")
        nav = ["Number bhej kar design select karein" if ur
               else "Reply with a number to select a design"]
        if offset + len(page) < total:
            nav.append("'More'")
        if offset > 0:
            nav.append("'Previous'")
        nav.append("'Back' colors ke liye" if ur else "'Back' for colors")
        nav_text = ", ".join(nav) + "."

        lines = [header]
        if text_lines:
            lines += [""] + text_lines
        if not media_items:
            # Nothing to send as media — keep it a single self-contained text.
            lines += ["", nav_text]

        return ProcessedResponse(
            message="\n".join(lines), intent="color_products", confidence=1.0,
            media_items=media_items,
            media_footer=nav_text if media_items else None,
            sources=[f"catalog:category:{category_id}"],
            store_id=store_id, customer_number=customer_number,
        )

    def _product_detail_response(self, products, pid, conversation, response_lang, store_id,
                                customer_number, include_image: bool = True):
        product = next((p for p in products if p.id == pid), None)
        if not product:
            return None
        conversation.current_product_id = product.id
        conversation.add_recently_shown_products([product.id])
        active_vars = [v for v in product.variants if v.is_active]
        sizes, colors = [], []
        for v in active_vars:
            if v.size and v.size not in sizes:
                sizes.append(v.size)
            if v.color and v.color not in colors:
                colors.append(v.color)
        prices = [v.price for v in active_vars if v.price]
        in_stock = any(v.stock > 0 for v in active_vars)

        ur = response_lang in ("ur", "roman_urdu")
        lines = [f"*{product.name}*"]
        if prices:
            lo, hi = min(prices), max(prices)
            lines.append(f"Price: Rs. {lo:,.0f}" + (f" – Rs. {hi:,.0f}" if hi != lo else ""))
        elif product.base_price:
            lines.append(f"Price: Rs. {product.base_price:,.0f}")
        if sizes:
            lines.append(("Available sizes: " if not ur else "Sizes: ") + ", ".join(sizes))
        if colors:
            lines.append(("Available colors: " if not ur else "Colors: ") + ", ".join(colors))
        lines.append("Stock: " + (("Available" if not ur else "Available") if in_stock
                                   else ("Out of stock" if not ur else "Stock khatam")))

        # Purchase call-to-action — turn "viewing" into "ordering" the way a real
        # shop owner asks for the sale. Only invite an order when it's in stock;
        # out of stock → steer back to other designs. This is what makes the
        # guided flow (categories → products → choose → ORDER) actually close.
        lines.append("")
        if in_stock:
            if ur:
                lines.append("Order karne ke liye 'Order' likhein, ya doosray designs "
                             "dekhne ke liye 'Back' likhein.")
            else:
                lines.append("Reply 'Order' to buy this, or 'Back' to see other designs.")
        else:
            if ur:
                lines.append("Ye abhi stock mein nahi hai. Doosray designs dekhne ke liye "
                             "'Back' likhein.")
            else:
                lines.append("This is currently out of stock. Reply 'Back' to see other designs.")

        return ProcessedResponse(
            message="\n".join(lines), intent="product_search", confidence=1.0,
            matched_product_id=product.id,
            matched_variant_id=active_vars[0].id if len(active_vars) == 1 else None,
            image_url=product.image_url if include_image else None,
            sources=[f"catalog:product:{product.id}"],
            store_id=store_id, customer_number=customer_number,
        )

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

    # Intents that are a QUESTION asked during checkout rather than an answer to
    # the checkout question. Each is answered from the database and must never
    # consume the expected order field. order_cancel / order_status short-circuit
    # earlier in process(); human_agent_request is here so the handoff is still
    # created instead of being swallowed by the order prompt.
    _ORDER_INTERRUPT_INTENTS = frozenset({
        "human_agent_request", "complaint",
        "picture_request", "price_query", "stock_query",
        "color_query", "size_query", "negotiation",
        "delivery_query", "returns_query", "exchange_query", "cod_query",
        "store_info",
    })

    # Product facts answered straight from the catalogue rather than from the
    # generic search pipeline, because during checkout we already know exactly
    # which product and variant the customer means.
    _GROUNDED_INTERRUPTS = frozenset({
        "picture_request", "price_query", "stock_query", "color_query", "size_query",
    })

    @staticmethod
    def _log_order_routing(store_id, conversation, expected_order_field,
                           deterministic_intent, deterministic_confidence,
                           llm_classification, final_intent, decision):
        """Record how one checkout turn was routed.

        Deliberately carries no message text, name, phone or address — only the
        classification and the decision, which is what is needed to explain a
        turn that went the wrong way.
        """
        logger.info(
            "order_turn_routing",
            store_id=store_id,
            order_stage=conversation.order_stage,
            expected_order_field=expected_order_field,
            deterministic_intent=deterministic_intent,
            deterministic_confidence=round(float(deterministic_confidence or 0), 2),
            llm_intent=(llm_classification.intent if llm_classification else None),
            llm_confidence=(round(float(llm_classification.confidence), 2)
                            if llm_classification else None),
            llm_answers_expected_field=(llm_classification.expected_field_valid
                                        if llm_classification else None),
            final_intent=final_intent,
            decision=decision,
        )

    def _checkout_pending_reminder(self, conversation, store_language) -> str:
        """The outstanding checkout question, phrased as a reminder."""
        prompt = self.orders.get_next_prompt(conversation, store_language)
        if not prompt:
            return ""
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        return t("checkout_still_waiting", lang, prompt=prompt)

    async def _checkout_interrupt(
        self, db, conversation, message, intent_name, entities, response,
        products, store_language, llm_classification,
    ):
        """Answer a question asked mid-checkout without consuming the order field.

        Returns a ProcessedResponse to short-circuit the turn, or None to let the
        order state machine handle the message as an answer. Order state is never
        mutated here — that is the whole point.
        """
        if conversation.order_stage in ("BROWSING", "ORDER_CREATED"):
            return None
        if intent_name not in self._ORDER_INTERRUPT_INTENTS:
            return None

        product = self._product(products, conversation.current_product_id)
        if not product:
            return None

        # A bare "black" or "M" answering the colour/size question can be labelled
        # color_query/size_query. While that question is on the table, a message
        # that names one of THIS product's real labels is an answer, not a query.
        # Only skip when the entity actually answers the question being asked:
        # a size named while we are choosing a variant is an answer, while the
        # same word at the name/phone step ("is medium available?") is a question.
        if conversation.order_stage == "PRODUCT_SELECTED":
            label_color, label_size = self._match_variant_labels(product, message)
            if label_color or label_size or entities.color or entities.size:
                return None
        if conversation.order_stage == "VARIANT_SELECTED" and entities.quantity:
            return None
        # Deterministic answer-guards, kept deliberately narrow: they only cover
        # the intents that a real ANSWER can be mislabelled as, so the model
        # being unavailable cannot cost us a payment method or an address.
        # A broad guard here is worse than none — treating every plausible-
        # looking sentence as the answer swallowed "Send me the picture" as a
        # delivery address.
        if (conversation.order_stage == "ADDRESS_REQUIRED"
                and intent_name == "cod_query"
                and self._payment_method(normalized=normalize_text(message))):
            return None
        if (conversation.order_stage == "CUSTOMER_DETAILS_REQUIRED"
                and intent_name == "store_info"
                and self._looks_like_address(message, intent_name)):
            # "address" is a store_info keyword, so a real delivery address can
            # be labelled store_info. The address step owns that message.
            return None

        # The model saw the expected order field when it classified this message.
        # If it says the message DOES supply that field, believe it over an intent
        # label and let the state machine consume the turn.
        if llm_classification and llm_classification.expected_field_valid is True:
            return None

        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        variant = self._variant(product, conversation.current_variant_id)
        reminder = self._checkout_pending_reminder(conversation, store_language)

        if intent_name in self._GROUNDED_INTERRUPTS:
            answer, image_url = self._product_fact_answer(
                product, variant, intent_name, lang, entities)
            # We answered this from the catalogue itself, so any low-confidence
            # escalation the generic search pipeline raised no longer applies.
            # Propagating it handed the conversation to a human — and silenced
            # the bot for the rest of the order — over a question we had just
            # answered correctly.
            needs_human, escalation_reason = False, None
        elif intent_name in ("human_agent_request", "complaint"):
            # The pipeline re-detects intent from the raw text and had labelled
            # this a product search, so the customer got "we couldn't find ... in
            # our catalogue" instead of being put through to a person. Build the
            # handoff reply from the accepted intent instead.
            handoff = self.processor.response_builder.build_human_handoff_response(
                "explicit_request" if intent_name == "human_agent_request" else "complaint",
                store_language,
            )
            answer, image_url = handoff.message, None
            needs_human, escalation_reason = True, handoff.escalation_reason
        else:
            # Policy intents: the pipeline already answered them from the store's
            # own policies. Keep that answer, keep its escalation flag.
            answer, image_url = response.message, None
            needs_human, escalation_reason = response.needs_human, response.escalation_reason

        if not answer:
            return None

        return ProcessedResponse(
            message=answer + reminder,
            intent=intent_name,
            confidence=1.0,
            matched_product_id=product.id,
            matched_variant_id=variant.id if variant else None,
            image_url=image_url,
            sources=[f"catalog:product:{product.id}"] if image_url or intent_name in self._GROUNDED_INTERRUPTS else response.sources,
            extracted_entities=response.extracted_entities,
            needs_human=needs_human,
            escalation_reason=escalation_reason,
            store_id=response.store_id,
            customer_number=response.customer_number,
        )

    def _product_fact_answer(self, product, variant, intent_name, lang, entities=None):
        """Answer a product question from persisted rows. Returns (text, image_url).

        Everything here reads the database. Nothing is model-generated, so the
        assistant can never quote a price, a stock level or an image that the
        seller did not actually save.
        """
        active = [v for v in product.variants if v.is_active]
        chosen = [variant] if variant else active

        if intent_name == "picture_request":
            image_url = catalog_gallery.resolve_media_url(product.image_url)
            if not image_url:
                # Honest, not "I'll send it shortly" — there is nothing to send.
                return t("picture_none_saved", lang, product=product.name), None
            bits = [f"*{product.name}*"]
            colors = [v.color for v in chosen if v.color]
            sizes = [v.size for v in chosen if v.size]
            if colors:
                bits.append(("رنگ: " if lang == "ur" else "Colour: ") + ", ".join(dict.fromkeys(colors)))
            if sizes:
                bits.append(("سائز: " if lang == "ur" else "Size: ") + ", ".join(dict.fromkeys(sizes)))
            price = catalog_gallery.gallery_price(product) or (
                min((v.price for v in chosen if v.price), default=None))
            if price:
                bits.append(f"Price: PKR {price:,.0f}")
            return "\n".join(bits), image_url

        if intent_name == "price_query":
            prices = [v.price for v in chosen if v.price] or [product.base_price or 0]
            lo, hi = min(prices), max(prices)
            if not lo:
                return None, None
            text = f"*{product.name}* — PKR {lo:,.0f}"
            if hi != lo:
                text += f" – PKR {hi:,.0f}"
            return text, None

        if intent_name == "stock_query":
            in_stock = [v for v in chosen if v.stock and v.stock > 0]
            if not in_stock:
                return f"*{product.name}* — " + t("stock_out", lang), None
            total = sum(v.stock for v in in_stock)
            return f"*{product.name}* — " + t("stock_available", lang, stock=total), None

        if intent_name in ("color_query", "size_query"):
            key = "color" if intent_name == "color_query" else "size"
            in_stock = [v for v in active if v.stock and v.stock > 0]
            labels = list(dict.fromkeys(
                getattr(v, key) for v in in_stock if getattr(v, key)))

            # The customer asked about one specific label ("is medium available?").
            # Answer that question rather than listing everything.
            asked = getattr(entities, key, None) if entities else None
            if asked:
                match = next((lab for lab in labels
                              if lab.strip().casefold() == str(asked).strip().casefold()), None)
                if match:
                    return t("variant_label_available", lang,
                             label=match, product=product.name), None
                if labels:
                    return t("variant_label_unavailable", lang, label=asked,
                             product=product.name, options=", ".join(labels)), None
                # The product simply has no such option — saying "out of stock"
                # here would be untrue, since the product itself is available.
                stock_line = (t("stock_available", lang, stock=sum(v.stock for v in in_stock))
                              if in_stock else t("stock_out", lang))
                none_key = "no_size_options" if key == "size" else "no_color_options"
                return t(none_key, lang, product=product.name) + " " + stock_line, None

            if not labels:
                stock_line = (t("stock_available", lang, stock=sum(v.stock for v in in_stock))
                              if in_stock else t("stock_out", lang))
                none_key = "no_size_options" if key == "size" else "no_color_options"
                return t(none_key, lang, product=product.name) + " " + stock_line, None

            label_word = (("رنگ" if key == "color" else "سائز") if lang == "ur"
                          else ("Colours" if key == "color" else "Sizes"))
            return f"*{product.name}*\n{label_word}: " + ", ".join(labels), None

        return None, None

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
        llm_classification=None,
    ) -> ProcessedResponse | None:
        active = conversation.order_stage not in {"BROWSING", "ORDER_CREATED"}
        if not active and intent not in {"order_request", "order_confirmation"}:
            return None

        # Stage at the START of this turn. Cascading (several fields in one message,
        # e.g. "medium 2") is intentional, but the name/phone reply must not also be
        # swallowed as the delivery address just because it contains phone digits —
        # so the address step only fires on a turn that BEGAN awaiting the address.
        entry_stage = conversation.order_stage

        product = self._product(products, conversation.current_product_id)
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        if not product:
            return self._order_message(
                t("select_product_first", lang),
                conversation, response,
            )

        # Start an order only from an explicit buying action.
        if conversation.order_stage in {"BROWSING", "ORDER_CREATED"}:
            if intent == "order_request":
                conversation.order_stage = "BROWSING"
                self.orders.advance_stage(conversation, product=product)
            elif intent == "order_confirmation":
                # Only advance if they explicitly provided size/quantity
                if entities.quantity or entities.size:
                    conversation.order_stage = "BROWSING"
                    self.orders.advance_stage(conversation, product=product)
                elif self._is_affirmative(message):
                    # They are looking at a specific product and answered a
                    # confirmation prompt ("Confirmed", "Proceed", "Haan"). A shop
                    # owner would start writing the order, not re-answer with a
                    # catalogue search — which is what used to happen, producing
                    # "we couldn't find 'confirmed' in our catalogue".
                    conversation.order_stage = "BROWSING"
                    self.orders.advance_stage(conversation, product=product)
                else:
                    # They just said "Yes, that one" or confirmed a product.
                    # This is product selection, NOT order confirmation.
                    return None

        # The size/colour question lists this product's real labels, so a bare
        # "M" or "Black" answering it is read against exactly those labels. The
        # generic extractor deliberately does not treat single letters as sizes
        # (it would guess sizes out of ordinary chat), which left the customer
        # re-asked forever right at the point of sale.
        if conversation.order_stage == "PRODUCT_SELECTED":
            label_color, label_size = self._match_variant_labels(product, message)
            if label_color:
                entities.color = label_color
            if label_size:
                entities.size = label_size

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
            if variant is None:
                # If the product has exactly one active variant there is nothing to
                # choose — auto-select it so we don't ask a pointless size/color
                # question (the way a shop owner wouldn't ask about a one-size item).
                active_vars = [v for v in product.variants if v.is_active]
                if len(active_vars) == 1:
                    variant = active_vars[0]
            if variant:
                self.orders.advance_stage(conversation, variant=variant)

        if conversation.order_stage == "VARIANT_SELECTED":
            # An explicit number always counts ("medium 2" in one message). Reading
            # a bare yes as "one piece" only makes sense when the customer was
            # already being asked how many — otherwise the "Order" that just
            # started the funnel would silently answer the quantity question too.
            quantity = entities.quantity
            if (
                quantity is None
                and intent == "order_confirmation"
                and entry_stage == "VARIANT_SELECTED"
            ):
                quantity = 1
            if quantity:
                self.orders.advance_stage(conversation, quantity=quantity)

        if conversation.order_stage == "QUANTITY_SELECTED" and entry_stage == "QUANTITY_SELECTED":
            # Same rule as the address step: only a reply sent while we were
            # actually asking for the name may be stored as the name, or "Order"
            # ends up as the customer's name.
            # A phone already captured on an earlier turn stands in for the
            # WhatsApp number, so a later bare name completes the pair.
            name, phone = self._customer_details(
                message, conversation.customer_phone or customer_number)
            # The model sees the expected order field in the same classification
            # request made for every inbound message. It can veto text that is
            # semantically not a name; local validation remains authoritative so
            # a model outage or hallucinated extraction cannot corrupt an order.
            if llm_classification and llm_classification.expected_field_valid is False:
                name = phone = None
            if name and phone:
                self.orders.advance_stage(
                    conversation, customer_name=name, customer_phone=phone
                )
            elif self._is_refusal(message, llm_classification):
                # Repeating the same prompt at someone who just said no reads as
                # a broken machine. Say why the name is needed and offer a way out.
                return self._order_message(
                    t("checkout_name_refused", lang), conversation, response)
            else:
                supplied_phone = self._phone_in_message(message)
                if supplied_phone:
                    # They gave the number but no usable name. Keep the number —
                    # making them retype it is the kind of thing that loses a sale.
                    conversation.customer_phone = supplied_phone
                    return self._order_message(
                        t("checkout_name_only", lang), conversation, response)
                if message.strip():
                    # They replied, but not with a name. Repeating the identical
                    # sentence is what made the bot look hard-coded; show the
                    # format that actually works instead.
                    return self._order_message(
                        t("checkout_name_phone_example", lang), conversation, response)

        if conversation.order_stage == "CUSTOMER_DETAILS_REQUIRED" and entry_stage == "CUSTOMER_DETAILS_REQUIRED":
            ai_accepts = not (
                llm_classification and llm_classification.expected_field_valid is False
            )
            if ai_accepts and self._looks_like_address(message, intent):
                conversation.requested_city = entities.delivery_city
                self.orders.advance_stage(
                    conversation, customer_address=message.strip()
                )

        if conversation.order_stage == "ADDRESS_REQUIRED":
            payment = self._payment_method(normalized=normalize_text(message))
            if llm_classification and llm_classification.expected_field_valid is False:
                payment = None
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
            # The previous turn showed the summary and asked "confirm? (Yes/No)",
            # so a plain affirmative IS the confirmation regardless of how the LLM
            # labelled it. Without this the funnel stalls here and no order is
            # ever written (the bug where orders never reached the dashboard).
            if (intent == "order_confirmation" or self._is_affirmative(message)) and variant:
                return await self._finalize_order(
                    db, conversation, product, variant, lang, response
                )
            return self._order_message(
                t("order_confirm_or_cancel", lang),
                conversation, response,
            )

        prompt = self.orders.get_next_prompt(conversation, store_language)
        if prompt:
            return self._order_message(prompt, conversation, response)
        return None

    async def _finalize_order(
        self,
        db: AsyncSession,
        conversation: Conversation,
        product: Product,
        variant: ProductVariant,
        lang: str,
        response: ProcessedResponse,
    ) -> ProcessedResponse:
        """Commit an order atomically: lock variant, validate, persist, decrement.

        An order is only successful after the row is validated and stock is
        decremented within the caller's transaction. A failed check returns a
        truthful message and never creates an order or mutates stock.
        """
        qty = conversation.quantity or 1

        # Re-load and lock the authoritative variant row inside the transaction.
        # FOR UPDATE serializes concurrent final-unit purchases on Postgres;
        # SQLite ignores the clause but the single-writer model is equivalent.
        locked = await db.execute(
            select(ProductVariant)
            .where(ProductVariant.id == variant.id)
            .with_for_update()
        )
        fresh = locked.scalar_one_or_none()
        if fresh is None:
            return self._order_message(
                t("order_item_no_longer_available", lang), conversation, response
            )

        # Verify the variant still belongs to this store and is active.
        parent = await db.get(Product, fresh.product_id)
        if (
            parent is None
            or parent.store_id != conversation.store_id
            or not parent.is_active
            or not fresh.is_active
        ):
            return self._order_message(
                t("order_item_no_longer_available", lang), conversation, response
            )

        # Verify sufficient stock before committing anything.
        if fresh.stock < qty:
            return self._order_message(
                t("order_insufficient_stock", lang, stock=fresh.stock),
                conversation, response,
            )

        # Persist the order and decrement stock in one transaction.
        order = self.orders.create_order(conversation, product, fresh)
        db.add(order)
        fresh.stock -= qty
        await db.flush()
        self.conversations.clear_order_context(conversation)
        return self._order_message(
            t("order_confirmed", lang, order_id=order.id),
            conversation, response,
        )

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
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        message = t("order_cancelled", lang)
        if order is None and conversation.order_stage in ("BROWSING", "ORDER_CREATED"):
            # Nothing in progress and no order on file — don't claim we cancelled
            # something that never existed.
            return ProcessedResponse(
                message=t("order_not_found", lang), intent="order_cancel",
                confidence=1.0, store_id=conversation.store_id,
            )
        if order:
            # Cancelling releases the units back to the catalogue. Confirming an
            # order decremented stock, so without this the seller silently loses
            # sellable inventory on every cancellation. Guarded on status so a
            # repeated "cancel" can never restock the same order twice.
            await self._restore_stock(db, order)
            order.status = "cancelled"
            await db.flush()
            message = t("order_cancelled_with_id", lang, order_id=order.id)
        self.conversations.clear_order_context(conversation)
        return ProcessedResponse(
            message=message, intent="order_cancel", confidence=1.0,
            sources=[f"order:{order.id}"] if order else [],
            store_id=conversation.store_id,
        )

    async def _restore_stock(self, db: AsyncSession, order: Order) -> None:
        """Return an order's reserved units to their variants.

        Locks each variant row so a concurrent purchase cannot lose the update.
        """
        for item in order.items:
            if not item.variant_id or not item.quantity:
                continue
            variant = (await db.execute(
                select(ProductVariant)
                .where(ProductVariant.id == item.variant_id)
                .with_for_update()
            )).scalar_one_or_none()
            if variant is not None:
                variant.stock += item.quantity

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

        authoritative_image_url = None
        if ai.selected_product_id:
            for p in candidates:
                if p["id"] == ai.selected_product_id:
                    authoritative_image_url = p.get("image_url")
                    break

        # Server-side validation against AI future promises (English, Roman Urdu, Urdu script)
        if self._detect_future_action_promise(ai.response_message):
            # Reject AI response and fall back to the deterministic one.
            return response

        # Only `_finalize_order` may tell a customer their order is placed, and it
        # always includes the real order ID. The AI otherwise improvises a
        # convincing "your order has been confirmed!" while no order row exists and
        # no stock is reserved — the customer believes they have bought something
        # and the seller never sees it.
        if self._detect_false_order_claim(ai.response_message):
            return response

        # Preserve deterministic image and variants if AI didn't select a valid one
        final_product_id = ai.selected_product_id if ai.selected_product_id else response.matched_product_id
        final_variant_id = ai.selected_variant_id if ai.selected_variant_id else response.matched_variant_id
        final_image_url = authoritative_image_url if ai.selected_product_id else response.image_url

        return ProcessedResponse(
            message=ai.response_message,
            intent=response.intent,
            confidence=ai.confidence,
            matched_product_id=final_product_id,
            matched_variant_id=final_variant_id,
            image_url=final_image_url,
            sources=response.sources,
            extracted_entities=response.extracted_entities,
            needs_clarification=ai.clarification_needed,
            needs_human=ai.needs_human,
            escalation_reason=ai.escalation_reason,
            store_id=response.store_id,
            customer_number=response.customer_number,
        )

    @staticmethod
    def _build_vision_query(vision: dict) -> str | None:
        """Build a bounded catalog-search query from visual analysis.

        Combines the customer's caption, detected visual attributes (colour,
        category, style, material, branding) and any OCR text. Falls back to the
        description only when nothing else is present. All vision output is
        untrusted descriptive data — used purely as search terms, never as
        instructions. The result is length-capped so it cannot dominate matching.
        """
        parts: list[str] = []
        caption = (vision.get("original_caption") or "").strip()
        if caption:
            parts.append(caption)
        for attr in (vision.get("attributes") or []):
            if isinstance(attr, str) and attr.strip():
                parts.append(attr.strip())
        ocr = (vision.get("text_ocr") or "").strip()
        if ocr:
            parts.append(ocr)
        if not parts:
            description = (vision.get("description") or "").strip()
            if description:
                # Use only the first few words of a verbose description.
                parts.append(" ".join(description.split()[:8]))
        query = " ".join(parts).strip()
        return query[:200] if query else None

    @staticmethod
    def _vision_no_match_message(vision: dict, store_language: str) -> str:
        """Honest, vision-grounded reply when no catalog item matches the image.

        References what was actually seen without claiming availability, and
        offers to look for similar items. Never invents products.
        """
        description = (vision.get("description") or "").strip()
        # Keep the snippet short and single-line for a clean WhatsApp reply.
        snippet = " ".join(description.split())[:120]
        if store_language in ("ur", "roman_urdu"):
            if snippet:
                return (
                    f"Mujhe tasveer mein {snippet} nazar aa raha hai, lekin is store "
                    "ke catalog mein iska exact match nahi mila. Kya aap milte-julte "
                    "options dekhna chahenge?"
                )
            return (
                "Mujhe is store ke catalog mein is tasveer ka exact match nahi mila. "
                "Kya aap milte-julte options dekhna chahenge?"
            )
        if snippet:
            return (
                f"I can see {snippet}, but I couldn't find an exact match in this "
                "store's catalog. Would you like to see similar items?"
            )
        return (
            "I couldn't find an exact match for this image in this store's catalog. "
            "Would you like to see similar items?"
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
    def _canonical_size(value: str) -> str:
        """Fold size spellings together so "M", "m" and "Medium" are one size."""
        v = (value or "").strip().lower()
        return SIZE_NORMALIZE.get(v, v)

    @classmethod
    def _match_variant_labels(cls, product, message):
        """Resolve a short reply against this product's own variant labels.

        Returns (color, size) using the seller's exact stored labels, so the
        variant lookup that follows matches on the real row. Only whole-message
        matches count, which keeps "Order" or "Back" from ever being read as a
        size.
        """
        text = normalize_text(message).strip()
        if not text:
            return None, None
        color = size = None
        for v in product.variants:
            if not v.is_active:
                continue
            if v.size and cls._canonical_size(text) == cls._canonical_size(v.size):
                size = v.size
            if v.color and normalize_color(text) == normalize_color(v.color):
                color = v.color
        return color, size

    @staticmethod
    def _matching_variant(product, color, size):
        matches = [
            variant for variant in product.variants
            if variant.is_active and variant.stock > 0
            and (not color or (variant.color or "").lower() == color.lower())
            and (not size or (variant.size or "").lower() == size.lower())
        ]
        return matches[0] if len(matches) == 1 else None

    _PHONE_RE = re.compile(r"\b(?:\+?92|0)?3\d{9}\b")

    @classmethod
    def _phone_in_message(cls, message: str) -> str | None:
        """A Pakistani mobile number typed by the customer, or None.

        Distinct from the WhatsApp number they are messaging from: this is what
        they explicitly gave us, so it can be kept while we ask for the name.
        """
        match = cls._PHONE_RE.search(message or "")
        return match.group(0) if match else None

    # Deterministic refusals, so a declining customer is recognised even when the
    # model is unavailable. The LLM signal is preferred when present.
    _REFUSAL_PATTERNS = (
        r"\b(do|does)?\s?n['’]?t\s+(want|wanna|wish)\b",
        r"\bwon['’]?t\s+(give|share|tell|provide)\b",
        r"\b(not|no)\s+(giving|sharing|telling|providing)\b",
        r"\brefuse\b",
        r"\bnahi\s+(dena|dunga|dungi|batana|bataunga|bataungi)\b",
        r"\bnaam\s+nahi\b",
        r"\bnahi\s+bata\w*\b",
        r"نہیں\s*(دوں|دینا|بتا)",
    )

    @classmethod
    def _is_refusal(cls, message: str, llm_classification=None) -> bool:
        if llm_classification is not None and getattr(llm_classification, "is_refusal", None) is True:
            return True
        text = normalize_text(message or "").casefold()
        return any(re.search(pat, text) for pat in cls._REFUSAL_PATTERNS)

    @staticmethod
    def _customer_details(message, fallback_phone):
        phone_match = re.search(r'\b(?:\+?92|0)?3\d{9}\b', message)
        phone = phone_match.group(0) if phone_match else fallback_phone
        name_text = re.sub(r'\b(?:\+?92|0)?3\d{9}\b', '', message)
        name_text = re.sub(r'\b(my name is|name|naam|phone|number|hai|is)\b', '', name_text, flags=re.I)
        name = " ".join(name_text.split()).strip(" ,-")
        if not ConversationController._plausible_customer_name(name):
            return None, None
        return name.title(), phone

    @staticmethod
    def _plausible_customer_name(name: str) -> bool:
        """Reject commands/refusals that the old extractor stored as names."""
        name = " ".join((name or "").split()).strip(" ,-")
        if not 2 <= len(name) <= 80 or any(char.isdigit() for char in name):
            return False
        words = name.casefold().split()
        if not 1 <= len(words) <= 5:
            return False
        blocked = {
            "order", "confirm", "confirmed", "yes", "no", "ok", "okay",
            "cod", "address", "price", "product", "send", "picture", "photo",
            "nahi", "nahin", "haan", "want", "dont", "don't", "refuse",
            "hello", "hi", "hey", "enter", "entering", "give", "giving",
            "provided", "provide", "skip", "not", "my", "name", "phone",
        }
        if any(word.strip("'-.!") in blocked for word in words):
            return False
        return all(char.isalpha() or char in " '-." for char in name)

    @classmethod
    def _looks_like_address(cls, message, intent):
        """Is this reply the delivery address?

        The guard exists so a bare "ok"/"haan" is never stored as an address, and
        it is read deterministically from the text. It used to key off `intent`,
        but a real address classifies as `unknown` (0.0) so the LLM's label always
        won — and when the LLM called an address an `acknowledgement` the address
        step stalled forever and the order was never completed.
        """
        if cls._is_affirmative(message):
            return False
        text = message.strip()
        if len(text) < 6:
            return False
        if re.search(r'\d|street|road|block|phase|sector|house|gali|mohalla', text, re.I) or "," in text:
            return True
        # Most Pakistani addresses given over WhatsApp are just "City Area"
        # ("Mardan Katlang") — no house number, no comma, no street word. The
        # old rule rejected every one of them and the order stalled forever.
        # Questions asked at this step no longer reach here: interrupt intents
        # are routed away before the address is read, which is what makes
        # accepting a bare two-word place name safe.
        words = [w for w in re.split(r"\s+", text) if w]
        return len(words) >= 2 and all(
            all(ch.isalpha() or ch in "-'." for ch in w) for w in words)

    # --- Deterministic "yes" reading -------------------------------------
    # Used only on a turn that has just asked a Yes/No question. Kept
    # deterministic on purpose: a real LLM commonly labels "haan"/"ok"/"👍" as a
    # bare `acknowledgement` (a known intent at ~0.9) which outranks the
    # deterministic `order_confirmation` (0.7) and overrides it — the customer
    # then confirms forever and the order is never recorded. Urdu-script
    # affirmatives are included because the bot replies in Urdu script live, so
    # customers answer in it, and the regex intent table does not cover them.
    _AFFIRM_EMOJI = ("👍", "✅", "👌", "🆗")
    _AFFIRM_WORDS = {
        "haan", "han", "hn", "haa", "ji", "jee", "yes", "yeah", "yep", "yup", "ya",
        "ok", "okay", "okey", "theek", "thik", "teek", "sahi", "acha", "achha", "accha",
        "confirm", "confirmed", "pakka", "final", "done", "order", "book", "bilkul",
        "karo", "kardo", "krdo", "kardein", "lo",
        # "proceed"/"go ahead" style replies to a confirmation prompt
        "proceed", "ahead", "go", "chalo", "chalein", "shuru", "aagay", "agay", "barhein",
        "کریں", "چلیں", "آگے", "شروع",
        "ہاں", "جی", "ٹھیک", "اوکے", "اوکی", "کنفرم", "بالکل", "کریں", "کردیں", "کرو",
    }
    _AFFIRM_FILLER = {
        "hai", "hain", "he", "h", "please", "plz", "thanks", "thank", "you", "shukriya",
        "bhai", "yaar", "yr", "ap", "aap", "sure", "g", "gi", "it", "this",
        "that", "i", "me", "mein", "ab", "abhi", "place", "my", "kar", "do", "dein", "den",
        "ہے", "کر", "دو", "دیں", "براہ", "کرم", "شکریہ", "میں",
    }

    @classmethod
    def _is_affirmative(cls, message: str) -> bool:
        """True when the reply is a plain yes and nothing else.

        Every token must be an affirmative or filler word, so a question such as
        "kya price hai?" or a correction can never be read as a confirmation.
        """
        raw = (message or "").strip()
        if not raw:
            return False
        has_emoji = any(e in raw for e in cls._AFFIRM_EMOJI)
        tokens = [tok.strip(".,!?۔:;-'\"") for tok in normalize_text(raw).lower().split()]
        tokens = [tok for tok in tokens if tok]
        if not tokens:
            return has_emoji  # a bare 👍 normalizes to an empty string
        if not all(tok in cls._AFFIRM_WORDS or tok in cls._AFFIRM_FILLER for tok in tokens):
            return False
        return has_emoji or any(tok in cls._AFFIRM_WORDS for tok in tokens)

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
            image_url=base.image_url,
            sources=base.sources,
            extracted_entities=base.extracted_entities,
            store_id=base.store_id,
            customer_number=base.customer_number,
        )

    # Phrases that assert an order exists / is placed. Only the deterministic
    # `_finalize_order` may say this, and it names a real order ID.
    _FALSE_ORDER_CLAIM_PHRASES = (
        "order has been", "order is confirmed", "order confirmed", "order is placed",
        "order has successfully", "successfully confirmed", "successfully placed",
        "order placed", "placed your order", "confirmed your order", "booked your order",
        "finalize your order", "finalise your order", "finalizing your order",
        "order is on its way", "order ho gaya", "order ho gya", "order confirm ho",
        "order place ho", "order kar diya", "order kardiya", "order mukammal",
        "آرڈر کنفرم", "آرڈر ہو گیا", "آرڈر ہوگیا", "آرڈر کر دیا", "آرڈر کردیا",
        "آرڈر مکمل", "آرڈر درج",
    )

    @classmethod
    def _detect_false_order_claim(cls, message: str) -> bool:
        """Does this AI text claim an order was created?

        Used to reject the response: an order only exists when the state machine
        wrote one, and that path produces its own message carrying the order ID.
        """
        if not message:
            return False
        cleaned = " ".join(re.sub(r"[^\w\s؀-ۿ]", " ", message.lower()).split())
        return any(phrase in cleaned for phrase in cls._FALSE_ORDER_CLAIM_PHRASES)

    @staticmethod
    def _detect_future_action_promise(message: str) -> bool:
        """Detect if the message promises a future action like fetching images."""
        if not message:
            return False

        import re
        cleaned = re.sub(r'[^\w\s]', ' ', message.lower())
        cleaned = " ".join(cleaned.split())

        phrases = [
            "fetching", "hold on", "sending the picture", "sending pictures",
            "will send", "fetch", "wait a moment", "sending it now", "shortly",
            "bhej rahi hoon", "bhejta hoon", "bhej raha hoon", "wait karein", "wait karain",
            "tasveer bhejta", "tasveer bhej rahi", "bhej deiti hoon", "tasveer bhejta hoon",
            "تصویر بھیج", "تصویریں", "انتظار کریں", "بھیج رہا", "بھیج رہی"
        ]

        cleaned_phrases = [" ".join(re.sub(r'[^\w\s]', ' ', p).split()) for p in phrases]

        for phrase in cleaned_phrases:
            if phrase in cleaned:
                return True

        lower_msg = message.lower()
        for phrase in phrases:
            if phrase in lower_msg:
                return True

        return False

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
