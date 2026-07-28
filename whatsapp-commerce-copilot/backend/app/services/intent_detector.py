"""Intent detection via regex and keyword classification.

Detects: greeting, product_search, price_query, stock_query, color_query,
size_query, cod_query, delivery_query, returns_query, exchange_query,
order_request, order_confirmation, complaint, human_agent_request, unknown.
"""
import re
from dataclasses import dataclass, field


@dataclass
class IntentResult:
    """Result of intent detection."""
    intent: str
    confidence: float
    requested_fields: list[str] = field(default_factory=list)
    sub_intents: list[str] = field(default_factory=list)


# Intent patterns: (pattern, intent, confidence, requested_fields)
INTENT_PATTERNS: list[tuple[str, str, float, list[str]]] = [
    # Greetings
    (r'\b(hi|hello|hey|assalam|salam|aoa|aslam)\b', 'greeting', 0.9, []),
    (r'\b(good\s*(morning|evening|afternoon))\b', 'greeting', 0.9, []),

    # Human agent request (high priority - check before product queries)
    (r'\b(human|agent|real\s*person|operator|insan|insaan|banda|manager)\b', 'human_agent_request', 0.95, []),
    (r'\b(baat\s*kar(na|o|ain)|connect\s*kar(o|ain))\b', 'human_agent_request', 0.9, []),

    # Complaints
    (r'\b(complaint|complain|shikayat|problem|issue|masla|mushkil|wrong|galat|kharab|defective)\b', 'complaint', 0.9, []),
    (r'\b(refund|paisa\s*wapas|return\s*kar(na|o))\b', 'complaint', 0.85, []),

    # Order confirmation
    (r'\b(confirm|haan|han|yes|ok|theek|order\s*kar\s*(do|dein|diya|lo)|place\s*order)\b', 'order_confirmation', 0.7, []),
    (r'\b(i\s*confirm|confirmed|pakka|final)\b', 'order_confirmation', 0.8, []),

    # Order request
    (r'\b(order|kharidna|khareed|buy|purchase|lena|le\s*lo|manga|mangwana|chahiye)\b', 'order_request', 0.75, []),
    (r'\b(i\s*want|mujhe\s*chahiye|add\s*to\s*cart)\b', 'order_request', 0.8, []),

    # COD query
    (r'\b(cod|cash\s*on\s*delivery)\b', 'cod_query', 0.95, ['cod']),

    # Delivery query
    (r'\b(delivery|deliver|shipping|ship|kitne\s*din|kab\s*tak|dispatch)\b', 'delivery_query', 0.9, ['delivery']),
    (r'\b(charges|delivery\s*charges|shipping\s*cost)\b', 'delivery_query', 0.85, ['delivery_charges']),

    # Returns query
    (r'\b(return|returns|wapas|wapsi)\b', 'returns_query', 0.85, ['returns']),

    # Exchange query
    (r'\b(exchange|badal|tabdeel)\b', 'exchange_query', 0.85, ['exchange']),

    # Price query
    (r'\b(price|qeemat|kimat|rate|kitne\s*ka|kitne\s*ki|kitna|cost|daam)\b', 'price_query', 0.85, ['price']),

    # Stock/availability query
    (r'\b(available|stock|availability|mil\s*sakta|mil\s*sakti|milega|milegi|moujood|mojud|hai\s*kya)\b', 'stock_query', 0.8, ['availability']),

    # Product search (broad - lower priority)
    (r'\b(show|dikhao|dikha|batao|bata|chahiye|want|need|looking\s*for|find)\b', 'product_search', 0.6, []),
]


def detect_intent(normalized_text: str) -> IntentResult:
    """Detect intent from normalized text.

    Supports multiple intents/requested_fields in one message.
    Returns the highest-confidence primary intent plus all requested_fields.
    """
    if not normalized_text or not normalized_text.strip():
        return IntentResult(intent="unknown", confidence=0.0)

    text = normalized_text.lower().strip()

    matches: list[tuple[str, float, list[str]]] = []
    all_requested_fields: list[str] = []
    all_sub_intents: list[str] = []

    for pattern, intent, confidence, req_fields in INTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matches.append((intent, confidence, req_fields))
            all_requested_fields.extend(req_fields)
            if intent not in all_sub_intents:
                all_sub_intents.append(intent)

    if not matches:
        # Check if message has product-like words (nouns without clear intent)
        # Treat as product_search with low confidence
        tokens = text.split()
        if len(tokens) >= 1 and not any(t in {'the', 'a', 'an', 'is', 'are'} for t in tokens):
            return IntentResult(
                intent="product_search",
                confidence=0.4,
                requested_fields=[],
                sub_intents=["product_search"],
            )
        return IntentResult(intent="unknown", confidence=0.0)

    # Sort by confidence descending
    matches.sort(key=lambda x: x[1], reverse=True)
    primary_intent = matches[0][0]
    primary_confidence = matches[0][1]

    # Deduplicate requested fields
    seen = set()
    unique_fields = []
    for f in all_requested_fields:
        if f not in seen:
            seen.add(f)
            unique_fields.append(f)

    # If we have product-related queries alongside policy queries, merge fields
    # e.g., "sky blue kurta available hai? price aur cod bhi bata dein"
    # → intent=product_search (or stock_query), requested_fields=[availability, price, cod]
    product_intents = {'product_search', 'price_query', 'stock_query', 'color_query', 'size_query'}
    policy_intents = {'cod_query', 'delivery_query', 'returns_query', 'exchange_query'}

    has_product = any(m[0] in product_intents for m in matches)
    has_policy = any(m[0] in policy_intents for m in matches)

    if has_product and has_policy:
        # Product query with policy questions
        primary_intent = "product_search"
        if 'availability' not in unique_fields:
            unique_fields.insert(0, 'availability')
    elif has_product:
        # Multiple product-related intents → pick the most specific
        for intent_name in ['stock_query', 'price_query', 'product_search']:
            if any(m[0] == intent_name for m in matches):
                primary_intent = intent_name
                break

    return IntentResult(
        intent=primary_intent,
        confidence=primary_confidence,
        requested_fields=unique_fields,
        sub_intents=all_sub_intents,
    )
