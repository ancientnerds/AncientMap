# SPDX-License-Identifier: AGPL-3.0-only
"""The static export outside the founders' POST: the shared job body, the locked CLI, the nightly.

D25 (2026-10-08): the export runs after every write wave and every night at 04:30 UTC, always
through the advisory lock of ``rebuild-static``, so no two exports write the 362 MB index at once.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from api.services import background_jobs as bj
from api.services import rebuild_static as rs
from api.services import static_export_schedule as sched


def test_the_job_body_runs_the_export_in_a_child_process():
    """The 1.76M-site index must not be built inside the serving API process."""
    with patch.object(rs, "run_module", return_value={"elapsed_seconds": 1.0}) as run:
        assert rs.run_static_export() == {"elapsed_seconds": 1.0}
    # --no-library: public/data/library/ belongs to the library refresh job
    assert run.call_args.args == ("pipeline.static_exporter", "--no-library")
    assert run.call_args.kwargs["timeout_s"] == rs.REBUILD_STATIC_TIMEOUT_S == 30 * 60


def test_the_cli_runs_the_export_job_under_the_shared_lock(capsys):
    with patch.object(rs, "run_job", return_value=True) as run:
        assert rs.main() == 0
    assert run.call_args.args == (rs.REBUILD_STATIC_JOB, rs.run_static_export)


def test_the_cli_exits_1_when_the_export_failed(capsys):
    with patch.object(rs, "run_job", return_value=False):
        assert rs.main() == 1
    assert "failed" in capsys.readouterr().err


def test_the_cli_exits_3_when_an_export_already_runs(capsys):
    with patch.object(rs, "run_job", side_effect=bj.JobAlreadyRunning("rebuild-static")):
        assert rs.main() == 3
    assert "already running" in capsys.readouterr().err


def test_the_nightly_run_starts_the_same_job_as_the_post():
    with patch.object(sched, "start_job", return_value={"state": "running"}) as start:
        assert sched.start_nightly_export() == "started"
    assert start.call_args.args == (rs.REBUILD_STATIC_JOB, rs.run_static_export)


def test_the_nightly_run_logs_a_running_export_as_the_known_state_it_is(caplog):
    with (
        caplog.at_level("INFO", logger=sched.logger.name),
        patch.object(sched, "start_job", side_effect=bj.JobAlreadyRunning("rebuild-static")),
    ):
        assert sched.start_nightly_export() == "running"
    assert [r.levelname for r in caplog.records] == ["INFO"]


def test_the_nightly_run_does_not_hide_other_errors():
    with patch.object(sched, "start_job", side_effect=ConnectionError("db down")):
        with pytest.raises(ConnectionError):
            sched.start_nightly_export()


def test_04_30_utc_is_the_hour_after_the_backup_and_the_reindex():
    assert (sched.EXPORT_HOUR_UTC, sched.EXPORT_MINUTE_UTC) == (4, 30)


def test_seconds_until_the_next_04_30():
    from api.routes.vector_sync import _seconds_until_next

    with patch("api.routes.vector_sync.datetime") as dt:
        dt.now.return_value = datetime(2026, 10, 8, 4, 0, tzinfo=UTC)
        assert _seconds_until_next(4, 30) == 30 * 60
        dt.now.return_value = datetime(2026, 10, 8, 4, 30, tzinfo=UTC)
        assert _seconds_until_next(4, 30) == 24 * 3600
        # the default stays "on the hour"
        dt.now.return_value = datetime(2026, 10, 8, 2, 59, tzinfo=UTC)
        assert _seconds_until_next(3) == 60


def test_the_loop_sleeps_until_04_30_then_starts_the_export():
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 2:
            raise asyncio.CancelledError

    async def run() -> None:
        with (
            patch.object(sched, "_seconds_until_next", return_value=1234.0) as until,
            patch.object(sched.asyncio, "sleep", fake_sleep),
            patch.object(sched, "start_nightly_export", return_value="started") as export,
        ):
            with pytest.raises(asyncio.CancelledError):
                await sched.schedule_static_export()
        assert until.call_args.args == (4, 30)
        assert export.call_count == 1

    asyncio.run(run())
    assert slept == [1234.0, 1234.0]


def test_start_static_export_scheduler_creates_the_task():
    async def run() -> None:
        with patch.object(sched, "schedule_static_export") as loop:
            loop.return_value = asyncio.sleep(0)
            sched.start_static_export_scheduler()
            assert sched._export_task is not None
            await sched._export_task
        assert loop.call_count == 1

    asyncio.run(run())
