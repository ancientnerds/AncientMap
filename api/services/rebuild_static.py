# SPDX-License-Identifier: AGPL-3.0-only
"""The static export as a locked job: the shared body, and the command line for after a wave.

    docker exec ancient_nerds_api python -m api.services.rebuild_static

(as the container user, never ``-u root``: the exporter refuses root.) The export takes the
advisory lock of the ``rebuild-static`` job, the same one ``POST /api/sites/rebuild-static``
and the nightly run (api/services/static_export_schedule.py) take, so no two exports write
``public/data/sites/index.json`` at once, and its status row
(``GET /api/sites/rebuild-static/status``) tells the other readers what happened. It waits for
the export and exits 0 when it succeeded, 1 when it failed (the error is in the log and the
status row) and 3 when an export already runs; nothing was started in that case.

Run it after the last deploy of a wave: a deploy restarts the container and kills a running
export (the status then reads "interrupted").
"""

from __future__ import annotations

import logging
import sys

from api.services.background_jobs import JobAlreadyRunning, run_job, run_module

#: Background-job name of the static export (api/services/background_jobs.py).
REBUILD_STATIC_JOB = "rebuild-static"

#: The last full export took about 4 minutes; half an hour means something is stuck.
REBUILD_STATIC_TIMEOUT_S = 30 * 60


def run_static_export() -> dict:
    """The job body: the export in a child process (it also writes the file snapshot).

    --no-library: public/data/library/ belongs to the library refresh job, which runs
    under its own lock; this export would only re-write the same table's rows there.
    """
    return run_module(
        "pipeline.static_exporter", "--no-library", timeout_s=REBUILD_STATIC_TIMEOUT_S
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        ok = run_job(REBUILD_STATIC_JOB, run_static_export)
    except JobAlreadyRunning:
        print("a static export is already running; nothing was started", file=sys.stderr)
        return 3
    if not ok:
        print(
            "the static export failed; the error is in the log above and in "
            "GET /api/sites/rebuild-static/status",
            file=sys.stderr,
        )
        return 1
    print("static export ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
