"""Uncited-claim pass for the weekly article (audit P5-15).

verify_all_citations strips rejected [N] markers but leaves the claim prose
uncited; _strip_uncited_claims reuses Theo's strip_uncited_factual_paragraphs
to drop that prose. These tests pin: the registry-number mirroring plus the
skip guard (duplicate-URL collapse / non-contiguous numbering), the [VN]
video-marker shielding, the no-claim-injection guarantee (rejected citations
must never be re-attached from source snippets), and the metrics wiring.
"""

from pipeline.lyra.article_generator import _strip_uncited_claims

CITED = (
    "The excavation at the tell revealed a sequence of mudbrick platforms "
    "dated by radiocarbon to the late fourth millennium BCE, according to "
    "the published stratigraphy of the lower town [1]."
)
UNCITED = (
    "Entirely separate researchers argued the platforms were aligned to "
    "lunar standstills and encoded a forgotten calendar system spanning "
    "dozens of generations of continuous observation at this location."
)


def _sources(n=3):
    return [
        {
            "citation": i,
            "url": f"https://example.org/s{i}",
            "label": f"Source {i}",
            "snippet": f"Snippet text {i}",
            "type": "news",
        }
        for i in range(1, n + 1)
    ]


def test_uncited_paragraph_dropped_cited_kept():
    body = f"## New Excavations & Fieldwork\n\n{CITED}\n\n{UNCITED}"
    out, metrics = _strip_uncited_claims(body, _sources())
    assert CITED in out
    assert "lunar standstills" not in out
    assert metrics["uncited_seen"] == 1
    assert metrics["dropped"] == 1
    assert metrics["injected"] == 0
    assert "skipped" not in metrics


def test_duplicate_source_urls_skip_strip_entirely():
    # Two citation entries with the same URL collapse to ONE registry source
    # id (register_source dedupes by canonical URL hash), so the registry
    # cannot mirror the article's [N] numbering — the strip must SKIP and
    # leave the body byte-identical rather than risk renumbering corruption.
    sources = _sources(2)
    sources[1]["url"] = sources[0]["url"]
    body = f"## Artifact Discoveries\n\n{CITED}\n\n{UNCITED}"
    out, metrics = _strip_uncited_claims(body, sources)
    assert out == body
    assert "skipped" in metrics
    assert "dropped" not in metrics


def test_noncontiguous_citation_numbers_skip_strip():
    # After _cleanup_citations the article's numbers are contiguous from 1;
    # anything else means the registry's 1,2,3... order cannot mirror them.
    sources = _sources(2)
    sources[0]["citation"] = 2
    sources[1]["citation"] = 3
    body = f"## Artifact Discoveries\n\n{CITED}\n\n{UNCITED}"
    out, metrics = _strip_uncited_claims(body, sources)
    assert out == body
    assert "skipped" in metrics


def test_video_cited_paragraph_survives_and_markers_restored():
    # [VN] video citations are legitimate article citations but invisible to
    # the strip's numeric-[N] check — without shielding this paragraph would
    # be destroyed.
    video_para = (
        "In the accompanying field walkthrough the excavator describes the "
        "collapsed gateway and the reused orthostats in detail, pointing to "
        "tool marks along the northern jamb of the entrance [V2]."
    )
    body = f"## Architecture & Monuments\n\n{video_para}\n\n{UNCITED}"
    out, metrics = _strip_uncited_claims(body, _sources())
    assert video_para in out
    assert "[V2]" in out
    assert "lunar standstills" not in out
    assert metrics["dropped"] == 1


def test_rejected_claims_never_reinjected_from_snippets():
    # The registry is built WITHOUT claims, so even a snippet with perfect
    # lexical overlap must not rescue the paragraph — re-attaching would
    # launder a citation the verifier may have just rejected.
    sources = _sources(1)
    sources[0]["snippet"] = UNCITED
    body = f"## Artifact Discoveries\n\n{CITED}\n\n{UNCITED}"
    out, metrics = _strip_uncited_claims(body, sources)
    assert "lunar standstills" not in out
    assert metrics["injected"] == 0
    assert metrics["dropped"] == 1
