# SPDX-License-Identifier: AGPL-3.0-only
"""Pass 2 of a Lyra answer: the messages that ask the model to insert entity markers.

The list starts with system messages and ends with the human turn; ``mypy api/`` read the
first element as its type and refused the human message (HUMAN_ONLY A7). It is typed as
``list[BaseMessage]`` now; these tests pin the order the agent sends.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from api.services.lyra_prompts import MARKER_INJECTION_PROMPT, build_marker_injection_messages


def test_the_prose_and_catalogue_follow_the_instructions_as_the_human_turn():
    msgs = build_marker_injection_messages(
        prose="Stonehenge stands on Salisbury Plain.",
        user_question="Where is Stonehenge?",
        entities_json='{"sites": []}',
        context_prompt="",
    )

    assert [type(m) for m in msgs] == [SystemMessage, HumanMessage]
    assert msgs[0].content == MARKER_INJECTION_PROMPT
    human = msgs[1].content
    assert '## Entities Catalogue\n{"sites": []}' in human
    assert "## Prose to Annotate\nStonehenge stands on Salisbury Plain." in human
    assert "## Original Question\nWhere is Stonehenge?" in human


def test_a_context_prompt_comes_as_a_second_system_message():
    msgs = build_marker_injection_messages(
        prose="p", user_question="q", entities_json="{}", context_prompt="Site: Petra"
    )

    assert [type(m) for m in msgs] == [SystemMessage, SystemMessage, HumanMessage]
    assert msgs[1].content == "Site: Petra"
