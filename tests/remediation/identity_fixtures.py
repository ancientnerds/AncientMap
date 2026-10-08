"""Synthetic production rows for the identity discovery tests (the shape `export.py` reads)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import entities, export  # noqa: E402

_COUNTER = {"n": 0}


def site(**over: Any) -> dict[str, Any]:
    """One `shown` row; every key `export.SHOWN_SQL` selects, with an unremarkable default."""
    _COUNTER["n"] += 1
    n = _COUNTER["n"]
    row: dict[str, Any] = {
        "id": f"00000000-0000-4000-8000-{n:012d}",
        "name": f"Site {n}",
        "country": "Greece",
        "site_type": "Temple",
        "lat": 38.0,
        "lon": 23.0,
        "period_start": -500,
        "period_end": None,
        "period_name": "500 BC",
        "source_url": None,
        "scope_status": None,
        "scope_reason": None,
        "created_at": f"2026-03-04 21:07:{n % 60:02d}",
        "parent_site_id": None,
        "description": "A ruined temple.",
        "description_chars": 16,
        "description_lane": "L",
        "images": 1,
        "images_all": 1,
        "links": 0,
        "names_rows": 1,
        "has_card": False,
        "outside_window": False,
    }
    row.update(over)
    return row


def ext(site_id: str, kind: str, value: str) -> dict[str, str]:
    return {"site_id": site_id, "kind": kind, "value": value}


def export_of(
    shown: list[dict[str, Any]],
    *,
    ext_ids: list[dict[str, Any]] | None = None,
    names: list[dict[str, Any]] | None = None,
    pairs: list[dict[str, Any]] | None = None,
    losers: list[dict[str, Any]] | None = None,
    period_journal: list[dict[str, Any]] | None = None,
) -> export.Export:
    return export.Export(
        shown=shown,
        ext_ids=ext_ids or [],
        names=names or [],
        pairs=pairs or [],
        losers=losers or [],
        period_journal=period_journal or [],
        exported_at="2026-10-08 20:00:00+00",
    )


def entity(qid: str, *, p31: tuple[str, ...] = (), label: str | None = None, aliases=()) -> dict:
    """A raw `wbgetentities` entity with the parts the discovery reads."""
    return {
        "id": qid,
        "labels": {"en": {"language": "en", "value": label}} if label else {},
        "aliases": {"en": [{"language": "en", "value": a} for a in aliases]},
        "claims": {
            "P31": [
                {
                    "mainsnak": {
                        "snaktype": "value",
                        "datavalue": {"type": "wikibase-entityid", "value": {"id": c}},
                    },
                    "rank": "normal",
                }
                for c in p31
            ]
        },
    }


def store_of(
    tmp_path: Path,
    items: dict[str, dict[str, Any]],
    classes: dict[str, str],
    *,
    delta: dict[str, dict[str, Any]] | None = None,
) -> entities.EntityStore:
    """An `EntityStore` over throwaway harvest and delta roots."""
    harvest_root, delta_root = tmp_path / "harvest", tmp_path / "delta"
    for root, group in ((harvest_root, items), (delta_root, delta or {})):
        (root / "entities").mkdir(parents=True, exist_ok=True)
        for qid, item in group.items():
            (root / "entities" / f"{qid}.json").write_text(json.dumps(item), encoding="utf-8")
    (harvest_root / "CLASSES.json").write_text(
        json.dumps({q: {"label": label, "p279": []} for q, label in classes.items()}),
        encoding="utf-8",
    )
    return entities.EntityStore(harvest_root, delta_root)
