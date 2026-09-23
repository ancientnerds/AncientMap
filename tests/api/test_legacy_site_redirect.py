# SPDX-License-Identifier: AGPL-3.0-only
"""/site.html?id={uuid} — die Alt-URL jeder Fundstätte.

Drei Zweige, drei ehrliche Antworten. Bis 12.09.2026 gab es nur zwei: alles
ohne kuratierten Treffer landete per 301 auf /sites/. Das ist eine
Weiterleitung auf eine NICHT gleichwertige Seite — Google wertet so etwas
wie einen Soft 404, und wer den Link zu einer nicht kuratierten Fundstätte
geteilt bekam, sah eine generische Länderliste statt seines Datensatzes.

DB-los im Stil von test_sitemap.py: die Route wird direkt mit einer
Fake-Session aufgerufen.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from api.routes import sites_html as sh

CURATED_ID = "9c8b7a65-4321-4cba-8000-111122223333"
BULK_ID = "b7cd329f-7690-4c88-9676-fa9345aaee91"
UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def _db(curated: SimpleNamespace | None, exists: bool) -> MagicMock:
    """First execute(): the curated row. Second: whether the id exists at all, with its
    scope_status."""
    db = MagicMock()
    db.execute.return_value.fetchone.side_effect = [
        curated,
        SimpleNamespace(scope_status=None) if exists else None,
    ]
    return db


def _call(db: MagicMock, site_id: str):
    return asyncio.run(sh.legacy_site_redirect(id=site_id, db=db))


def test_kuratierte_site_geht_301_auf_ihre_detailseite():
    row = SimpleNamespace(name="Göbekli Tepe", country="Türkiye")
    resp = _call(_db(row, exists=True), CURATED_ID)
    assert resp.status_code == 301
    # Prozentkodiert: der Slug trägt Nicht-ASCII (encode_path).
    assert resp.headers["location"] == "/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65"


def test_nicht_kuratierte_site_geht_auf_den_globus_statt_auf_die_laenderliste():
    """Die Fundstätte existiert, hat aber keine Detailseite — der Globus ist
    der Ort, an dem sie tatsächlich zu sehen ist. Die Fragment-Form erzeugt
    keine zweite crawlbare URL."""
    resp = _call(_db(None, exists=True), BULK_ID)
    assert resp.status_code == 301
    assert resp.headers["location"] == f"/globe.html#focus={BULK_ID}"
    assert "/sites/" not in resp.headers["location"]


def test_unbekannte_id_ist_404_keine_weiterleitung():
    resp = _call(_db(None, exists=False), UNKNOWN_ID)
    assert resp.status_code == 404
    assert "location" not in resp.headers


def test_fehlende_id_ist_404():
    """?id= leer: früher eine 301 auf /sites/, also ein erfundenes Ziel."""
    db = MagicMock()
    resp = _call(db, "")
    assert resp.status_code == 404
    db.execute.assert_not_called()


def _detail(curated, uncurated_id: str | None) -> MagicMock:
    db = MagicMock()
    uncurated = SimpleNamespace(id=uncurated_id, scope_status=None) if uncurated_id else None
    db.execute.return_value.fetchone.side_effect = [curated, uncurated]
    return db


def test_detailseite_einer_nicht_kuratierten_site_geht_auf_den_globus():
    """/sites/jordan/tell-el-hammam-b7cd329f: die Fundstätte liegt in der DB
    (wikidata), hat aber keine Detailseite. Bis 12.09.2026 ein 404 auf einen
    existierenden Datensatz."""
    db = _detail(None, BULK_ID)
    resp = asyncio.run(sh.site_detail(country="jordan", slug="tell-el-hammam-b7cd329f", db=db))
    assert resp.status_code == 301
    assert resp.headers["location"] == f"/globe.html#focus={BULK_ID}"


def test_detailseite_ohne_jeden_treffer_bleibt_404():
    db = _detail(None, None)
    resp = asyncio.run(sh.site_detail(country="jordan", slug="erfunden-deadbeef", db=db))
    assert resp.status_code == 404


def test_praefixsuche_nutzt_einen_uuid_bereich_keinen_ausdruck():
    """Die Suche läuft über 1,7 Mio. Zeilen und ist von aussen auslösbar —
    als Ausdruck auf id::text wäre sie ein Seq-Scan pro 404."""
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    sh._site_by_prefix("b7cd329f", db)
    sql = str(db.execute.call_args[0][0])
    params = db.execute.call_args[0][1]
    assert "LEFT(REPLACE" not in sql
    assert "id >=" in sql and "id <=" in sql
    assert params["lo"] == "b7cd329f-0000-0000-0000-000000000000"
    assert params["hi"] == "b7cd329f-ffff-ffff-ffff-ffffffffffff"


def test_utm_parameter_ueberleben_die_weiterleitung():
    row = SimpleNamespace(name="Göbekli Tepe", country="Türkiye")
    resp = asyncio.run(
        sh.legacy_site_redirect(
            id=CURATED_ID, utm_source="discord", utm_medium="bot", db=_db(row, exists=True)
        )
    )
    assert resp.headers["location"] == (
        "/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65?utm_source=discord&utm_medium=bot"
    )
    resp = asyncio.run(
        sh.legacy_site_redirect(id=BULK_ID, utm_source="discord", db=_db(None, exists=True))
    )
    assert resp.headers["location"] == f"/globe.html?utm_source=discord#focus={BULK_ID}"
