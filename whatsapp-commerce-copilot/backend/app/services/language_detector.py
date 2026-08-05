"""Language detection using keyword/heuristic classifier.

langdetect cannot reliably detect Roman Urdu — this is a known limitation
documented in docs/SECURITY_AND_LIMITATIONS.md. We use keyword presence
and character analysis instead.

Supported input_language values: english, roman_urdu, urdu_script, mixed, unknown
Supported response_language values: en, ur
"""
import re
from typing import NamedTuple


class LanguageDetection(NamedTuple):
    """Result of language detection."""
    input_language: str   # english | roman_urdu | urdu_script | mixed | unknown
    response_language: str  # en | ur
    confidence: float
    is_neutral: bool  # True → short/number/emoji reply; do not update session language


# Common Roman Urdu keywords — not found in typical English e-commerce text.
ROMAN_URDU_KEYWORDS = {
    "hai", "hain", "mein", "ka", "ki", "ke", "ko", "se", "ye", "yeh",
    "wo", "woh", "kya", "kyun", "kaise", "kitne", "kitna", "kitni",
    "aur", "bhi", "nahi", "nhi", "haan", "han", "ji", "acha", "theek",
    "bata", "batao", "bataen", "dein", "dijiye", "chahiye", "sakta",
    "sakti", "wala", "wali", "walay", "abhi", "pehle", "baad",
    "agar", "lekin", "magar", "toh", "phir", "sath", "liye",
    "raha", "rahi", "rahe", "gaya", "gayi", "gaye",
    "karo", "karna", "hoga", "hogi", "hoge", "tha", "thi",
    "par", "pe", "uske", "iske", "unka", "inka", "apna", "apni",
    "din", "raat", "puri", "sab", "koi", "kuch",
    # footwear / shopping specific
    "jootay", "joote", "joota", "juta", "jutay", "chappal", "sandle",
    "kalay", "kala", "safaid", "lal", "neela", "hara",
    "dikhao", "dikha", "dekhna", "dikhaye",
    "size", "salam", "assalam", "walekum", "shukriya",
    "order", "mangwana", "lena", "kharidna",
    "paas", "available", "milega", "milegi",
    "konsa", "kaunsa", "pehla", "doosra", "teesra",
    "pehle", "baad", "zaroor", "bilkul",
    "delivery", "bhejo", "bhej",
    "aapka", "mera", "meri", "hamara", "hamari",
}

# Urdu script character range (U+0600–U+06FF)
URDU_SCRIPT_RANGE = range(0x0600, 0x0700)

# Explicit English language request patterns
_ENGLISH_REQUEST = re.compile(
    r'\b(reply\s+in\s+english|respond\s+in\s+english|english\s+(mein\s+)?jawab|'
    r'english\s+use\s+karo|please\s+reply\s+in\s+english)\b',
    re.IGNORECASE,
)

# Explicit Urdu language request patterns (Latin or Urdu script)
_URDU_REQUEST = re.compile(
    r'\b(urdu\s+(mein\s+)?jawab|reply\s+in\s+urdu|urdu\s+use\s+karo|'
    r'اردو\s+میں\s+جواب)\b',
    re.IGNORECASE,
)

# "Neutral" patterns: only digits, emoji, punctuation, SKU codes, or very short tokens
_NEUTRAL_PATTERN = re.compile(
    r'^[\d\s\U0001F300-\U0001FFFF\U00002600-\U000026FF\U00002700-\U000027BF'
    r'\U0001F900-\U0001F9FF,.!?+\-*/=@#%^&()\[\]{}<>|\\/"\'`~_]+$'
)


def detect_language(text: str) -> LanguageDetection:
    """Detect language of input text.

    Returns a LanguageDetection namedtuple with:
        input_language  – english | roman_urdu | urdu_script | mixed | unknown
        response_language – en | ur
        confidence      – 0.0–1.0
        is_neutral      – True when the message is too short/ambiguous to change session lang
    """
    if not text or not text.strip():
        return LanguageDetection("unknown", "en", 0.0, is_neutral=True)

    text_stripped = text.strip()

    # --- 1. Explicit language-switch requests (highest priority) ---
    if _ENGLISH_REQUEST.search(text_stripped):
        return LanguageDetection("english", "en", 1.0, is_neutral=False)
    if _URDU_REQUEST.search(text_stripped):
        return LanguageDetection("roman_urdu", "ur", 1.0, is_neutral=False)

    # --- 2. Urdu script detection ---
    urdu_char_count = sum(1 for c in text_stripped if ord(c) in URDU_SCRIPT_RANGE)
    total_alpha = sum(1 for c in text_stripped if c.isalpha())

    if total_alpha == 0:
        # digits, emoji, punctuation only
        return LanguageDetection("unknown", "en", 0.5, is_neutral=True)

    urdu_script_ratio = urdu_char_count / total_alpha

    if urdu_script_ratio > 0.4:
        return LanguageDetection("urdu_script", "ur", min(0.6 + urdu_script_ratio * 0.4, 1.0), is_neutral=False)

    # --- 3. Neutral check for short messages (<=2 words, no Urdu keywords) ---
    words = text_stripped.split()
    if len(words) <= 2 and _NEUTRAL_PATTERN.match(text_stripped):
        return LanguageDetection("unknown", "en", 0.3, is_neutral=True)

    # --- 4. Roman Urdu keyword analysis ---
    tokens = {w.lower().strip(".,!?;:'\"") for w in words}
    roman_urdu_hits = tokens & ROMAN_URDU_KEYWORDS
    hit_ratio = len(roman_urdu_hits) / len(tokens) if tokens else 0

    if hit_ratio >= 0.5:
        return LanguageDetection("roman_urdu", "ur", min(0.7 + hit_ratio * 0.3, 0.98), is_neutral=False)

    if hit_ratio > 0:
        # Mixed: has some Roman Urdu mixed with English
        return LanguageDetection("mixed", "ur", 0.6, is_neutral=False)

    # --- 5. Neutral check: very short pure-token messages ---
    if len(tokens) <= 2:
        return LanguageDetection("english", "en", 0.5, is_neutral=True)

    return LanguageDetection("english", "en", 0.85, is_neutral=False)
