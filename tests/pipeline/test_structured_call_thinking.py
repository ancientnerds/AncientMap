"""structured_llm_call forwards an explicit thinking block and reports usage.

Without the explicit block, thinking_for_effort() returns adaptive for every
effort level and reasoning tokens cost ~7x the visible output — the
prospector's per-window extraction must run with thinking disabled.
"""

from types import SimpleNamespace
from unittest.mock import patch

from pipeline.lyra import minimax_shared

SCHEMA = {
    "type": "object",
    "properties": {"mentions": {"type": "array", "items": {"type": "string"}}},
    "required": ["mentions"],
    "additionalProperties": False,
}


def _fake_response():
    return SimpleNamespace(
        content=[SimpleNamespace(text='{"mentions": ["a"]}')],
        stop_reason="end_turn",
        usage={"input_tokens": 120, "output_tokens": 7},
    )


def test_thinking_block_is_forwarded_verbatim():
    with patch("pipeline.lyra.config.call_api", return_value=_fake_response()) as call:
        minimax_shared.structured_llm_call(
            "sys", "user", SCHEMA, 100, temperature=0.1, thinking={"type": "disabled"}
        )
    assert call.call_args.kwargs["thinking"] == {"type": "disabled"}


def test_without_thinking_nothing_is_passed_so_the_default_applies():
    with patch("pipeline.lyra.config.call_api", return_value=_fake_response()) as call:
        minimax_shared.structured_llm_call("sys", "user", SCHEMA, 100, temperature=0.1)
    assert "thinking" not in call.call_args.kwargs


def test_usage_sink_receives_the_response_usage():
    usage: dict = {}
    with patch("pipeline.lyra.config.call_api", return_value=_fake_response()):
        parsed = minimax_shared.structured_llm_call(
            "sys", "user", SCHEMA, 100, temperature=0.1, usage=usage
        )
    assert parsed == {"mentions": ["a"]}
    assert usage == {"input_tokens": 120, "output_tokens": 7}
