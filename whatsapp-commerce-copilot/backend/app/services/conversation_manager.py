"""Conversation manager — manages conversation state and follow-up resolution.

Handles:
- Get or create conversation for a customer
- Resolve follow-up messages using conversation context
- Store clarification candidates for disambiguation
- Update conversation state after each message
"""
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.services.response_builder import ProcessedResponse


class ConversationManager:
    """Manage conversation state for follow-up resolution."""

    async def get_or_create_conversation(
        self,
        db: AsyncSession,
        store_id: str,
        customer_number: str,
    ) -> tuple[Conversation, Customer]:
        """Get existing active conversation or create a new one."""
        # Get or create customer
        result = await db.execute(
            select(Customer).where(
                Customer.store_id == store_id,
                Customer.phone_number == customer_number,
            )
        )
        customer = result.scalar_one_or_none()

        if not customer:
            customer = Customer(
                store_id=store_id,
                phone_number=customer_number,
            )
            db.add(customer)
            await db.flush()

        # Get active conversation
        result = await db.execute(
            select(Conversation).where(
                Conversation.store_id == store_id,
                Conversation.customer_id == customer.id,
            ).order_by(Conversation.created_at.desc()).limit(1).options(selectinload(Conversation.messages))
        )
        conversation = result.scalar_one_or_none()

        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        # If conversation is closed, or expired (e.g., > 24 hours old), clear order context and reset to active
        if conversation:
            is_expired = (now - conversation.updated_at).total_seconds() > 24 * 3600
            if conversation.status == "closed" or is_expired:
                conversation.status = "active"
                self.clear_order_context(conversation)

        if not conversation:
            conversation = Conversation(
                store_id=store_id,
                customer_id=customer.id,
                status="active",
                is_ai_controlled=True,
            )
            # Initialize messages to avoid lazy-loading (and MissingGreenlet) later
            conversation.messages = []
            db.add(conversation)
            await db.flush()

        return conversation, customer

    def clear_product_context(self, conversation: Conversation):
        """Clear current product and variants (e.g., on a new topic)."""
        conversation.current_product_id = None
        conversation.current_variant_id = None
        conversation.selected_color = None
        conversation.selected_size = None
        conversation.quantity = None

    def clear_order_context(self, conversation: Conversation):
        """Clear product context and order state."""
        self.clear_product_context(conversation)
        conversation.order_stage = "BROWSING"
        conversation.customer_name = None
        conversation.payment_method = None
        # Intentionally keeping customer_phone and customer_address for future convenience


    def apply_context(
        self,
        conversation: Conversation,
        response: ProcessedResponse,
    ):
        """Update conversation context from the latest response."""
        if response.matched_product_id:
            conversation.current_product_id = response.matched_product_id
        if response.matched_variant_id:
            conversation.current_variant_id = response.matched_variant_id

        # Update selected attributes from entities
        entities = response.extracted_entities
        if entities.get("color"):
            conversation.selected_color = entities["color"]
        if entities.get("size"):
            conversation.selected_size = entities["size"]

        # Update preferences
        prefs = conversation.get_preferences()
        for key in ["category", "style", "color", "size", "budget_min", "budget_max"]:
            val = entities.get(key)
            if val is not None:
                prefs[key] = val
        conversation.set_preferences(prefs)

        # Store clarification candidates and recently shown products
        recently_shown = []
        if response.clarification_options:
            candidate_ids = [opt["product_id"] for opt in response.clarification_options]
            conversation.set_clarification_candidates_list(candidate_ids)
            conversation.pending_clarification = "product_selection"
            recently_shown.extend(candidate_ids)
        elif response.matched_product_id:
            # Clear clarification if we got a definite match
            conversation.pending_clarification = None
            conversation.clarification_candidates = None
            recently_shown.append(response.matched_product_id)
            
        if recently_shown:
            conversation.add_recently_shown_products(recently_shown)

    def resolve_followup(
        self,
        conversation: Conversation,
        message: str,
        entities: dict,
    ) -> dict:
        """Resolve follow-up context from conversation state.

        Returns a dict of resolved context to merge with extracted entities:
        {
            "product_id": resolved product ID,
            "color": resolved color,
            "size": resolved size,
            "from_context": True,
        }
        """
        resolved = {}
        message_lower = message.lower().strip()

        # Check if this is a clarification response (number selection)
        if conversation.pending_clarification == "product_selection":
            candidates = conversation.get_clarification_candidates_list()
            selected = self._resolve_numbered_choice(message_lower, candidates)
            if selected:
                resolved["product_id"] = selected
                resolved["from_context"] = True
                return resolved

        # Check if message is a pronoun reference to the selected product
        context_pronouns = {
            "this", "that", "this one", "that one", "the selected one", 
            "same one", "it", "its picture", "its photo", "send again", 
            "picture again", "the picture again", "send the picture again"
        }
        
        has_product_ref = bool(entities.get("product_query") or entities.get("sku") or entities.get("category"))
        is_pronoun_ref = False
        
        if entities.get("product_query") and entities.get("product_query").lower().strip() in context_pronouns:
            is_pronoun_ref = True
            has_product_ref = False # Treat as NO new product reference
            
        # Also check direct message for explicit pronouns if extractor missed it
        clean_msg = message_lower.replace("yes,", "").replace("yes", "").replace("haan,", "").replace("haan", "").strip()
        if not is_pronoun_ref and clean_msg in context_pronouns:
            is_pronoun_ref = True
            has_product_ref = False

        if not has_product_ref and conversation.current_product_id:
            # No new product reference — use context product
            resolved["product_id"] = conversation.current_product_id
            resolved["from_context"] = True

            # Fill in missing attributes from context
            if not entities.get("color") and conversation.selected_color:
                resolved["color"] = conversation.selected_color
            if not entities.get("size") and conversation.selected_size:
                resolved["size"] = conversation.selected_size
        elif has_product_ref:
            resolved["is_new_topic"] = True

        # Also return the recently shown products and preferences for search context
        resolved["recently_shown_products"] = conversation.get_recently_shown_products()
        resolved["preferences"] = conversation.get_preferences()

        return resolved

    def _resolve_numbered_choice(
        self,
        message: str,
        candidates: list[str],
    ) -> str | None:
        """Resolve a numbered choice from clarification candidates.

        Handles: "1", "first", "second", "2", "pehla", "doosra", "teesra", "number 2", "second one"
        """
        import re
        
        number_words = {
            "1": 0, "first": 0, "pehla": 0, "pehli": 0, "pahla": 0,
            "2": 1, "second": 1, "doosra": 1, "doosri": 1, "dusra": 1,
            "3": 2, "third": 2, "teesra": 2, "teesri": 2, "tisra": 2,
            "4": 3, "fourth": 3, "chautha": 3,
            "5": 4, "fifth": 4, "panchwa": 4,
        }
        
        # Check for "number X" or "X one"
        match = re.search(r'\b(?:number|num|no\.?)\s*(\d+)\b', message)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
                
        match = re.search(r'\b(\d+)\s*(?:one|wala)\b', message)
        if match:
            idx = int(match.group(1)) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]

        # Simple word matching ("second", "second one")
        tokens = message.split()
        for word, idx in number_words.items():
            if word in tokens or message.strip() == word or message.replace(" one", "").strip() == word or message.replace(" wala", "").strip() == word:
                if 0 <= idx < len(candidates):
                    return candidates[idx]

        return None

    async def save_message(
        self,
        db: AsyncSession,
        conversation: Conversation,
        content: str,
        direction: str,
        message_type: str = "text",
        whatsapp_message_id: str | None = None,
        processed_result: dict | None = None,
    ) -> Message:
        """Save a message to the conversation."""
        # Duplicate check
        if whatsapp_message_id:
            existing = await db.execute(
                select(Message).where(Message.whatsapp_message_id == whatsapp_message_id)
            )
            if existing.scalar_one_or_none():
                raise DuplicateMessageError(whatsapp_message_id)

        msg = Message(
            conversation_id=conversation.id,
            direction=direction,
            content=content,
            message_type=message_type,
            whatsapp_message_id=whatsapp_message_id,
            processed_result_json=json.dumps(processed_result) if processed_result else None,
        )
        db.add(msg)
        return msg

    async def get_message_by_whatsapp_id(
        self,
        db: AsyncSession,
        whatsapp_message_id: str | None,
    ) -> Message | None:
        if not whatsapp_message_id:
            return None
        result = await db.execute(
            select(Message).where(
                Message.whatsapp_message_id == whatsapp_message_id
            )
        )
        return result.scalar_one_or_none()


class DuplicateMessageError(Exception):
    """Raised when a duplicate WhatsApp message ID is detected."""
    def __init__(self, message_id: str):
        self.message_id = message_id
        super().__init__(f"Duplicate message: {message_id}")
