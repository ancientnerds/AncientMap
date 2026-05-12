"""Tests for the bare `[N]` / `[...]` debug-token scrubber."""

from __future__ import annotations

from pipeline.lyra.theo_citations import strip_debug_tokens


def test_strips_bare_N() -> None:
    text = "The Sea Peoples arrived [N] and overran Ugarit."
    assert strip_debug_tokens(text) == "The Sea Peoples arrived  and overran Ugarit."


def test_strips_bare_ellipsis_ascii() -> None:
    text = "Climate stressors [...] contributed to collapse."
    assert strip_debug_tokens(text) == "Climate stressors  contributed to collapse."


def test_strips_bare_ellipsis_unicode() -> None:
    text = "Multiple proxies […] confirm drought."
    assert strip_debug_tokens(text) == "Multiple proxies  confirm drought."


def test_keeps_numeric_citations() -> None:
    text = "Ramesses III defeated the coalition [12]."
    assert strip_debug_tokens(text) == text


def test_keeps_numbered_placeholders() -> None:
    # `[N - topic]` is handled separately by detect_placeholder_markers.
    text = "Migration patterns [N - aDNA] remain debated."
    assert strip_debug_tokens(text) == text


def test_keeps_markdown_image() -> None:
    # Negative lookahead `(?!\()` avoids munching `![alt](url)` style links.
    text = "See the relief: ![N](http://example.com/relief.png)"
    # Note: `[N]` followed by `(` is preserved entirely.
    assert "(http" in strip_debug_tokens(text)


def test_multiple_in_one_paragraph() -> None:
    text = "First claim [N] second claim [...] third claim [...] done."
    result = strip_debug_tokens(text)
    assert "[N]" not in result
    assert "[...]" not in result
    assert "First claim" in result and "done." in result
