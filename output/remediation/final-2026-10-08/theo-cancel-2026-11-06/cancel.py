"""D110 (2026-11-06): the paused request afe7c26a goes to 'cancelled'.

Same path as theo-cancel-2026-11-05/cancel.py (D85): status flip +
release_reservation_in_session in one transaction, run in ancient_nerds_api.
The row's reservation was already released (reservation_released = true), so
the release call is the function's exactly-once no-op; it stays for parity.
Prints one JSON line per row: {"phase": "before"|"after", "row": {...}}.
"""
import json

from sqlalchemy import text

from api.services.theo_worker import release_reservation_in_session
from pipeline.database import get_session

RID = "afe7c26a-f54a-4eea-8427-9034733aa47c"
COLS = "id, user_id, status, created_at, started_at, completed_at, reservation_released, is_public, error_message, question"


def dump(session, phase):
    rows = session.execute(
        text(f"SELECT {COLS} FROM research_requests WHERE id = CAST(:id AS uuid)"), {"id": RID}
    ).mappings().all()
    for r in rows:
        print(json.dumps({"phase": phase, "row": {k: str(v) if v is not None else None for k, v in r.items()}}))
    return rows


with get_session() as session:
    before = dump(session, "before")
    assert len(before) == 1 and before[0]["status"] == "paused", before
    n = session.execute(
        text("UPDATE research_requests SET status = 'cancelled' WHERE id = :id AND status = 'paused'"), {"id": RID}
    ).rowcount
    assert n == 1, n
    release_reservation_in_session(session, RID)
    session.commit()

with get_session() as session:
    after = dump(session, "after")
    assert len(after) == 1 and after[0]["status"] == "cancelled" and after[0]["reservation_released"] is True, after
