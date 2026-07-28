"""Tests for entity extraction."""
import pytest
from app.services.entity_extractor import extract_entities
from app.services.text_normalizer import normalize_text


class TestColorExtraction:
    def test_sky_blue(self):
        result = extract_entities(normalize_text("Sky blue kurta dikhao"))
        assert result.color == "sky blue"

    def test_off_white(self):
        result = extract_entities(normalize_text("Off white kurta hai?"))
        assert result.color == "off white"

    def test_off_white_hyphenated(self):
        result = extract_entities(normalize_text("off-white kurta"))
        assert result.color == "off white"

    def test_navy_blue(self):
        result = extract_entities(normalize_text("navy blue sneakers"))
        assert result.color == "navy blue"

    def test_black(self):
        result = extract_entities(normalize_text("black shoes dikhao"))
        assert result.color == "black"

    def test_maroon(self):
        result = extract_entities(normalize_text("maroon kurta hai?"))
        assert result.color == "maroon"


class TestSizeExtraction:
    def test_medium_size(self):
        result = extract_entities(normalize_text("medium size kurta"))
        assert result.size is not None
        assert result.size.lower() == "medium"

    def test_numeric_size(self):
        result = extract_entities(normalize_text("sneakers size 42"))
        assert result.size == "42"

    def test_large_size(self):
        result = extract_entities(normalize_text("large kurta"))
        assert result.size is not None
        assert result.size.lower() == "large"


class TestQuantityVsSizeDisambiguation:
    def test_2_pieces_size_40(self):
        """'I want 2 pieces in size 40' → quantity=2, size=40"""
        result = extract_entities(normalize_text("I want 2 pieces in size 40"))
        assert result.quantity == 2
        assert result.size == "40"

    def test_3_pieces(self):
        result = extract_entities(normalize_text("3 pieces chahiye"))
        assert result.quantity == 3


class TestSKUExtraction:
    def test_sku_detection(self):
        result = extract_entities(normalize_text("WEK-001 ka price batao"))
        assert result.sku == "WEK-001"

    def test_variant_sku(self):
        result = extract_entities(normalize_text("WEK-001-SB-M available hai?"))
        assert result.sku is not None
        assert "WEK" in result.sku


class TestProductQuery:
    def test_kurta_query(self):
        result = extract_entities(normalize_text("sky blue kurta medium size mein available hai"))
        assert result.product_query is not None
        assert "kurta" in result.product_query or result.category == "kurta"

    def test_sneakers_query(self):
        result = extract_entities(normalize_text("navy blue sneakers size 42 ki price"))
        assert result.product_query is not None or result.category == "sneakers"
        assert result.color == "navy blue"
        assert result.size == "42"


class TestCategoryExtraction:
    def test_kurta_category(self):
        result = extract_entities(normalize_text("kurta dikhao"))
        assert result.category == "kurta"

    def test_sneakers_category(self):
        result = extract_entities(normalize_text("sneakers hai?"))
        assert result.category == "sneakers"

    def test_loafer_category(self):
        result = extract_entities(normalize_text("loafers dikhao"))
        assert result.category == "loafers"
