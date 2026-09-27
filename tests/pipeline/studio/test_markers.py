from __future__ import annotations

import json

import pytest
from PIL import Image

from pipeline.studio import casefile, handoff, markers
from pipeline.studio.errors import StudioError
from tests.pipeline.studio import episode_fixtures as ef


def _cf(data=None):
    return casefile.from_dict(data or ef.casefile())


def test_crop_geometry():
    # box [0.1, 0.5, 0.1, 0.3] on 1000x800 plus 10 % of its size on every side
    assert markers.crop_box([0.1, 0.5, 0.1, 0.3], 1000, 800) == (90, 376, 210, 664)
    assert markers.crop_box([0.0, 0.0, 1.0, 1.0], 400, 300) == (0, 0, 400, 300)
    assert markers.upscaled(120, 288) == (512, 1229)
    assert markers.upscaled(600, 800) == (600, 800)


def test_export_writes_crops_context_and_tasks(tmp_path):
    ef.write_casefile(tmp_path)
    ef.write_media(tmp_path)
    counts = markers.export_markers(tmp_path, _cf())
    assert counts == {"tasks": 1, "pending": 1, "accepted": 0}
    row = handoff.read_jsonl(tmp_path / markers.CHECK_DIR / "tasks.jsonl")[0]
    assert (row["ref"], row["media_id"], row["label"]) == ("mk1", "m1", "1 PERSON")
    with Image.open(tmp_path / row["crop_path"]) as crop:
        assert min(crop.size) >= markers.MIN_CROP_SIDE
    with Image.open(tmp_path / row["context_path"]) as context:
        assert context.size == (400, 300)
    prompt = (tmp_path / markers.CHECK_DIR / row["prompt_path"]).read_text(encoding="utf-8")
    assert prompt.startswith("IMPORTANT:") and '"label": "1 PERSON"' in prompt


def test_hits_pass_and_a_changed_box_needs_a_new_check(tmp_path):
    ef.write_casefile(tmp_path)
    ef.write_media(tmp_path)
    assert markers.marker_problems(tmp_path, _cf()) == [
        "mk1: no accepted crop check hits for the current image and box"
    ]
    ef.accept_markers(tmp_path)
    assert markers.marker_problems(tmp_path, _cf()) == []
    moved = ef.mutated(media__0__markers__0__box=[0.2, 0.5, 0.1, 0.3])
    assert markers.marker_problems(tmp_path, _cf(moved)) == [
        "mk1: no accepted crop check hits for the current image and box"
    ]


def test_a_miss_is_an_error(tmp_path):
    ef.write_casefile(tmp_path)
    ef.write_media(tmp_path)
    ef.accept_markers(tmp_path, verdict="misses")
    assert markers.marker_problems(tmp_path, _cf()) == [
        "mk1: the crop check says the box misses: one person, inside the box"
    ]
    accepted = json.loads((tmp_path / markers.CHECK_DIR / "accepted.json").read_text())
    assert [a["verdict"] for a in accepted.values()] == ["misses"]


def test_media_with_markers_carry_no_exif_rotation(tmp_path):
    ef.write_casefile(tmp_path)
    (tmp_path / "media").mkdir()
    exif = Image.Exif()
    exif[markers.EXIF_ORIENTATION] = 6
    Image.new("RGB", (400, 300), (200, 190, 170)).save(
        tmp_path / "media" / "stone_person.jpg", format="JPEG", exif=exif
    )
    rotated = "m1: media/stone_person.jpg has EXIF orientation 6; save it with the pixels rotated"
    with pytest.raises(StudioError, match=rotated):
        markers.export_markers(tmp_path, _cf())
    assert not (tmp_path / markers.CHECK_DIR / "tasks.jsonl").exists()
    assert markers.marker_problems(tmp_path, _cf())[0].startswith(rotated)
