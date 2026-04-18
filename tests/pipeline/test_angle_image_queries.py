"""Tests for angle_image_queries: query parser + list output validation."""

from __future__ import annotations

from pipeline.lyra.angle_image_queries import parse_queries


def test_parse_queries_accepts_valid_list():
    raw = '{"queries":["Nebra sky disc","Enuma Elish tablet","Dresden Codex Venus"]}'
    assert parse_queries(raw) == ["Nebra sky disc", "Enuma Elish tablet", "Dresden Codex Venus"]


def test_parse_queries_strips_markdown_fences():
    raw = '```json\n{"queries":["a","b"]}\n```'
    assert parse_queries(raw) == ["a", "b"]


def test_parse_queries_filters_empty_and_too_long():
    # Empty strings + strings > 80 chars should be dropped
    raw = '{"queries":["ok", "", "  ", "' + "x" * 100 + '", "also ok"]}'
    out = parse_queries(raw)
    assert out == ["ok", "also ok"]


def test_parse_queries_handles_garbage():
    assert parse_queries("not json") == []
    assert parse_queries("") == []
    assert parse_queries('{"queries":"not a list"}') == []


def test_parse_queries_dedupes_preserving_order():
    raw = '{"queries":["a","b","a","c","b"]}'
    assert parse_queries(raw) == ["a", "b", "c"]


def test_parse_queries_caps_at_five():
    raw = '{"queries":["a","b","c","d","e","f","g"]}'
    assert len(parse_queries(raw)) == 5
