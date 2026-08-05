import pytest
import json
from app.models.conversation import Conversation
from app.services.conversation_manager import ConversationManager
from app.services.response_builder import ProcessedResponse
from app.services.catalog_search import CatalogSearchService
from app.models.product import Product, ProductVariant

@pytest.fixture
def conversation_manager():
    return ConversationManager()

@pytest.fixture
def sample_products():
    return [
        Product(id="prod1", name="Casual Black Sneakers", category="sneakers", is_active=True, store_id="store1"),
        Product(id="prod2", name="Running Black Sneakers", category="sneakers", is_active=True, store_id="store1"),
    ]

def test_recently_shown_products_limit(conversation_manager):
    conv = Conversation(id="conv1", customer_id="cust1", store_id="store1")
    
    conv.add_recently_shown_products(["prod1", "prod2"])
    assert conv.get_recently_shown_products() == ["prod1", "prod2"]
    
    # Adding a lot of products should cap at 5
    conv.add_recently_shown_products(["prod3", "prod4", "prod5", "prod6"])
    # "prod1" should be removed, list should have 5 items
    assert len(conv.get_recently_shown_products()) == 5
    assert conv.get_recently_shown_products() == ["prod2", "prod3", "prod4", "prod5", "prod6"]

def test_resolve_followup_returns_recently_shown_and_preferences(conversation_manager):
    conv = Conversation(id="conv1", customer_id="cust1", store_id="store1")
    conv.set_preferences({"category": "sneakers"})
    conv.add_recently_shown_products(["prod1"])
    
    entities = {"product_query": "casual"}
    resolved = conversation_manager.resolve_followup(conv, "casual", entities)
    
    assert resolved["recently_shown_products"] == ["prod1"]
    assert resolved["preferences"] == {"category": "sneakers"}

def test_apply_context_stores_recently_shown(conversation_manager):
    conv = Conversation(id="conv1", customer_id="cust1", store_id="store1")
    
    # Test ambiguous clarification choices
    response1 = ProcessedResponse(
        message="Choices:",
        intent="product_search",
        confidence=0.5,
        clarification_options=[{"product_id": "prod1"}, {"product_id": "prod2"}]
    )
    conversation_manager.apply_context(conv, response1)
    
    assert conv.get_recently_shown_products() == ["prod1", "prod2"]
    
    # Test definite match
    response2 = ProcessedResponse(
        message="Found it",
        intent="product_search",
        confidence=0.9,
        matched_product_id="prod3"
    )
    conversation_manager.apply_context(conv, response2)
    
    # Definite match adds to recently shown
    assert conv.get_recently_shown_products() == ["prod1", "prod2", "prod3"]

def test_catalog_search_prioritizes_recently_shown(sample_products):
    search_service = CatalogSearchService()
    
    # Both matches should normally have similar scores for "sneakers"
    res_normal = search_service.search(sample_products, query="sneakers")
    
    # Ambiguous because both are sneakers
    assert res_normal.is_ambiguous is True
    
    # But if prod1 was recently shown, it should be prioritized
    res_recent = search_service.search(sample_products, query="sneakers", recently_shown_products=["prod1"])
    
    assert res_recent.is_ambiguous is False
    assert res_recent.best_match.product.id == "prod1"

def test_catalog_search_ambiguous_still_works(sample_products):
    search_service = CatalogSearchService()
    
    # If both were recently shown, it remains ambiguous
    res_recent = search_service.search(sample_products, query="sneakers", recently_shown_products=["prod1", "prod2"])
    
    assert res_recent.is_ambiguous is True
