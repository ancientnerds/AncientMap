"""End-to-end test that strip + smart-injection recovers Run-8-style uncited
paragraphs from real-shaped registry claims.

The Run 8 paper had 9 factual paragraphs that the writer produced from the
claim pack but failed to attach `[N]` markers to. The section-preservation
safeguard restored them, but they still showed up in the audit count. The
smart-injection helper (see `inject_citation_for_paragraph`) was added to
match those orphan paragraphs against `registry.claims` by content overlap
and re-attach the missing markers.

This test wires up a synthetic registry mirroring the Shining Ones run
(Watchers, Anunnaki, Dogon, Giza, Ezekiel, Puma Punku, Teotihuacan), feeds
it a paper where every section's prose matches a claim but lacks a marker,
and asserts:
  1. Every factual paragraph survives the strip (content-preserving).
  2. Every factual paragraph gains an `[N]` marker (audit-passing).
  3. The injected reference numbers all resolve to a registered source.
"""

from __future__ import annotations

import re

from pipeline.lyra.theo_citations import (
    CitationRegistry,
    audit_citations,
    finalize_references,
    strip_uncited_factual_paragraphs,
)


def _build_shining_ones_registry() -> tuple[CitationRegistry, dict[str, str]]:
    """Synthetic registry that mirrors the topics in the Shining Ones runs.

    Returns the populated registry plus a {topic_key: source_id} map so the
    test fixture can reason about which source SHOULD be cited where.
    """
    registry = CitationRegistry()

    sources = {
        "watchers": registry.register_source(
            "https://example.org/enoch-watchers",
            "The Book of Enoch and the Watcher Tradition",
            "Scholarly review of the Watchers narrative.",
        ),
        "anunnaki": registry.register_source(
            "https://example.org/sumerian-anunnaki",
            "Anunnaki in Sumerian Cuneiform",
            "Translation analysis of celestial-visitor passages.",
        ),
        "dogon": registry.register_source(
            "https://example.org/dogon-sirius",
            "The Dogon Sirius Mystery",
            "Anthropological account of Dogon astronomical knowledge.",
        ),
        "giza": registry.register_source(
            "https://example.org/giza-construction",
            "Giza Pyramid Construction Methods",
            "Engineering analysis of the Great Pyramid blocks.",
        ),
        "ezekiel": registry.register_source(
            "https://example.org/ezekiel-vision",
            "Ezekiel's Vision in Hebrew Bible Scholarship",
            "Survey of interpretations of Ezekiel chapter 1.",
        ),
        "punku": registry.register_source(
            "https://example.org/puma-punku-precision",
            "Puma Punku Precision Stoneworking",
            "Survey of andesite block tolerances at Puma Punku.",
        ),
        "teotihuacan": registry.register_source(
            "https://example.org/teotihuacan-isotopes",
            "Teotihuacan Isotope Evidence for Contact",
            "Strontium isotope analysis of Teotihuacan burials.",
        ),
    }

    registry.add_claim(
        "The Watchers in the Book of Enoch are described as fallen angels who descended "
        "from heaven and taught humans forbidden knowledge including astronomy and metallurgy.",
        [sources["watchers"]],
    )
    registry.add_claim(
        "Sumerian cuneiform tablets from the third millennium BCE describe the Anunnaki "
        "as celestial beings who descended to earth and shaped early human civilization.",
        [sources["anunnaki"]],
    )
    registry.add_claim(
        "The Dogon people of Mali possessed detailed astronomical knowledge of the Sirius "
        "binary system that anthropologists found difficult to explain through ordinary cultural transmission.",
        [sources["dogon"]],
    )
    registry.add_claim(
        "Construction of the Giza pyramids required moving and aligning multi-ton limestone "
        "blocks with tolerances that continue to surprise modern engineers.",
        [sources["giza"]],
    )
    registry.add_claim(
        "Ezekiel's vision in the Hebrew Bible presents interpretive challenges that span "
        "merkabah mysticism, prophetic theophany, and modern ancient-astronaut readings.",
        [sources["ezekiel"]],
    )
    registry.add_claim(
        "Puma Punku features andesite blocks cut with precision tolerances under one millimeter "
        "and assembled with metal clamps cast in place into prepared sockets.",
        [sources["punku"]],
    )
    registry.add_claim(
        "Strontium isotope analysis of burials at Teotihuacan documents organized contact "
        "between distant communities and challenges purely-local development models.",
        [sources["teotihuacan"]],
    )

    return registry, sources


