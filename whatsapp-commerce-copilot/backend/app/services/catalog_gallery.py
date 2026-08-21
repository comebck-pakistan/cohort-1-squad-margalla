"""Gallery-readiness rules and catalogue picture captions.

One source of truth, shared by two callers that must agree:

* the seller API (`routers/products.py`), which refuses to mark an incomplete
  product gallery-ready, so a direct API call cannot bypass the dashboard form;
* the conversation controller, which refuses to send a customer a picture whose
  caption would be missing a price, a colour or a category.

Keeping both on these helpers is what stops the two ends drifting apart — a
product the seller was told is "gallery-ready" is exactly a product the customer
gallery will actually send.
"""
from __future__ import annotations

from app.config import get_settings

# Field keys used in the 4xx `fields` map and by the dashboard to highlight the
# offending input. Kept stable — the frontend matches on them.
FIELD_NAME = "name"
FIELD_CATEGORY = "category_id"
FIELD_COLOR = "color"
FIELD_PRICE = "price"
FIELD_IMAGE = "image"
FIELD_STOCK = "stock"
FIELD_ACTIVE = "is_active"

# Names that carry no information for a customer browsing a picture gallery.
# Compared against the trimmed, lowercased name.
_PLACEHOLDER_NAMES = {
    "test", "testing", "product", "products", "item", "sample",
    "demo", "abc", "xyz", "na", "n/a", "none", "untitled", "new product",
}


def name_error(name: str | None) -> str | None:
    """Validate a product name. Returns an error string, or None when valid."""
    cleaned = (name or "").strip()
    if not cleaned:
        return "Product name is required"
    # "At least 2 meaningful characters" — punctuation and digits alone are not
    # a name a customer can recognise in a caption.
    if len([c for c in cleaned if c.isalpha()]) < 2:
        return "Product name must contain at least 2 letters"
    if cleaned.lower() in _PLACEHOLDER_NAMES:
        return "Product name looks like a placeholder"
    return None


def price_error(price) -> str | None:
    """A gallery price must be a real, positive number — never `PKR 0`."""
    if price is None or price == "":
        return "Price is required"
    try:
        value = float(price)
    except (TypeError, ValueError):
        return "Price must be a number"
    if value != value or value in (float("inf"), float("-inf")):
        return "Price must be a number"
    if value <= 0:
        return "Price must be greater than zero"
    return None


def stock_error(stock) -> str | None:
    """Stock must be a whole number, zero or greater."""
    if stock is None or stock == "":
        return "Stock is required"
    if isinstance(stock, bool):
        return "Stock must be a whole number"
    if isinstance(stock, float) and not stock.is_integer():
        return "Stock must be a whole number"
    try:
        value = int(stock)
    except (TypeError, ValueError):
        return "Stock must be a whole number"
    if value < 0:
        return "Stock cannot be negative"
    return None


def color_error(color: str | None) -> str | None:
    """Colour is what the gallery filters on, so it cannot be blank."""
    if not (color or "").strip():
        return "Colour is required"
    return None


def resolve_media_url(image_url: str | None) -> str | None:
    """Turn a stored image path into a URL WhatsApp's fetcher can reach.

    Values already absolute (a seller pasting a CDN link) are returned as-is.
    A stored relative path such as "/uploads/x.jpg" is prefixed with the
    configured public media base — never with a hard-coded host.
    """
    url = (image_url or "").strip()
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = get_settings().media_base_url
    if not base:
        return None
    return f"{base}/{url.lstrip('/')}"


def sellable_variants(product, color: str | None = None):
    """Variants a customer could actually buy right now.

    Active, in stock, priced, and carrying a colour — the four things a gallery
    caption and the order flow both depend on. Optionally narrowed to one
    colour, matched on the normalised form so "Blk"/"black" collapse.
    """
    from app.services.text_normalizer import normalize_color

    target = normalize_color(color) if color else None
    out = []
    for v in getattr(product, "variants", None) or []:
        if not v.is_active or v.stock is None or v.stock <= 0:
            continue
        if not v.color or not v.price or v.price <= 0:
            continue
        if target is not None and normalize_color(v.color) != target:
            continue
        out.append(v)
    return out


def gallery_blockers(product, color: str | None = None) -> dict[str, str]:
    """Everything standing between this product and the picture gallery.

    Empty dict means gallery-ready. Used by the seller API to explain a
    rejection field-by-field, and by the controller to decide (and log) which
    catalogue rows to skip.
    """
    blockers: dict[str, str] = {}

    err = name_error(getattr(product, "name", None))
    if err:
        blockers[FIELD_NAME] = err

    if not getattr(product, "category_id", None):
        blockers[FIELD_CATEGORY] = "A saved category is required"

    if not resolve_media_url(getattr(product, "image_url", None)):
        blockers[FIELD_IMAGE] = "Product image is required"

    if not getattr(product, "is_active", False):
        blockers[FIELD_ACTIVE] = "Product must be active"

    variants = sellable_variants(product, color)
    if not variants:
        # Say which of the four conditions actually failed, rather than a vague
        # "no variants" the seller cannot act on.
        all_variants = list(getattr(product, "variants", None) or [])
        active = [v for v in all_variants if v.is_active]
        if not all_variants or not active:
            blockers[FIELD_ACTIVE] = "At least one active variant is required"
        elif not any(v.color for v in active):
            blockers[FIELD_COLOR] = "Colour is required"
        elif not any((v.price or 0) > 0 for v in active):
            blockers[FIELD_PRICE] = "Price must be greater than zero"
        else:
            blockers[FIELD_STOCK] = "At least one variant must be in stock"

    return blockers


def is_gallery_ready(product, color: str | None = None) -> bool:
    return not gallery_blockers(product, color)


def gallery_price(product, color: str | None = None) -> float | None:
    """The price the caption must show: the lowest sellable variant price.

    Falls back to the product's base price only when it is itself valid, so a
    caption never advertises `PKR 0`.
    """
    prices = [v.price for v in sellable_variants(product, color)]
    if prices:
        return min(prices)
    base = getattr(product, "base_price", None)
    return base if base and base > 0 else None


def build_caption(number: int, product_name: str, category_name: str | None,
                  color: str | None, price: float | None) -> str | None:
    """The mandatory catalogue picture caption.

        1. Premium Cotton Suit
        Category: Cotton
        Colour: Blue
        Price: PKR 4,500

    Returns None when any required value is missing — the caller must then skip
    the picture rather than send an incomplete one. Values come from persisted
    catalogue rows only; nothing here is model-generated.
    """
    if not product_name or not category_name or not color:
        return None
    if not price or price <= 0:
        return None
    return (
        f"{number}. {product_name}\n"
        f"Category: {category_name}\n"
        f"Colour: {color}\n"
        f"Price: PKR {price:,.0f}"
    )
