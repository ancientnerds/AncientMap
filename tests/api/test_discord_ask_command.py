# SPDX-License-Identifier: AGPL-3.0-only
"""/ask answers wherever it is used, and hands _handle_ask a guild member or nothing.

The command posts "X asked: ..." and opens a thread on that message for the answer. Only a
text channel's message can carry such a thread. Until 2026-09-26 the command called
``interaction.channel.create_thread`` on whatever channel it ran in: in a thread (a Lyra
follow-up thread included) or a voice channel's chat that attribute does not exist, the
AttributeError reached the catch-all, and the player got "Something went wrong" instead of
the answer Lyra had already written and charged for. ``mypy api/`` flagged the call
(HUMAN_ONLY A7: "VoiceChannel | StageChannel | ... | Thread ... has no attribute
create_thread").

DB-less: the bot is built without logging in, _handle_ask is replaced, and the interaction
is a stand-in whose user and channel are spec'd on the real discord.py classes, so the
isinstance checks the command makes see the classes they check for.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from api.services import discord_bot


class _Followup:
    def __init__(self) -> None:
        self.sent: list[str | None] = []

    async def send(self, content: str | None = None, **_kwargs: object) -> SimpleNamespace:
        self.sent.append(content)
        return SimpleNamespace(id=4242)


@pytest.fixture
def ask(monkeypatch):
    """Runs /ask with a canned answer; returns (run, members seen by _handle_ask)."""
    members: list[object] = []

    async def handle_ask(discord_id, question, *, history=None, member=None):
        members.append(member)
        return "Göbekli Tepe is older than writing.", []

    monkeypatch.setattr(discord_bot, "_handle_ask", handle_ask)
    monkeypatch.setattr(discord_bot, "_bot", None)
    command = discord_bot._get_bot().tree.get_command("ask")
    monkeypatch.setattr(discord_bot, "_bot", None)

    def run(user: object, channel: object) -> _Followup:
        followup = _Followup()
        interaction = SimpleNamespace(
            user=user,
            channel=channel,
            response=SimpleNamespace(defer=AsyncMock()),
            followup=followup,
        )
        asyncio.run(command.callback(interaction, "How old is Göbekli Tepe?"))
        return followup

    return run, members


def _member() -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 1234567890
    member.display_name = "Petra"
    return member


def test_in_a_text_channel_the_answer_goes_to_a_thread_on_the_question(ask):
    run, members = ask
    thread = SimpleNamespace(send=AsyncMock())
    channel = MagicMock(spec=discord.TextChannel)
    channel.create_thread = AsyncMock(return_value=thread)

    followup = run(_member(), channel)

    assert channel.create_thread.await_args.kwargs["message"].id == 4242
    thread.send.assert_awaited_once_with("Göbekli Tepe is older than writing.")
    assert followup.sent == ["**Petra** asked: How old is Göbekli Tepe?"]
    assert isinstance(members[0], discord.Member)


def test_inside_a_thread_the_answer_goes_to_the_thread_itself(ask):
    run, _ = ask
    followup = run(_member(), MagicMock(spec=discord.Thread))

    assert followup.sent == [
        "**Petra** asked: How old is Göbekli Tepe?",
        "Göbekli Tepe is older than writing.",
    ]


def test_without_thread_permission_the_answer_goes_to_the_channel(ask):
    run, _ = ask
    channel = MagicMock(spec=discord.TextChannel)
    channel.create_thread = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "no")
    )

    followup = run(_member(), channel)

    assert followup.sent[-1] == "Göbekli Tepe is older than writing."


def test_a_user_outside_the_guild_reaches_handle_ask_as_no_member(ask):
    """_handle_ask reads member.roles to register a new player; a plain discord.User has no
    roles, so outside the guild it must get None (the DM handler's rule), not the User."""
    run, members = ask
    user = MagicMock(spec=discord.User)
    user.id = 1234567890
    user.display_name = "Petra"

    run(user, MagicMock(spec=discord.DMChannel))

    assert members == [None]


def test_the_bots_own_id_is_its_logged_in_users_id(monkeypatch):
    bot = discord_bot.LyraBot()
    with pytest.raises(RuntimeError, match="not logged in"):
        _ = bot.own_id
    monkeypatch.setattr(bot._connection, "user", SimpleNamespace(id=987654321))
    assert bot.own_id == 987654321
