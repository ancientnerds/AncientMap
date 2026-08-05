"""Activity feed endpoint shaping (spec §7)."""

from datetime import datetime
from types import SimpleNamespace

from api.routes.public_v1 import _activity_items


def test_activity_items_shape():
    rows = [
        SimpleNamespace(
            created_at=datetime(2026, 8, 4, 3, 0),
            kind="curator",
            summary="Denkstunde: 3 claims",
            details={"claims": 3},
        )
    ]
    items = _activity_items(rows)
    assert items[0]["kind"] == "curator"
    assert items[0]["summary"].startswith("Denkstunde")
    assert items[0]["created_at"].startswith("2026-08-04")
