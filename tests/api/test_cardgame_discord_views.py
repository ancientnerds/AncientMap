# SPDX-License-Identifier: AGPL-3.0-only
"""The card game's Discord views: runtime buttons, disabling, the clicked message.

``mypy api/`` (HUMAN_ONLY A7) refused three patterns of api/cardgame/discord_commands.py,
none of them wrong at runtime: handlers assigned over ``Button.callback`` on the instance
(LyraView, QuizView, ExpeditionListView), ``item.disabled = True`` on children typed as the
base ``Item``, and ``interaction.message.edit`` on an Optional message. They are now a
``_CallbackButton`` built with its handler, ``_disable_buttons`` and
``_component_message``. These tests pin what the views do with them.

DB-less: only the paths that stop before a database session are clicked; the interaction
is a stand-in with the attributes the handlers read.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from api.cardgame import discord_commands as dc

OWNER = "1234567890"


def _interaction(user_id: str, message: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(id=int(user_id)),
        message=message,
        response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock()),
    )


def _buttons(view: discord.ui.View) -> list[dc._CallbackButton]:
    items = list(view.children)
    assert all(isinstance(i, dc._CallbackButton) for i in items)
    return [i for i in items if isinstance(i, dc._CallbackButton)]


def test_the_lyra_view_offers_one_button_per_tier_and_answers_only_its_player():
    async def run() -> SimpleNamespace:
        view = dc.LyraView(OWNER)
        buttons = _buttons(view)
        assert [b.custom_id for b in buttons] == [f"lyra_tier_{t}" for t in (1, 2, 3, 4)]
        assert [b.row for b in buttons] == [0, 0, 1, 1]
        stranger = _interaction("42")
        await buttons[2].callback(stranger)
        return stranger

    stranger = asyncio.run(run())

    stranger.response.send_message.assert_awaited_once_with("Not your Lyra duel.", ephemeral=True)


def test_a_quiz_answer_moves_the_buttons_to_the_next_question():
    quiz_data = {
        "session_id": "s1",
        "questions": [
            {"question": "Where is Giza?", "choices": ["Egypt", "Peru"], "type": "country"},
            {"question": "Oldest?", "choices": ["A", "B", "C"], "type": "age_comparison"},
        ],
    }

    async def run() -> tuple[dc.QuizView, SimpleNamespace, SimpleNamespace]:
        view = dc.QuizView(OWNER, quiz_data)
        assert [b.label for b in _buttons(view)] == ["Egypt", "Peru"]
        stranger, player = _interaction("42"), _interaction(OWNER)
        await _buttons(view)[1].callback(stranger)
        await _buttons(view)[0].callback(player)
        return view, stranger, player

    view, stranger, player = asyncio.run(run())

    stranger.response.send_message.assert_awaited_once_with(
        "This is someone else's quiz.", ephemeral=True
    )
    assert view.answers == ["Egypt"]
    assert [b.custom_id for b in _buttons(view)] == ["quiz_1_0", "quiz_1_1", "quiz_1_2"]
    kwargs = player.response.edit_message.await_args.kwargs
    assert kwargs["view"] is view
    assert kwargs["embed"].title == "Question 2/2"


def test_a_completed_expedition_shows_a_disabled_done_button():
    expeditions = [
        {"id": "nile", "name": "Nile", "stages": 5},
        {"id": "andes", "name": "Andes", "stages": 4},
    ]
    progress = [{"expedition_id": "nile", "current_stage": 5, "completed": True}]

    async def run() -> list[dc._CallbackButton]:
        return _buttons(dc.ExpeditionListView(OWNER, expeditions, progress))

    done, open_ = asyncio.run(run())

    assert (done.label, done.disabled, done.style) == (
        "Nile (Done)",
        True,
        discord.ButtonStyle.secondary,
    )
    assert (open_.label, open_.disabled, open_.custom_id) == (
        "Andes (0/4)",
        False,
        "expedition_andes",
    )


def test_disabling_a_duel_greys_out_accept_and_decline():
    async def run() -> dc.DuelView:
        view = dc.DuelView("b1", OWNER, "42")
        dc._disable_buttons(view)
        return view

    view = asyncio.run(run())

    assert [(i.label, i.disabled) for i in view.children if isinstance(i, discord.ui.Button)] == [
        ("Accept", True),
        ("Decline", True),
    ]


def test_the_clicked_message_is_the_interactions_message():
    message = MagicMock(spec=discord.Message)
    assert dc._component_message(_interaction(OWNER, message)) is message
    with pytest.raises(RuntimeError, match="without its message"):
        dc._component_message(_interaction(OWNER, None))


def test_a_snap_view_that_times_out_applies_the_result_and_closes_its_message(monkeypatch):
    applied: list[int] = []
    monkeypatch.setattr(
        dc.SnapView,
        "_apply_and_stop",
        lambda self, snap_multiplier: applied.append(snap_multiplier),
    )
    monkeypatch.setattr(dc, "_build_result_embed", lambda *a, **k: "result-embed")
    message = MagicMock(spec=discord.Message)
    message.edit, message.reply = AsyncMock(), AsyncMock()

    async def run() -> dc.SnapView:
        view = dc.SnapView("b1", OWNER, "42", result={}, original_stake=10)
        assert view.message is None  # DuelView sets it once the message is sent
        view.message = message
        await view.on_timeout()
        return view

    view = asyncio.run(run())

    assert applied == [1]
    assert all(i.disabled for i in view.children if isinstance(i, discord.ui.Button))
    message.edit.assert_awaited_once_with(view=view)
    message.reply.assert_awaited_once_with(embed="result-embed")
