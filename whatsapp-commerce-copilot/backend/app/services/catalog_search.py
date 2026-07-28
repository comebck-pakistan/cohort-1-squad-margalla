"""Catalog search service — product matching within a single store.

Matching strategy (in priority order):
1. Exact SKU match
2. Exact alias match
3. Token overlap scoring (product name + aliases)
4. Fuzzy matching via rapidfuzz (token_sort_ratio >= FUZZY_THRESHOLD)

All queries are store-scoped. No cross-store access.
"""
from dataclasses import dataclass, field
from rapidfuzz import fuzz
from app.services.text_normalizer import normalize_color, tokenize
from app.models.product import Product, ProductVariant

# --- Named Scoring Constants ---
EXACT_SKU_SCORE = 100.0
EXACT_ALIAS_SCORE = 95.0
HIGH_TOKEN_OVERLAP_SCORE = 85.0
MEDIUM_TOKEN_OVERLAP_SCORE = 70.0
FUZZY_THRESHOLD = 85  # rapidfuzz token_sort_ratio minimum
FUZZY_SCORE_WEIGHT = 0.8  # Multiply fuzzy score by this to rank below exact matches
MINIMUM_MATCH_SCORE = 40.0  # Below this, don't consider it a match
AMBIGUOUS_SCORE_GAP = 10.0  # If top two scores are within this gap, it's ambiguous


@dataclass
class MatchedProduct:
    """A product match result with score and variant info."""
    product: Product
    score: float
    match_reason: str
    matched_variants: list[ProductVariant] = field(default_factory=list)
    matched_variant: ProductVariant | None = None


@dataclass
class CatalogSearchResult:
    """Result of a catalog search."""
    matches: list[MatchedProduct] = field(default_factory=list)
    best_match: MatchedProduct | None = None
    is_ambiguous: bool = False
    source_type: str = ""  # "sku", "alias", "token", "fuzzy", "none"

    @property
    def found(self) -> bool:
        return len(self.matches) > 0


