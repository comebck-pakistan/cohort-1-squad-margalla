"""Order manager — state machine for order collection.

States: BROWSING → PRODUCT_SELECTED → VARIANT_SELECTED → QUANTITY_SELECTED →
        CUSTOMER_DETAILS_REQUIRED → ADDRESS_REQUIRED → PAYMENT_METHOD_REQUIRED →
        ORDER_CONFIRMATION → ORDER_CREATED

Collects: product, variant, quantity, customer name, phone, address, city,
          payment method. Shows final summary before creating order.
"""
import uuid
from app.models.conversation import Conversation
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductVariant

# Valid order stages
ORDER_STAGES = [
    "BROWSING",
    "PRODUCT_SELECTED",
    "VARIANT_SELECTED",
    "QUANTITY_SELECTED",
    "CUSTOMER_DETAILS_REQUIRED",
    "ADDRESS_REQUIRED",
    "PAYMENT_METHOD_REQUIRED",
    "ORDER_CONFIRMATION",
    "ORDER_CREATED",
]


class OrderManager:
    """Manage order state machine and order creation."""

    def get_next_prompt(
        self,
        conversation: Conversation,
        store_language: str = "roman_urdu",
    ) -> str | None:
        """Get the next prompt to show customer based on order stage."""
        stage = conversation.order_stage

        prompts = {
            "roman_urdu": {
                "PRODUCT_SELECTED": "Kaunsa color aur size chahiye?",
                "VARIANT_SELECTED": "Kitne pieces chahiye?",
                "QUANTITY_SELECTED": "Order ke liye apna naam aur phone number bataen.",
                "CUSTOMER_DETAILS_REQUIRED": "Delivery address aur city bataen.",
                "ADDRESS_REQUIRED": "Payment method kya hoga? (COD / Online)",
                "PAYMENT_METHOD_REQUIRED": None,  # Show summary
            },
            "english": {
                "PRODUCT_SELECTED": "Which color and size would you like?",
                "VARIANT_SELECTED": "How many pieces would you like?",
                "QUANTITY_SELECTED": "Please provide your name and phone number for the order.",
                "CUSTOMER_DETAILS_REQUIRED": "Please provide your delivery address and city.",
                "ADDRESS_REQUIRED": "What payment method would you prefer? (COD / Online)",
                "PAYMENT_METHOD_REQUIRED": None,  # Show summary
            },
        }

        lang_prompts = prompts.get(store_language, prompts["english"])
        return lang_prompts.get(stage)

    def advance_stage(
        self,
        conversation: Conversation,
        product: Product | None = None,
        variant: ProductVariant | None = None,
        quantity: int | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        customer_address: str | None = None,
        payment_method: str | None = None,
    ) -> str:
        """Advance the order stage based on provided data. Returns new stage."""
        stage = conversation.order_stage

        if stage == "BROWSING" and product:
            conversation.current_product_id = product.id
            conversation.order_stage = "PRODUCT_SELECTED"
            return "PRODUCT_SELECTED"

        if stage == "PRODUCT_SELECTED" and variant:
            conversation.current_variant_id = variant.id
            conversation.selected_color = variant.color
            conversation.selected_size = variant.size
            conversation.order_stage = "VARIANT_SELECTED"
            return "VARIANT_SELECTED"

        if stage == "VARIANT_SELECTED" and quantity:
            conversation.quantity = quantity
            conversation.order_stage = "QUANTITY_SELECTED"
            return "QUANTITY_SELECTED"

        if stage == "QUANTITY_SELECTED" and customer_name and customer_phone:
            conversation.customer_name = customer_name
            conversation.customer_phone = customer_phone
            conversation.order_stage = "CUSTOMER_DETAILS_REQUIRED"
            return "CUSTOMER_DETAILS_REQUIRED"

        if stage == "CUSTOMER_DETAILS_REQUIRED" and customer_address:
            conversation.customer_address = customer_address
            conversation.order_stage = "ADDRESS_REQUIRED"
            return "ADDRESS_REQUIRED"

        if stage == "ADDRESS_REQUIRED" and payment_method:
            conversation.payment_method = payment_method
            conversation.order_stage = "PAYMENT_METHOD_REQUIRED"
            return "PAYMENT_METHOD_REQUIRED"

        return stage

    def build_order_summary(
        self,
        conversation: Conversation,
        product: Product,
        variant: ProductVariant,
        store_language: str = "roman_urdu",
    ) -> str:
        """Build order summary for confirmation."""
        qty = conversation.quantity or 1
        total = variant.price * qty

        if store_language == "roman_urdu":
            return (
                f"📋 *Order Summary*\n\n"
                f"Product: {product.name}\n"
                f"Color: {variant.color or 'N/A'}\n"
                f"Size: {variant.size or 'N/A'}\n"
                f"Quantity: {qty}\n"
                f"Price: Rs. {variant.price:,.0f} × {qty} = Rs. {total:,.0f}\n\n"
                f"Naam: {conversation.customer_name}\n"
                f"Phone: {conversation.customer_phone}\n"
                f"Address: {conversation.customer_address}\n"
                f"Payment: {conversation.payment_method}\n\n"
                f"Kya aap yeh order confirm karna chahte hain? (Haan/Nahi)"
            )
        else:
            return (
                f"📋 *Order Summary*\n\n"
                f"Product: {product.name}\n"
                f"Color: {variant.color or 'N/A'}\n"
                f"Size: {variant.size or 'N/A'}\n"
                f"Quantity: {qty}\n"
                f"Price: Rs. {variant.price:,.0f} × {qty} = Rs. {total:,.0f}\n\n"
                f"Name: {conversation.customer_name}\n"
                f"Phone: {conversation.customer_phone}\n"
                f"Address: {conversation.customer_address}\n"
                f"Payment: {conversation.payment_method}\n\n"
                f"Would you like to confirm this order? (Yes/No)"
            )

    def create_order(
        self,
        conversation: Conversation,
        product: Product,
        variant: ProductVariant,
    ) -> Order:
        """Create an order from conversation state."""
        qty = conversation.quantity or 1
        total = variant.price * qty

        order = Order(
            store_id=conversation.store_id,
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            status="pending",
            total_amount=total,
            customer_name=conversation.customer_name,
            customer_phone=conversation.customer_phone,
            customer_address=conversation.customer_address,
            payment_method=conversation.payment_method,
        )

        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            variant_id=variant.id,
            product_name=product.name,
            variant_description=f"{variant.color or ''} {variant.size or ''}".strip(),
            quantity=qty,
            unit_price=variant.price,
        )
        order.items = [item]

        conversation.order_stage = "ORDER_CREATED"

        return order
