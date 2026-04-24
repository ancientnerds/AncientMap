"""Tests for parse helpers in config.py.

Verifies that parse_prefilled_json and parse_json_response work correctly.
"""

from pipeline.lyra.config import (
    parse_json_response,
    parse_prefilled_json,
)

# ---------------------------------------------------------------------------
# Tests: parse helpers
# ---------------------------------------------------------------------------


class TestParseHelpers:
    def test_parse_json_response_plain(self):
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_response_fenced(self):
        result = parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_prefilled_json_complete(self):
        result = parse_prefilled_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_prefilled_json_missing_brace(self):
        result = parse_prefilled_json('"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_prefilled_json_with_whitespace(self):
        result = parse_prefilled_json('  \n  {"key": "value"}  \n  ')
        assert result == {"key": "value"}
