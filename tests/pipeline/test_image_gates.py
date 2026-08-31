"""Unit tests for the metadata and vision relevance gates."""

from __future__ import annotations

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.image_gates import (
    build_vlm_prompt,
    metadata_gate_passes,
    parse_vlm_verdict,
    verdict_is_accept,
    verdict_is_meaningful,
    verdict_is_safe,
)


def _cand(title="", desc="", artist="", url="https://x/y.jpg", source="wikimedia"):
    return ImageCandidate(
        url=url,
        source=source,
        title=title,
        description=desc,
        artist=artist,
        license="CC BY-SA 4.0",
        license_url="",
        thumbnail_url=url,
        metadata={},
    )


def test_metadata_gate_accepts_matching_keywords():
    c = _cand(title="Nebra sky disc", desc="Bronze Age astronomical disc")
    must_show = "The Nebra Sky Disc itself, bronze with gold celestial inlays"
    assert metadata_gate_passes(c, must_show) is True


def test_metadata_gate_rejects_unrelated():
    c = _cand(title="Great Pyramid of Giza at sunset", desc="Tourist photo")
    must_show = "The Nebra Sky Disc itself, bronze with gold celestial inlays"
    assert metadata_gate_passes(c, must_show) is False


def test_metadata_gate_rejects_empty_metadata():
    c = _cand(title="", desc="")
    assert metadata_gate_passes(c, "Anything") is False


def test_parse_vlm_verdict_accepts_well_formed_meaningful():
    raw = (
        '{"primary_entity_in_claim":"Nebra Sky Disc",'
        '"what_image_actually_shows":"bronze disc with gold celestial inlays",'
        '"match":"exact","verdict":"meaningful","reason":"literal match"}'
    )
    v = parse_vlm_verdict(raw)
    assert v is not None
    assert v["verdict"] == "meaningful"
    assert verdict_is_meaningful(v) is True
    assert verdict_is_accept(v) is True
    assert verdict_is_safe(v) is True


def test_weak_verdict_embeds_as_illustration_not_as_evidence():
    """`weak` is the judge's MIDDLE verdict: related, but not literal.

    Treating it as a rejection (behaviour until 2026-08-31) threw away the
    middle of a three-level scale and cost ~95% of all candidates — 862
    opportunities across 12 papers lost every candidate they had. It may be
    embedded, but never as evidence: `verdict_is_accept` stays False, which
    is what marks the caption as an illustration.
    """
    raw = (
        '{"primary_entity_in_claim":"Anunnaki deities",'
        '"what_image_actually_shows":"generic Mesopotamian cylinder seal",'
        '"match":"related","verdict":"weak","reason":"same culture, wrong subject"}'
    )
    v = parse_vlm_verdict(raw)
    assert v is not None
    assert verdict_is_meaningful(v) is False
    assert verdict_is_accept(v) is False, "weak is never citable evidence"
    assert verdict_is_safe(v) is True, "weak may still illustrate the passage"


def test_weak_but_off_topic_is_still_rejected():
    """The middle verdict is not a loophole: off_topic fails whatever the
    verdict field claims."""
    raw = (
        '{"primary_entity_in_claim":"Anunnaki deities",'
        '"what_image_actually_shows":"a modern office building",'
        '"match":"off_topic","verdict":"weak","reason":"unrelated"}'
    )
    v = parse_vlm_verdict(raw)
    assert verdict_is_safe(v) is False


def test_misleading_verdict_rejected():
    raw = (
        '{"primary_entity_in_claim":"20th-century psychologist",'
        '"what_image_actually_shows":"European Renaissance portrait",'
        '"match":"off_topic","verdict":"misleading","reason":"wrong person and era"}'
    )
    v = parse_vlm_verdict(raw)
    assert verdict_is_meaningful(v) is False
    assert verdict_is_accept(v) is False
    assert verdict_is_safe(v) is False


def test_misleading_is_rejected_even_when_match_looks_fine():
    """A judge that says 'misleading' outranks its own match field."""
    raw = (
        '{"primary_entity_in_claim":"Nebra Sky Disc",'
        '"what_image_actually_shows":"a replica sold in a gift shop",'
        '"match":"related","verdict":"misleading","reason":"modern replica"}'
    )
    assert verdict_is_safe(parse_vlm_verdict(raw)) is False


def test_parse_vlm_verdict_handles_garbage():
    assert parse_vlm_verdict("not json") is None
    assert parse_vlm_verdict("") is None


def test_parse_vlm_verdict_strips_code_fences():
    raw = (
        "```json\n"
        '{"primary_entity_in_claim":"x","what_image_actually_shows":"y",'
        '"match":"exact","verdict":"meaningful","reason":"ok"}\n'
        "```"
    )
    v = parse_vlm_verdict(raw)
    assert v is not None and v["verdict"] == "meaningful"


def test_vlm_outage_does_not_silently_pass():
    # Null verdict (VLM API down) must drop the candidate — we prefer no image
    # over an unvalidated one under the strict schema.
    assert verdict_is_meaningful(None) is False
    assert verdict_is_accept(None) is False
    assert verdict_is_safe(None) is False


def test_build_vlm_prompt_includes_claim_and_ideal_subject():
    prompt = build_vlm_prompt(
        claim="The Nebra Sky Disc dates to the early Bronze Age",
        what_image_must_show="The Nebra Sky Disc itself",
        forbidden_elements=["reconstructions", "tourist photos"],
    )
    assert "Nebra Sky Disc" in prompt
    assert "Bronze Age" in prompt
    assert "reconstructions" in prompt
    assert "meaningful|weak|misleading" in prompt


# --- Pre-filter width (2026-08-31) -----------------------------------------
# The cheap filter exists to save VLM calls, not to judge relevance — the
# docstring always said "VLM still runs as the strict downstream gate". At
# two required tokens it was deciding instead of pre-filtering: 587 of 971
# opportunities across 12 papers reached the judge with nothing to judge.


def test_metadata_gate_accepts_a_terse_but_on_topic_title():
    """Museum and Commons titles are terse; a perfect image can share exactly
    one content word with a full sentence of must-show text."""
    c = _cand(title="Solar flare", desc="")
    must_show = "A photograph showing a solar eruption on the surface of the Sun"
    assert metadata_gate_passes(c, must_show) is True


def test_metadata_gate_still_rejects_unrelated_titles():
    c = _cand(title="Great Pyramid of Giza at sunset", desc="Tourist photo")
    assert metadata_gate_passes(c, "The Nebra Sky Disc, bronze with gold inlays") is False


def test_rank_by_metadata_overlap_puts_the_best_candidate_first():
    """A looser filter only pays off if the judge sees the best ones first —
    the probe budget is spent in list order."""
    from pipeline.lyra.image_gates import rank_by_metadata_overlap

    weak = _cand(title="Ancient lines in the desert", desc="")
    strong = _cand(title="Nebra sky disc bronze", desc="gold celestial inlays")
    must_show = "The Nebra Sky Disc itself, bronze with gold celestial inlays"
    ranked = rank_by_metadata_overlap([weak, strong], must_show)
    assert ranked[0] is strong
    assert ranked[1] is weak


def test_rank_by_metadata_overlap_is_stable_for_equal_scores():
    from pipeline.lyra.image_gates import rank_by_metadata_overlap

    a = _cand(title="Nebra sky disc", desc="")
    b = _cand(title="Nebra sky disc", desc="")
    assert rank_by_metadata_overlap([a, b], "Nebra sky disc bronze") == [a, b]
