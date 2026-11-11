# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/indexnow.py — Schluesseldatei, Payload, Chunking, Pfadbildung.

DB-los: submit() wird gegen ein gepatchtes httpx.post geprueft, die
Pfadbildung ist eine reine Funktion.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import indexnow as ix
from pipeline.utils.public_sites import D57_STAGED_PREFIX, D57_UNDONE_PREFIX


def test_schluesseldatei_liegt_im_frontend_public_und_traegt_den_schluessel():
    assert ix.KEY_FILE.name == f"{ix.INDEXNOW_KEY}.txt"
    assert ix.KEY_FILE.read_text(encoding="utf-8").strip() == ix.INDEXNOW_KEY
    assert len(ix.INDEXNOW_KEY) == 32


def _response(status: int) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, text="")


def test_submit_schickt_host_key_keylocation_und_dedupliziert():
    with patch.object(ix.httpx, "post", return_value=_response(202)) as post:
        ok = ix.submit(
            [
                "https://ancientnerds.com/a",
                "",
                "https://ancientnerds.com/a",
                "https://ancientnerds.com/b",
            ]
        )
    assert ok is True
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert payload["host"] == "ancientnerds.com"
    assert payload["key"] == ix.INDEXNOW_KEY
    assert payload["keyLocation"] == f"https://ancientnerds.com/{ix.INDEXNOW_KEY}.txt"
    assert payload["urlList"] == ["https://ancientnerds.com/a", "https://ancientnerds.com/b"]
    assert post.call_args.args[0] == ix.ENDPOINT


def test_submit_teilt_in_chunks_und_meldet_ablehnung_ohne_zu_werfen():
    urls = [f"https://ancientnerds.com/{n}" for n in range(5)]
    with (
        patch.object(ix, "CHUNK", 2),
        patch.object(
            ix.httpx, "post", side_effect=[_response(200), _response(422), _response(200)]
        ) as post,
    ):
        ok = ix.submit(urls)
    assert ok is False
    assert post.call_count == 3
    assert [len(c.kwargs["json"]["urlList"]) for c in post.call_args_list] == [2, 2, 1]


def test_submit_ueberlebt_netzfehler_und_leere_listen():
    with patch.object(ix.httpx, "post", side_effect=OSError("down")) as post:
        assert ix.submit(["https://ancientnerds.com/x"]) is False
    post.assert_called_once()
    with patch.object(ix.httpx, "post") as post:
        assert ix.submit([]) is True
    post.assert_not_called()


def test_pfade_je_gruppe_mit_hub_und_kodierung():
    paths = ix.paths_for(
        stories=[(4711, "Göbekli Tepe: new enclosure found")],
        papers=["the-egyptian-hard-stone-precision-debate"],
        journals=[],
        sites=[("Türkiye", "Göbekli Tepe", "9c8b7a65-4321-4cba-8000-111122223333")],
    )
    assert paths == [
        f"/news-archive/{ix.story_slug('Göbekli Tepe: new enclosure found', 4711)}",
        "/news-archive/",
        "/research/the-egyptian-hard-stone-precision-debate",
        "/research/",
        "/sites/türkiye/göbekli-tepe-9c8b7a65",
        "/sites/",
    ]
    assert ix.page_url("/sites/türkiye/göbekli-tepe-9c8b7a65") == (
        "https://ancientnerds.com/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65"
    )


def test_nichts_geaendert_ergibt_keine_pfade():
    assert ix.paths_for([], [], [], []) == []


# --------------------------------------------------- entfernte Seiten (E4) und der D57-Insert (O12)
SINCE = "2026-11-11 10:00:00"
IN_WINDOW, BEFORE = "2026-11-11 11:00:00", "2026-11-11 09:00:00"
STAGED = f"{D57_STAGED_PREFIX} inserted hidden by the insert lane"
UNDONE = f"{D57_UNDONE_PREFIX} (x-rollback): retired, never deleted"


