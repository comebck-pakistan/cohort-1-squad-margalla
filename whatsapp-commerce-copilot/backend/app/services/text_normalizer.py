"""Text normalization for incoming messages.

Handles: lowercase, whitespace normalization, color alias normalization,
Roman Urdu common terms, special character cleanup.
"""
import re

# Color aliases → canonical form
COLOR_ALIASES: dict[str, str] = {
    "off white": "off white",
    "off-white": "off white",
    "offwhite": "off white",
    "sky blue": "sky blue",
    "sky-blue": "sky blue",
    "skyblue": "sky blue",
    "navy blue": "navy blue",
    "navy-blue": "navy blue",
    "navyblue": "navy blue",
    "dark blue": "navy blue",
    "light blue": "sky blue",
    "golden": "golden",
    "gold": "golden",
    "blk": "black",
    "wht": "white",
    "brn": "brown",
    "nvy": "navy blue",
    "gry": "grey",
    "gray": "grey",
}

# Roman Urdu common normalizations
ROMAN_URDU_NORMALIZATIONS: dict[str, str] = {
    "kya": "kya",
    "kyun": "kyun",
    "kaise": "kaise",
    "kitne": "kitne",
    "kitna": "kitna",
    "kitni": "kitni",
    "wala": "wala",
    "wali": "wali",
    "walay": "walay",
    "bata": "bata",
    "batao": "batao",
    "bataen": "bataen",
    "bta": "bata",
    "btao": "batao",
    "btaen": "bataen",
    "hain": "hain",
    "hai": "hai",
    "h": "hai",
    "nhi": "nahi",
    "nai": "nahi",
    "ji": "ji",
    "g": "ji",
    "plz": "please",
    "pls": "please",
    "thx": "thanks",
    "thnx": "thanks",
}


def normalize_text(text: str) -> str:
    """Normalize input text for processing.

    Steps:
    1. Strip and lowercase
    2. Normalize whitespace
    3. Remove special characters (keep alphanumeric, spaces, ?, !, ., -)
    4. Normalize multi-word color names
    5. Apply Roman Urdu normalizations
    """
    if not text:
        return ""

    # Step 1: Strip and lowercase
    result = text.strip().lower()

    # Step 2: Normalize whitespace
    result = re.sub(r'\s+', ' ', result)

    # Step 3: Remove special characters but keep useful punctuation
    result = re.sub(r'[^\w\s\?\!\.\-]', '', result)

    # Step 4: Normalize multi-word colors (must be done before tokenization)
    for alias, canonical in COLOR_ALIASES.items():
        if alias in result:
            result = result.replace(alias, canonical)

    return result.strip()


def normalize_color(color: str) -> str:
    """Normalize a color string to its canonical form."""
    color = color.strip().lower()
    return COLOR_ALIASES.get(color, color)


def tokenize(text: str) -> list[str]:
    """Split normalized text into tokens."""
    return [t for t in text.split() if t]
