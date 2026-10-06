"""The candidate judgement's own tests: the packing, the answer's shape, and the write side.

DB-less and offline: no network, no download - the paths in a candidate are strings the tests do
not read. What is measured here is the stage's discipline: a site is never split across two agents,
every candidate of an answered site is judged exactly once, an answer that names a file nobody
offered is refused by name, and only a `depicts` verdict becomes a fetch target.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "remediation"))

from candidate_search import judge as CJ  # noqa: E402


def _site(site_id: str, files: list[str], name: str = "Gonnus") -> dict:
    return {
        "site_id": site_id,
        "name": name,
        "country": "Italy",
        "floor": {"min_width": 800, "min_height": 300},
        "candidates": [
            {
                "file": f,
                "why": "a search",
                "picture_url": f"https://upload.wikimedia.org/{f}",
                "original_url": f"https://upload.wikimedia.org/orig/{f}",
                "width": 1600,
                "height": 1200,
                "path": f"pictures/{f}",
            }
            for f in files
        ],
    }


def _answer(site: dict, verdicts: list[str], note: str = "") -> dict:
    return {
        "site_id": site["site_id"],
        "verdicts": [
            {"file": c["file"], "verdict": v, "note": note}
            for c, v in zip(site["candidates"], verdicts, strict=True)
        ],
        "note": "",
    }


class TestThePacking:
    def test_a_site_is_never_split_across_two_batches(self) -> None:
        sites = [_site(f"{i:08d}", ["a.jpg", "b.jpg"]) for i in range(12)]
        batches = CJ.pack(sites, images_per_batch=4, sites_per_batch=6)
        seen: list[str] = []
        for batch in batches:
            for site in batch["sites"]:
                assert site["site_id"] not in seen
                seen.append(site["site_id"])
        assert seen == [s["site_id"] for s in sites]

    def test_a_batch_never_exceeds_its_image_count(self) -> None:
        sites = [_site(f"{i:08d}", ["a.jpg", "b.jpg", "c.jpg"]) for i in range(10)]
        for batch in CJ.pack(sites, images_per_batch=6, sites_per_batch=99):
            assert batch["images"] <= 6

    def test_a_site_bigger_than_a_batch_gets_its_own_and_the_surplus_is_refused(self) -> None:
        big = _site("big", [f"{i}.jpg" for i in range(40)])
        batches = CJ.pack([big], images_per_batch=36)
        assert len(batches) == 1
        assert batches[0]["images"] == 36
        assert batches[0]["refused"] == [4], "a candidate nobody looks at is named, not dropped"

    def test_a_site_without_candidates_is_not_batched(self) -> None:
        empty = {"site_id": "e", "name": "x", "country": "y", "candidates": []}
        assert CJ.pack([empty]) == []


class TestTheAnswerShape:
    def test_one_verdict_per_candidate_in_any_order_is_accepted(self, tmp_path: Path) -> None:
        site = _site("a", ["x.jpg", "y.jpg"])
        answer = _answer(site, [CJ.OTHER, CJ.DEPICTS])
        answer["verdicts"].reverse()
        out = tmp_path / "run"
        summary = CJ.import_answers(out, {"a": answer}, {"a": site})
        assert summary["verdicts"] == {CJ.DEPICTS: 1, CJ.OTHER: 1, CJ.REGION: 0}, (
            "the map always names all three"
        )
        assert summary["sites_with_a_picture"] == 1

    def test_a_file_nobody_offered_is_refused_by_name(self, tmp_path: Path) -> None:
        site = _site("a", ["x.jpg"])
        answer = _answer(site, [CJ.DEPICTS])
        answer["verdicts"].append({"file": "Mars.jpg", "verdict": CJ.DEPICTS, "note": ""})
        summary = CJ.import_answers(tmp_path / "run", {"a": answer}, {"a": site})
        assert summary["sites_refused"] == 1
        refused = (tmp_path / "run" / CJ.REFUSED).read_text(encoding="utf-8")
        assert "Mars.jpg" in refused

    def test_a_candidate_left_unjudged_is_refused(self, tmp_path: Path) -> None:
        site = _site("a", ["x.jpg", "y.jpg"])
        answer = {
            "site_id": "a",
            "verdicts": [{"file": "x.jpg", "verdict": CJ.DEPICTS, "note": ""}],
        }
        summary = CJ.import_answers(tmp_path / "run", {"a": answer}, {"a": site})
        assert summary["sites_refused"] == 1
        assert "y.jpg" in (tmp_path / "run" / CJ.REFUSED).read_text(encoding="utf-8")

    def test_a_candidate_judged_twice_is_refused(self, tmp_path: Path) -> None:
        site = _site("a", ["x.jpg"])
        answer = {
            "site_id": "a",
            "verdicts": [
                {"file": "x.jpg", "verdict": CJ.DEPICTS, "note": ""},
                {"file": "x.jpg", "verdict": CJ.OTHER, "note": ""},
            ],
        }
        summary = CJ.import_answers(tmp_path / "run", {"a": answer}, {"a": site})
        assert summary["sites_refused"] == 1
        assert "twice" in (tmp_path / "run" / CJ.REFUSED).read_text(encoding="utf-8")

    def test_an_unknown_verdict_is_refused(self, tmp_path: Path) -> None:
        site = _site("a", ["x.jpg"])
        summary = CJ.import_answers(
            tmp_path / "run", {"a": _answer(site, ["looks nice"])}, {"a": site}
        )
        assert summary["sites_refused"] == 1
        assert "verdict" in (tmp_path / "run" / CJ.REFUSED).read_text(encoding="utf-8")

    def test_a_site_without_an_answer_is_refused_by_name(self, tmp_path: Path) -> None:
        summary = CJ.import_answers(tmp_path / "run", {}, {"a": _site("a", ["x.jpg"])})
        assert summary["sites_refused"] == 1
        assert "no answer" in (tmp_path / "run" / CJ.REFUSED).read_text(encoding="utf-8")


class TestTheWriteSide:
    def test_only_a_depicts_verdict_becomes_a_fetch_target(self, tmp_path: Path) -> None:
        verdicts = [
            {"site_id": "a", "file": "a.jpg", "verdict": CJ.OTHER, "width": 4000, "height": 3000},
            {"site_id": "b", "file": "b.jpg", "verdict": CJ.REGION, "width": 4000, "height": 3000},
            {
                "site_id": "c",
                "file": "c1.jpg",
                "verdict": CJ.DEPICTS,
                "width": 1600,
                "height": 1200,
            },
        ]
        out = tmp_path / "run"
        summary = CJ.write_targets(out, verdicts)
        assert summary["sites_to_fetch"] == 1
        target = json.loads((out / CJ.TARGETS).read_text(encoding="utf-8"))
        assert target == {
            "site_id": "c",
            "commons_file": "c1.jpg",
            "width": 1600,
            "height": 1200,
        }

    def test_the_largest_depicts_candidate_of_a_site_wins(self, tmp_path: Path) -> None:
        verdicts = [
            {
                "site_id": "a",
                "file": "small.jpg",
                "verdict": CJ.DEPICTS,
                "width": 800,
                "height": 600,
            },
            {
                "site_id": "a",
                "file": "big.jpg",
                "verdict": CJ.DEPICTS,
                "width": 4000,
                "height": 3000,
            },
            {
                "site_id": "a",
                "file": "huge.jpg",
                "verdict": CJ.OTHER,
                "width": 9000,
                "height": 6000,
            },
        ]
        out = tmp_path / "run"
        CJ.write_targets(out, verdicts)
        lines = (out / CJ.TARGETS).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["commons_file"] == "big.jpg"


class TestThePrompt:
    def test_the_prompt_names_every_candidate_path_and_the_three_verdicts(self) -> None:
        site = _site("a", ["x.jpg", "y.jpg"])
        text = CJ.prompt_for(site)
        assert "pictures/x.jpg" in text and "pictures/y.jpg" in text
        for verdict in (CJ.DEPICTS, CJ.REGION, CJ.OTHER):
            assert verdict in text
        assert "site_id: a" in text


class TestTheExport:
    def test_a_fetched_candidate_lands_on_disk_and_the_prompt_names_its_path(
        self, tmp_path: Path
    ) -> None:
        site = _site("a", ["x.jpg"])

        class _Answer:
            status_code = 200
            content = b"\xff\xd8\xff\xe0not-a-real-jpeg-but-bytes-are-bytes"

        class _Client:
            def get(self, url: str) -> _Answer:
                return _Answer()

        out = CJ.export(tmp_path / "run", [site], _Client(), images_per_batch=36, sites_per_batch=6)
        assert out["prompt_files"] == 1
        prompt = (tmp_path / "run" / "cand-0001" / "a.prompt.txt").read_text(encoding="utf-8")
        assert "pictures" in prompt and "x.jpg" in prompt
        fetched = json.loads(json.dumps(out))  # the summary is plain data
        assert fetched["candidates"] == 1 and fetched["refused_images"] == 0
        assert list((tmp_path / "run" / CJ.PICTURES).iterdir()), "the image is on disk"

    def test_an_image_that_will_not_download_is_refused_by_name(self, tmp_path: Path) -> None:
        site = _site("a", ["x.jpg", "y.jpg"])

        class _Answer:
            status_code = 404
            content = b""

        class _Client:
            def get(self, url: str) -> _Answer:
                return _Answer()

        out = CJ.export(tmp_path / "run", [site], _Client())
        assert out["refused_images"] == 2
        assert {r["file"] for r in out["refusals"]} == {"x.jpg", "y.jpg"}
        assert all("HTTP 404" in r["reason"] for r in out["refusals"])
        assert out["prompt_files"] == 0, "a site whose every image failed is not asked about"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
