"""Entity extraction from normalized text.

Extracts: product_query, sku, category, color, size, quantity,
delivery_city, requested_fields, language.
Handles: quantity vs size disambiguation, multi-word colors, SKU patterns.
"""
import re
from dataclasses import dataclass, field
from app.services.text_normalizer import normalize_color


@dataclass
class ExtractedEntities:
    """Extracted entities from a message."""
    product_query: str | None = None
    sku: str | None = None
    category: str | None = None
    color: str | None = None
    size: str | None = None
    quantity: int | None = None
    delivery_city: str | None = None
    requested_fields: list[str] = field(default_factory=list)
    language: str = "english"
    confidence: float = 0.0
    needs_clarification: bool = False
    raw_text: str = ""


# Known colors (multi-word first for greedy matching)
KNOWN_COLORS = [
    "sky blue", "navy blue", "off white", "royal blue", "light blue",
    "dark blue", "light green", "dark green", "light pink", "dark pink",
    "black", "white", "red", "blue", "green", "pink", "yellow",
    "orange", "purple", "brown", "grey", "gray", "maroon", "beige",
    "golden", "silver", "tan", "cream", "coral", "teal", "burgundy",
    "olive", "peach", "lavender", "ivory", "turquoise", "khaki",
]

# Known size tokens
KNOWN_SIZES = {
    "xs", "extra small",
    "s", "small", "chota", "chhota",
    "m", "medium", "medium size", "darmiyana",
    "l", "large", "bada", "bara",
    "xl", "extra large",
    "xxl", "2xl",
    "xxxl", "3xl",
    # Numeric shoe sizes
    "36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46",
}

# Size normalization
SIZE_NORMALIZE = {
    "xs": "XS", "extra small": "XS",
    "s": "Small", "small": "Small", "chota": "Small", "chhota": "Small",
    "m": "Medium", "medium": "Medium", "darmiyana": "Medium",
    "l": "Large", "large": "Large", "bada": "Large", "bara": "Large",
    "xl": "XL", "extra large": "XL",
    "xxl": "XXL", "2xl": "XXL",
    "xxxl": "XXXL", "3xl": "XXXL",
}

# Product category keywords
CATEGORY_KEYWORDS = {
    "kurta": "kurta",
    "kurtas": "kurta",
    "kameez": "shalwar kameez",
    "shalwar": "shalwar kameez",
    "suit": "suit",
    "lawn": "lawn suit",
    "waistcoat": "waistcoat",
    "vest": "waistcoat",
    "sadri": "waistcoat",
    "sneakers": "sneakers",
    "sneaker": "sneakers",
    "shoes": "shoes",
    "shoe": "shoes",
    "loafers": "loafers",
    "loafer": "loafers",
    "sandals": "sandals",
    "sandal": "sandals",
    "heels": "heels",
    "heel": "heels",
    "chappal": "sandals",
}

# SKU pattern: 2-4 uppercase letters, dash, 3 digits, optional variant suffix
SKU_PATTERN = re.compile(r'\b([A-Z]{2,4}-\d{3}(?:-[A-Z]{2}-[A-Z0-9]+)?)\b', re.IGNORECASE)

# Quantity pattern: "X pieces", "X pcs", "X qty", or just a number before "piece"
QUANTITY_PATTERNS = [
    re.compile(r'(\d+)\s*(?:pieces?|pcs?|qty|quantity|adad)\b', re.IGNORECASE),
    re.compile(r'\b(?:i\s*want|mujhe|chahiye)\s*(\d+)\b', re.IGNORECASE),
]

# Size patterns: "size X", "size: X", "X size", or standalone named sizes
SIZE_PATTERNS = [
    re.compile(r'\b(medium|large|small|xl|xxl|xs|extra\s*small|extra\s*large)\b', re.IGNORECASE),
    re.compile(r'\bsize\s*:?\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'\b(\d{2})\s*size\b', re.IGNORECASE),
]

# City detection (major Pakistani cities)
CITIES = {
    "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
    "multan", "peshawar", "quetta", "sialkot", "gujranwala",
    "hyderabad", "bahawalpur", "sargodha", "sahiwal", "abbottabad",
    "mardan", "sukkur", "larkana", "mirpur", "muzaffarabad",
}


def extract_entities(normalized_text: str, language: str = "english") -> ExtractedEntities:
    """Extract entities from normalized text."""
    if not normalized_text:
        return ExtractedEntities(raw_text="")

    text = normalized_text.lower().strip()
    entities = ExtractedEntities(raw_text=text, language=language)

    # 1. Extract SKU
    sku_match = SKU_PATTERN.search(text.upper())
    if sku_match:
        entities.sku = sku_match.group(1).upper()
        entities.confidence = 0.95

    # 2. Extract color (multi-word colors first)
    extracted_color = _extract_color(text)
    if extracted_color:
        entities.color = normalize_color(extracted_color)

    # 3. Extract size and quantity (with disambiguation)
    _extract_size_and_quantity(text, entities)

    # 4. Extract category
    for keyword, category in CATEGORY_KEYWORDS.items():
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, text):
            entities.category = category
            break

    # 5. Extract product query (strip color, size, quantity, policy words)
    entities.product_query = _extract_product_query(text, entities)

    # 6. Extract delivery city
    for city in CITIES:
        if re.search(r'\b' + re.escape(city) + r'\b', text):
            entities.delivery_city = city.title()
            break

    # 7. Set confidence
    if entities.sku:
        entities.confidence = 0.95
    elif entities.product_query and entities.color:
        entities.confidence = 0.85
    elif entities.product_query or entities.category:
        entities.confidence = 0.7
    elif entities.color or entities.size:
        entities.confidence = 0.5
    else:
        entities.confidence = 0.3

    return entities


