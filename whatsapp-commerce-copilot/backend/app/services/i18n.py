"""Centralised multilingual message templates.

All customer-facing strings must go through t() so that adding a new
language never requires touching business logic.

Usage:
    from app.services.i18n import t
    msg = t("welcome", "ur", store="StepUp Footwear")

Supported lang codes: "en", "ur"
Falls back to English for any unknown lang code.
"""
from typing import Any

# ---------------------------------------------------------------------------
# Message catalogue
# ---------------------------------------------------------------------------
# All Urdu strings are written in proper Unicode Urdu script.
# Numbers, brand names, order IDs and SKUs are kept as-is.
# ---------------------------------------------------------------------------

_MESSAGES: dict[str, dict[str, str]] = {
    # --- Greetings ---
    "welcome": {
        "en": "Hello! Welcome to {store}. How can I help you today?",
        "ur": "السلام علیکم! {store} میں خوش آمدید۔ آج میں آپ کی کیسے مدد کر سکتا ہوں؟",
    },
    "welcome_returning": {
        "en": "Hello again! Welcome back. Would you like to continue where we left off?",
        "ur": "دوبارہ خوش آمدید! کیا آپ پچھلی گفتگو جاری رکھنا چاہتے ہیں؟",
    },

    # --- Product search ---
    "product_not_found": {
        "en": "Sorry, we couldn't find '{query}' in our catalogue. Could you provide more details?",
        "ur": "معاف کیجیے، '{query}' ہمارے کیٹالاگ میں نہیں ملا۔ کیا آپ مزید تفصیل بتا سکتے ہیں؟",
    },
    "product_choice": {
        "en": "Which product are you referring to?",
        "ur": "آپ کس پروڈکٹ کی بات کر رہے ہیں؟",
    },
    "product_available_list": {
        "en": "Here are some of our available products:",
        "ur": "یہ ہمارے دستیاب پروڈکٹس ہیں:",
    },
    "product_variants_label": {
        "en": "Available variants:",
        "ur": "دستیاب اقسام:",
    },

    # --- Stock / price labels ---
    "stock_available": {
        "en": "Available (Stock: {stock})",
        "ur": "دستیاب (اسٹاک: {stock})",
    },
    "stock_out": {
        "en": "Currently out of stock",
        "ur": "ابھی اسٹاک میں نہیں ہے",
    },
    "out_of_stock_label": {
        "en": "Out of stock",
        "ur": "اسٹاک ختم",
    },

    # --- Order flow prompts ---
    "ask_color_size": {
        "en": "Which color and size would you like?",
        "ur": "آپ کو کون سا رنگ اور سائز چاہیے؟",
    },
    "ask_quantity": {
        "en": "How many pieces would you like?",
        "ur": "آپ کتنے پیس چاہتے ہیں؟",
    },
    "ask_name_phone": {
        "en": "Please provide your name and phone number for the order.",
        "ur": "آرڈر کے لیے اپنا نام اور فون نمبر بتائیں۔",
    },
    "ask_address": {
        "en": "Please provide your delivery address and city.",
        "ur": "اپنا ڈیلیوری پتہ اور شہر بتائیں۔",
    },
    "ask_payment": {
        "en": "What payment method would you prefer? (COD / Online)",
        "ur": "ادائیگی کا طریقہ کیا ہوگا؟ (COD / آن لائن)",
    },

    # --- Order summary / confirmation ---
    "order_summary_header": {
        "en": "📋 *Order Summary*",
        "ur": "📋 *آرڈر کی تفصیل*",
    },
    "order_confirm_prompt": {
        "en": "Would you like to confirm this order? (Yes/No)",
        "ur": "کیا آپ یہ آرڈر کنفرم کرنا چاہتے ہیں؟ (ہاں/نہیں)",
    },
    "order_confirmed": {
        "en": "✅ Your order is confirmed. Order ID: {order_id}",
        "ur": "✅ آپ کا آرڈر کنفرم ہو گیا۔ آرڈر ID: {order_id}",
    },
    "order_cancelled": {
        "en": "Okay, the order has been cancelled.",
        "ur": "ٹھیک ہے، آرڈر منسوخ کر دیا گیا ہے۔",
    },
    "order_confirm_or_cancel": {
        "en": "Reply Yes to confirm the order, or No to cancel.",
        "ur": "آرڈر کنفرم کرنے کے لیے ہاں، یا منسوخ کرنے کے لیے نہیں لکھیں۔",
    },
    "order_not_found": {
        "en": "I couldn't find an order for this number. Please send the order ID if you have it.",
        "ur": "اس نمبر کا کوئی آرڈر نہیں ملا۔ اگر آرڈر ID ہے تو بھیجیں۔",
    },
    "order_status": {
        "en": "Order {order_id} is currently {status}.",
        "ur": "آرڈر {order_id} کی موجودہ صورتحال: {status}۔",
    },
    "select_product_first": {
        "en": "Please select a product first.",
        "ur": "پہلے کوئی پروڈکٹ منتخب کریں۔",
    },
    "variant_unavailable": {
        "en": "That color/size combination isn't available. Please choose another.",
        "ur": "یہ رنگ/سائز کا مجموعہ دستیاب نہیں ہے۔ براہ کرم کوئی دوسرا انتخاب کریں۔",
    },
    "order_item_no_longer_available": {
        "en": "Sorry, this item is no longer available.",
        "ur": "معاف کیجیے، یہ چیز اب دستیاب نہیں رہی۔",
    },
    "order_insufficient_stock": {
        "en": "Sorry, the requested quantity is not available. Only {stock} left in stock.",
        "ur": "معاف کیجیے، درخواست کردہ تعداد دستیاب نہیں ہے۔ صرف {stock} اسٹاک میں باقی ہیں۔",
    },

    # --- Alternatives ---
    "alternatives_available": {
        "en": "These alternatives are available:",
        "ur": "یہ متبادل دستیاب ہیں:",
    },
    "no_other_options": {
        "en": "There are no other options in this category right now.",
        "ur": "اس وقت اس کیٹیگری میں کوئی دوسرا آپشن نہیں ہے۔",
    },

    # --- Human handoff ---
    "handoff": {
        "en": "I'm connecting you with a team member. Please wait a moment.",
        "ur": "آپ کو ہمارے ٹیم ممبر سے جوڑا جا رہا ہے۔ تھوڑا انتظار کریں۔",
    },

    # --- Fallback / error responses ---
    "fallback_ack": {
        "en": "Got it 👍 Can I help with anything else?",
        "ur": "ٹھیک ہے 👍 کیا میں کسی اور چیز میں مدد کر سکتا ہوں؟",
    },
    "fallback_unsupported": {
        "en": "I can help with products, delivery, and orders.",
        "ur": "میں پروڈکٹس، ڈیلیوری اور آرڈرز سے متعلق سوالات میں مدد کر سکتا ہوں۔",
    },
    "fallback_unknown": {
        "en": "I didn't quite understand. Please share the product name, picture, size, or your order question.",
        "ur": "مجھے بات سمجھ نہیں آئی۔ پروڈکٹ کا نام، تصویر، سائز، یا آرڈر سے متعلق سوال بتائیں۔",
    },
    "error_retry": {
        "en": "Sorry, I didn't understand that. Could you please rephrase?",
        "ur": "معاف کیجیے، مجھے سمجھ نہیں آیا۔ کیا آپ دوبارہ بتا سکتے ہیں؟",
    },
    "policy_not_found": {
        "en": "We don't have information about that right now. Can I help with something else?",
        "ur": "ابھی اس بارے میں معلومات دستیاب نہیں ہیں۔ کیا آپ کچھ اور پوچھنا چاہتے ہیں؟",
    },
    "picture_not_uploaded": {
        "en": "\nA picture for this product has not been uploaded yet.",
        "ur": "\nاس پروڈکٹ کی تصویر ابھی کیٹالاگ میں شامل نہیں کی گئی ہے۔",
    },
    "negotiation_note": {
        "en": "\nThis is the catalogue price. I can ask a team member to confirm any special discount.",
        "ur": "\nیہ کیٹالاگ قیمت ہے۔ کسی خاص رعایت کے لیے میں ٹیم ممبر سے تصدیق کروا سکتا ہوں۔",
    },
    "ai_error_fallback": {
        "en": "Sorry, I'm having trouble responding right now. Let me connect you with a team member.",
        "ur": "معاف کیجیے، ابھی جواب دینے میں مشکل ہو رہی ہے۔ آپ کو ہمارے ٹیم ممبر سے جوڑ رہا ہوں۔",
    },
    "service_unavailable": {
        "en": "Sorry, we're having a temporary issue on our side. Please try again in a moment.",
        "ur": "معاف کیجیے، ہمارے سسٹم میں ابھی عارضی مسئلہ ہے۔ براہ کرم تھوڑی دیر بعد دوبارہ کوشش کریں۔",
    },

    # --- Order summary field labels ---
    "label_product": {
        "en": "Product",
        "ur": "پروڈکٹ",
    },
    "label_color": {
        "en": "Color",
        "ur": "رنگ",
    },
    "label_size": {
        "en": "Size",
        "ur": "سائز",
    },
    "label_quantity": {
        "en": "Quantity",
        "ur": "تعداد",
    },
    "label_price": {
        "en": "Price",
        "ur": "قیمت",
    },
    "label_name": {
        "en": "Name",
        "ur": "نام",
    },
    "label_phone": {
        "en": "Phone",
        "ur": "فون",
    },
    "label_address": {
        "en": "Address",
        "ur": "پتہ",
    },
    "label_payment": {
        "en": "Payment",
        "ur": "ادائیگی",
    },
    "label_na": {
        "en": "N/A",
        "ur": "N/A",
    },
    "label_available_sizes": {
        "en": "Available sizes",
        "ur": "دستیاب سائز",
    },
    "label_available_colors": {
        "en": "Available colors",
        "ur": "دستیاب رنگ",
    },
    "label_available": {
        "en": "Available",
        "ur": "دستیاب",
    },
    "label_stock": {
        "en": "Stock",
        "ur": "اسٹاک",
    },
    "ask_size": {
        "en": "Would you like to select a size?",
        "ur": "کیا آپ کوئی سائز منتخب کرنا چاہیں گے؟",
    },
    "ask_color": {
        "en": "Which color would you prefer?",
        "ur": "آپ کو کون سا رنگ چاہیے؟",
    },
}


def t(key: str, lang: str, **kwargs: Any) -> str:
    """Translate a message key into the requested language.

    Args:
        key:    Message key from the catalogue above.
        lang:   "en" or "ur". Falls back to "en" for unknown values.
        **kwargs: Format arguments substituted into the template.

    Returns:
        Translated and formatted string.

    Raises:
        KeyError: If the key does not exist in the catalogue.
    """
    # Normalise lang: only "ur" maps to Urdu; everything else → English
    resolved_lang = "ur" if lang == "ur" else "en"

    entry = _MESSAGES.get(key)
    if entry is None:
        # Graceful degradation: return the key itself so the bot never crashes
        return key

    template = entry.get(resolved_lang, entry.get("en", key))
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
