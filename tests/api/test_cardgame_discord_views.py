# SPDX-License-Identifier: AGPL-3.0-only
"""The card game's Discord views, driven through what Discord sees and does.

``mypy api/`` (HUMAN_ONLY A7) refused three patterns of api/cardgame/discord_commands.py,
none of them wrong at runtime: handlers assigned over ``Button.callback`` on the instance
(LyraView, QuizView, ExpeditionListView), ``item.disabled = True`` on children typed as the
base ``Item``, and ``interaction.message.edit`` on an Optional message. The views now use
``_CallbackButton``, ``_disable_buttons`` and ``_component_message``.

The behaviour tests below do not name those helpers. They read the components a view sends
to Discord (``View.to_components()``), click buttons through ``item.callback`` (the call
discord.py makes on a click), and check what the handler answers. They pass against the code
before the change as well (checked by running them on 7b6c736's discord_commands.py), so they
show the change kept every label, style, custom id, row, disabled flag and handler binding.
The last test pins the helpers themselves.

DB-less: a click that opens a session gets tests/fake_sql.OrmSession through a patched
``pipeline.database.get_session`` (the views import it when clicked); the interaction is a
stand-in with the attributes the handlers read.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import pipeline.database
from api.cardgame import discord_commands as dc
from api.cardgame.constants import LYRA_TIERS
from tests.fake_sql import OrmSession

OWNER = "1234567890"
STRANGER = "42"


def _interaction(user_id: str, message: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(id=int(user_id)),
        message=message,
        response=SimpleNamespace(
            send_message=AsyncMock(), edit_message=AsyncMock(), defer=AsyncMock()
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _message() -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.edit, message.reply = AsyncMock(), AsyncMock()
    return message


def _buttons(view: discord.ui.View) -> list[discord.ui.Button]:
    return [i for i in view.children if isinstance(i, discord.ui.Button)]


def _button(custom_id: str, label: str, style: int, *, disabled: bool = False) -> dict:
    return {
        "type": 2,
        "style": style,
        "disabled": disabled,
        "label": label,
        "custom_id": custom_id,
    }


def _row(*buttons: dict) -> dict:
    return {"type": 1, "components": list(buttons)}


def _db(monkeypatch: pytest.MonkeyPatch, *answers: list[Any]) -> OrmSession:
    session = OrmSession(answers)

    @contextmanager
    def get_session() -> Iterator[OrmSession]:
        yield session

    monkeypatch.setattr(pipeline.database, "get_session", get_session)
    return session


GREEN, RED, PRIMARY, SECONDARY = 3, 4, 1, 2


def test_the_lyra_view_sends_one_button_per_tier_in_two_rows():
    async def run() -> list[dict]:
        return dc.LyraView(OWNER).to_components()

    assert asyncio.run(run()) == [
        _row(
            _button("lyra_tier_1", "★ Casual", GREEN),
            _button("lyra_tier_2", "★★ Scholar", GREEN),
        ),
        _row(
            _button("lyra_tier_3", "★★★ Sage", RED),
            _button("lyra_tier_4", "⭐ Ancient", RED),
        ),
    ]


def test_each_lyra_button_challenges_its_own_tier_and_only_for_its_player(monkeypatch):
    player = SimpleNamespace(id=uuid.uuid4(), discord_id=OWNER)
    _db(monkeypatch, [player], [player], [player], [player])
    asked: list[int] = []

    def can_challenge_lyra(session: Any, user_id: Any, tier: int) -> tuple[bool, str]:
        asked.append(tier)
        return False, "win"

    monkeypatch.setattr("api.cardgame.lyra_duel.can_challenge_lyra", can_challenge_lyra)

    async def run() -> tuple[SimpleNamespace, list[SimpleNamespace]]:
        view = dc.LyraView(OWNER)
        stranger = _interaction(STRANGER)
        await _buttons(view)[2].callback(stranger)
        clicks = []
        for button in _buttons(view):
            click = _interaction(OWNER)
            await button.callback(click)
            clicks.append(click)
        return stranger, clicks

    stranger, clicks = asyncio.run(run())

    stranger.response.send_message.assert_awaited_once_with("Not your Lyra duel.", ephemeral=True)
    assert asked == [1, 2, 3, 4]
    for tier, click in zip((1, 2, 3, 4), clicks, strict=True):
        click.response.defer.assert_awaited_once_with(ephemeral=True)
        text = click.followup.send.await_args.args[0]
        assert text.startswith(f"You've already challenged {LYRA_TIERS[tier]['name']} today.")


QUIZ = {
    "session_id": "s1",
    "questions": [
        {"question": "Where is Giza?", "choices": ["Egypt", "Peru"], "type": "country"},
        {"question": "Oldest?", "choices": ["A", "B", "C"], "type": "age_comparison"},
    ],
}


def test_a_quiz_answer_sends_the_next_questions_buttons_and_the_last_submits(monkeypatch):
    player = SimpleNamespace(id=uuid.uuid4(), discord_id=OWNER)
    _db(monkeypatch, [player])
    submitted: list[list[str]] = []

    def submit_quiz_answers(session: Any, user: Any, session_id: str, answers: list[str]) -> dict:
        submitted.append(list(answers))
        rows = [{"is_correct": True, "explanation": "ok"}] * len(answers)
        return {
            "score": 2,
            "total": 2,
            "results": rows,
            "rewards": {"credits": 0, "xp": 0, "bonus_card": None},
        }

    monkeypatch.setattr("api.cardgame.quiz.submit_quiz_answers", submit_quiz_answers)

    async def run() -> tuple[list[list[dict]], SimpleNamespace, SimpleNamespace, SimpleNamespace]:
        view = dc.QuizView(OWNER, QUIZ)
        sent = [view.to_components()]
        stranger, first, last = _interaction(STRANGER), _interaction(OWNER), _interaction(OWNER)
        await _buttons(view)[1].callback(stranger)
        await _buttons(view)[0].callback(first)
        sent.append(view.to_components())
        await _buttons(view)[2].callback(last)
        return sent, stranger, first, last

    sent, stranger, first, last = asyncio.run(run())

    assert sent == [
        [_row(_button("quiz_0_0", "Egypt", PRIMARY), _button("quiz_0_1", "Peru", PRIMARY))],
        [
            _row(_button("quiz_1_0", "A", PRIMARY), _button("quiz_1_1", "B", PRIMARY)),
            _row(_button("quiz_1_2", "C", PRIMARY)),
        ],
    ]
    stranger.response.send_message.assert_awaited_once_with(
        "This is someone else's quiz.", ephemeral=True
    )
    assert first.response.edit_message.await_args.kwargs["embed"].title == "Question 2/2"
    assert submitted == [["Egypt", "C"]]
    assert last.followup.send.await_args.kwargs["embed"].title == "Quiz Results: 2/2"


def test_the_expedition_list_sends_a_disabled_done_button_and_plays_the_clicked_one(monkeypatch):
    player = SimpleNamespace(id=uuid.uuid4(), discord_id=OWNER)
    _db(monkeypatch, [player])
    expeditions = [
        {"id": "nile", "name": "Nile", "stages": 5},
        {"id": "andes", "name": "Andes", "stages": 4},
        {"id": "indus", "name": "Indus", "stages": 3},
        {"id": "yellow", "name": "Yellow River", "stages": 6},
    ]
    progress = [
        {"expedition_id": "nile", "current_stage": 5, "completed": True},
        {"expedition_id": "indus", "current_stage": 1, "completed": False},
    ]

    def play_expedition_stage(session: Any, user: Any, expedition_id: str) -> dict:
        raise ValueError(f"played {expedition_id}")

    monkeypatch.setattr("api.cardgame.expedition.play_expedition_stage", play_expedition_stage)

    async def run() -> tuple[list[dict], SimpleNamespace]:
        view = dc.ExpeditionListView(OWNER, expeditions, progress)
        click = _interaction(OWNER)
        await _buttons(view)[3].callback(click)
        return view.to_components(), click

    sent, click = asyncio.run(run())

    assert sent == [
        _row(
            _button("expedition_nile", "Nile (Done)", SECONDARY, disabled=True),
            _button("expedition_andes", "Andes (0/4)", GREEN),
            _button("expedition_indus", "Indus (1/3)", GREEN),
        ),
        _row(_button("expedition_yellow", "Yellow River (0/6)", GREEN)),
    ]
    click.followup.send.assert_awaited_once_with("played yellow", ephemeral=True)


def test_declining_a_duel_greys_out_accept_and_decline_in_the_edited_message(monkeypatch):
    battle = SimpleNamespace(status="pending")
    _db(monkeypatch, [battle])

    async def run() -> tuple[dc.DuelView, SimpleNamespace, SimpleNamespace]:
        view = dc.DuelView(str(uuid.uuid4()), OWNER, STRANGER)
        challenger, defender = _interaction(OWNER), _interaction(STRANGER)
        decline = _buttons(view)[1]
        await decline.callback(challenger)
        await decline.callback(defender)
        return view, challenger, defender

    view, challenger, defender = asyncio.run(run())

    challenger.response.send_message.assert_awaited_once_with(
        "Only the challenged player can decline.", ephemeral=True
    )
    assert battle.status == "declined"
    defender.response.edit_message.assert_awaited_once_with(
        content="Duel declined.", embed=None, view=view
    )
    assert [(b["label"], b["disabled"]) for b in view.to_components()[0]["components"]] == [
        ("Accept", True),
        ("Decline", True),
    ]


def test_a_snap_both_players_continue_closes_the_clicked_message(monkeypatch):
    applied: list[int] = []
    monkeypatch.setattr(
        dc.SnapView,
        "_apply_and_stop",
        lambda self, snap_multiplier: applied.append(snap_multiplier),
    )
    monkeypatch.setattr(dc, "_build_result_embed", lambda *a, **k: "result-embed")
    message = _message()

    async def run() -> tuple[dc.SnapView, SimpleNamespace, SimpleNamespace]:
        view = dc.SnapView("b1", OWNER, STRANGER, result={}, original_stake=10)
        first, second = _interaction(OWNER, message), _interaction(STRANGER, message)
        continue_ = _buttons(view)[1]
        await continue_.callback(first)
        await continue_.callback(second)
        return view, first, second

    view, first, second = asyncio.run(run())

    first.response.send_message.assert_awaited_once_with("Waiting for opponent...", ephemeral=True)
    assert applied == [1]
    assert all(b.disabled for b in _buttons(view))
    message.edit.assert_awaited_once_with(view=view)
    second.followup.send.assert_awaited_once_with(embed="result-embed")


def test_a_snap_view_that_times_out_applies_the_result_and_closes_its_message(monkeypatch):
    applied: list[int] = []
    monkeypatch.setattr(
        dc.SnapView,
        "_apply_and_stop",
        lambda self, snap_multiplier: applied.append(snap_multiplier),
    )
    monkeypatch.setattr(dc, "_build_result_embed", lambda *a, **k: "result-embed")
    message = _message()

    async def run() -> dc.SnapView:
        view = dc.SnapView("b1", OWNER, STRANGER, result={}, original_stake=10)
        view.message = message  # what DuelView does once the message is sent
        await view.on_timeout()
        return view

    view = asyncio.run(run())

    assert applied == [1]
    assert all(b.disabled for b in _buttons(view))
    message.edit.assert_awaited_once_with(view=view)
    message.reply.assert_awaited_once_with(embed="result-embed")


def test_the_view_helpers_run_the_handler_grey_out_buttons_and_read_the_message():
    clicked: list[Any] = []

    async def on_click(interaction: Any) -> None:
        clicked.append(interaction)

    async def run() -> tuple[dc._CallbackButton, dc.DuelView, dc.SnapView]:
        button = dc._CallbackButton(
            on_click, label="Go", style=discord.ButtonStyle.primary, custom_id="go", row=1
        )
        await button.callback(SimpleNamespace(tag="click"))
        duel = dc.DuelView("b1", OWNER, STRANGER)
        dc._disable_buttons(duel)
        return button, duel, dc.SnapView("b1", OWNER, STRANGER, result={}, original_stake=10)

    button, duel, snap = asyncio.run(run())

    assert [c.tag for c in clicked] == ["click"]
    assert (button.label, button.custom_id, button.row, button.disabled) == ("Go", "go", 1, False)
    assert all(b.disabled for b in _buttons(duel))
    assert snap.message is None  # declared before DuelView sets it
    message = _message()
    assert dc._component_message(_interaction(OWNER, message)) is message
    with pytest.raises(RuntimeError, match="without its message"):
        dc._component_message(_interaction(OWNER, None))
