# SPDX-License-Identifier: AGPL-3.0-only
"""Jobs that outlive their request, run once across both API instances.

Why a job and not a request: nginx cuts every /api/ request at 120 s
(ancientnerds-nginx-config, ``location /api/``: proxy_read_timeout 120s) and the deploy
curls the library refresh with ``--max-time 120``. The full static export takes about four
minutes (VPS mtimes 2026-08-18), and the library refresh spent 112 s in one scan alone, so
both requests were cut off and reported as failures while the work went on or died with
the connection. A POST now starts the job and answers 202; a GET reports it.

Why Postgres and not a module dict: ``api`` (:8000) and ``api2`` (:8001) sit behind one
round-robin upstream. In-process state answers a status poll that lands on the other
instance with "idle", and a second start there runs the job twice over the same files.
So both facts live in the database:

* the mutual exclusion is a session-level advisory lock, held on a dedicated AUTOCOMMIT
  connection for the whole run. Postgres drops it when that connection closes, so a
  process that dies mid-job cannot leave the job locked forever. AUTOCOMMIT keeps the
  connection out of "idle in transaction", which the database kills after 15 minutes.
* the status is a row in ``pipeline_heartbeats`` (the project's generic heartbeat table,
  plan section 9.1), named ``job:<name>``. Every instance reads the same row.

A status row that says "running" while nobody holds the lock is reported as
"interrupted": the process that ran it is gone (a deploy restarted the container).
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import threading
import time
import zlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from pipeline.database import engine, get_session

logger = logging.getLogger(__name__)

#: First key of every advisory lock this module takes ("AN" in ASCII), so these locks
#: never collide with a lock some other code takes with a single bigint key.
LOCK_NAMESPACE = 0x414E

_STATUS_PREFIX = "job:"


class JobAlreadyRunning(Exception):
    """Another instance (or this one) holds the job's lock."""


def lock_id(name: str) -> int:
    """Second advisory-lock key for ``name``: a stable, positive int4.

    Positive so that pg_locks (which reports the keys as unsigned oids) can be compared
    with it directly.
    """
    return zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF


class InstanceLock:
    """A Postgres advisory lock that holds across threads and across API instances.

    ``connect`` returns a new SQLAlchemy Connection; tests inject a fake. The lock lives on
    that connection's database session, so it is held from ``try_acquire()`` until
    ``release()`` - or until the process dies and the connection with it.
    """

    def __init__(self, name: str, connect: Callable[[], Any] | None = None) -> None:
        self.name = name
        self.key = lock_id(name)
        self._connect = connect or (
            lambda: engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        )
        self._conn: Any = None

    def try_acquire(self) -> bool:
        if self._conn is not None:
            raise RuntimeError(f"lock {self.name!r} is already held by this object")
        conn = self._connect()
        got = conn.execute(
            text("SELECT pg_try_advisory_lock(:ns, :key)"),
            {"ns": LOCK_NAMESPACE, "key": self.key},
        ).scalar()
        if not got:
            conn.close()
            return False
        self._conn = conn
        return True

    def release(self) -> None:
        if self._conn is None:
            raise RuntimeError(f"lock {self.name!r} is not held")
        conn, self._conn = self._conn, None
        try:
            released = conn.execute(
                text("SELECT pg_advisory_unlock(:ns, :key)"),
                {"ns": LOCK_NAMESPACE, "key": self.key},
            ).scalar()
            if not released:
                # Postgres says this session did not hold it: the connection was replaced
                # underneath us. Loud, because the mutual exclusion was not what we thought.
                logger.error("[JOB] advisory lock %s was not held at release", self.name)
        finally:
            conn.close()


def lock_is_held(db: Any, name: str) -> bool:
    """Whether any session currently holds the advisory lock of ``name``."""
    return bool(
        db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND classid = :ns AND objid = :key AND objsubid = 2 AND granted)"
            ),
            {"ns": LOCK_NAMESPACE, "key": lock_id(name)},
        ).scalar()
    )


