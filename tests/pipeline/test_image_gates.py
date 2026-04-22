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


def test_weak_verdict_rejected_by_strict_gate():
    # A thematically adjacent but non-literal match — must NOT pass the gate
    # under the strict schema, even though the image is "related".
    raw = (
        '{"primary_entity_in_claim":"Anunnaki deities",'
        '"what_image_actually_shows":"generic Mesopotamian cylinder seal",'
        '"match":"related","verdict":"weak","reason":"same culture, wrong subject"}'
    )
    v = parse_vlm_verdict(raw)
    assert v is not None
    assert verdict_is_meaningful(v) is False
    assert verdict_is_accept(v) is False
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


def test_parse_vlm_verdict_handles_garbage():
    assert parse_vlm_verdict("not json") is None
    assert parse_vlm_verdict("") is None


def test_parse_vlm_verdict_strips_code_fences():
    raw = (
        '```json\n'
        '{"primary_entity_in_claim":"x","what_image_actually_shows":"y",'
        '"match":"exact","verdict":"meaningful","reason":"ok"}\n'
        '```'
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
