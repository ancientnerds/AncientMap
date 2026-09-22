# SPDX-License-Identifier: AGPL-3.0-only
"""E4 (migration 0020) in the pipeline consumers: static export, IndexNow, library, the
Qdrant site index and the shorts batch - plus the Qdrant change detection and the library
scan's query shape.

DB-less: every consumer runs against tests/fake_sql (strict about text(), records the SQL).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.utils.public_sites import is_retired, not_retired
from tests.fake_sql import OrmSession, RecordingSession

REPO = Path(__file__).resolve().parents[2]
SHOWN = not_retired()
US = not_retired("us")
U = not_retired("u")


class _ctx:
    """get_session() stand-in yielding one fake session."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


# --------------------------------------------------------------------------------------
# static export
# --------------------------------------------------------------------------------------


def _exporter_session(monkeypatch, answers=None) -> RecordingSession:
    from pipeline import static_exporter

    session = RecordingSession(answers)
    monkeypatch.setattr(static_exporter, "get_session", lambda: _ctx(session))
    return session


def test_hub_rows_count_only_shown_sites():
    from pipeline.static_exporter import fetch_hub_rows

    session = RecordingSession()
    fetch_hub_rows(session)
    assert SHOWN in session.statement_with("GROUP BY country")


def test_site_index_and_alt_names_leave_retired_sites_out(tmp_path, monkeypatch):
    from pipeline.static_exporter import StaticExporter

    session = _exporter_session(monkeypatch)
    StaticExporter(tmp_path)._export_site_index()
    assert US in session.statement_with("FROM unified_sites us\n                LEFT JOIN card_stats")
    assert US in session.statement_with("FROM unified_site_names usn")


def test_site_details_leave_retired_sites_out(tmp_path, monkeypatch):
    from pipeline.static_exporter import REGIONS, StaticExporter

    session = _exporter_session(monkeypatch)
    StaticExporter(tmp_path)._export_site_details()
    regional = [sql for sql in session.statements() if "lat BETWEEN :min_lat" in sql]
    assert len(regional) == len(REGIONS)
    for sql in regional:
        assert SHOWN in sql


def test_image_index_and_content_links_leave_retired_sites_out(tmp_path, monkeypatch):
    from pipeline.static_exporter import StaticExporter

    session = _exporter_session(monkeypatch)
    exporter = StaticExporter(tmp_path)
    exporter._export_wiki_images()
    exporter._export_content_links()
    for fragment in ("FROM wiki_images", "FROM site_content_links"):
        sql = session.statement_with(fragment)
        assert "NOT EXISTS" in sql and is_retired("us") in sql, fragment


def _snapshot_row(site_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=site_id,
        name=name,
        lat=1.0,
        lon=2.0,
        source_id="ancient_nerds",
        site_type=None,
        period_start=None,
        period_end=None,
        period_name=None,
        country="Peru",
        description=None,
        thumbnail_url=None,
        source_url=None,
        edited_by="initial",
        created_at=datetime(2026, 1, 1),
        hero_url=None,
        hero_attribution_url=None,
        reference_links=[],
    )


def test_file_snapshot_leaves_retired_sites_out_and_writes_the_manifest(tmp_path):
    from pipeline.static_exporter import write_file_snapshot

    session = RecordingSession({"FROM unified_sites us": [_snapshot_row("a", "Machu Picchu")]})
    key = write_file_snapshot(session, tmp_path)
    assert US in session.statement_with("FROM unified_sites us")
    data = json.loads((tmp_path / f"{key}.json").read_text(encoding="utf-8"))
    assert [s["n"] for s in data["sites"]] == ["Machu Picchu"]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [e["date"] for e in manifest["snapshots"]] == [key]


