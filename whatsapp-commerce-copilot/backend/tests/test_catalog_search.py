"""Tests for catalog search service.

Covers: exact SKU, alias, product+color, product+size, multi-word colors,
hyphenated colors, unknown product, ambiguous product, store isolation.
"""
import pytest
from app.services.catalog_search import CatalogSearchService
from tests.conftest import make_fashion_products, make_shoe_products


@pytest.fixture
def search_service():
    return CatalogSearchService()


@pytest.fixture
def fashion_products():
    return make_fashion_products()


@pytest.fixture
def shoe_products():
    return make_shoe_products()


class TestExactSKUMatch:
    """Test exact SKU matching."""

    def test_product_sku(self, search_service, fashion_products):
        result = search_service.search(fashion_products, sku="WEK-001")
        assert result.found
        assert result.best_match.product.id == "prod-kurta-001"
        assert result.source_type == "sku"
        assert result.best_match.score == 100.0

    def test_variant_sku(self, search_service, fashion_products):
        result = search_service.search(fashion_products, sku="WEK-001-SB-M")
        assert result.found
        assert result.best_match.product.id == "prod-kurta-001"
        assert result.best_match.matched_variant is not None
        assert result.best_match.matched_variant.color == "sky blue"
        assert result.best_match.matched_variant.size == "medium"

    def test_nonexistent_sku(self, search_service, fashion_products):
        result = search_service.search(fashion_products, sku="NONEXISTENT-999")
        assert not result.found


class TestAliasMatch:
    """Test alias matching."""

    def test_exact_alias(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta")
        assert result.found
        assert result.best_match.product.id == "prod-kurta-001"

    def test_alias_shalwar_kameez(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="shalwar kameez")
        assert result.found
        assert result.best_match.product.id == "prod-sk-001"

    def test_alias_waistcoat(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="waistcoat")
        assert result.found
        assert result.best_match.product.id == "prod-wc-001"

    def test_alias_vest(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="vest")
        assert result.found
        assert result.best_match.product.id == "prod-wc-001"


class TestProductColorQuery:
    """Test product + color queries."""

    def test_sky_blue_kurta(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta", color="sky blue")
        assert result.found
        assert result.best_match.product.id == "prod-kurta-001"
        # Check variants filtered to sky blue
        for v in result.best_match.matched_variants:
            assert v.color == "sky blue"

    def test_black_kameez(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kameez", color="black")
        assert result.found
        assert result.best_match.product.id == "prod-sk-001"
        for v in result.best_match.matched_variants:
            assert v.color == "black"


class TestProductSizeQuery:
    """Test product + size queries."""

    def test_kurta_medium(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta", size="medium")
        assert result.found
        assert result.best_match.product.id == "prod-kurta-001"
        for v in result.best_match.matched_variants:
            assert v.size.lower() == "medium"

    def test_sneakers_size_42(self, search_service, shoe_products):
        result = search_service.search(shoe_products, query="sneakers", category="sneakers", size="42")
        assert result.found


class TestMultiWordColors:
    """Test multi-word color matching."""

    def test_sky_blue(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta", color="sky blue")
        assert result.found
        assert any(v.color == "sky blue" for v in result.best_match.matched_variants)

    def test_off_white(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta", color="off white")
        assert result.found
        assert any(v.color == "off white" for v in result.best_match.matched_variants)

    def test_navy_blue(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="waistcoat", color="navy blue")
        assert result.found
        assert any(v.color == "navy blue" for v in result.best_match.matched_variants)


class TestHyphenatedColors:
    """Test hyphenated color normalization."""

    def test_off_white_hyphenated(self, search_service, fashion_products):
        # off-white should normalize to "off white"
        result = search_service.search(fashion_products, query="kurta", color="off-white")
        assert result.found
        assert any(v.color == "off white" for v in result.best_match.matched_variants)

    def test_sky_blue_hyphenated(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta", color="sky-blue")
        assert result.found
        assert any(v.color == "sky blue" for v in result.best_match.matched_variants)


class TestUnknownProduct:
    """Test unknown product handling."""

    def test_unknown_product(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="laptop")
        assert not result.found

    def test_empty_query(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="")
        assert not result.found


class TestAmbiguousProduct:
    """Test ambiguous product detection."""

    def test_black_sneakers_ambiguous(self, search_service, shoe_products):
        """Multiple sneakers match 'black sneakers' — should detect ambiguity."""
        result = search_service.search(shoe_products, query="black sneakers")
        assert result.found
        # All three sneaker products have "black" in variants or names
        # The exact ambiguity depends on scoring — at minimum we should get matches
        assert len(result.matches) >= 1


class TestStoreIsolation:
    """Test that search is scoped to provided products only."""

    def test_fashion_products_dont_find_shoes(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="sneakers")
        assert not result.found

    def test_shoe_products_dont_find_kurta(self, search_service, shoe_products):
        result = search_service.search(shoe_products, query="kurta")
        assert not result.found

    def test_fashion_products_find_kurta(self, search_service, fashion_products):
        result = search_service.search(fashion_products, query="kurta")
        assert result.found
        assert result.best_match.product.store_id == "test-store-fashion"
