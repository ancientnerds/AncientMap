"""Attempt budget for the weekly journal, spent from the database.

WHY this exists: on 2026-10-05 the journal for the week of 2026-09-28 never
appeared. The attempt counter lived in ``orchestrator.main``'s memory, so each
of the eight deploys that Monday started a fresh "attempt 1/3" and killed the
run in flight; and ``should_generate_article()`` only opened on Monday, so after
the last attempt was killed by the 06:41 UTC deploy on Tuesday the week was lost
without a fourth try. Both facts are now rows, not variables: a restart cannot
refund an attempt, and a Tuesday retry reads the same budget the Monday run
spent against.

One row per covered week (``week_start`` = the Monday of the week the journal
covers, NOT the Monday it runs on — the two differ by a week). The row is
written before the run starts: a crash burns an attempt, which is the intent
(a crashed attempt already cost hours of quota).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime

from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)

#: Attempts per covered week. Was MAX_ARTICLE_ATTEMPTS in orchestrator.py, then
#: 3 — spent within two hours on 2026-10-06: three deploys, three attempts, and
#: a week with no journal. A deploy kills the run and a killed run has already
#: spent its attempt, so the budget has to survive the deploys of a normal
#: working day, not just the failures of the pipeline.
MAX_ATTEMPTS = 8
#: Minimum spacing between two attempts. A journal run takes hours, so this
#: only separates retries of runs that failed fast.
RETRY_INTERVAL_S = 1800

#: Weeks this process has already refused for a spent budget, so the refusal is
#: logged once instead of once a minute until the window closes. A restart
#: forgets it and says so again — that is the useful moment to repeat it.
_spent_budget_logged: set[date] = set()


def may_attempt(
    attempts: int,
    last_attempt_at: datetime | None,
    now: datetime,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    retry_interval_s: int = RETRY_INTERVAL_S,
) -> bool:
    """Whether another attempt for this week may start right now."""
    if attempts >= max_attempts:
        return False
    if last_attempt_at is None:
        return True
    return (now - last_attempt_at).total_seconds() >= retry_interval_s


def budget_spent(attempts: int, *, max_attempts: int = MAX_ATTEMPTS) -> bool:
    """Whether the week's attempts are used up (as opposed to merely too early)."""
    return attempts >= max_attempts


def _engine_connect() -> Callable[[], object]:
    """pipeline.database's connection factory, imported late: the module builds
    the engine from settings at import time, and the lyra image imports this
    module before the database is reachable."""
    from pipeline.database import engine

    return engine.connect


def _read_attempt(week_start: date, connect: Callable[[], object]) -> tuple[int, datetime | None]:
    with connect() as conn:
        row = conn.execute(
            sa_text(
                "SELECT attempts, last_attempt_at FROM lyra_journal_attempts "
                "WHERE week_start = :week_start"
            ),
            {"week_start": week_start},
        ).fetchone()
    if row is None:
        return 0, None
    return int(row[0]), row[1]


def _spend_attempt(week_start: date, connect: Callable[[], object]) -> None:
    with connect() as conn:
        conn.execute(
            sa_text(
                """
                INSERT INTO lyra_journal_attempts (week_start, attempts, last_attempt_at, updated_at)
                VALUES (:week_start, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (week_start) DO UPDATE SET
                    attempts = lyra_journal_attempts.attempts + 1,
                    last_attempt_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"week_start": week_start},
        )
        conn.commit()


def claim_attempt(
    week_start: date,
    *,
    now: datetime | None = None,
    connect: Callable[[], object] | None = None,
) -> bool:
    """Spend one attempt for the covered week if the budget allows it.

    Returns True when the caller should start a run. The attempt is recorded
    before the run starts, so a run killed mid-flight cannot be repeated for
    free — and a container restart mid-week continues the budget instead of
    resetting it.
    """
    now = now or datetime.now(UTC)
    connect = connect or _engine_connect()
    attempts, last_attempt_at = _read_attempt(week_start, connect)
    if budget_spent(attempts):
        # Once, not once a minute: the orchestrator asks every loop, and the
        # window is open for JOURNAL_GRACE_HOURS.
        if week_start not in _spent_budget_logged:
            _spent_budget_logged.add(week_start)
            logger.info(
                "Journal budget for week %s is spent after %d attempt(s) (last at %s) "
                "— no run until the next Monday slot",
                week_start,
                attempts,
                last_attempt_at.isoformat() if last_attempt_at else "never",
            )
        return False
    if not may_attempt(attempts, last_attempt_at, now):
        # Normal: the retry spacing has not elapsed. The loop wakes every 60s.
        logger.debug(
            "Journal attempt for week %s waits for the retry spacing (last at %s)",
            week_start,
            last_attempt_at.isoformat() if last_attempt_at else "never",
        )
        return False
    _spend_attempt(week_start, connect)
    logger.info(
        "Journal attempt %d/%d claimed for week %s at %s",
        attempts + 1,
        MAX_ATTEMPTS,
        week_start,
        now.isoformat(),
    )
    return True


def finish_week(week_start: date, *, connect: Callable[[], object] | None = None) -> None:
    """Mark the covered week as written — its budget is spent and no attempt may
    start any more.

    Without this the loop would keep claiming the remaining attempts of a week
    whose journal is already in the database, and generate_weekly_article would
    answer each one with "Active article for week already exists".
    """
    with (connect or _engine_connect())() as conn:
        conn.execute(
            sa_text(
                """
                INSERT INTO lyra_journal_attempts (week_start, attempts, last_attempt_at, updated_at)
                VALUES (:week_start, :max_attempts, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (week_start) DO UPDATE SET
                    attempts = :max_attempts,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"week_start": week_start, "max_attempts": MAX_ATTEMPTS},
        )
        conn.commit()
    logger.info("Journal week %s is written — its attempt budget is spent", week_start)


def spent_attempts(week_start: date, *, connect: Callable[[], object] | None = None) -> int:
    """How many attempts the covered week has spent (diagnostics and tests)."""
    return _read_attempt(week_start, connect or _engine_connect())[0]


def last_attempt_at(
    week_start: date, *, connect: Callable[[], object] | None = None
) -> datetime | None:
    """When the covered week last started an attempt (diagnostics and tests)."""
    return _read_attempt(week_start, connect or _engine_connect())[1]


__all__ = [
    "MAX_ATTEMPTS",
    "RETRY_INTERVAL_S",
    "budget_spent",
    "claim_attempt",
    "finish_week",
    "last_attempt_at",
    "may_attempt",
    "spent_attempts",
]
