from __future__ import annotations

import io
import json
import sys

import pytest
from PIL import Image

from pipeline.studio import __main__ as cli
from pipeline.studio import config, remote
from pipeline.studio.paper import publish, pull
from pipeline.studio.paper.workspace import workspace
from tests.pipeline.studio import fixtures as fx

RUN = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch):
    monkeypatch.setattr(config, "load_env", lambda: None)


def test_every_paper_command_is_registered():
    parser = cli.build_parser()
    register = [
        "paper",
        "register-video",
        fx.REQ,
        "--youtube-id",
        "dQw4w9WgXcQ",
        "--title",
        "t",
        "--published-at",
        "2026-10-01T18:00:00+00:00",
        "--timestamps",
        "ts.json",
    ]
    for command in (
        ["paper", "list"],
        ["paper", "pull", fx.REQ],
        ["paper", "pull", fx.REQ, "--dossier-from", RUN],
        ["paper", "number", fx.REQ],
        ["paper", "check", fx.REQ],
        ["paper", "claims-export", fx.REQ],
        ["paper", "claims-import", fx.REQ],
        ["paper", "images-export", fx.REQ],
        ["paper", "images-import", fx.REQ],
        ["paper", "bundle", fx.REQ],
        ["paper", "publish", fx.REQ, "--dry-run"],
        ["paper", "correct", fx.REQ, "--text", "x"],
        ["paper", "correct", fx.REQ, "--entries", "entries.json", "--with-report"],
        ["paper", "correct", fx.REQ, "--text", "x", "--republish"],
        ["paper", "correct", fx.REQ, "--text", "x", "--report-file", "paper.md"],
        ["paper", "correct", fx.REQ, "--text", "x", "--report-file", "paper.md", "--rewrite"],
        register,
        [*register, "--poster", "package/thumbnail_2.jpg"],
    ):
        assert callable(parser.parse_args(command).func)


@pytest.mark.parametrize(
    "extra",
    [
        ["--text", "x", "--entries", "entries.json"],
        ["--text", "x", "--with-report", "--republish"],
        ["--with-report"],
    ],
)
def test_correct_modes_exclude_each_other(extra):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["paper", "correct", fx.REQ, *extra])


def test_pull_passes_the_fresh_run_of_a_rewrite(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seen = []

    def fake_pull(request_id, dossier_from=None):
        seen.append((request_id, dossier_from))
        return workspace(request_id)

    monkeypatch.setattr(pull, "pull", fake_pull)
    assert cli.main(["paper", "pull", fx.REQ, "--dossier-from", RUN]) == 0
    assert cli.main(["paper", "pull", fx.REQ]) == 0
    assert seen == [(fx.REQ, RUN), (fx.REQ, None)]


def test_rewrite_needs_a_report_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    assert cli.main(["paper", "correct", fx.REQ, "--text", "x", "--rewrite"]) == 2
    assert "--rewrite goes with --report-file" in capsys.readouterr().err


def test_number_then_check_through_the_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    fx.make_workspace(tmp_path)
    assert cli.main(["paper", "number", fx.REQ]) == 0
    assert json.loads(capsys.readouterr().out) == {"sources": 2, "images": 0}
    assert cli.main(["paper", "check", fx.REQ]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] is False and "claims" in out["failing"]


def test_studio_errors_exit_2_with_the_message(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    assert cli.main(["paper", "number", fx.REQ]) == 2
    assert "error:" in capsys.readouterr().err


def test_list_prints_the_remote_listing(monkeypatch, capsys):
    monkeypatch.setattr(remote, "check_module", lambda *a, **k: b'{"id": "x"}\n')
    assert cli.main(["paper", "list"]) == 0
    assert capsys.readouterr().out == '{"id": "x"}\n'


def test_cli_writes_utf8_whatever_the_console_codepage(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", newline="\n"))
    listing = '[{"question": "Şanlıurfa"}]\n'
    monkeypatch.setattr(remote, "check_module", lambda *a, **k: listing.encode("utf-8"))
    assert cli.main(["paper", "list"]) == 0
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8") == listing


@pytest.mark.parametrize("mode", ["republish", "rewrite"])
def test_a_republish_prints_the_notice_it_sent(monkeypatch, tmp_path, capsys, mode):
    """Both rewrite paths of owner decision 18 print A's `paper_published` notice (decision 21)."""
    monkeypatch.setenv("STUDIO_ASSETS", str(tmp_path))
    seen = {}
    effects = {"indexnow": {"ok": True}, "qdrant": {"ok": True}, "notify": {"discord": False}}

    def fake_correct(ws, entries, **modes):
        seen.update(modes)
        return {"apply": {"ok": True, "journal_id": 9, "side_effects": effects}}

    monkeypatch.setattr(publish, "correct", fake_correct)
    paper = tmp_path / "paper.md"
    paper.write_text("# Title\n\nThe rewritten paper.\n", encoding="utf-8")
    flags = {
        "republish": ["--republish"],
        "rewrite": ["--report-file", str(paper), "--rewrite"],
    }[mode]
    assert cli.main(["paper", "correct", fx.REQ, "--text", "Rewritten.", *flags]) == 0
    assert json.loads(capsys.readouterr().out)["side_effects"]["notify"] == {"discord": False}
    assert seen == {
        "with_report": False,
        "republish": mode == "republish",
        "report": None if mode == "republish" else "# Title\n\nThe rewritten paper.\n",
        "rewrite": mode == "rewrite",
    }


def test_register_video_sends_the_poster_between_two_dry_runs(monkeypatch, tmp_path):
    events = []

    def fake_run(module, args, *, stdin=None, timeout):
        events.append(("run", args, json.loads(stdin).get("poster")))
        return remote.RemoteResult(0, b'{"ok": true}', "")

    def fake_upload(request_id, files, timeout=900):
        events.append(("upload", [p.name for p in files], None))

    monkeypatch.setattr(remote, "run_module", fake_run)
    monkeypatch.setattr(remote, "upload_research_images", fake_upload)
    stamps = tmp_path / "ts.json"
    stamps.write_text('{"ev-01": 42}', encoding="utf-8")
    thumb = tmp_path / "thumbnail_1.jpg"
    Image.new("RGB", (1280, 720)).save(thumb, format="JPEG")
    args = ["paper", "register-video", fx.REQ, "--youtube-id", "dQw4w9WgXcQ", "--title", "t"]
    args += ["--published-at", "2026-10-01T18:00:00+00:00", "--timestamps", str(stamps)]
    assert cli.main([*args, "--poster", str(thumb)]) == 0
    poster = f"/data/research-images/{fx.REQ}/video_dQw4w9WgXcQ.jpg"
    assert events == [
        ("run", ["--register-video", "--dry-run"], None),
        ("upload", ["video_dQw4w9WgXcQ.jpg"], None),
        ("run", ["--register-video", "--dry-run"], poster),
        ("run", ["--register-video"], poster),
    ]
    events.clear()
    assert cli.main(args) == 0  # without --poster: a posterless registration
    assert events == [
        ("run", ["--register-video", "--dry-run"], None),
        ("run", ["--register-video"], None),
    ]