def _retired(sites, journal) -> set[str]:
    """Die Sites, die ``_RETIRED_SITES_SQL`` als entfernte Seiten meldet. ``sites``: (id, status,
    reason[, source, country]); ``journal``: (site, column, old, new, applied_at)."""
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA case_sensitive_like = ON")  # Postgres' LIKE unterscheidet Gross und Klein
    db.execute(
        "CREATE TABLE unified_sites (id TEXT, name TEXT, source_id TEXT, country TEXT, "
        "scope_status TEXT, scope_reason TEXT)"
    )
    db.execute(
        "CREATE TABLE remediation_change_log (table_name TEXT, column_name TEXT, row_pk TEXT, "
        "site_id_ref TEXT, old_value TEXT, new_value TEXT, applied_at TEXT)"
    )
    for sid, status, reason, *rest in sites:
        source, country = rest or ("ancient_nerds", "Greece")
        db.execute(
            "INSERT INTO unified_sites VALUES (?, ?, ?, ?, ?, ?)",
            (sid, sid, source, country, status, reason),
        )
    db.executemany(
        "INSERT INTO remediation_change_log VALUES ('unified_sites', ?, ?, ?, ?, ?, ?)",
        [(column, sid, sid, old, new, at) for sid, column, old, new, at in journal],
    )
    return {row[2] for row in db.execute(ix._RETIRED_SITES_SQL.text, {"since": SINCE})}


def _status(sid: str, old: str | None, new: str, at: str = IN_WINDOW):
    return (sid, "scope_status", old, new, at)


def test_ein_zurueckgezogener_kurierter_ort_wird_als_entfernte_seite_gemeldet():
    sites = [
        ("e4", "retired", "E3: period_start 900 is 400 years past the cutoff"),
        ("nie-bewertet", "retired", None),  # status NULL -> retired, ohne Grund: das NULL-Loch
        ("alt", "retired", "E3: ..."),
        ("wieder-da", "in_scope", "D58 label rule ..."),
        ("fremd", "retired", "x", "osm", "Greece"),
        ("ohne-land", "retired", "x", "ancient_nerds", None),
        ("anderes-feld", "retired", "x"),
    ]
    journal = [
        _status("e4", "in_scope", "retired"),
        _status("nie-bewertet", None, "retired"),
        _status("alt", None, "retired", BEFORE),
        _status("wieder-da", None, "retired"),
        _status("fremd", None, "retired"),
        _status("ohne-land", None, "retired"),
        ("anderes-feld", "scope_reason", None, "retired", IN_WINDOW),
    ]
    assert _retired(sites, journal) == {"e4", "nie-bewertet"}


def test_ein_versteckt_angelegter_d57_ort_ist_keine_entfernte_seite():
    """O12: der Insert legt den Ort als 'retired' an (old_value NULL). Er hatte nie eine Seite -
    solange er gestaged ist und auch, wenn der Insert zurueckgenommen wurde."""
    sites = [("gestaged", "retired", STAGED), ("zurueckgenommen", "retired", UNDONE)]
    journal = [_status("gestaged", None, "retired"), _status("zurueckgenommen", None, "retired")]
    assert _retired(sites, journal) == set()
    assert ix._RETIRED_SITES_SQL.text.count(f"LIKE '{D57_STAGED_PREFIX}%'") == 1
    assert ix._RETIRED_SITES_SQL.text.count(f"LIKE '{D57_UNDONE_PREFIX}%'") == 1


def test_ein_gezeigter_und_wieder_versteckter_d57_ort_wird_gemeldet():
    """Der Rollback des Un-Retire schreibt 'in_scope' -> 'retired' und den Staged-Grund zurueck:
    die Seite gab es, also wird sie gemeldet - auch wenn die Anlage-Zeile im Fenster liegt."""
    sites = [("gezeigt-gewesen", "retired", STAGED), ("dann-zurueckgenommen", "retired", UNDONE)]
    journal = [
        _status("gezeigt-gewesen", None, "retired"),
        _status("gezeigt-gewesen", "retired", "in_scope"),
        _status("gezeigt-gewesen", "in_scope", "retired"),
        _status("dann-zurueckgenommen", None, "retired", BEFORE),
        _status("dann-zurueckgenommen", "in_scope", "retired"),
    ]
    assert _retired(sites, journal) == {"gezeigt-gewesen", "dann-zurueckgenommen"}
