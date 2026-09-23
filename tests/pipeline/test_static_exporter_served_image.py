# SPDX-License-Identifier: AGPL-3.0-only
"""The static export picks a site's image the way every live reader does: never an excluded one.

`sites/index.json` carries one image per site (`im`). Until 2026-09-23 the exporter chose it with
`ORDER BY is_hero DESC, is_lead DESC, sort_order` over *all* of a site's `wiki_images` rows, while
the SSR detail page, the country hub, `/api/wiki-images/{id}` and `images/index.json` all leave
`is_excluded` rows out. Measured on production (design entry 7, "Phase-2 image residue"): 132
curated sites resolved to an excluded row in the export, 130 of them `is_lead` rows - so the next
full export would have put an image a founder or a lane had removed back on the globe.

DB-less: the exporter runs against `tests/fake_sql` (strict about `text()`, records the SQL). The
fake cannot evaluate SQL, so the pick is asserted on the statement itself.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from tests.fake_sql import RecordingSession


class _ctx:
    def __init__(self, session: RecordingSession) -> None:
        self.session = session

    def __enter__(self) -> RecordingSession:
        return self.session

    def __exit__(self, *exc: object) -> bool:
        return False


def _index_statement(tmp_path, monkeypatch, answers=None) -> tuple[RecordingSession, str]:
    from pipeline import static_exporter

    session = RecordingSession(answers)
    monkeypatch.setattr(static_exporter, "get_session", lambda: _ctx(session))
    static_exporter.StaticExporter(tmp_path)._export_site_index()
    return session, session.statement_with("hero_filename")


def _image_pick(sql: str) -> str:
    """The body of the LATERAL subquery that chooses `hero_filename`."""
    match = re.search(r"LEFT JOIN LATERAL \((?P<body>.*?)\) wi ON true", sql, re.S)
    assert match is not None, sql
    return match["body"]


def test_the_exported_site_image_is_never_an_excluded_row(tmp_path, monkeypatch):
    _, sql = _index_statement(tmp_path, monkeypatch)
    body = " ".join(_image_pick(sql).split())
    assert "FROM wiki_images WHERE site_id = us.id AND is_excluded IS NOT TRUE" in body, body
    # ... and among the live rows it is still the served pick: hero first, then lead, then order.
    assert body.endswith("ORDER BY is_hero DESC, is_lead DESC, sort_order LIMIT 1"), body


def test_the_picked_file_becomes_the_sites_local_image_path(tmp_path, monkeypatch):
    """What the pick feeds: `im` is the local file of the chosen row, in the site's shard."""
    row = SimpleNamespace(
        id="abcdef12-0000-4000-8000-000000000001",
        name="Temple",
        lat=1.0,
        lon=2.0,
        source_id="ancient_nerds",
        site_type=None,
        period_start=None,
        period_end=None,
        period_name=None,
        country=None,
        description=None,
        thumbnail_url="/data/images/wiki/abcdef12/hero.webp",
        source_url=None,
        card_description=None,
        best_wiki_url=None,
        source_language=None,
        raw_data=None,
        hero_filename="Temple_gate.webp",
    )
    _index_statement(tmp_path, monkeypatch, {"hero_filename": [row]})
    index = json.loads((tmp_path / "sites" / "index.json").read_text(encoding="utf-8"))
    (site,) = index["sites"]
    assert site["im"] == "/data/images/wiki/abcdef12/Temple_gate.webp"
