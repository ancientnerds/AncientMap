# SPDX-License-Identifier: AGPL-3.0-only
"""scripts/remediation/static_export_check.py: is the served index.json the database's state?

D25 (2026-10-08): the globe popup shows `d` (the first 500 characters of the description) and `cd`
(the card text) from public/data/sites/index.json, so after a wave the file must carry exactly the
database's texts. The check runs inside the API container; these tests give it a fake session and
an in-memory index, and compute the expected hashes the way Postgres does (sha256 of the UTF-8
bytes of left(text, 500)).
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.fake_sql import RecordingSession

REPO = Path(__file__).resolve().parents[2]
REMEDIATION = REPO / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

import static_export_check as SEC  # noqa: E402

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
C = "33333333-3333-3333-3333-333333333333"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_file(sites: list[dict], **overrides) -> io.StringIO:
    doc = {
        "sites": sites,
        "count": len(sites),
        "by_source": {},
        "exported_at": "2026-10-08T05:00:00+00:00",
    }
    doc.update(overrides)
    return io.StringIO(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))


def db_row(site_id: str, description: str = "", card: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=site_id, dh=sha(description[:500]), ch=sha(card))


def session(rows: list[SimpleNamespace], shown: int | None = None) -> RecordingSession:
    return RecordingSession({"ANY(": rows, "count(*)": [(len(rows) if shown is None else shown,)]})


def test_a_matching_index_has_no_difference():
    long = "é" * 700
    sites = [{"i": A, "d": long[:500], "cd": "Card ✓"}, {"i": B}]
    db = session([db_row(A, long, "Card ✓"), db_row(B)])
    report = SEC.check(index_file(sites), db)
    assert report.differing == 0
    assert report.sites == 2


def test_a_changed_description_is_counted_once():
    sites = [{"i": A, "d": "old sentence"}, {"i": B, "d": "same"}]
    db = session([db_row(A, "new sentence"), db_row(B, "same")])
    report = SEC.check(index_file(sites), db)
    assert report.differing == 1
    assert report.description == [A]
    assert report.card == []


def test_a_changed_card_text_is_counted():
    sites = [{"i": A, "cd": "old card"}, {"i": B}]
    db = session([db_row(A, card="new card"), db_row(B, card="a card the file lacks")])
    report = SEC.check(index_file(sites), db)
    assert sorted(report.card) == [A, B]
    assert report.differing == 2


def test_the_description_is_compared_at_500_characters():
    """The file carries description[:500]; a longer database text is not a difference."""
    db = session([db_row(A, "x" * 900)])
    assert SEC.check(index_file([{"i": A, "d": "x" * 500}]), db).differing == 0
    assert SEC.check(index_file([{"i": A, "d": "x" * 900}]), db).differing == 1


def test_a_site_only_in_the_file_or_only_in_the_database_is_a_difference():
    sites = [{"i": A}, {"i": C}]  # C was retired after the export
    db = session([db_row(A)], shown=2)  # B is shown but missing from the file
    report = SEC.check(index_file(sites), db)
    assert report.only_in_file == [C]
    assert report.shown_missing_from_file == 1
    assert report.differing == 2


def test_a_duplicate_id_in_the_file_is_a_difference():
    sites = [{"i": A}, {"i": A}]
    report = SEC.check(index_file(sites), session([db_row(A)], shown=1))
    assert report.duplicates == [A]
    assert report.differing == 1


def test_a_truncated_file_is_refused_not_compared():
    text = index_file([{"i": A, "d": "x"}, {"i": B, "d": "y"}]).getvalue()
    with pytest.raises(SEC.IndexFileError, match="ends inside"):
        SEC.check(io.StringIO(text[: len(text) // 2]), session([db_row(A), db_row(B)]))


def test_a_declared_count_that_differs_from_the_sites_is_refused():
    with pytest.raises(SEC.IndexFileError, match="count"):
        SEC.check(index_file([{"i": A}], count=2), session([db_row(A)]))


def test_the_reader_streams_across_chunk_borders():
    sites = [{"i": f"{n:08d}-0000-0000-0000-000000000000", "d": "ü" * 40} for n in range(300)]
    seen = [s["i"] for s in SEC.read_sites(index_file(sites), chunk_size=64)]
    assert seen == [s["i"] for s in sites]


def test_the_lookup_uses_the_exporters_shown_predicate_and_reads_only():
    db = session([db_row(A)])
    SEC.check(index_file([{"i": A}]), db)
    lookup = db.statement_with("ANY(")
    assert "sha256(convert_to(left(" in lookup and "500" in lookup
    assert "retired" in lookup.lower() or "scope_status" in lookup
    assert db.statements()[0].strip().upper().startswith("SET TRANSACTION READ ONLY")


def test_main_exits_1_when_the_files_differ_and_0_when_not(tmp_path, monkeypatch, capsys):
    path = tmp_path / "index.json"
    path.write_text(index_file([{"i": A, "d": "old"}]).getvalue(), encoding="utf-8")
    monkeypatch.setattr(SEC, "get_session", lambda: session([db_row(A, "new")]))
    assert SEC.main(["--index", str(path)]) == 1
    assert "differing sites: 1" in capsys.readouterr().out
    monkeypatch.setattr(SEC, "get_session", lambda: session([db_row(A, "old")]))
    assert SEC.main(["--index", str(path)]) == 0
    assert "differing sites: 0" in capsys.readouterr().out
