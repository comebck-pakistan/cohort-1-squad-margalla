"""Language detection using keyword/heuristic classifier.

langdetect cannot reliably detect Roman Urdu — this is a known limitation
documented in docs/SECURITY_AND_LIMITATIONS.md. We use keyword presence
and character analysis instead.

Supported: english, roman_urdu, urdu_script, mixed
"""

# Common Roman Urdu keywords (not found in English)
ROMAN_URDU_KEYWORDS = {
    "hai", "hain", "mein", "ka", "ki", "ke", "ko", "se", "ye", "yeh",
    "wo", "woh", "kya", "kyun", "kaise", "kitne", "kitna", "kitni",
    "aur", "bhi", "nahi", "nhi", "haan", "han", "ji", "acha", "theek",
    "bata", "batao", "bataen", "dein", "dijiye", "chahiye", "sakta",
    "sakti", "wala", "wali", "walay", "abhi", "pehle", "baad",
    "agar", "lekin", "magar", "toh", "phir", "sath", "liye",
    "raha", "rahi", "rahe", "gaya", "gayi", "gaye",
    "karo", "karna", "hoga", "hogi", "hoge", "tha", "thi", "the",
    "par", "pe", "uske", "iske", "unka", "inka", "apna", "apni",
    "din", "raat", "puri", "sab", "koi", "kuch",
}

# Urdu script character range (U+0600 to U+06FF)
URDU_SCRIPT_RANGE = range(0x0600, 0x0700)


def detect_language(text: str) -> str:
    """Detect language of input text.

    Returns: 'english', 'roman_urdu', 'urdu_script', or 'mixed'
    """
    if not text or not text.strip():
        return "english"

    text = text.strip()

    # Check for Urdu script characters
    urdu_char_count = sum(1 for c in text if ord(c) in URDU_SCRIPT_RANGE)
    total_alpha = sum(1 for c in text if c.isalpha())

    if total_alpha == 0:
        return "english"

    urdu_script_ratio = urdu_char_count / total_alpha if total_alpha > 0 else 0

    if urdu_script_ratio > 0.5:
        return "urdu_script"

    # Tokenize for keyword analysis
    tokens = set(text.lower().split())

    # Count Roman Urdu keyword hits
    roman_urdu_hits = tokens & ROMAN_URDU_KEYWORDS
    hit_ratio = len(roman_urdu_hits) / len(tokens) if tokens else 0

    if hit_ratio > 0.3:
        if hit_ratio > 0.6:
            return "roman_urdu"
        return "mixed"

    # Check for Roman Urdu in presence of English
    if roman_urdu_hits:
        return "mixed"

    return "english"