def _extract_color(text: str) -> str | None:
    """Extract color from text, preferring multi-word colors."""
    for color in KNOWN_COLORS:
        # Use word boundary matching
        pattern = r'\b' + re.escape(color) + r'\b'
        if re.search(pattern, text):
            return color
    return None


def _extract_size_and_quantity(text: str, entities: ExtractedEntities):
    """Extract size and quantity with disambiguation.

    Key rule: "I want 2 pieces in size 40" → quantity=2, size=40
    """
    # First check for explicit quantity patterns ("2 pieces", "3 qty")
    for pattern in QUANTITY_PATTERNS:
        match = pattern.search(text)
        if match:
            entities.quantity = int(match.group(1))
            break

    # Then check for explicit size patterns ("size 40", "medium")
    for pattern in SIZE_PATTERNS:
        match = pattern.search(text)
        if match:
            size_val = match.group(1).lower()
            # Normalize named sizes
            if size_val in SIZE_NORMALIZE:
                entities.size = SIZE_NORMALIZE[size_val]
            else:
                # Check if it's a numeric size
                try:
                    size_num = int(size_val)
                    if 30 <= size_num <= 50:  # Valid shoe/clothing size range
                        entities.size = str(size_num)
                except ValueError:
                    entities.size = size_val.title()
            break

    # Disambiguation: if we found a number that could be either quantity or size
    # and it wasn't resolved by patterns above
    if entities.size is None and entities.quantity is None:
        # Look for standalone numbers
        numbers = re.findall(r'\b(\d+)\b', text)
        for num_str in numbers:
            num = int(num_str)
            if 30 <= num <= 50:  # Likely a shoe/clothing size
                entities.size = str(num)
            elif 1 <= num <= 20:  # Likely a quantity
                entities.quantity = num


def _extract_product_query(text: str, entities: ExtractedEntities) -> str | None:
    """Extract the product query by stripping known entities and noise words."""
    # Remove known entities from text
    query = text

    # Remove color
    if entities.color:
        query = re.sub(r'\b' + re.escape(entities.color) + r'\b', '', query)

    # Remove size
    if entities.size:
        query = re.sub(r'\bsize\s*:?\s*' + re.escape(entities.size.lower()) + r'\b', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\b' + re.escape(entities.size.lower()) + r'\b', '', query)

    # Remove quantity
    if entities.quantity:
        query = re.sub(r'\b' + str(entities.quantity) + r'\s*(?:pieces?|pcs?|qty)?\b', '', query)

    # Remove noise words (Roman Urdu + English)
    noise_words = {
        'mein', 'hai', 'hain', 'kya', 'kia', 'konsa', 'kuch', 'koi', 'ka', 'ki', 'ke', 'ko', 'se',
        'ye', 'yeh', 'wo', 'woh', 'bhi', 'aur', 'available', 'stock',
        'price', 'kimat', 'qeemat', 'rate', 'kitne', 'kitna', 'kitni',
        'bata', 'batao', 'bataen', 'dein', 'dijiye', 'dikhao', 'dikha',
        'show', 'me', 'the', 'a', 'an', 'is', 'are', 'in', 'for',
        'and', 'or', 'i', 'want', 'need', 'looking', 'cod', 'cash',
        'on', 'delivery', 'return', 'exchange', 'charges', 'shipping',
        'din', 'days', 'please', 'plz', 'thanks', 'thank', 'you',
        'wala', 'wali', 'walay', 'pieces', 'piece', 'pcs',
        'chahiye', 'mangwana', 'lena', 'kharidna', 'buy', 'purchase',
        'size', 'color', 'rang', 'hogi', 'hoga', 'hoge',
        'do', 'de', 'lo', 'le', 'kar', 'karo', 'karein',
    }

    # Strip punctuation from tokens before filtering
    tokens = query.split()
    cleaned = []
    for t in tokens:
        clean = re.sub(r'[^\w]', '', t)
        if clean and clean.lower() not in noise_words and len(clean) > 1:
            cleaned.append(clean)

    if cleaned:
        return ' '.join(cleaned)

    # If nothing remains, use category
    if entities.category:
        return entities.category

    return None
