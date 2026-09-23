"""Text processing utility functions for the data pipeline."""

import re
import unicodedata


def normalize_name(name: str, remove_parentheses: bool = True, remove_brackets: bool = True) -> str:
    """Normalize a site name for matching and deduplication.

    Applies the following transformations:
    - Unicode NFKD normalization (decomposes characters)
    - Removes diacritical marks (accents)
    - Optionally removes content in brackets [...]
    - Optionally removes content in parentheses (...)
    - Converts to lowercase
    - Strips whitespace

    Args:
        name: The name to normalize
        remove_parentheses: Whether to remove content in parentheses
        remove_brackets: Whether to remove content in square brackets

    Returns:
        Normalized name string, or empty string if input is empty/None
    """
    if not name:
        return ""

    # Unicode normalization - decompose characters
    name = unicodedata.normalize("NFKD", name)

    # Remove diacritical marks (combining characters)
    name = "".join(c for c in name if not unicodedata.combining(c))

    # Remove bracketed content
    if remove_brackets:
        name = re.sub(r"\[.*?\]", "", name)

    if remove_parentheses:
        name = re.sub(r"\(.*?\)", "", name)

    # Lowercase and strip
    return name.lower().strip()


def normalize_for_search(text: str) -> str:
    """Normalize text for search/indexing.

    More aggressive normalization suitable for search:
    - Removes all special characters
    - Removes extra whitespace
    - Lowercase

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Unicode normalization
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # Remove non-alphanumeric (keep spaces)
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    return text.lower().strip()


def clean_description(description: str | None, max_length: int = 1000) -> str | None:
    """Clean and truncate a description string.

    Args:
        description: Raw description text
        max_length: Maximum length (default 1000 chars)

    Returns:
        Cleaned description or None if empty
    """
    if not description:
        return None

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", description).strip()

    # Remove HTML tags if present
    text = re.sub(r"<[^>]+>", "", text)

    # Truncate if needed
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return text if text else None


# Strings an LLM emits to mean "I have no name for this". They arrive as real
# JSON strings, not JSON null, so `if value:` and SQL COALESCE both let them
# through. Until 2026-09-14 they reached the radar as site titles: 47 cards
# were literally called "null" and the DB was trigram-searched for the word.
_LLM_NULL_NAMES = {"null", "none", "nil", "n/a", "na", "unknown", "undefined", "-", "--"}


def clean_llm_name(name: str | None) -> str | None:
    """Return a usable site name from LLM output, or None.

    Rejects the placeholder strings models emit instead of omitting the field.
    Use this at every boundary where a model-supplied name enters the pipeline.
    """
    if not name:
        return None
    cleaned = re.sub(r"\s+", " ", name).strip().strip("\"'")
    if not cleaned or cleaned.lower() in _LLM_NULL_NAMES:
        return None
    return cleaned


_TRANSLITERATION_MAP = {
    "ph": "f",
    "kh": "ch",
    "ae": "a",
    "oe": "o",
    "sch": "sh",
    "tch": "ch",
    "qu": "k",
    "ck": "k",
    "th": "t",
    "dh": "d",
    "gh": "g",
    "bh": "b",
    "ue": "u",
    "ie": "i",
    "ey": "i",
    "ay": "i",
    "ou": "u",
    "oo": "u",
    "ee": "i",
    "ts": "s",
    "tz": "s",
    "dj": "j",
    "zh": "z",
}


def normalize_transliteration(name: str) -> str:
    """Aggressive phonetic normalization for matching transliterated names.

    Handles common archaeological name transliteration variants:
    ph↔f, kh↔ch, ae↔a, doubled consonants, etc.
    """
    if not name:
        return ""

    # Start with standard normalization
    result = normalize_name(name)

    # Apply transliteration substitutions (longer patterns first)
    for old, new in sorted(_TRANSLITERATION_MAP.items(), key=lambda x: -len(x[0])):
        result = result.replace(old, new)

    # Remove doubled consonants (e.g. "ll" -> "l", "ss" -> "s")
    result = re.sub(r"([bcdfghjklmnpqrstvwxyz])\1+", r"\1", result)

    # Remove spaces and hyphens for pure phonetic comparison
    result = result.replace(" ", "").replace("-", "")

    return result


PERIOD_BUCKET_TO_YEAR = {
    "< 4500 BC": -4500,
    "4500 - 3000 BC": -4500,
    "3000 - 1500 BC": -3000,
    "1500 - 500 BC": -1500,
    "500 BC - 1 AD": -500,
    "1 - 500 AD": 1,
    "500 - 1000 AD": 500,
    "1000 - 1500 AD": 1000,
    "1500+ AD": 1500,
}


def extract_period_from_text(text: str) -> int | None:
    """Try to extract a year from text.

    First checks for exact period bucket labels (e.g. "3000 - 1500 BC"),
    then falls back to parsing patterns like "500 BC", "100 AD".

    Args:
        text: Text to search

    Returns:
        Year as integer (negative for BC/BCE) or None
    """
    if not text:
        return None

    # Check for exact period bucket labels first
    stripped = text.strip()
    if stripped in PERIOD_BUCKET_TO_YEAR:
        return PERIOD_BUCKET_TO_YEAR[stripped]

    # Strip commas from numbers: "11,000 BC" → "11000 BC"
    text = re.sub(r"(\d),(\d)", r"\1\2", text)

    text = text.upper()

    # Pattern: number followed by BC/BCE/AD/CE
    patterns = [
        r"C\.?\s*A?\.?\s*(\d+)\s*(BC|BCE)",  # c. 500 BC, ca. 500 BCE
        r"(\d+)\s*(BC|BCE)",  # 500 BC, 500 BCE
        r"(\d+)\s*(AD|CE)",  # 500 AD, 500 CE
        r"C\.?\s*A?\.?\s*(\d+)\s*(AD|CE)",  # c. 500 AD
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year = int(match.group(1))
            era = match.group(2)
            if era in ("BC", "BCE"):
                return -year
            return year

    # Pattern: "X years ago" / "X year old" (assume BC for large numbers)
    match = re.search(r"(\d+)\+?\s*YEARS?\s*(?:AGO|OLD)", text)
    if match:
        years = int(match.group(1))
        if years > 100:
            return -years

    return None


def extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML: drop script and style blocks, strip tags, fold whitespace.

    Moved here from `pipeline/lyra/handlers/content_fetch.py` (2026-09-23) unchanged, so the Lyra
    handler and the remediation's search-hit check (`scripts/remediation/phase3/search_evidence.py`)
    read a page with one function. Entities are left as they are, as the handler always had them.
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Canonical period bucket definitions: (label, lower_bound, upper_bound)
# Mirrors frontend categorizePeriod() in src/data/sites.ts.
PERIOD_BUCKETS: list[tuple[str, int, int]] = [
    ("< 4500 BC", -999999, -4500),
    ("4500 - 3000 BC", -4500, -3000),
    ("3000 - 1500 BC", -3000, -1500),
    ("1500 - 500 BC", -1500, -500),
    ("500 BC - 1 AD", -500, 1),
    ("1 - 500 AD", 1, 500),
    ("500 - 1000 AD", 500, 1000),
    ("1000 - 1500 AD", 1000, 1500),
    ("1500+ AD", 1500, 999999),
]


def categorize_period(year: int | None) -> str | None:
    """Convert a year to a canonical period bucket name.

    Mirrors frontend categorizePeriod() in src/data/sites.ts, which compares upper bounds only:
    the first bucket is open below and the last one open above. The table's -999999/999999 are
    range-filter bounds, not limits of the classification - testing `lo <= year` here sent every
    year below -999999 to "1500+ AD" (the three Atapuerca-era sites at -1,400,000, whose stored
    and displayed label is "< 4500 BC"; fixed 2026-09-22).
    """
    if year is None:
        return None
    for label, _lo, hi in PERIOD_BUCKETS:
        if year < hi:
            return label
    return PERIOD_BUCKETS[-1][0]


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Convert a string to a safe filename.

    Args:
        name: Original name
        max_length: Maximum filename length

    Returns:
        Safe filename string
    """
    if not name:
        return "unnamed"

    # Remove/replace unsafe characters
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = re.sub(r"\s+", "_", safe)
    safe = re.sub(r"_+", "_", safe)
    safe = safe.strip("_")

    # Truncate
    if len(safe) > max_length:
        safe = safe[:max_length]

    return safe or "unnamed"
