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
from app.services.i18n import t

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


def _lang(store_language: str) -> str:
    """Normalise store_language to i18n code."""
    if store_language in ("ur", "roman_urdu"):
        return "ur"
    return "en"


class OrderManager:
    """Manage order state machine and order creation."""

    def get_next_prompt(
        self,
        conversation: Conversation,
        store_language: str = "roman_urdu",
    ) -> str | None:
        """Get the next prompt to show customer based on order stage."""
        lang = _lang(store_language)
        stage = conversation.order_stage

        stage_key_map = {
            "PRODUCT_SELECTED": "ask_color_size",
            "VARIANT_SELECTED": "ask_quantity",
            "QUANTITY_SELECTED": "ask_name_phone",
            "CUSTOMER_DETAILS_REQUIRED": "ask_address",
            "ADDRESS_REQUIRED": "ask_payment",
            "PAYMENT_METHOD_REQUIRED": None,  # Show summary
        }
        key = stage_key_map.get(stage)
        if key is None:
            return None
        return t(key, lang)

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
        lang = _lang(store_language)
        qty = conversation.quantity or 1
        total = variant.price * qty

        na = t("label_na", lang)
        lines = [
            t("order_summary_header", lang),
            "",
            f"{t('label_product', lang)}: {product.name}",
            f"{t('label_color', lang)}: {variant.color or na}",
            f"{t('label_size', lang)}: {variant.size or na}",
            f"{t('label_quantity', lang)}: {qty}",
            f"{t('label_price', lang)}: Rs. {variant.price:,.0f} × {qty} = Rs. {total:,.0f}",
            "",
            f"{t('label_name', lang)}: {conversation.customer_name}",
            f"{t('label_phone', lang)}: {conversation.customer_phone}",
            f"{t('label_address', lang)}: {conversation.customer_address}",
            f"{t('label_payment', lang)}: {conversation.payment_method}",
            "",
            t("order_confirm_prompt", lang),
        ]
        return "\n".join(lines)

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
