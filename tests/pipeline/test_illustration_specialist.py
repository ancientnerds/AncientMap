"""Tests for illustration specialist schema + parse."""

from __future__ import annotations

import pytest  # noqa: F401  -- used by parametrize-style tests below

from pipeline.lyra.illustration_specialist import parse_opportunities


def test_parse_opportunities_accepts_valid():
    raw = """{"opportunities":[
        {"paragraph_index":3,"keyword":"Nebra Sky Disc","search_query":"Nebra sky bronze disc",
         "what_image_must_show":"The Nebra Sky Disc itself — bronze disc with gold celestial inlays",
         "forbidden_elements":["modern replicas","people in frame"],
         "rationale":"The disc IS the evidence for the claim."}
    ]}"""
    opps = parse_opportunities(raw)
    assert len(opps) == 1
    o = opps[0]
    assert o["paragraph_index"] == 3
    assert o["keyword"] == "Nebra Sky Disc"
    assert "bronze disc" in o["search_query"]
    assert "disc IS" in o["rationale"]


def test_parse_opportunities_drops_when_hard_required_field_missing():
    # paragraph_index + search_query are the only HARD required fields.
    # Missing search_query → drop.
    raw = '{"opportunities":[{"paragraph_index":1,"keyword":"x"}]}'
    assert parse_opportunities(raw) == []


def test_parse_opportunities_handles_garbage_json():
    assert parse_opportunities("not json at all") == []
    assert parse_opportunities("") == []


# ---- Lenient parsing: Run 10 regression -----------------------------------
# The strict "all 6 fields required" rule silently dropped every opportunity
# in Run 10 because MiniMax was consistently omitting one of the optional
# fields (likely `forbidden_elements`). Now only paragraph_index +
# search_query are required; the rest get safe defaults.


def test_parse_opportunities_fills_missing_forbidden_elements():
    raw = """{"opportunities":[
        {"paragraph_index":2,"keyword":"Puma Punku","search_query":"Puma Punku H blocks",
         "what_image_must_show":"Sandstone H-blocks","rationale":"Visual proof of geometry."}
    ]}"""
    opps = parse_opportunities(raw)
    assert len(opps) == 1
    assert opps[0]["forbidden_elements"] == []
    assert opps[0]["keyword"] == "Puma Punku"


def test_parse_opportunities_fills_missing_keyword_and_rationale():
    raw = """{"opportunities":[
        {"paragraph_index":0,"search_query":"Anunnaki cylinder seal"}
    ]}"""
    opps = parse_opportunities(raw)
    assert len(opps) == 1
    assert opps[0]["keyword"] == ""
    assert opps[0]["rationale"] == ""
    assert opps[0]["forbidden_elements"] == []
    assert opps[0]["what_image_must_show"] == ""


def test_parse_opportunities_drops_non_dict_entries():
    raw = '{"opportunities":["not a dict",{"paragraph_index":0,"search_query":"x"}]}'
    opps = parse_opportunities(raw)
    assert len(opps) == 1
    assert opps[0]["search_query"] == "x"


def test_parse_opportunities_treats_empty_string_as_missing():
    # paragraph_index present but search_query empty → drop (no usable query)
    raw = '{"opportunities":[{"paragraph_index":0,"search_query":""}]}'
    assert parse_opportunities(raw) == []
