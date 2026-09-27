"""`python -m pipeline.studio.ledger_cli --record|--publish < payload.json` (API container).

Run over ssh by the local studio (`docker exec -i ancient_nerds_api python -m ...`), so the
database credentials never leave the VPS. Prints one JSON object {"ok": bool, ...}; exit 0 on
success, 1 when the payload or the write is refused. Every write is read back in a fresh
session after the commit.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy.orm import Session

from pipeline.studio.ledger import (
    LedgerError,
    publish,
    publish_params,
    record,
    row_from_json,
    visible_after_commit,
)

SessionFactory = Callable[[], AbstractContextManager[Session]]


def _session_factory() -> SessionFactory:
    from pipeline.database import get_session

    return get_session


def run(mode: str, payload: Any, sessions: SessionFactory) -> dict[str, Any]:
    if mode == "record":
        row = row_from_json(payload)
        with sessions() as session:
            inserted = record(session, row)
        with sessions() as session:
            if not visible_after_commit(session, video_sha256=row.video_sha256, youtube_id=None):
                raise LedgerError("the row is not readable after the commit")
        return {"ok": True, "inserted": inserted}
    params = publish_params(payload)
    with sessions() as session:
        publish(session, params)
    with sessions() as session:
        if not visible_after_commit(
            session, video_sha256=params["video_sha256"], youtube_id=params["youtube_id"]
        ):
            raise LedgerError("the published status is not readable after the commit")
    return {"ok": True}


def main(argv: list[str] | None = None, sessions: SessionFactory | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.studio.ledger_cli")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_const", const="record", dest="mode")
    mode.add_argument("--publish", action="store_const", const="publish", dest="mode")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        payload = json.loads(sys.stdin.read())
        out = run(args.mode, payload, sessions if sessions is not None else _session_factory())
    except (LedgerError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
