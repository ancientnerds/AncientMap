"""The wikidata items the identity discovery reads: the 2026-09-26 harvest, plus a delta.

The harvest (`fields/harvest.py`, `output/remediation/fields/harvest/`) holds the raw
`wbgetentities` entity of 4,517 items and the English label and P279 parents of every P31 class.
It is the main checkout's gitignored run data and is **never written here**. The sites it does not
hold (an item linked after 2026-09-26, 28 files that were never fetched) are fetched into a delta
of the same layout inside the identity run directory, with the harvest's own functions
(`fields.harvest.fetch_entities` / `fetch_classes`: 50 ids per call, one request at a time, one
second apart, the User-Agent that names https://ancientnerds.com), so there is one fetcher and one
cache format. A failed Wikimedia request raises and stops the run; nothing is recorded as absent
that was not answered as absent.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import harvest as H  # noqa: E402

from identity import common  # noqa: E402

DELTA_SUBDIR = "harvest_delta"
SOURCE_HARVEST = "harvest"
SOURCE_DELTA = "delta"
P_INSTANCE = "P31"


def en_label(entity: Mapping[str, Any]) -> str | None:
    return ((entity.get("labels") or {}).get("en") or {}).get("value")


def en_aliases(entity: Mapping[str, Any]) -> list[str]:
    return [a["value"] for a in (entity.get("aliases") or {}).get("en", [])]


def instance_of(entity: Mapping[str, Any]) -> list[str]:
    """The classes named by the item's non-deprecated P31 statements."""
    return H.item_ids(entity, P_INSTANCE)


class EntityStore:
    """Items and class labels from the harvest, then from the delta; a missing item is `None`."""

    def __init__(self, harvest_root: Path, delta_root: Path) -> None:
        self.roots = ((SOURCE_HARVEST, harvest_root), (SOURCE_DELTA, delta_root))
        self.classes: dict[str, Any] = {}
        for _, root in self.roots:
            path = root / H.CLASSES_FILE
            if path.exists():
                self.classes.update(json.loads(path.read_text(encoding="utf-8")))

    def path(self, source: str, qid: str) -> Path:
        return H.entity_path(dict(self.roots)[source], qid)

    def get(self, qid: str) -> tuple[dict[str, Any] | None, str | None]:
        """`(entity, source)`; `(None, None)` when neither root holds the item."""
        for source, root in self.roots:
            path = H.entity_path(root, qid)
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8")), source
        return None, None

    def class_label(self, class_qid: str) -> str:
        """The English label of a class; its id when the label is unknown (never an empty string)."""
        return (self.classes.get(class_qid) or {}).get("label") or class_qid

    def missing(self, qids: Iterable[str]) -> list[str]:
        return sorted({q for q in qids if self.get(q)[0] is None})


def fetch_delta(
    qids: Iterable[str],
    harvest_root: Path,
    delta_root: Path,
    *,
    net: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = H.PACE_SECONDS,
) -> dict[str, int]:
    """Fetch the items neither root holds, and the classes they name, into the delta root.

    The delta's class file starts as a copy of the harvest's, so only classes nobody has labelled
    are asked.
    """
    store = EntityStore(harvest_root, delta_root)
    wanted = store.missing(qids)
    delta_root.mkdir(parents=True, exist_ok=True)
    classes = delta_root / H.CLASSES_FILE
    if not classes.exists():
        shutil.copyfile(harvest_root / H.CLASSES_FILE, classes)
    if not wanted:
        return {"asked": 0, "fetched": 0}
    net = net or H.open_fetcher(delta_root)
    fetched = H.fetch_entities(net, delta_root, wanted, sleep=sleep, pace=pace)
    H.fetch_classes(net, delta_root, wanted, sleep=sleep, pace=pace)
    return {"asked": len(wanted), "fetched": fetched["fetched"]}


def delta_dir(run: Path) -> Path:
    return run / DELTA_SUBDIR


def default_store(root: Path | None = None) -> EntityStore:
    return EntityStore(common.harvest_dir(root), delta_dir(common.run_dir(root)))
