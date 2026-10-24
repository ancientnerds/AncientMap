# SPDX-License-Identifier: AGPL-3.0-only
"""The loader's global scope rule (D58): `label_scope` on every parsed record, with its items.

The loader asks no verdict, so it keeps only `in_scope`: a site past its region's cutoff and a
Viking subject (by the Wikidata item the parser leaves in `raw_data`) are filtered, a borderline
record (a borderline country dated 500-1500) is held - as E3's 500 AD held it before D58.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from pipeline import unified_loader as UL


def rec(name: str, country: str, lat: float, lon: float, start: int, **raw: Any) -> dict:
    return {
        "name": name,
        "country": country,
        "lat": lat,
        "lon": lon,
        "period_start": start,
        "period_end": None,
        "raw_data": raw,
    }


RECORDS = [
    rec("Prambanan", "Indonesia", -7.75, 110.49, 850),
    rec("Chrobry", "Poland", 51.56, 15.52, 1000),
    rec("L'Anse aux Meadows", "Canada", 51.6, -55.53, 1000, wikidata="Q189113"),
    rec("L'Anse aux Meadows", "Canada", 51.6, -55.53, 1000, wikidata_id="Q189113"),
    rec("Krak des Chevaliers", "Syria", 34.76, 36.29, 1142),
    rec("Palmyra", "Syria", 34.55, 38.27, -100),
    rec("Mesa Verde", "United States", 37.18, -108.49, 1200, wikidata="Q1"),
]


def loaded(tmp_path: Path) -> list[str]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "data.json").write_text("[]", encoding="utf-8")
    loader = UL.UnifiedLoader(skip_backup=True)
    loader.raw_dir = tmp_path
    loader._truncated = True
    loader._parse_test = lambda *_args: iter([dict(r) for r in RECORDS])
    written: list[dict] = []
    loader._insert_batch = lambda _session, batch: written.extend(batch)
    loader._load_source(MagicMock(), "src", {"format": "test"}, 100)
    return [r["name"] for r in written]


def test_the_loader_keeps_only_what_the_label_rule_admits_without_a_verdict(tmp_path: Path) -> None:
    assert loaded(tmp_path) == ["Prambanan", "Palmyra", "Mesa Verde"]


def test_record_qids_reads_both_keys_the_parsers_write() -> None:
    assert UL.record_qids({"raw_data": {"wikidata_id": "Q1", "wikidata": "Q2"}}) == ["Q1", "Q2"]
    assert UL.record_qids({"raw_data": {"wikidata": None, "osm_id": 5}}) == []
    assert UL.record_qids({}) == []
