"""Tests for `PaperHandler._validate_title` — guards against the Run 9 bug
where the outline LLM returned the user question verbatim as the title."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline.lyra.handlers.paper import PaperHandler
from pipeline.lyra.research_state import ResearchState

QUESTION = (
    "I was always pondering about the Legends of the so called Shining Ones. "
    "What if these were beings from other planets coming to earth, interacting "
    "with early humans, giving them knowledge which results in stories about "
    "ancient egypt gods or Hermes Trismegistus or others like Quetzalcoatle "
    "that came from the skies?"
)


def _make_handler(rescue_response: str = "The Shining Ones in Comparative Mythology"):
    """Build a PaperHandler with a mocked _llm_call that returns `rescue_response`."""
    state = ResearchState(question=QUESTION, request_id="test-rid")
    bus = MagicMock()
    sem = asyncio.Semaphore(1)
    handler = PaperHandler(state, bus, sem)
    # Mock _llm_call to return the rescue title
    handler._llm_call = AsyncMock(return_value=rescue_response)
    return handler


@pytest.mark.asyncio
async def test_short_valid_title_passes_through():
    handler = _make_handler()
    out = await handler._validate_title("The Shining Ones in Mythology", settings=None)
    assert out == "The Shining Ones in Mythology"
    handler._llm_call.assert_not_called()


@pytest.mark.asyncio
async def test_oversized_title_triggers_rescue():
    handler = _make_handler(rescue_response="The Anunnaki and Sky-Visitor Traditions")
    bad_title = "X" * 200  # way over 100 chars
    out = await handler._validate_title(bad_title, settings=None)
    assert out == "The Anunnaki and Sky-Visitor Traditions"
    handler._llm_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_question_echo_triggers_rescue():
    """Title that's a substring of the question is rejected."""
    handler = _make_handler(rescue_response="Ancient Sky Beings and Cultural Memory")
    # First 50 chars of the question — should be detected as an echo
    bad_title = QUESTION[:50]
    out = await handler._validate_title(bad_title, settings=None)
    assert out == "Ancient Sky Beings and Cultural Memory"
    handler._llm_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_question_as_title_triggers_rescue():
    """The exact Run 9 failure mode."""
    handler = _make_handler(rescue_response="Shining Ones and Ancient Astronaut Theories")
    out = await handler._validate_title(QUESTION, settings=None)
    assert out == "Shining Ones and Ancient Astronaut Theories"
    handler._llm_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_rescue_also_invalid_falls_back_to_question_prefix():
    """If rescue ALSO returns a bad title, fall back to question[:60]."""
    handler = _make_handler(rescue_response=QUESTION)  # rescue also echoes
    out = await handler._validate_title("X" * 200, settings=None)
    # Falls back to question[:60], rstripped of trailing punctuation
    assert out == QUESTION[:60].rstrip(".,;:")
    assert len(out) <= 60
    handler._llm_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_rescue_strips_quotes_and_takes_first_line():
    """Rescue LLM output gets cleaned: quotes stripped, only first line kept."""
    handler = _make_handler(rescue_response='"The Shining Ones"\nExtra commentary line')
    out = await handler._validate_title("X" * 200, settings=None)
    assert out == "The Shining Ones"


@pytest.mark.asyncio
async def test_rescue_failure_falls_back_gracefully():
    """If the rescue LLM call raises, fall back to question prefix."""
    handler = _make_handler()
    handler._llm_call = AsyncMock(side_effect=RuntimeError("llm down"))
    out = await handler._validate_title("X" * 200, settings=None)
    assert out == QUESTION[:60].rstrip(".,;:")
    handler._llm_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_title_triggers_rescue():
    handler = _make_handler(rescue_response="A Real Title")
    out = await handler._validate_title("", settings=None)
    assert out == "A Real Title"


@pytest.mark.asyncio
async def test_title_at_exact_length_boundary():
    """100-char title is valid (boundary inclusive)."""
    handler = _make_handler()
    title = "A" * 100  # exactly 100 chars, doesn't echo question
    out = await handler._validate_title(title, settings=None)
    assert out == title
    handler._llm_call.assert_not_called()