_UPSERT_STATUS = text("""
    INSERT INTO pipeline_heartbeats (pipeline_name, last_heartbeat, status, last_error, step_data)
    VALUES (:name, NOW(), :status, :error, CAST(:data AS jsonb))
    ON CONFLICT (pipeline_name) DO UPDATE SET
        last_heartbeat = NOW(),
        status = EXCLUDED.status,
        last_error = EXCLUDED.last_error,
        step_data = EXCLUDED.step_data
""")


def _write_status(name: str, status: str, data: dict, error: str | None = None) -> None:
    with get_session() as session:
        session.execute(
            _UPSERT_STATUS,
            {
                "name": _STATUS_PREFIX + name,
                "status": status,
                "error": error,
                "data": json.dumps(data, default=str),
            },
        )


def read_status(db: Any, name: str) -> dict:
    """The job's last recorded run plus whether it is running right now."""
    row = db.execute(
        text(
            "SELECT status, last_heartbeat, last_error, step_data FROM pipeline_heartbeats "
            "WHERE pipeline_name = :name"
        ),
        {"name": _STATUS_PREFIX + name},
    ).fetchone()
    running = lock_is_held(db, name)
    if row is None:
        return {"job": name, "state": "running" if running else "never_run"}
    data = row.step_data or {}
    state = row.status
    if state == "running" and not running:
        state = "interrupted"
    return {
        "job": name,
        "state": state,
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "instance": data.get("instance"),
        "result": data.get("result"),
        "error": row.last_error,
    }


def start_job(name: str, work: Callable[[], dict], lock: InstanceLock | None = None) -> dict:
    """Run ``work`` in a background thread unless the job already runs anywhere.

    Raises JobAlreadyRunning when the lock is held. ``work`` returns a small JSON-able
    dict that becomes the status's ``result``; an exception it raises becomes the
    status's ``error`` and is logged with its traceback - never swallowed.
    """
    lock = lock or InstanceLock(name)
    if not lock.try_acquire():
        raise JobAlreadyRunning(name)
    started = {
        "started_at": datetime.now(UTC).isoformat(),
        "instance": socket.gethostname(),
    }
    try:
        _write_status(name, "running", started)
    except Exception:
        lock.release()
        raise
    thread = threading.Thread(
        target=_run, args=(name, work, lock, started), name=f"job-{name}", daemon=True
    )
    thread.start()
    return {"job": name, "state": "running", **started}


def _run(name: str, work: Callable[[], dict], lock: InstanceLock, started: dict) -> None:
    try:
        try:
            result = work()
        except Exception as exc:
            logger.exception("[JOB] %s failed", name)
            _write_status(
                name,
                "error",
                {**started, "finished_at": datetime.now(UTC).isoformat()},
                error=f"{type(exc).__name__}: {exc}"[:2000],
            )
            return
        _write_status(
            name, "ok", {**started, "finished_at": datetime.now(UTC).isoformat(), "result": result}
        )
        logger.info("[JOB] %s finished: %s", name, result)
    finally:
        lock.release()


def run_module(module: str, *args: str, timeout_s: int) -> dict:
    """Run ``python -m module args`` to completion as a child process; raise on failure.

    For jobs whose memory must not stay in the API process: the static export builds its
    1.76M-site index in memory (about 1.5 GB of output, host 3.6 GB free, no swap), and
    CPython keeps a grown heap after the objects are gone. A child process returns all of
    it when it exits, and the kernel's OOM killer would pick the child, not the API.
    """
    started = time.monotonic()
    proc = subprocess.run(  # noqa: S603 - fixed argv: our interpreter and our own module
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    tail = (proc.stdout + proc.stderr)[-1500:]
    if proc.returncode != 0:
        raise RuntimeError(f"{module} exited {proc.returncode}: {tail}")
    return {"elapsed_seconds": round(time.monotonic() - started, 1), "output_tail": tail[-500:]}
