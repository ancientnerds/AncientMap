"""Claims-per-node shaping (spec §7 Focus-Card)."""

from types import SimpleNamespace

from api.routes.public_v1 import _claim_items


def test_claim_items_shape():
    rows = [
        SimpleNamespace(
            text="The dating is contested",
            status="contested",
            confidence=0.6,
            external_source_count=1,
            paper_ids=["abc"],
        )
    ]
    items = _claim_items(rows)
    assert items[0]["status"] == "contested"
    assert items[0]["confidence"] == 0.6
    assert items[0]["paper_ids"] == ["abc"]
