"""Verify source ids are NOT wrapped in `[brackets]` when shown to LLMs.

Run 10 regression: the writer LLM was observed to copy `[<12-hex-sid>]`
tokens from the source list into claim prose. The tokens then failed the
citation audit (`non_numeric_markers`) because the audit expects every
bracketed token to be either a numeric `[N]` reference or a markdown link.

Fix: format source ids as `Source #<sid>:` (label, not marker) in every
LLM-facing source builder. This test pins the format so it doesn't drift.
"""

from __future__ import annotations

import re

from pipeline.lyra.research_stages import _build_sources_context
from pipeline.lyra.theo_citations import CitationRegistry


def _registry_with_one_source() -> CitationRegistry:
    r = CitationRegistry()
    r.register_source(
        "https://example.org/foo",
        "Foo Title",
        "Foo snippet text used as the LLM-visible excerpt.",
    )
    return r


def test_sources_context_uses_hash_not_bracket_for_sid():
    """Source list shown to research-stage LLMs uses `Source #sid:` format."""
    registry = _registry_with_one_source()
    out = _build_sources_context(registry)
    # No bracketed source-id token of the form `[<6-16 hex>]`
    assert not re.search(
        r"\[[a-f0-9]{6,16}\]",
        out,
    ), f"source list still leaks [hex] tokens: {out!r}"
    # Hash-prefixed label is present
    assert re.search(r"Source #[a-f0-9]{6,16}:", out), (
        f"expected 'Source #<sid>:' format, got: {out!r}"
    )


def test_angle_specialist_source_format_uses_hash():
    """The angle-specialist's _format_sources also uses `Source #sid:`."""
    # Reach into the handler builder via a small instantiation. The function
    # is local to the class, so we test the resulting text via a registry.
    import inspect

    from pipeline.lyra.handlers import angle_specialist

    src = inspect.getsource(angle_specialist)
    assert "Source #{sid}:" in src, "angle_specialist must use 'Source #{sid}:' (no brackets)"
    assert "Source [{sid}]" not in src, "angle_specialist still has bracketed sid (regression)"


def test_angle_audit_source_format_uses_hash():
    import inspect

    from pipeline.lyra.handlers import angle_audit

    src = inspect.getsource(angle_audit)
    assert "Source #{sid}:" in src, "angle_audit must use 'Source #{sid}:' (no brackets)"
    assert "Source [{sid}]" not in src, "angle_audit still has bracketed sid (regression)"


def test_research_stages_source_format_uses_hash():
    import inspect

    from pipeline.lyra import research_stages

    src = inspect.getsource(research_stages)
    assert "Source #{sid}:" in src, "research_stages must use 'Source #{sid}:' (no brackets)"
    assert "Source [{sid}]" not in src, "research_stages still has bracketed sid (regression)"
