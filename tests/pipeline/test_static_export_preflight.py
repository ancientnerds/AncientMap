# SPDX-License-Identifier: AGPL-3.0-only
"""The static export writes nothing unless it can write everything, and never runs as root.

Why (plan docs/procedures/SITES_DB_REMEDIATION_2026-09.md 9.4: "`POST /api/sites/rebuild-static`
is broken in production (the API runs as uid 1000, `public/data` is owned by root)"): an export
run as root on 2026-08-18 (`docker exec -u root`, which docs/procedures/PROJECT_LESSONS.md then
recommended) left `sites/`, `sites/details/*`, `sources.json`, `links.json` and
`images/index.json` owned by root. Read on production 2026-09-25 inside `ancient_nerds_api`
(euid 1000): every one of them NOT-WRITABLE. The rebuild job runs the export as that user, so it
fails at its first write, and the next root run would only renew the files that break it.

So the export refuses to run as root, and before its first write it lists every target the
effective user cannot write - all of them, with the remedy - instead of dying on the first one
or, once some are fixed, half-way through with half the files new.

DB-less: a refused export must not have read the database either.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.fake_sql import RecordingSession


class _ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


@pytest.fixture
def exporter(monkeypatch):
    from pipeline import static_exporter

    session = RecordingSession()
    monkeypatch.setattr(static_exporter, "get_session", lambda: _ctx(session))
    monkeypatch.setattr(static_exporter.os, "geteuid", lambda: 1000, raising=False)
    return static_exporter, session


def _unwritable(monkeypatch, module, *paths: Path) -> None:
    """Make exactly these paths unwritable to the export (as root-owned files are to uid 1000)."""
    blocked = {str(p) for p in paths}
    monkeypatch.setattr(module, "_writable", lambda path: str(path) not in blocked)


def test_the_fixed_targets_of_a_full_export(tmp_path, exporter):
    module, _ = exporter
    targets = {p.relative_to(tmp_path).as_posix() for p in module.export_targets(tmp_path)}
    for name in (
        "sources.json",
        "sources.json.gz",
        "sites/index.json",
        "sites/index.json.gz",
        "sites/details/europe.json",
        "sites/details/africa.json.gz",
        "images/index.json",
        "images/index.json.gz",
        "hubs.snapshot.json",
        "links.json",
        "links.json.gz",
        "snapshots",  # a new snapshot file is created there, old ones are pruned
        "snapshots/manifest.json",
    ):
        assert name in targets, name
    assert "hubs.snapshot.json.gz" not in targets  # written without its gzip companion
    assert len([t for t in targets if t.startswith("sites/details/")]) == 2 * len(module.REGIONS)


def test_sites_only_and_no_library_leave_their_files_out(tmp_path, exporter):
    module, _ = exporter
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "texts.json").write_text("{}", encoding="utf-8")
    (tmp_path / "library" / "periods").mkdir(parents=True)
    (tmp_path / "library" / "periods" / "bronze-age.json").write_text("{}", encoding="utf-8")

    def rel(**kw):
        return {p.relative_to(tmp_path).as_posix() for p in module.export_targets(tmp_path, **kw)}

    full = rel()
    assert {"content/texts.json", "library/periods/bronze-age.json", "links.json"} <= full
    no_library = rel(library=False)
    assert "content/texts.json" in no_library
    assert not any(t.startswith("library/") for t in no_library)
    sites_only = rel(sites_only=True)
    assert not any(t.startswith(("content/", "library/", "links.json")) for t in sites_only)


def test_every_unwritable_target_is_named_before_anything_is_written(
    tmp_path, exporter, monkeypatch
):
    module, session = exporter
    (tmp_path / "sites" / "details").mkdir(parents=True)
    for name in ("sources.json", "links.json", "sites/index.json", "sites/details/europe.json"):
        (tmp_path / name).write_text("old", encoding="utf-8")
    _unwritable(
        monkeypatch,
        module,
        tmp_path / "sources.json",
        tmp_path / "sites" / "details" / "europe.json",
    )
    with pytest.raises(PermissionError) as exc:
        module.StaticExporter(tmp_path).export_all(sites_only=True)
    message = str(exc.value)
    assert str(tmp_path / "sources.json") in message
    assert str(tmp_path / "sites" / "details" / "europe.json") in message
    assert "chown" in message  # the remedy, not just the symptom
    assert (tmp_path / "sources.json").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "hubs.snapshot.json").exists()
    assert not (tmp_path / "snapshots").exists()
    assert session.statements() == []


def test_a_missing_file_in_a_directory_it_cannot_write_is_named(tmp_path, exporter, monkeypatch):
    """`sites/` itself root-owned: index.json may be gone, the export still cannot create it."""
    module, session = exporter
    (tmp_path / "sites").mkdir()
    _unwritable(monkeypatch, module, tmp_path / "sites")
    with pytest.raises(PermissionError) as exc:
        module.StaticExporter(tmp_path).export_all(sites_only=True)
    assert str(tmp_path / "sites") in str(exc.value)
    assert session.statements() == []


def test_the_export_refuses_to_run_as_root(tmp_path, exporter, monkeypatch):
    module, session = exporter
    monkeypatch.setattr(module.os, "geteuid", lambda: 0, raising=False)
    with pytest.raises(PermissionError, match="root"):
        module.StaticExporter(tmp_path).export_all(sites_only=True)
    assert list(tmp_path.iterdir()) == []
    assert session.statements() == []


def test_the_hubs_only_refresh_is_checked_too(tmp_path, exporter, monkeypatch):
    module, session = exporter
    (tmp_path / "hubs.snapshot.json").write_text("old", encoding="utf-8")
    _unwritable(monkeypatch, module, tmp_path / "hubs.snapshot.json")
    with pytest.raises(PermissionError):
        module.export_hubs_snapshot(tmp_path)
    assert session.statements() == []
    monkeypatch.setattr(module.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(module, "_writable", lambda path: True)
    with pytest.raises(PermissionError, match="root"):
        module.export_hubs_snapshot(tmp_path)


def test_a_writable_tree_exports_as_before(tmp_path, exporter):
    module, _ = exporter
    module.StaticExporter(tmp_path).export_all(sites_only=True)
    assert (tmp_path / "sources.json").exists()
    assert (tmp_path / "hubs.snapshot.json").exists()


def test_writable_asks_the_operating_system():
    from pipeline import static_exporter

    assert static_exporter._writable(Path(os.getcwd())) is os.access(os.getcwd(), os.W_OK)
