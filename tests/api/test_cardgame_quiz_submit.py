# SPDX-License-Identifier: AGPL-3.0-only
"""submit_quiz_answers grades against the rows it locked.

The quiz row and the player row are read again FOR UPDATE, so two submits of one quiz
serialize and the second sees the score of the first. Those re-reads were ``.first()``,
typed Optional, and ``mypy api/`` flagged every use (HUMAN_ONLY A7). They are ``.one()``
now: the rows were found moments before in the same transaction, and a re-read that
finds nothing raises NoResultFound instead of an AttributeError on None.

DB-less on tests/fake_sql.OrmSession: real ORM queries, rendered with the PostgreSQL
dialect, answered from a queue in call order.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import NoResultFound

from api.cardgame import quiz
from api.cardgame.constants import QUIZ_CREDITS_PER_CORRECT, QUIZ_XP_PER_CORRECT
from tests.fake_sql import OrmSession

USER_ID = uuid.uuid4()
QUIZ_ID = uuid.uuid4()


def _quiz_row(score: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=QUIZ_ID,
        user_id=USER_ID,
        score=score,
        answers_key=["Egypt", "Peru"],
        explanations=["Giza is in Egypt.", "Machu Picchu is in Peru."],
        submitted_at=None,
    )


def test_a_submit_grades_the_locked_quiz_and_pays_the_locked_player():
    looked_up, locked = _quiz_row(), _quiz_row()
    player = SimpleNamespace(id=USER_ID, credits=10)
    stats = SimpleNamespace(xp=0, total_cards=0)
    # session.get(quiz), the quiz lock, the player lock, session.get(stats)
    session = OrmSession([[looked_up], [locked], [player], [stats]])

    out = quiz.submit_quiz_answers(
        session, SimpleNamespace(id=USER_ID), str(QUIZ_ID), ["Egypt", "Chile"]
    )

    assert (out["score"], out["total"]) == (1, 2)
    assert [r["is_correct"] for r in out["results"]] == [True, False]
    assert locked.score == 1 and locked.submitted_at is not None
    assert looked_up.score is None  # the grade lands on the row the lock returned
    assert player.credits == 10 + QUIZ_CREDITS_PER_CORRECT
    assert stats.xp == QUIZ_XP_PER_CORRECT
    quiz_lock, player_lock = session.sql
    assert "FROM quiz_sessions" in quiz_lock and quiz_lock.endswith("FOR UPDATE")
    assert "FROM discord_users" in player_lock and player_lock.endswith("FOR UPDATE")


def test_a_quiz_already_graded_under_the_lock_is_refused():
    session = OrmSession([[_quiz_row()], [_quiz_row(score=2)]])

    with pytest.raises(quiz.QuizAlreadySubmittedError):
        quiz.submit_quiz_answers(session, SimpleNamespace(id=USER_ID), str(QUIZ_ID), ["Egypt"])


def test_a_quiz_row_gone_before_the_lock_raises_instead_of_reading_none():
    session = OrmSession([[_quiz_row()], []])

    with pytest.raises(NoResultFound):
        quiz.submit_quiz_answers(session, SimpleNamespace(id=USER_ID), str(QUIZ_ID), ["Egypt"])
