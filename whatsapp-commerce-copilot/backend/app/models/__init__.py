"""All SQLAlchemy models — import this module to register all tables."""
from app.models.store import Store
from app.models.product import Product, ProductAlias, ProductVariant
from app.models.category import Category
from app.models.policy import StorePolicy
from app.models.customer import Customer
from app.models.conversation import Conversation, Message
from app.models.order import Order, OrderItem
from app.models.whatsapp import WhatsAppSession
from app.models.handoff import HumanHandoff
from app.models.auth import AuthSession

__all__ = [
    "Store",
    "Product",
    "ProductAlias",
    "ProductVariant",
    "Category",
    "StorePolicy",
    "Customer",
    "Conversation",
    "Message",
    "Order",
    "OrderItem",
    "WhatsAppSession",
    "HumanHandoff",
    "AuthSession",
]
