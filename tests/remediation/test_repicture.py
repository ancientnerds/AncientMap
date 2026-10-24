"""Gap 1 (2026-10-24): the lost renderings of the MiniMax pool, fetched again for exactly what needs them.

Offline: the needs (the old targets of the re-check and of the credit re-seed, the calibration's
adjudication sample drawn without looking at the disk), the fetch (the lane's host, width and MIME,
bytes Pillow decodes, a picture on disk kept and checked, a gone address recorded, a 429 stopping the
run), the manifest and its exit, and the consumers that now refuse a missing picture by name.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from candidate_search import pool as PL  # noqa: E402
from candidate_search import repicture as RP  # noqa: E402
from image_roles import calibrate as CAL  # noqa: E402
from served_image import commons as CM  # noqa: E402

SITE = "11111111-1111-4111-8111-111111111111"
SITE_B = "22222222-2222-4222-8222-222222222222"
URL = "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Tomb.jpg/1280px-Tomb.jpg"


def _jpeg(width: int = 1280, height: int = 853) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (120, 90, 60)).save(out, format="JPEG")
    return out.getvalue()


class FakeCommons:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def get(self, url: str) -> Any:
        self.asked.append(url)
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _ok(data: bytes | None = None, mime: str = "image/jpeg") -> SimpleNamespace:
    return SimpleNamespace(
        content=_jpeg() if data is None else data, headers={"content-type": mime}
    )


def _candidate(url: str = URL, file: str = "Tomb.jpg") -> dict[str, Any]:
    return {"file": file, "picture_url": url}


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


# --------------------------------------------------------------------------------- the fetch
def test_a_needed_picture_is_fetched_into_the_name_the_pool_reads(tmp_path: Path) -> None:
    commons = FakeCommons({URL: _ok()})
    out = RP.repicture(tmp_path, "credit", [(SITE, _candidate())], commons)
    assert out["ok"] and out["statuses"] == {RP.FETCHED: 1}
    path = PL.picture_path(tmp_path, _candidate())
    assert path.is_file()
    [line] = [json.loads(x) for x in (tmp_path / "REPICTURE_credit.jsonl").read_text().splitlines()]
    assert line["status"] == RP.FETCHED and line["width"] == 1280 and line["name"] == path.name
    assert line["content_type"] == "image/jpeg" and len(line["sha256"]) == 64


def test_a_picture_on_disk_is_checked_and_never_fetched_again(tmp_path: Path) -> None:
    path = PL.picture_path(tmp_path, _candidate())
    path.parent.mkdir(parents=True)
    path.write_bytes(_jpeg())
    commons = FakeCommons({})
    out = RP.repicture(tmp_path, "credit", [(SITE, _candidate())], commons)
    assert out["statuses"] == {RP.PRESENT: 1} and commons.asked == []


def test_a_broken_picture_on_disk_is_refused_by_name(tmp_path: Path) -> None:
    path = PL.picture_path(tmp_path, _candidate())
    path.parent.mkdir(parents=True)
    path.write_bytes(b"<html>not a picture</html>")
    out = RP.repicture(tmp_path, "credit", [(SITE, _candidate())], FakeCommons({}))
    assert not out["ok"] and out["statuses"] == {RP.REFUSED: 1}


def test_a_gone_address_is_recorded_and_the_run_fails(tmp_path: Path) -> None:
    commons = FakeCommons({URL: CM.Unfetchable(f"{URL}: HTTP 404")})
    out = RP.repicture(tmp_path, "credit", [(SITE, _candidate())], commons)
    assert not out["ok"] and out["statuses"] == {RP.GONE: 1}
    assert "HTTP 404" in out["not_on_disk"][0]


def test_a_429_stops_the_run_instead_of_refusing_the_picture(tmp_path: Path) -> None:
    commons = FakeCommons({URL: CM.CommonsError(f"{URL}: HTTP 429")})
    with pytest.raises(CM.CommonsError, match="429"):
        RP.repicture(tmp_path, "credit", [(SITE, _candidate())], commons)
    assert not PL.picture_path(tmp_path, _candidate()).exists()


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (
            SimpleNamespace(content=b"<html/>", headers={"content-type": "text/html"}),
            "Content-Type",
        ),
        (
            SimpleNamespace(content=b"\xff\xd8garbage", headers={"content-type": "image/jpeg"}),
            "Pillow",
        ),
        (
            SimpleNamespace(content=_jpeg(2000, 1000), headers={"content-type": "image/jpeg"}),
            "wide",
        ),
    ],
)
def test_a_rendering_that_is_not_the_lanes_is_refused(
    tmp_path: Path, answer: Any, reason: str
) -> None:
    out = RP.repicture(tmp_path, "credit", [(SITE, _candidate())], FakeCommons({URL: answer}))
    assert out["statuses"] == {RP.REFUSED: 1} and reason in out["not_on_disk"][0]
    assert not PL.picture_path(tmp_path, _candidate()).exists()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/Tomb.jpg",
        "http://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Tomb.jpg/1280px-Tomb.jpg",
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Tomb.jpg/400px-Tomb.jpg",
    ],
)
def test_only_a_commons_rendering_of_the_lanes_width_is_fetched(tmp_path: Path, url: str) -> None:
    commons = FakeCommons({})
    out = RP.repicture(tmp_path, "credit", [(SITE, _candidate(url))], commons)
    assert out["statuses"] == {RP.REFUSED: 1} and commons.asked == []


def test_an_original_smaller_than_the_width_is_its_own_rendering() -> None:
    assert (
        RP.rendering_problem("https://upload.wikimedia.org/wikipedia/commons/a/ab/Tomb.jpg") is None
    )


def test_a_dry_run_counts_and_fetches_nothing(tmp_path: Path) -> None:
    commons = FakeCommons({})
    out = RP.repicture(tmp_path, "pool", [(SITE, _candidate())], commons, dry_run=True)
    assert out == {"need": "pool", "needed": 1, "on_disk": 0, "missing": 1, "dry_run": True}
    assert commons.asked == [] and not (tmp_path / "REPICTURE_pool.jsonl").exists()


def test_a_picture_needed_twice_is_one_line(tmp_path: Path) -> None:
    out = RP.repicture(
        tmp_path, "credit", [(SITE, _candidate()), (SITE, _candidate())], FakeCommons({URL: _ok()})
    )
    assert out["needed"] == 1


def test_an_empty_or_unknown_need_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RP.RepictureError, match="names no picture"):
        RP.repicture(tmp_path, "credit", [], FakeCommons({}))
    with pytest.raises(RP.RepictureError, match="not one of"):
        RP.repicture(tmp_path, "everything", [(SITE, _candidate())], FakeCommons({}))


# --------------------------------------------------------------------------------- the needs
def _old_run(tmp_path: Path) -> Path:
    old = tmp_path / "candidates-2026-10-06"
    _write(
        old / "CANDIDATES.jsonl",
        [
            {"site_id": SITE, "candidates": [_candidate(), _candidate(URL + "x", "Other.jpg")]},
            {"site_id": SITE_B, "candidates": [_candidate(URL + "y", "B.jpg")]},
        ],
    )
    _write(
        old / "VERDICTS.jsonl",
        [
            {"site_id": SITE, "file": "Tomb.jpg", "verdict": "depicts"},
            {"site_id": SITE, "file": "Other.jpg", "verdict": "other_site"},
            {"site_id": SITE_B, "file": "B.jpg", "verdict": "depicts"},
        ],
    )
    _write(
        old / "TARGETS.jsonl",
        [
            {"site_id": SITE, "commons_file": "Tomb.jpg"},
            {"site_id": SITE_B, "commons_file": "B.jpg"},
        ],
    )
    return old


def test_the_credit_need_is_the_targets_of_the_named_sites(tmp_path: Path) -> None:
    old = _old_run(tmp_path)
    sites = tmp_path / "CREDIT_SITES_CLAUDE.txt"
    sites.write_text(f"{SITE}\n", encoding="utf-8")
    assert [(s, c["file"]) for s, c in RP.need_credit(old, sites)] == [(SITE, "Tomb.jpg")]
    sites.write_text("33333333-3333-4333-8333-333333333333\n", encoding="utf-8")
    with pytest.raises(RP.RepictureError, match="no target"):
        RP.need_credit(old, sites)


def test_target_picks_name_the_repicture_command_for_a_missing_picture(tmp_path: Path) -> None:
    old = _old_run(tmp_path)
    with pytest.raises(PL.PoolError, match="repicture.py --need recheck"):
        PL.target_picks(old, [{"site_id": SITE}], {SITE})
    assert len(PL.target_candidates(old, [{"site_id": SITE}], {SITE})) == 1


def test_the_adjudication_sample_does_not_look_at_the_disk(tmp_path: Path) -> None:
    old = _old_run(tmp_path)
    args = (
        RP._jsonl(old / "CANDIDATES.jsonl"),
        RP._jsonl(old / "VERDICTS.jsonl"),
    )
    first = CAL.adjudication_sample({SITE, SITE_B}, *args, per_class=50, seed=1)
    PL.picture_path(old, _candidate()).parent.mkdir(parents=True)
    PL.picture_path(old, _candidate()).write_bytes(_jpeg())
    assert CAL.adjudication_sample({SITE, SITE_B}, *args, per_class=50, seed=1) == first
    assert {(s, c["file"]) for s, c in first} == {
        (SITE, "Tomb.jpg"),
        (SITE, "Other.jpg"),
        (SITE_B, "B.jpg"),
    }
    # a site the fresh read no longer shows has no record to ask about
    assert {s for s, _ in CAL.adjudication_sample({SITE}, *args, per_class=50, seed=1)} == {SITE}