def _build_uncited_paper() -> str:
    """Paper text that mirrors the Run 8 failure pattern: factual paragraphs that
    match registry claims but lack [N] markers."""
    return (
        "# The Shining Ones: Investigating Sky Beings Across Civilizations\n\n"
        "The Book of Enoch's Watchers narrative describes fallen angels who came down "
        "from heaven and taught humans forbidden knowledge they should not have, including "
        "astronomy and metallurgy that recur across later traditions.\n\n"
        "## Sky Beings in Ancient Texts\n\n"
        "Sumerian cuneiform tablets from the third millennium BCE describe the Anunnaki "
        "as celestial visitors who descended from the heavens and shaped human civilization "
        "in measurable archaeological ways.\n\n"
        "Ezekiel's vision in the Hebrew Bible presents interpretive challenges that span "
        "merkabah mysticism, prophetic theophany, and modern ancient-astronaut readings, "
        "all drawing on the same source text.\n\n"
        "## The Global Sky-Deity Pattern\n\n"
        "The Dogon people of Mali possessed detailed astronomical knowledge of the Sirius "
        "binary system that anthropologists found difficult to explain through ordinary "
        "cultural transmission alone.\n\n"
        "## Megalithic Construction\n\n"
        "Construction of the Giza pyramids required moving and aligning multi-ton limestone "
        "blocks with tolerances that continue to surprise modern engineers and split scholarly opinion.\n\n"
        "Puma Punku features andesite blocks cut with precision tolerances under one millimeter "
        "and assembled with metal clamps cast in place into prepared sockets.\n\n"
        "## What We Actually Know\n\n"
        "Strontium isotope analysis of burials at Teotihuacan documents organized contact "
        "between distant communities and challenges purely-local development models.\n"
    )


def test_strip_recovers_all_uncited_paragraphs_via_injection():
    """End-to-end: every uncited factual paragraph is recovered by injection."""
    registry, _sources = _build_shining_ones_registry()
    paper = _build_uncited_paper()

    out = strip_uncited_factual_paragraphs(paper, registry)

    # The seven topical paragraphs should all survive (content preservation).
    expected_phrases = [
        "Watchers narrative describes fallen angels",
        "Sumerian cuneiform tablets",
        "Ezekiel's vision in the Hebrew Bible",
        "Dogon people of Mali",
        "Giza pyramids required moving",
        "Puma Punku features andesite blocks",
        "Strontium isotope analysis of burials at Teotihuacan",
    ]
    for phrase in expected_phrases:
        assert phrase in out, f"Strip dropped a recoverable paragraph: {phrase!r}"

    # Every section's prose should now contain at least one [N] marker.
    sections = re.split(r"^##\s+", out, flags=re.MULTILINE)
    for sec in sections:
        if not sec.strip() or sec.startswith("#"):
            continue
        # Skip pure-heading remnants
        body = sec.split("\n", 1)[1] if "\n" in sec else ""
        if not body.strip():
            continue
        assert re.search(r"\[\d+\]", body), (
            f"Section body still uncited after injection: {sec[:120]!r}..."
        )


def test_audit_passes_after_finalize_then_strip():
    """The full pipeline ordering (finalize → strip → audit) yields a clean audit."""
    registry, _sources = _build_shining_ones_registry()
    paper = _build_uncited_paper()

    # finalize_references is normally called BEFORE strip in handlers/paper.py
    # (Step 7.5). With no working numbers, finalize collapses everything to an
    # empty assignment — the strip's injection then assigns fresh numbers via
    # `assign_reference_number`, which is the same code path the prod pipeline
    # uses when the writer forgot to mark a paragraph.
    paper_after_finalize, _ = finalize_references(paper, {}, registry)
    paper_after_strip = strip_uncited_factual_paragraphs(paper_after_finalize, registry)

    audit = audit_citations(paper_after_strip, registry)

    # No uncited paragraphs after injection rescues them
    assert audit["uncited_paragraphs"] == 0, (
        f"Audit still reports uncited paragraphs: {audit['uncited_paragraphs']}\n"
        f"--- Paper ---\n{paper_after_strip}"
    )
    # No invalid markers — every injected [N] resolves to a registered source
    assert audit["invalid_markers"] == [], (
        f"Injection produced invalid markers: {audit['invalid_markers']}"
    )
    # No placeholder leakage
    assert not audit["placeholder_markers"]
    # Audit passes
    assert audit["passed"] is True, f"Audit failed: {audit}"


