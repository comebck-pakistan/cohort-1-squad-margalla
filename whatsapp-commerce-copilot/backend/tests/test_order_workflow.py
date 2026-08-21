"""Tests for order workflow state machine."""
import pytest
from app.services.order_manager import OrderManager
from app.services.conversation_controller import ConversationController
from app.models.conversation import Conversation
from app.models.product import Product, ProductVariant


@pytest.fixture
def manager():
    return OrderManager()


@pytest.fixture
def conversation():
    return Conversation(
        id="conv-order-test",
        store_id="test-store",
        customer_id="cust-001",
        order_stage="BROWSING",
        is_ai_controlled=True,
    )


@pytest.fixture
def product():
    p = Product(
        id="prod-001",
        store_id="test-store",
        name="Women's Embroidered Kurta",
        category="kurta",
        sku="WEK-001",
        base_price=2500.0,
        is_active=True,
    )
    return p


@pytest.fixture
def variant():
    return ProductVariant(
        id="var-001",
        product_id="prod-001",
        color="sky blue",
        size="medium",
        price=2500.0,
        stock=4,
        sku="WEK-001-SB-M",
        is_active=True,
    )


class TestStageAdvancement:
    """Test order state machine transitions."""

    def test_browsing_to_product_selected(self, manager, conversation, product):
        stage = manager.advance_stage(conversation, product=product)
        assert stage == "PRODUCT_SELECTED"
        assert conversation.current_product_id == product.id

    def test_product_selected_to_variant_selected(self, manager, conversation, product, variant):
        conversation.order_stage = "PRODUCT_SELECTED"
        stage = manager.advance_stage(conversation, variant=variant)
        assert stage == "VARIANT_SELECTED"
        assert conversation.selected_color == "sky blue"
        assert conversation.selected_size == "medium"

    def test_variant_to_quantity(self, manager, conversation):
        conversation.order_stage = "VARIANT_SELECTED"
        stage = manager.advance_stage(conversation, quantity=2)
        assert stage == "QUANTITY_SELECTED"
        assert conversation.quantity == 2

    def test_quantity_to_details(self, manager, conversation):
        conversation.order_stage = "QUANTITY_SELECTED"
        stage = manager.advance_stage(
            conversation,
            customer_name="Ali Hassan",
            customer_phone="923001234567",
        )
        assert stage == "CUSTOMER_DETAILS_REQUIRED"
        assert conversation.customer_name == "Ali Hassan"


class TestCustomerDetailValidation:
    """Order replies must not be persisted as customer names."""

    @pytest.mark.parametrize("message", [
        "Order",
        "confirmed",
        "hello",
        "I am not entering my name",
        "send picture",
        "COD",
        "12345",
    ])
    def test_non_names_are_rejected(self, message):
        name, phone = ConversationController._customer_details(
            message, "923001234567"
        )
        assert name is None
        assert phone is None

    def test_real_name_and_phone_are_extracted(self):
        name, phone = ConversationController._customer_details(
            "My name is Ali Hassan, 03001234567", "923009999999"
        )
        assert name == "Ali Hassan"
        assert phone == "03001234567"

    def test_details_to_address(self, manager, conversation):
        conversation.order_stage = "CUSTOMER_DETAILS_REQUIRED"
        stage = manager.advance_stage(
            conversation,
            customer_address="123 Main St, Lahore",
        )
        assert stage == "ADDRESS_REQUIRED"

    def test_address_to_payment(self, manager, conversation):
        conversation.order_stage = "ADDRESS_REQUIRED"
        stage = manager.advance_stage(conversation, payment_method="COD")
        assert stage == "PAYMENT_METHOD_REQUIRED"
        assert conversation.payment_method == "COD"

    def test_full_flow(self, manager, conversation, product, variant):
        """Test complete order flow from BROWSING to PAYMENT_METHOD_REQUIRED."""
        manager.advance_stage(conversation, product=product)
        assert conversation.order_stage == "PRODUCT_SELECTED"

        manager.advance_stage(conversation, variant=variant)
        assert conversation.order_stage == "VARIANT_SELECTED"

        manager.advance_stage(conversation, quantity=1)
        assert conversation.order_stage == "QUANTITY_SELECTED"

        manager.advance_stage(conversation, customer_name="Test", customer_phone="923001234567")
        assert conversation.order_stage == "CUSTOMER_DETAILS_REQUIRED"

        manager.advance_stage(conversation, customer_address="Test Address, Lahore")
        assert conversation.order_stage == "ADDRESS_REQUIRED"

        manager.advance_stage(conversation, payment_method="COD")
        assert conversation.order_stage == "PAYMENT_METHOD_REQUIRED"


