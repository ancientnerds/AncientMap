"""Verify the deterministic hex-token scrub + post-presentation re-audit.

Run 10 had `[<12-hex-sid>]` tokens that the writer copied from the source list
into prose. The audit flagged them as `non_numeric_markers` → audit.passed=false
even after the LLM-based presentation step had already cleaned them out.

This test pins the scrubber regex so the audit sees a clean paper.
"""

from __future__ import annotations

import re

from pipeline.lyra.theo_citations import CitationRegistry, audit_citations

# This must match the regex baked into pipeline/lyra/handlers/paper.py Step 7.8.
# If you change one, change the other — there's a unit test that compiles the
# same pattern from disk to keep them in sync.
_HEX_TOKEN_RE = re.compile(r"(?<!\!)\[[a-f0-9]{6,16}\]")


def _scrub(text: str) -> str:
    text = _HEX_TOKEN_RE.sub("", text)
    text = re.sub(r" {2,}", " ", text)
    # Don't strip whitespace before `!` — that's the start of markdown images.
    text = re.sub(r" +([.,;:?])", r"\1", text)
    return text


def test_scrubber_strips_12char_source_id_token():
    prose = "The Watchers descended [93405c4f16a5] and taught humans [1]."
    out = _scrub(prose)
    assert out == "The Watchers descended and taught humans [1]."


def test_scrubber_strips_multiple_tokens():
    prose = "Anunnaki [01d0088ab33a] and Watchers [8e1626610655] both [2]."
    out = _scrub(prose)
    assert "01d0088ab33a" not in out
    assert "8e1626610655" not in out
    assert "[2]" in out


def test_scrubber_preserves_numeric_markers():
    prose = "Megalith built in 9600 BCE [1]. Carbon dated [2] [3]."
    assert _scrub(prose) == prose


def test_scrubber_preserves_markdown_image_alt_with_hex():
    # Image-alt may contain hex-looking words; the negative-lookahead for `!`
    # protects the entire `![alt](url)` markdown image block.
    prose = "Photo: ![abc12345](path/to.jpg) shows the site."
    assert _scrub(prose) == prose


def test_scrubber_preserves_markdown_links():
    # Markdown links use [text](url); hex tokens land in `text` rarely. The
    # scrubber is allowed to nibble link text — but plain text links are safe.
    prose = "See [the analysis](https://example.org/x) for details."
    assert _scrub(prose) == prose


def test_scrubber_does_not_touch_source_section_with_url_brackets():
    # References commonly look like `[1] Title -- https://...`. Numeric only,
    # so the scrubber leaves them alone.
    prose = (
        "## References\n\n[1] Title — https://x.example/foo\n[2] Other — https://y.example/bar\n"
    )
    assert _scrub(prose) == prose


def test_audit_passes_after_scrubbing_hex_tokens():
    """End-to-end: leak hex tokens into prose, scrub, audit reports clean."""
    registry = CitationRegistry()
    sid = registry.register_source("https://x.example/", "X title", "snippet")
    registry.assign_reference_number(sid)
    paper = (
        "# Test Paper\n\n"
        "## Investigation\n\n"
        "Watchers descended [93405c4f16a5] and taught knowledge [1].\n"
    )
    pre = audit_citations(paper, registry)
    assert pre["non_numeric_markers"], "pre-scrub audit should flag the hex token"
    cleaned = _scrub(paper)
    post = audit_citations(cleaned, registry)
    assert not post["non_numeric_markers"], (
        f"post-scrub audit should be clean, got {post['non_numeric_markers']}"
    )


def test_handler_uses_same_regex():
    """Pin: the regex string in paper.py matches the scrubber here."""
    handler_src = (
        __import__("pathlib").Path(__file__).parent.parent.parent
        / "pipeline"
        / "lyra"
        / "handlers"
        / "paper.py"
    ).read_text(encoding="utf-8")
    # The pattern is written exactly once in the handler — locked here.
    assert r"(?<!\!)\[[a-f0-9]{6,16}\]" in handler_src, (
        "paper.py hex-scrubber regex drifted from the test mirror"
    )