class CatalogSearchService:
    """Search products within a single store's catalog."""

    def search(
        self,
        products: list[Product],
        query: str | None = None,
        sku: str | None = None,
        color: str | None = None,
        size: str | None = None,
        category: str | None = None,
    ) -> CatalogSearchResult:
        """Search store catalog for matching products.

        Args:
            products: List of products (already filtered to one store)
            query: Product search query (normalized)
            sku: Exact SKU to match
            color: Color filter
            size: Size filter
            category: Category filter
        """
        result = CatalogSearchResult()

        if not products:
            result.source_type = "none"
            return result

        # Filter to active products only
        active_products = [p for p in products if p.is_active]

        # 1. Try exact SKU match first
        if sku:
            sku_result = self._match_by_sku(active_products, sku)
            if sku_result:
                result.matches = [sku_result]
                result.best_match = sku_result
                result.source_type = "sku"
                self._filter_variants(result, color, size)
                return result

        # 2. Try category filter
        if category:
            category_products = [
                p for p in active_products
                if p.category and p.category.lower() == category.lower()
            ]
            if category_products:
                active_products = category_products

        # 3. Try alias matching + token matching + fuzzy
        if query:
            scored_matches = self._score_products(active_products, query)

            if scored_matches:
                scored_matches.sort(key=lambda m: m.score, reverse=True)

                # Filter by minimum score
                scored_matches = [m for m in scored_matches if m.score >= MINIMUM_MATCH_SCORE]

                if scored_matches:
                    result.matches = scored_matches
                    result.best_match = scored_matches[0]
                    result.source_type = scored_matches[0].match_reason

                    # Check ambiguity
                    if len(scored_matches) >= 2:
                        gap = scored_matches[0].score - scored_matches[1].score
                        if gap < AMBIGUOUS_SCORE_GAP:
                            result.is_ambiguous = True

        # 3.5. If no query but we have color/size, search all products by variant attributes
        if not result.matches and not query and (color or size):
            for p in active_products:
                result.matches.append(MatchedProduct(
                    product=p, score=50.0, match_reason="attribute"
                ))
            if result.matches:
                result.source_type = "attribute"

        # 4. If no query match but we have category-filtered products, return them
        if not result.matches and category:
            for p in active_products:
                result.matches.append(MatchedProduct(
                    product=p, score=50.0, match_reason="category"
                ))
            if len(result.matches) == 1:
                result.best_match = result.matches[0]
                result.source_type = "category"
            elif len(result.matches) > 1:
                result.is_ambiguous = True
                result.source_type = "category"

        # 5. If NO query, NO category, NO color/size, just return all active products (generic catalog request)
        if not result.matches and not query and not category and not color and not size:
            for p in active_products:
                result.matches.append(MatchedProduct(
                    product=p, score=20.0, match_reason="generic"
                ))
            if len(result.matches) > 1:
                result.is_ambiguous = True
                result.source_type = "generic"
            elif len(result.matches) == 1:
                result.best_match = result.matches[0]
                result.source_type = "generic"

        # Apply color/size filters to variants
        self._filter_variants(result, color, size)

        # Post-filter: remove matches with no matching variants when color/size specified
        if color or size:
            result.matches = [m for m in result.matches if m.matched_variants]
            if len(result.matches) == 1:
                result.best_match = result.matches[0]
                result.is_ambiguous = False
            elif len(result.matches) == 0:
                result.best_match = None
            elif result.best_match and result.best_match not in result.matches:
                result.best_match = result.matches[0] if result.matches else None

        return result

    def _match_by_sku(self, products: list[Product], sku: str) -> MatchedProduct | None:
        """Try exact SKU match on products and their variants."""
        sku_upper = sku.upper()

        for product in products:
            # Check product-level SKU
            if product.sku and product.sku.upper() == sku_upper:
                return MatchedProduct(
                    product=product,
                    score=EXACT_SKU_SCORE,
                    match_reason="sku",
                )
            # Check variant-level SKU
            for variant in product.variants:
                if variant.sku and variant.sku.upper() == sku_upper:
                    return MatchedProduct(
                        product=product,
                        score=EXACT_SKU_SCORE,
                        match_reason="sku",
                        matched_variant=variant,
                        matched_variants=[variant],
                    )
        return None

    def _score_products(self, products: list[Product], query: str) -> list[MatchedProduct]:
        """Score all products against query using alias, token, and fuzzy matching."""
        query_lower = query.lower().strip()
        query_tokens = set(tokenize(query_lower))
        results: list[MatchedProduct] = []

        for product in products:
            best_score = 0.0
            best_reason = "none"

            # Collect all matchable names for this product
            matchable_names = [product.name.lower()]
            matchable_names.extend([a.alias.lower() for a in product.aliases])

            for name in matchable_names:
                # a. Exact alias match
                if query_lower == name:
                    best_score = max(best_score, EXACT_ALIAS_SCORE)
                    best_reason = "alias"
                    continue

                # b. Token overlap
                name_tokens = set(tokenize(name))
                if query_tokens and name_tokens:
                    overlap = query_tokens & name_tokens
                    if overlap:
                        overlap_ratio = len(overlap) / max(len(query_tokens), 1)
                        if overlap_ratio >= 0.8:
                            score = HIGH_TOKEN_OVERLAP_SCORE + (overlap_ratio * 5)
                        elif overlap_ratio >= 0.5:
                            score = MEDIUM_TOKEN_OVERLAP_SCORE + (overlap_ratio * 10)
                        else:
                            score = 50.0 + (overlap_ratio * 20)

                        if score > best_score:
                            best_score = score
                            best_reason = "token"

                # c. Fuzzy match (only if token match didn't yield high score)
                if best_score < HIGH_TOKEN_OVERLAP_SCORE:
                    fuzzy_score = fuzz.token_sort_ratio(query_lower, name)
                    if fuzzy_score >= FUZZY_THRESHOLD:
                        weighted = fuzzy_score * FUZZY_SCORE_WEIGHT
                        if weighted > best_score:
                            best_score = weighted
                            best_reason = "fuzzy"

            if best_score > 0:
                results.append(MatchedProduct(
                    product=product,
                    score=best_score,
                    match_reason=best_reason,
                ))

        return results

    def _filter_variants(
        self,
        result: CatalogSearchResult,
        color: str | None,
        size: str | None,
    ):
        """Filter matched variants by color and size."""
        if not color and not size:
            # Set all active variants as matched
            for match in result.matches:
                match.matched_variants = [v for v in match.product.variants if v.is_active]
            return

        normalized_color = normalize_color(color) if color else None

        for match in result.matches:
            filtered = []
            for variant in match.product.variants:
                if not variant.is_active:
                    continue

                color_ok = True
                size_ok = True

                if normalized_color and variant.color:
                    variant_color_norm = normalize_color(variant.color)
                    color_ok = variant_color_norm == normalized_color

                if size and variant.size:
                    size_ok = variant.size.lower() == size.lower()

                if color_ok and size_ok:
                    filtered.append(variant)

            match.matched_variants = filtered
            if len(filtered) == 1:
                match.matched_variant = filtered[0]