class TestOrderSummary:
    """Test order summary generation."""

    def test_summary_roman_urdu(self, manager, conversation, product, variant):
        conversation.quantity = 2
        conversation.customer_name = "Ali Hassan"
        conversation.customer_phone = "923001234567"
        conversation.customer_address = "123 Main St, Lahore"
        conversation.payment_method = "COD"

        summary = manager.build_order_summary(conversation, product, variant, "roman_urdu")
        # roman_urdu store_language now maps to Urdu-script output
        assert "Women's Embroidered Kurta" in summary  # product name never translated
        assert "sky blue" in summary  # colour string from DB never translated
        assert "medium" in summary    # size string from DB never translated
        assert "2" in summary
        assert "5,000" in summary  # 2500 × 2
        assert "Ali Hassan" in summary
        assert "COD" in summary
        # Summary should contain the Urdu-script confirm prompt
        urdu_chars = [c for c in summary if 0x0600 <= ord(c) <= 0x06FF]
        assert len(urdu_chars) > 0, "roman_urdu summary should contain Urdu Unicode characters"


class TestOrderCreation:
    """Test order creation from conversation state."""

    def test_create_order(self, manager, conversation, product, variant):
        conversation.quantity = 2
        conversation.customer_name = "Ali Hassan"
        conversation.customer_phone = "923001234567"
        conversation.customer_address = "123 Main St, Lahore"
        conversation.payment_method = "COD"

        order = manager.create_order(conversation, product, variant)
        assert order.store_id == "test-store"
        assert order.total_amount == 5000.0  # 2500 × 2
        assert order.customer_name == "Ali Hassan"
        assert order.payment_method == "COD"
        assert len(order.items) == 1
        assert order.items[0].quantity == 2
        assert order.items[0].unit_price == 2500.0
        assert conversation.order_stage == "ORDER_CREATED"

    def test_create_order_single_quantity(self, manager, conversation, product, variant):
        conversation.quantity = 1
        conversation.customer_name = "Test"
        conversation.customer_phone = "923001111111"
        conversation.customer_address = "Test Address"
        conversation.payment_method = "Online"

        order = manager.create_order(conversation, product, variant)
        assert order.total_amount == 2500.0
        assert order.items[0].quantity == 1


class TestNextPrompt:
    """Test getting next prompt for each stage."""

    def test_prompt_for_product_selected(self, manager, conversation):
        conversation.order_stage = "PRODUCT_SELECTED"
        prompt = manager.get_next_prompt(conversation, "roman_urdu")
        assert prompt is not None
        # roman_urdu → Urdu-script prompt; check it has Urdu Unicode characters
        urdu_chars = [c for c in prompt if 0x0600 <= ord(c) <= 0x06FF]
        assert len(urdu_chars) > 0, "roman_urdu prompt should be Urdu script"

    def test_prompt_for_variant_selected(self, manager, conversation):
        conversation.order_stage = "VARIANT_SELECTED"
        prompt = manager.get_next_prompt(conversation, "english")
        assert "pieces" in prompt.lower() or "many" in prompt.lower()

    def test_no_prompt_for_browsing(self, manager, conversation):
        conversation.order_stage = "BROWSING"
        prompt = manager.get_next_prompt(conversation, "roman_urdu")
        assert prompt is None