def test_injection_resolves_to_registered_sources():
    """Every [N] in the post-strip paper maps to a CitedSource via reference_numbers."""
    registry, sources = _build_shining_ones_registry()
    paper = _build_uncited_paper()

    paper_after_finalize, _ = finalize_references(paper, {}, registry)
    paper_after_strip = strip_uncited_factual_paragraphs(paper_after_finalize, registry)

    cited_nums = {int(m) for m in re.findall(r"\[(\d+)\]", paper_after_strip)}
    assert cited_nums, "No citations in paper after injection"

    # Reverse map: number -> sid
    num_to_sid = {num: sid for sid, num in registry.reference_numbers.items()}
    for n in cited_nums:
        assert n in num_to_sid, f"Citation [{n}] missing from registry.reference_numbers"
        sid = num_to_sid[n]
        assert sid in registry.sources, f"Citation [{n}] -> source {sid} not in sources"
        # And every cited source is one of the seven we registered for the test
        assert sid in sources.values(), f"Unexpected source cited: {sid}"


def test_strip_metrics_count_injection_vs_drop():
    """metrics_out reports counts split between recoveries and drops."""
    registry, _sources = _build_shining_ones_registry()

    # Three matched paragraphs (recoverable) + one unrelated paragraph (drop).
    paper = (
        "## Investigation\n\n"
        "The Book of Enoch's Watchers narrative describes fallen angels who came down "
        "from heaven and taught humans forbidden knowledge.\n\n"
        "Sumerian cuneiform tablets describe the Anunnaki as celestial beings who descended "
        "to earth and shaped early human civilization in measurable archaeological ways.\n\n"
        "The Roman aqueducts of Segovia were constructed during the reign of Trajan, "
        "delivering water with a precise gradient over twenty-five kilometers of countryside.\n\n"
        "The Dogon people of Mali possessed detailed astronomical knowledge of the Sirius "
        "binary system that anthropologists found difficult to explain through cultural transmission.\n"
    )

    metrics: dict = {}
    out = strip_uncited_factual_paragraphs(paper, registry, metrics_out=metrics)

    # Three uncited paragraphs matched a registry claim, one did not.
    assert metrics["uncited_seen"] == 4
    assert metrics["injected"] == 3
    assert metrics["dropped"] == 1

    # The recovered paragraphs should still be in the output, the dropped one gone.
    assert "Watchers narrative" in out
    assert "Sumerian cuneiform tablets" in out
    assert "Dogon people of Mali" in out
    assert "Roman aqueducts of Segovia" not in out


def test_strip_metrics_count_restored_sections():
    """When strip would gut a section below threshold, restored_sections increments."""
    registry, _sources = _build_shining_ones_registry()

    # Section with 4 long uncited paragraphs that DON'T match any claim — strip
    # would empty it, so the safeguard restores the original content.
    long_unrelated = (
        "The Roman aqueducts of Segovia were constructed during the reign of Trajan "
        "delivering water with a precise gradient over twenty-five kilometers of countryside "
        "from the Sierra Madre across the meseta into the city center where it served the public baths."
    )
    paper = (
        "## Roman Engineering\n\n"
        + long_unrelated
        + "\n\n"
        + long_unrelated
        + "\n\n"
        + long_unrelated
        + "\n\n"
        + long_unrelated
        + "\n"
    )

    metrics: dict = {}
    strip_uncited_factual_paragraphs(paper, registry, metrics_out=metrics)

    assert metrics["restored_sections"] >= 1


def test_format_references_includes_injected_sources():
    """The published bibliography lists every source the injection cited."""
    registry, _sources = _build_shining_ones_registry()
    paper = _build_uncited_paper()

    paper_after_finalize, _ = finalize_references(paper, {}, registry)
    paper_after_strip = strip_uncited_factual_paragraphs(paper_after_finalize, registry)

    refs = registry.format_references_list()
    assert refs, "No references generated after injection"

    cited_nums = {int(m) for m in re.findall(r"\[(\d+)\]", paper_after_strip)}
    for n in sorted(cited_nums):
        assert f"[{n}]" in refs, f"Cited [{n}] missing from References list"
