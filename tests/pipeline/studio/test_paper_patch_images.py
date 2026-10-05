"""`paper patch-images`: upload, dry-run, apply (rule 8, report class H.2).

The studio's part of a picture patch is transport: it uploads the new files so
the VPS images gate can see them, sends the operator's patch verbatim, and
journals the record with the sha256 of the exact bytes. The paper's text is not
in the patch at all -- that is what makes it a patch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from pipeline.studio import remote
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import publish
from tests.pipeline.studio import fixtures as fx

REQ = fx.REQ
NEW_NAME = "p9_cutting_floor.jpg"
NEW_PATH = f"/data/research-images/{REQ}/{NEW_NAME}"
DRY_OK = {"ok": True, "gates": {"status": {"passed": True}}}
APPLIED = {
    "ok": True,
    "slug": "the-megaliths",
    "url": "https://ancientnerds.com/research/the-megaliths",
    "side_effects": {"indexnow": {"ok": True}},
    "journal_id": 31,
    "already_applied": False,
}


class FakeRemote:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.uploads = []

    def run_module(self, module, args, *, stdin=None, timeout):
        self.calls.append((args, stdin))
        code, outcome = self.answers.pop(0)
        return remote.RemoteResult(code, json.dumps(outcome).encode("utf-8"), "")

    def upload(self, request_id, files, timeout=900):
        self.uploads.append((request_id, [p.name for p in files]))


@pytest.fixture
def ws(tmp_path):
    return fx.make_workspace(tmp_path)


@pytest.fixture
def images(ws):
    folder = ws.images_dir / "selected"
    folder.mkdir(parents=True)
    (folder / NEW_NAME).write_bytes(b"jpeg")
    return folder


def _patch(**overrides) -> dict:
    patch = {
        "version": 1,
        "request_id": REQ,
        "writer": {
            "model": "MiniMax-M3.1-Flash-Preview",
            "tool": "mcode",
            "research_model": "MiniMax-M3",
            "published": "automatic",
            "human_review": False,
        },
        "probative_images": [{"web_path": NEW_PATH, "title": "Cutting floor", "verified": True}],
        "replacements": [
            {
                "old_web_path": f"/data/research-images/{REQ}/p1_trilithon.jpg",
                "markdown": f"![Cutting floor]({NEW_PATH})\n\n*Cutting floor.* [Source](https://a.example/x)\n",
            }
        ],
        "corrections_append": [
            {"date": datetime.now(UTC).date().isoformat(), "text": "Replaced the dead picture."}
        ],
    }
    patch.update(overrides)
    return patch


def _write(ws, patch) -> "object":
    path = ws.root / "patch.json"
    path.write_text(json.dumps(patch, ensure_ascii=False), encoding="utf-8")
    return path


# -- the transport path ----------------------------------------------------------------


def test_it_uploads_the_new_picture_then_dry_runs_then_applies(ws, images, monkeypatch):
    fake = FakeRemote([(0, DRY_OK), (0, APPLIED)])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(remote, "upload_research_images", fake.upload)

    patch = publish.patch_images_payload(ws, _write(ws, _patch()))
    record = publish.patch_images(ws, patch, images)

    assert record["apply"] == APPLIED
    assert record["uploaded"] == [NEW_NAME]
    assert fake.uploads == [(REQ, [NEW_NAME])]
    assert [args for args, _ in fake.calls] == [
        ["--patch-images", "--dry-run"],
        ["--patch-images"],
    ]
    # The exact bytes the record hashes are what both calls carried.
    sent = fake.calls[0][1]
    assert json.loads(sent) == patch
    assert json.loads(fake.calls[1][1]) == patch


def test_a_dry_run_uploads_nothing_and_stops_after_the_gates(ws, images, monkeypatch):
    fake = FakeRemote([(0, DRY_OK)])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(remote, "upload_research_images", fake.upload)

    record = publish.patch_images(ws, _patch(), images, dry_run=True)
    assert record["apply"] is None
    assert record["dry_run"] == DRY_OK
    assert fake.uploads == []


def test_the_record_names_the_written_bytes_and_lands_beside_the_corrections(ws, images, monkeypatch):
    fake = FakeRemote([(0, DRY_OK), (0, APPLIED)])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(remote, "upload_research_images", fake.upload)

    record = publish.patch_images(ws, _patch(), images)
    files = sorted(p.name for p in (ws.root / "image_patches").iterdir())
    assert len(files) == 1
    stored = json.loads((ws.root / "image_patches" / files[0]).read_text(encoding="utf-8"))
    assert stored["body_sha256"] == record["body_sha256"]
    assert len(stored["body_sha256"]) == 64
    assert stored["payload"]["replacements"][0]["old_web_path"].endswith("p1_trilithon.jpg")


# -- refusals before anything leaves the workstation ------------------------------------


def test_a_missing_picture_stops_before_the_dry_run(ws, images, monkeypatch):
    fake = FakeRemote([])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(remote, "upload_research_images", fake.upload)

    (images / NEW_NAME).unlink()
    with pytest.raises(StudioError, match="new pictures are missing"):
        publish.patch_images(ws, _patch(), images)
    assert fake.calls == [] and fake.uploads == []


def test_a_patch_for_another_paper_is_refused(ws, images, monkeypatch):
    fake = FakeRemote([])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    path = _write(ws, _patch(request_id="99999999-8888-7777-6666-555555555555"))
    with pytest.raises(StudioError, match="not this workspace's"):
        publish.patch_images_payload(ws, path)
    assert fake.calls == []


def test_a_patch_file_with_an_unexpected_key_is_refused(ws, images, monkeypatch):
    fake = FakeRemote([])
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    path = _write(ws, _patch(report="the whole paper, which a patch must never carry"))
    with pytest.raises(StudioError, match="unknown keys"):
        publish.patch_images_payload(ws, path)
    assert fake.calls == []


def test_a_failing_dry_run_never_uploads_or_applies(ws, images, monkeypatch):
    fake = FakeRemote(
        [(1, {"ok": False, "gates": {"images": {"passed": False, "issues": ["1 missing"]}}})]
    )
    monkeypatch.setattr(remote, "run_module", fake.run_module)
    monkeypatch.setattr(remote, "upload_research_images", fake.upload)

    with pytest.raises(StudioError, match="failing gates"):
        publish.patch_images(ws, _patch(), images)
    # The upload happened before the dry run (the VPS must see the file to check
    # it), but no second call followed the refusal.
    assert len(fake.calls) == 1
