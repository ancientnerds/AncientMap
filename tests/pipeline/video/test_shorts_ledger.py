# SPDX-License-Identifier: AGPL-3.0-only
"""The site_shorts render ledger: migration 0021, the writer in the render step, and the
backfill of the renders made before the ledger existed (plan 10.4).

The fixtures are built in tmp_path with the shapes the render step writes (site.json,
selection.json, render/timeline.json, the mp4); the 16 real renders live only on the
workstation, gitignored.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pipeline.video import shorts_ledger
from tests.fake_sql import FakeResult, RecordingSession

REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / "migrations" / "0021_site_shorts_ledger.sql"
JAHANGIR = "50e5e380-1f89-4fa3-88de-e6ad35241316"
ISHTAR = "15f3ae9f-86e9-4198-97c9-e67b42c034dc"
RENDERED = {"status": "rendered", "status_reason": None}


class ScopeSession(RecordingSession):
    """RecordingSession whose scope lookup answers per site id, as the database does."""

    def __init__(self, scopes: dict[str, tuple[str | None, str | None]]) -> None:
        super().__init__({"INSERT INTO site_shorts": [object()]})
        self.scopes = scopes

    def execute(self, stmt, params=None):
        result = super().execute(stmt, params)
        if stmt is shorts_ledger._SCOPE_SQL:
            scope = self.scopes.get(params["site_id"])
            if scope is None:
                return FakeResult([])
            return FakeResult([SimpleNamespace(scope_status=scope[0], scope_reason=scope[1])])
        return result


class _ctx:
    """get_session() stand-in yielding one fake session."""

    def __init__(self, session) -> None:
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def _render_dir(
    root: Path, slug: str, *, period: str = "1500 - 500 BC", site_id: str | None = None
) -> Path:
    """A site directory as the render step leaves it."""
    site_dir = root / slug
    (site_dir / "render").mkdir(parents=True)
    site = {
        "id": site_id or ISHTAR,
        "name": slug.replace("-", " ").title(),
        "slug": slug,
        "period_name": period,
        "card_text": "A glazed-brick gate of Babylon, rebuilt by Nebuchadnezzar II.",
    }
    (site_dir / "site.json").write_text(json.dumps(site), encoding="utf-8")
    stills = [
        {"id": 11, "local_path": str(site_dir / "images" / "a.jpg")},
        {"id": 22, "local_path": str(site_dir / "images" / "b.jpg")},
        {"id": 33, "local_path": str(site_dir / "images" / "never-shown.jpg")},
    ]
    (site_dir / "selection.json").write_text(json.dumps({"stills": stills}), encoding="utf-8")
    timeline = [
        {"kind": "clip", "source": str(site_dir / "clips" / "short-opening.mp4")},
        {"kind": "still", "source": stills[1]["local_path"]},
        {"kind": "still", "source": stills[0]["local_path"]},
        {"kind": "still", "source": stills[1]["local_path"]},
        {"kind": "return", "source": str(site_dir / "clips" / "short-return.mp4")},
    ]
    (site_dir / "render" / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (site_dir / f"{slug}.mp4").write_bytes(b"not really an mp4 " + slug.encode())
    (site_dir / "description.txt").write_text(
        "...\n\nNarration: AI-generated voice (MiniMax speech-2.8-hd, English_expressive_narrator).\n",
        encoding="utf-8",
    )
    return site_dir


# --------------------------------------------------------------------------------------
# migration 0021
# --------------------------------------------------------------------------------------


def test_the_migration_enforces_the_module_vocabulary():
    sql = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r"status IN \(([^)]*)\)", sql)
    assert match is not None
    assert {t.strip().strip("'") for t in match.group(1).split(",")} == set(shorts_ledger.STATUSES)


def test_the_migration_keys_by_site_and_file_and_keeps_rows_when_a_site_goes():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "site_id              UUID REFERENCES unified_sites (id) ON DELETE SET NULL" in sql
    assert "CONSTRAINT site_shorts_video_unique UNIQUE (video_sha256)" in sql
    assert "status <> 'published' OR (youtube_id IS NOT NULL AND published_at IS NOT NULL)" in sql
    assert "status <> 'withdrawn' OR status_reason IS NOT NULL" in sql
    assert "CASCADE" not in sql


# --------------------------------------------------------------------------------------
# the row
# --------------------------------------------------------------------------------------


def test_image_ids_are_the_stills_on_screen_in_order(tmp_path):
    site_dir = _render_dir(tmp_path, "ishtar-gate")
    assert shorts_ledger.used_image_ids(site_dir) == [22, 11]  # 33 was selected, never shown


def test_a_still_the_selection_does_not_know_raises(tmp_path):
    site_dir = _render_dir(tmp_path, "ishtar-gate")
    timeline = json.loads((site_dir / "render" / "timeline.json").read_text(encoding="utf-8"))
    timeline.append({"kind": "still", "source": "C:/elsewhere/x.jpg"})
    (site_dir / "render" / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    with pytest.raises(LookupError):
        shorts_ledger.used_image_ids(site_dir)


def test_the_row_hashes_the_text_and_the_file(tmp_path):
    site_dir = _render_dir(tmp_path, "ishtar-gate")
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    video = site_dir / "ishtar-gate.mp4"
    when = datetime(2026, 9, 17, 22, 11, tzinfo=UTC)
    row = shorts_ledger.row_for_render(
        site, site_dir, video, voice_id="v", pipeline_commit="abc", rendered_at=when, **RENDERED
    )
    assert row.site_id == site["id"] and row.slug == "ishtar-gate"
    assert row.card_text_sha256 == hashlib.sha256(site["card_text"].encode()).hexdigest()
    assert row.video_sha256 == hashlib.sha256(video.read_bytes()).hexdigest()
    assert (row.status, row.status_reason) == ("rendered", None)


def test_a_retired_site_enters_the_ledger_withdrawn_with_its_scope_reason():
    session = ScopeSession({JAHANGIR: ("retired", "dated 1627, past the E3 window")})
    assert shorts_ledger.status_for(session, JAHANGIR) == (
        "withdrawn",
        "site retired (E4): dated 1627, past the E3 window",
    )
    session = ScopeSession({JAHANGIR: ("retired", None)})
    assert shorts_ledger.status_for(session, JAHANGIR) == ("withdrawn", "site retired (E4)")


@pytest.mark.parametrize("scope", [None, "in_scope", "pending"])
def test_a_shown_site_enters_the_ledger_rendered(scope):
    session = ScopeSession({ISHTAR: (scope, None)})
    assert shorts_ledger.status_for(session, ISHTAR) == ("rendered", None)
    (sql,) = session.statements()
    assert sql == shorts_ledger._SCOPE_SQL.text


def test_the_status_is_the_scope_decision_not_a_period_guess(tmp_path):
    """The old rule withdrew by period_name '1500+ AD' alone: it missed '> 1500 AD' and the
    Old World's '500 - 1000 AD', and it would withdraw an Americas site dated exactly 1500
    (inside the window). E4 decides per site; the ledger follows scope_status."""
    site_dir = _render_dir(tmp_path, "orongo", period="1500+ AD")
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    status = shorts_ledger.status_for(ScopeSession({site["id"]: (None, None)}), site["id"])
    assert status == ("rendered", None)
    assert not hasattr(shorts_ledger, "OUT_OF_SCOPE_PERIODS")


def test_a_render_of_a_site_that_is_gone_raises():
    with pytest.raises(LookupError, match="not in unified_sites"):
        shorts_ledger.status_for(ScopeSession({}), ISHTAR)


def test_a_naive_timestamp_and_a_missing_card_text_are_refused(tmp_path):
    site_dir = _render_dir(tmp_path, "ishtar-gate")
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    kw = {"voice_id": None, "pipeline_commit": None, **RENDERED}
    with pytest.raises(ValueError):
        shorts_ledger.row_for_render(
            site, site_dir, site_dir / "ishtar-gate.mp4", rendered_at=datetime(2026, 9, 1), **kw
        )
    with pytest.raises(ValueError):
        shorts_ledger.row_for_render(
            {**site, "card_text": ""},
            site_dir,
            site_dir / "ishtar-gate.mp4",
            rendered_at=datetime.now(UTC),
            **kw,
        )


def test_record_inserts_once_per_file(tmp_path):
    site_dir = _render_dir(tmp_path, "ishtar-gate")
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    row = shorts_ledger.row_for_render(
        site,
        site_dir,
        site_dir / "ishtar-gate.mp4",
        voice_id="v",
        pipeline_commit=None,
        rendered_at=datetime.now(UTC),
        **RENDERED,
    )
    session = RecordingSession({"INSERT INTO site_shorts": [1]})
    assert shorts_ledger.record(session, row) is True
    sql, params = session.log[0]
    assert "ON CONFLICT (video_sha256) DO NOTHING" in sql
    assert params["image_ids"] == [22, 11] and params["site_id"] == site["id"]
    assert shorts_ledger.record(RecordingSession(), row) is False  # already there


def test_current_commit_names_a_real_commit():
    assert re.fullmatch(r"[0-9a-f]{40}(-dirty)?", shorts_ledger.current_commit())


# --------------------------------------------------------------------------------------
# the writer in the render step
# --------------------------------------------------------------------------------------


def _render_step(tmp_path, monkeypatch, session) -> Path:
    """Run the render step of run_short over a finished site directory."""
    from pipeline.video import __main__ as video

    site_dir = _render_dir(tmp_path, "ishtar-gate")
    monkeypatch.setattr(video, "_exported_site_dir", lambda args: site_dir)
    monkeypatch.setattr(video.shorts_export, "country_code_for", lambda c: None)
    monkeypatch.setattr(
        video.shorts_render, "render_short", lambda *a, **k: site_dir / "ishtar-gate.mp4"
    )
    monkeypatch.setattr(video.shorts_ledger, "current_commit", lambda: "c0ffee")
    monkeypatch.setattr(video, "get_session", lambda: _ctx(session))
    args = Namespace(
        steps="render",
        site_id=ISHTAR,
        name=None,
        voice="English_expressive_narrator",
        music=None,
        flash=None,
        whoosh=None,
        music_start=0.0,
    )
    assert video.run_short(args) == site_dir / "ishtar-gate.mp4"
    return site_dir


def test_the_render_step_writes_the_ledger_row(tmp_path, monkeypatch):
    session = ScopeSession({ISHTAR: (None, None)})
    _render_step(tmp_path, monkeypatch, session)
    (scope_sql, _), (insert_sql, params) = session.log
    assert scope_sql == shorts_ledger._SCOPE_SQL.text  # read in the insert's transaction
    assert "INSERT INTO site_shorts" in insert_sql
    assert params["pipeline_commit"] == "c0ffee"
    assert params["voice_id"] == "English_expressive_narrator"
    assert (params["status"], params["status_reason"]) == ("rendered", None)


def test_a_site_retired_after_its_export_enters_the_ledger_withdrawn(tmp_path, monkeypatch):
    """The render step works offline from a site.json exported earlier; the scope is read
    when the row is written, so a retirement in between is not lost."""
    session = ScopeSession({ISHTAR: ("retired", "decided out of scope")})
    _render_step(tmp_path, monkeypatch, session)
    _, (_, params) = session.log
    assert params["status"] == "withdrawn"
    assert params["status_reason"] == "site retired (E4): decided out of scope"


def test_a_failed_ledger_write_fails_the_render_step(tmp_path, monkeypatch):
    from pipeline.video import __main__ as video

    site_dir = _render_dir(tmp_path, "ishtar-gate")
    monkeypatch.setattr(video.shorts_ledger, "current_commit", lambda: "c0ffee")

    class _down:
        def __enter__(self):
            raise ConnectionError("tunnel down")

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(video, "get_session", lambda: _down())
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    with pytest.raises(ConnectionError):
        video.record_render(site, site_dir, site_dir / "ishtar-gate.mp4", voice_id="v")


# --------------------------------------------------------------------------------------
# the backfill
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def backfill():
    spec = importlib.util.spec_from_file_location(
        "backfill_site_shorts_ledger", REPO / "scripts" / "backfill_site_shorts_ledger.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_backfill_plans_every_finished_render_and_nothing_else(tmp_path, backfill):
    _render_dir(tmp_path, "ishtar-gate")
    _render_dir(tmp_path, "tomb-of-jahangir", period="1500+ AD", site_id=JAHANGIR)
    unfinished = _render_dir(tmp_path, "kerbatch")
    (unfinished / "kerbatch.mp4").unlink()  # exported, never rendered
    session = ScopeSession({ISHTAR: (None, None), JAHANGIR: (None, None)})
    rows = backfill.plan(tmp_path, session)
    assert [(r.slug, r.status) for r in rows] == [
        ("ishtar-gate", "rendered"),
        ("tomb-of-jahangir", "withdrawn"),  # the reviewed decision; not retired (yet)
    ]
    assert rows[1].status_reason == backfill.WITHDRAWN_BEFORE_THE_LEDGER[JAHANGIR]
    assert all(r.voice_id == "English_expressive_narrator" for r in rows)
    assert all(r.pipeline_commit is None for r in rows)  # nobody recorded it


def test_the_backfill_withdraws_a_retired_site_with_its_e4_reason(tmp_path, backfill):
    """A retirement in unified_sites is the record: it withdraws any render, the brief's
    Jahangir decision included, with the reason E4 wrote."""
    _render_dir(tmp_path, "ishtar-gate")
    _render_dir(tmp_path, "tomb-of-jahangir", period="1500+ AD", site_id=JAHANGIR)
    session = ScopeSession({ISHTAR: ("retired", "decided out"), JAHANGIR: ("retired", "1627")})
    rows = backfill.plan(tmp_path, session)
    assert [(r.status, r.status_reason) for r in rows] == [
        ("withdrawn", "site retired (E4): decided out"),
        ("withdrawn", "site retired (E4): 1627"),
    ]


def test_the_backfill_plan_reads_the_scope_and_writes_nothing(tmp_path, backfill, capsys):
    """The plan shows exactly the statuses --apply would insert, so it reads each site's
    scope. It used to open no session at all - and print statuses guessed from the period,
    which --apply could not have agreed with once a site is retired."""
    _render_dir(tmp_path, "ishtar-gate")
    session = ScopeSession({ISHTAR: (None, None)})
    with patch("pipeline.database.get_session", return_value=_ctx(session)):
        assert backfill.main(["--root", str(tmp_path)]) == 0
    assert session.statements() == [shorts_ledger._SCOPE_SQL.text]
    assert "plan only" in capsys.readouterr().out


def test_the_backfill_apply_inserts_every_planned_row(tmp_path, backfill, capsys):
    _render_dir(tmp_path, "ishtar-gate")
    _render_dir(tmp_path, "tomb-of-jahangir", period="1500+ AD", site_id=JAHANGIR)
    session = ScopeSession({ISHTAR: (None, None), JAHANGIR: (None, None)})
    with patch("pipeline.database.get_session", return_value=_ctx(session)):
        assert backfill.main(["--root", str(tmp_path), "--apply"]) == 0
    inserts = [params for sql, params in session.log if "INSERT INTO site_shorts" in sql]
    assert [(p["site_id"], p["status"]) for p in inserts] == [
        (ISHTAR, "rendered"),
        (JAHANGIR, "withdrawn"),
    ]
    assert "inserted 2" in capsys.readouterr().out


def test_the_voice_comes_from_the_description_the_render_wrote(tmp_path, backfill):
    site_dir = _render_dir(tmp_path, "ishtar-gate")
    assert backfill.voice_of(site_dir) == "English_expressive_narrator"
    (site_dir / "description.txt").write_text("no voice line", encoding="utf-8")
    with pytest.raises(LookupError):
        backfill.voice_of(site_dir)
