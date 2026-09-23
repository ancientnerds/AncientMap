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
    assert US in session.statement_with(
        "FROM unified_sites us\n                LEFT JOIN card_stats"
    )
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


def test_a_whole_sites_export_runs_to_the_end(tmp_path, monkeypatch):
    """End to end over empty tables: every step, the snapshot and the summary. A string in
    the stats once made the summary's number formatting raise after all files were
    written - the job would have reported a failed export that had succeeded."""
    from pipeline.static_exporter import StaticExporter

    session = _exporter_session(monkeypatch)
    StaticExporter(tmp_path).export_all(sites_only=True)
    for produced in ("sources.json", "sites/index.json", "images/index.json", "hubs.snapshot.json"):
        assert (tmp_path / produced).exists(), produced
    manifest = json.loads((tmp_path / "snapshots" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["snapshots"]) == 1
    assert any("FROM unified_sites us" in sql for sql in session.statements())


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
        {
            "FROM remediation_change_log l": [
                SimpleNamespace(
                    country="Syria", name="Damascus Gate", id="17cf019a-0000-4000-8000-000000000000"
                )
            ]
        }
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
    spec = importlib.util.spec_from_file_location(
        "indexnow_submit", REPO / "scripts" / "indexnow_submit.py"
    )
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


def _short_site_row(**kw) -> SimpleNamespace:
    base = {
        "id": "17cf019a-0000-4000-8000-000000000000",
        "name": "Damascus Gate",
        "country": "Syria",
        "lat": 33.51,
        "lon": 36.31,
        "site_type": "Gate/archway/bridge",
        "period_name": "1500+ AD",
        "description": "A gate of the old city.",
        "scope_status": None,
        "scope_reason": None,
        "card_description": "A gate of the old city.",
        "rarity_tier": 4,
        "rarity_score": 0.9,
        "total_power": 30,
        "antiquity": 6,
        "fortification": 7,
        "cultural_influence": 6,
        "mystery": 5,
        "legacy": 6,
        "civilization": "Syria",
        "card_text_sha256": None,  # no card provenance yet: the audit's S13 fails it
    }
    return SimpleNamespace(**{**base, **kw})


def test_a_single_site_short_of_a_retired_site_is_refused():
    """`python -m pipeline.video short --site <id>` bypasses the batch filter; the export
    refuses the site before a single image is read, so no short of it is ever rendered."""
    from pipeline.video import shorts_export

    session = RecordingSession(
        {"FROM unified_sites s": [_short_site_row(scope_status="retired", scope_reason="1537")]}
    )
    with pytest.raises(shorts_export.RetiredSite, match=r"retired \(E4\): 1537"):
        shorts_export.export_site(session, "17cf019a-0000-4000-8000-000000000000")
    assert not any("FROM wiki_images" in sql for sql in session.statements())


def test_a_single_site_short_of_a_shown_site_is_exported():
    from pipeline.video import shorts_export

    session = RecordingSession({"FROM unified_sites s": [_short_site_row()]})
    site = shorts_export.export_site(session, "17cf019a-0000-4000-8000-000000000000")
    assert site["name"] == "Damascus Gate" and site["images"] == []
    assert "s.scope_status" in session.statement_with("FROM unified_sites s")


def test_a_short_by_name_never_resolves_a_retired_site():
    from pipeline.video import shorts_export

    session = RecordingSession()
    with pytest.raises(LookupError, match="not retired"):
        shorts_export.resolve_site_id(session, "Damascus Gate")
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
    session = RecordingSession(
        {
            "scope_status = 'retired'": [
                SimpleNamespace(id="gone"),
                SimpleNamespace(id="never-indexed"),
            ]
        }
    )
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


def test_an_export_without_the_library_leaves_library_files_alone(tmp_path, monkeypatch):
    from pipeline.static_exporter import StaticExporter

    session = _exporter_session(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(StaticExporter, "_export_library", lambda self: calls.append("library"))
    monkeypatch.setattr(StaticExporter, "_export_content", lambda self: None)
    monkeypatch.setattr(StaticExporter, "_export_content_links", lambda self: None)
    StaticExporter(tmp_path).export_all(library=False)
    assert calls == []
    StaticExporter(tmp_path).export_all()
    assert calls == ["library"]
    assert session.statements()


def test_the_cli_flag_reaches_the_export(monkeypatch):
    from pipeline import static_exporter

    seen: list[dict] = []
    monkeypatch.setattr(static_exporter, "build_static", lambda **kw: seen.append(kw))
    monkeypatch.setattr("sys.argv", ["static_exporter", "--no-library"])
    static_exporter.main()
    assert seen[0]["library"] is False


def test_library_refs_to_retired_sites_are_dropped_from_stored_rows():
    """A source cited only by a now-retired site keeps its row but loses the link to
    the page that answers 410; rows the upsert saw this run are rewritten anyway."""
    from pipeline.library_aggregator import LibraryAggregator

    session = RecordingSession()
    LibraryAggregator()._strip_retired_refs(session)
    (sql,) = session.statements()
    assert sql.startswith("WITH retired AS (SELECT id::text AS id FROM unified_sites WHERE ")
    assert is_retired() in sql
    assert "UPDATE library_sources ls" in sql
    assert "e.ref->>'type' = 'site' AND e.ref->>'id' IN (SELECT id FROM retired)" in sql
    assert "DELETE" not in sql.upper()


def test_a_library_refresh_strips_retired_refs_after_its_upsert(monkeypatch):
    """The strip step is part of every refresh, and it runs after the flush: the upsert
    rewrites the parent_refs of the rows it saw, so a strip before it would be undone."""
    from sqlalchemy import text

    from pipeline import library_aggregator as la

    session = RecordingSession()
    monkeypatch.setattr(la, "get_session", lambda: _ctx(session))
    scans: list[str] = []
    for scan in ("_scan_news_items", "_scan_research", "_scan_sites", "_scan_articles"):
        monkeypatch.setattr(
            la.LibraryAggregator, scan, lambda self, s, name=scan: scans.append(name)
        )

    def flush(self, s) -> int:
        s.execute(text("SELECT 'flush marker'"))
        return 3

    monkeypatch.setattr(la.LibraryAggregator, "_flush_to_db", flush)
    assert la.LibraryAggregator().aggregate_all() == 3
    assert scans == ["_scan_news_items", "_scan_research", "_scan_sites", "_scan_articles"]
    flushed, stripped = session.statements()
    assert flushed == "SELECT 'flush marker'"
    assert stripped == la._STRIP_RETIRED_REFS.text


def test_the_research_graph_never_seeds_a_retired_site():
    from pipeline.lyra.graph_injectors import inject_from_sites

    session = RecordingSession()
    inject_from_sites(session)
    assert not_retired("us") in session.statement_with("FROM card_stats cs")


def test_the_full_graph_ingest_creates_no_node_for_a_retired_site():
    """The nightly full ingest wrote every curated site as a node, retired ones included,
    and the public graph serves each with a "Show on globe" link."""
    from pipeline.lyra.graph_full_ingest import _GraphWriter, _ingest_sites

    session = RecordingSession()
    _ingest_sites(_GraphWriter(session))
    sites = session.statement_with("FROM unified_sites")
    assert "source_id = 'ancient_nerds'" in sites
    assert SHOWN in sites


def test_the_frontier_picker_never_picks_the_node_of_a_retired_site():
    """An injector promoted reference site nodes to frontier before any site was retired;
    the pick, not a demotion write, keeps Theo from spending a multi-hour run on one."""
    from pipeline.lyra.research_graph import _pick_frontier

    session = RecordingSession()
    assert _pick_frontier(session, ("site", "topic")) is None
    pick = " ".join(session.statement_with("FOR UPDATE OF n SKIP LOCKED").split())
    assert (
        "AND NOT EXISTS ( SELECT 1 FROM unified_sites us_site "
        f"WHERE us_site.id = n.site_id AND {is_retired('us_site')} )"
    ) in pick


def test_the_spatial_miner_anchors_no_candidate_on_a_retired_site():
    from pipeline.lyra.graph_miner import mine_spatial_cooccurrence

    session = RecordingSession()
    mine_spatial_cooccurrence(session)
    assert not_retired("s") in session.statement_with("JOIN unified_sites s")
