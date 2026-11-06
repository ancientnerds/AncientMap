"""The boundary check's spellings follow the spellings a new row may take.

The insert lane (D57) accepts a country spelled as the frontend's flag map spells it
(`countryFlags.ts`, the T05 census's vocabulary) and then asks the boundary file whether the point
lies in it (`bcases.classify.country_after_move`, which compares `country_census.canonical` on both
sides). A flag-map spelling the boundary file names otherwise was refused as `country-disagrees`
however close the point lay: Nan Madol, "Micronesia", 2026-11-06.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import country_census as CC  # noqa: E402
from bcases import classify as BC  # noqa: E402

FLAGS_TS = REPO / "ancient-nerds-map" / "src" / "utils" / "countryFlags.ts"
FLAG_LINE = re.compile(r"^\s*'([^']+)':\s*'([A-Z]{2})'", re.MULTILINE)


@pytest.fixture(scope="module")
def boundaries() -> dict[str, Any]:
    return json.loads(CC.BOUNDARIES.read_text(encoding="utf-8"))


def test_every_flag_spelling_names_its_own_polygon(boundaries: dict[str, Any]) -> None:
    polygons: dict[str, set[str]] = {}
    for feature in boundaries["features"]:
        props = feature["properties"]
        polygons.setdefault(props["ISO3166-1-Alpha-2"], set()).add(CC.canonical(props["name"]))
    pairs = FLAG_LINE.findall(FLAGS_TS.read_text(encoding="utf-8"))
    assert len(pairs) > 200, "the flag map was not read"
    wrong = [
        (name, code, sorted(polygons[code]))
        for name, code in pairs
        if code in polygons and CC.canonical(name) not in polygons[code]
    ]
    assert wrong == []


def test_nan_madol_lies_off_the_coast_of_micronesia() -> None:
    out = BC.country_after_move("Micronesia", 6.841944, 158.332222, CC.load_countries())
    assert out["agrees"] is True
    assert out["polygon"] == []
    assert out["note"] is not None and out["note"].startswith("coast, ")
