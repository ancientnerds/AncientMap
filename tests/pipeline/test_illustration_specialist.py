"""Tests for illustration specialist schema + parse."""

from __future__ import annotations

import pytest

from pipeline.lyra.illustration_specialist import parse_opportunities


def test_parse_opportunities_accepts_valid():
    raw = """{"opportunities":[
        {"claim_index":3,"needs_image":true,"search_query":"Nebra sky bronze disc",
         "what_image_must_show":"The Nebra Sky Disc itself — bronze disc with gold celestial inlays",
         "forbidden_elements":["modern replicas","people in frame"],
         "rationale":"The disc IS the evidence for the claim."}
    ]}"""
    opps = parse_opportunities(raw)
    assert len(opps) == 1
    o = opps[0]
    assert o["claim_index"] == 3
    assert o["needs_image"] is True
    assert "bronze disc" in o["search_query"]
    assert "disc IS" in o["rationale"]


def test_parse_opportunities_rejects_missing_fields():
    # Missing required field → skip
    raw = '{"opportunities":[{"claim_index":1,"needs_image":true}]}'
    assert parse_opportunities(raw) == []


def test_parse_opportunities_filters_needs_image_false():
    raw = """{"opportunities":[
        {"claim_index":1,"needs_image":false,"search_query":"","what_image_must_show":"",
         "forbidden_elements":[],"rationale":"framing paragraph, no image helps"}
    ]}"""
    assert parse_opportunities(raw) == []


def test_parse_opportunities_handles_garbage_json():
    assert parse_opportunities("not json at all") == []
    assert parse_opportunities("") == []
