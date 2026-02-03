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
        text = text[:max_length - 3] + "..."

    return text if text else None


def extract_period_from_text(text: str) -> int | None:
    """Try to extract a year from text.

    Looks for patterns like:
    - "500 BC", "500 BCE"
    - "100 AD", "100 CE"
    - "c. 500 BC"
    - "ca. 500 BCE"

    Args:
        text: Text to search

    Returns:
        Year as integer (negative for BC/BCE) or None
    """
    if not text:
        return None

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

    return None


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
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe = re.sub(r'\s+', '_', safe)
    safe = re.sub(r'_+', '_', safe)
    safe = safe.strip('_')

    # Truncate
    if len(safe) > max_length:
        safe = safe[:max_length]

    return safe or "unnamed"