def test_two_snapshots_in_one_second_leave_one_manifest_entry(tmp_path):
    """The old rebuild-static wrote two snapshots back to back; same key, two entries."""
    from pipeline import static_exporter

    fixed = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    session = RecordingSession({"FROM unified_sites us": [_snapshot_row("a", "X")]})
    with patch.object(static_exporter, "datetime", _Frozen):
        static_exporter.write_file_snapshot(session, tmp_path)
        static_exporter.write_file_snapshot(session, tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [e["date"] for e in manifest["snapshots"]] == ["2026-09-22_120000"]


def test_snapshot_retention_prunes_files_and_entries(tmp_path, monkeypatch):
    from pipeline import static_exporter

    monkeypatch.setattr(static_exporter, "MAX_FILE_SNAPSHOTS", 2)
    old = [{"date": f"2026-01-0{i}_000000", "file": f"2026-01-0{i}_000000.json"} for i in (1, 2)]
    for entry in old:
        (tmp_path / entry["file"]).write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"snapshots": old}), encoding="utf-8")
    session = RecordingSession({"FROM unified_sites us": [_snapshot_row("a", "X")]})
    key = static_exporter.write_file_snapshot(session, tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [e["date"] for e in manifest["snapshots"]] == [key, "2026-01-02_000000"]
    assert not (tmp_path / "2026-01-01_000000.json").exists()


def test_a_corrupt_manifest_raises_instead_of_dropping_the_history(tmp_path):
    from pipeline.static_exporter import write_file_snapshot

    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        write_file_snapshot(RecordingSession(), tmp_path)


# --------------------------------------------------------------------------------------
# IndexNow
# --------------------------------------------------------------------------------------


def test_indexnow_announces_shown_sites_changed_by_the_journal():
    from pipeline import indexnow as ix

    sql = ix._CHANGED_SITES_SQL.text
    assert U in sql
    assert "jlast.applied_at" in sql and ">= :since" in sql


def test_indexnow_announces_retirements_as_removed_urls():
    from pipeline import indexnow as ix

    session = RecordingSession(
        {"FROM remediation_change_log l": [SimpleNamespace(country="Syria", name="Damascus Gate", id="17cf019a-0000-4000-8000-000000000000")]}
    )
    paths = ix.recent_retired_paths(session, datetime(2026, 9, 22, tzinfo=UTC))
    assert paths == ["/sites/syria/damascus-gate-17cf019a", "/sites/"]
    sql = session.statement_with("FROM remediation_change_log l")
    assert "l.column_name = 'scope_status'" in sql and "l.new_value = 'retired'" in sql
    assert is_retired("u") in sql  # still retired now, not un-retired since
    # joined on the indexed uuid; a CAST of row_pk would fail on wiki_images' integer keys
    assert "u.id = l.site_id_ref" in sql and "CAST(l.row_pk" not in sql


def test_submit_recent_sends_changed_and_retired_pages(monkeypatch):
    from pipeline import indexnow as ix

    monkeypatch.setattr(ix, "get_session", lambda: _ctx(RecordingSession()))
    monkeypatch.setattr(ix, "recent_public_paths", lambda s, since: ["/sites/peru/x-1"])
    monkeypatch.setattr(ix, "recent_retired_paths", lambda s, since: ["/sites/syria/y-2"])
    with patch.object(ix, "submit") as submit:
        assert ix.submit_recent() == 2
    assert list(submit.call_args.args[0]) == [
        "https://ancientnerds.com/sites/peru/x-1",
        "https://ancientnerds.com/sites/syria/y-2",
    ]


def test_indexnow_catch_up_script_keeps_only_pages_changed_since_a_date():
    spec = importlib.util.spec_from_file_location("indexnow_submit", REPO / "scripts" / "indexnow_submit.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ancientnerds.com/sites/a</loc><lastmod>2026-09-21</lastmod></url>
  <url><loc>https://ancientnerds.com/sites/b</loc><lastmod>2026-09-12</lastmod></url>
  <url><loc>https://ancientnerds.com/sites/c</loc></url>
</urlset>"""
    from datetime import date

    assert module.part_urls(xml) == [f"https://ancientnerds.com/sites/{x}" for x in "abc"]
    assert module.part_urls(xml, date(2026, 9, 20)) == ["https://ancientnerds.com/sites/a"]


# --------------------------------------------------------------------------------------
# library aggregator: the site scan's shape and speed
# --------------------------------------------------------------------------------------


def test_library_site_scan_filters_in_sql_and_reads_only_the_citations():
    """112 s -> 0.65 s: the old scan materialised 1,736,055 full ORM rows to find 2,217."""
    from pipeline.library_aggregator import LibraryAggregator

    session = OrmSession(
        [
            [
                SimpleNamespace(
                    id="5281654c-0000-4000-8000-000000000000",
                    name="Borremose",
                    country="Denmark",
                    source_id="ancient_nerds",
                    period_name="500 BC - 1 AD",
                    citations=[{"url": "https://example.org/a", "title": "A"}],
                )
            ]
        ]
    )
    agg = LibraryAggregator()
    agg._scan_sites(session)
    (sql,) = session.sql
    assert "unified_sites.raw_data ? 'description_citations'" in sql
    assert "unified_sites.scope_status IS DISTINCT FROM 'retired'" in sql
    # only the citations leave the database, not the whole raw_data document
    select_list = sql.split("FROM unified_sites")[0]
    # PostgreSQL 14+ subscript (production runs 16.4) or the arrow form - both are the key only
    assert (
        "raw_data['description_citations'] AS citations" in select_list
        or "raw_data -> 'description_citations' AS citations" in select_list
    )
    assert "unified_sites.raw_data," not in select_list
    assert agg.stats["sites"] == 1
    (row,) = agg.pending.values()
    assert row["parent_refs"][0]["path"] == "/sites/denmark/borremose-5281654c"


def test_library_flush_is_one_upsert_per_chunk_not_per_source(monkeypatch):
    from pipeline import library_aggregator as la

    agg = la.LibraryAggregator()
    for n in range(7):
        agg._register(
            url=f"https://example.org/{n}",
            title="t",
            snippet="",
            source_type="site",
            period_name=None,
            parent_type="site",
            parent_id=str(n),
            parent_title="p",
            parent_path=None,
        )
    monkeypatch.setattr(la, "_FLUSH_CHUNK", 3)
    session = RecordingSession()
    session.flush = lambda: None
    session.query = lambda *a: SimpleNamespace(count=lambda: 7)
    agg._flush_to_db(session)
    upserts = [sql for sql in session.statements() if "INSERT INTO library_sources" in sql]
    assert len(upserts) == 3  # 3 + 3 + 1 rows
    assert all("ON CONFLICT (id) DO UPDATE" in sql for sql in upserts)


# --------------------------------------------------------------------------------------
# shorts batch
# --------------------------------------------------------------------------------------


def test_shorts_batch_never_plans_a_retired_site(monkeypatch):
    from pipeline.video import __main__ as video

    session = RecordingSession()
    monkeypatch.setattr(video, "get_session", lambda: _ctx(session))
    video.batch_candidates(4, 10)
    assert not_retired("s") in session.statement_with("FROM unified_sites s")


# --------------------------------------------------------------------------------------
# Qdrant site index (scripts/build_lyra_index.py)
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lyra_index():
    """Import the script without its load_dotenv(): tests never read the .env."""
    spec = importlib.util.spec_from_file_location(
        "build_lyra_index_under_test", REPO / "scripts" / "build_lyra_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    with patch("dotenv.load_dotenv", return_value=False):
        spec.loader.exec_module(module)
    return module


def _site(**kw) -> SimpleNamespace:
    base = {
        "id": "17cf019a-0000-4000-8000-000000000000",
        "name": "Damascus Gate",
        "site_type": "Gate/archway/bridge",
        "period_name": "1500+ AD",
        "period_start": 1537,
        "country": "Syria",
        "description": "A gate of the old city.",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_content_hash_formula_is_unchanged(lyra_index):
    """Changing it would re-embed all ~145,000 points through Voyage."""
    r = _site()
    assert lyra_index._site_hash_input(r) == (
        "Damascus Gate|Gate/archway/bridge|1500+ AD|Syria|A gate of the old city."
    )


def test_a_period_only_correction_makes_the_point_stale(lyra_index):
    r = _site(period_start=1537)
    h = lyra_index._content_hash(lyra_index._site_hash_input(r))
    assert lyra_index.site_is_stale(r, {"content_hash": h, "period_start": 1}, h)
    assert not lyra_index.site_is_stale(r, {"content_hash": h, "period_start": 1537}, h)


def test_new_and_hash_changed_points_are_stale(lyra_index):
    r = _site()
    h = lyra_index._content_hash(lyra_index._site_hash_input(r))
    assert lyra_index.site_is_stale(r, None, h)
    assert lyra_index.site_is_stale(r, {"content_hash": "old", "period_start": 1537}, h)


def test_a_point_without_a_date_matches_a_site_without_a_date(lyra_index):
    """127,184 indexed sites have no period_start; they must not all re-embed."""
    r = _site(period_start=None)
    h = lyra_index._content_hash(lyra_index._site_hash_input(r))
    assert not lyra_index.site_is_stale(r, {"content_hash": h}, h)


def test_retired_points_are_deleted_and_only_those(lyra_index, monkeypatch):
    session = RecordingSession({"scope_status = 'retired'": [SimpleNamespace(id="gone"), SimpleNamespace(id="never-indexed")]})
    monkeypatch.setattr(lyra_index, "get_session", lambda: _ctx(session))
    deleted: list[list[str]] = []
    client = SimpleNamespace(
        delete=lambda collection_name, points_selector: deleted.append(points_selector.points)
    )
    assert lyra_index.delete_retired_points(client, "sites", {"gone", "kept"}) == 1
    assert deleted == [["gone"]]


def test_index_sites_reads_only_shown_sites_and_deletes_retired_points(lyra_index, monkeypatch):
    session = RecordingSession()
    monkeypatch.setattr(lyra_index, "get_session", lambda: _ctx(session))
    monkeypatch.setattr(lyra_index, "ensure_collection", lambda *a: None)
    monkeypatch.setattr(lyra_index, "create_payload_indexes", lambda *a: None)
    monkeypatch.setattr(lyra_index, "get_existing_payloads", lambda *a: {})
    calls: list[str] = []
    monkeypatch.setattr(lyra_index, "delete_retired_points", lambda *a: calls.append("delete") or 0)
    lyra_index.index_sites(client=None, embeddings=None, sparse_model=None)
    assert calls == ["delete"]
    assert US in session.statement_with("FROM unified_sites us")
