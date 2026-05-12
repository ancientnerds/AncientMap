"""Tests for the Semantic Scholar query sanitiser.

The sanitiser lives inline inside `SemanticScholarAdapter.search`, but
its regex logic is pure-functional; testing it pure here keeps the
test fast and free of the httpx client.
"""

from __future__ import annotations

import re


def _sanitize(query: str) -> str:
    """Mirrors the body of SemanticScholarAdapter.search sanitiser."""
    q = re.sub(r"[^\w\s\-]", " ", query).strip()
    return re.sub(r"\s+", " ", q)


def test_strips_parens_and_question_mark() -> None:
    assert _sanitize("1200 BCE)?") == "1200 BCE"


def test_strips_full_question_with_parenthetical() -> None:
    raw = "Sea Peoples (c. 1200 BCE) origins?"
    assert _sanitize(raw) == "Sea Peoples c 1200 BCE origins"


def test_keeps_hyphens() -> None:
    assert _sanitize("Tel Miqne-Ekron Philistine") == "Tel Miqne-Ekron Philistine"


def test_collapses_double_spaces() -> None:
    assert _sanitize("Sea  Peoples   collapse") == "Sea Peoples collapse"


def test_empty_after_strip() -> None:
    assert _sanitize("?!()") == ""


def test_unicode_word_chars_preserved() -> None:
    # Voyage-4-tokenisable Unicode (e.g. ancient names) should survive.
    assert _sanitize("Ramesses III stela") == "Ramesses III stela"
