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
from candidate_search import judge_run as JR  # noqa: E402


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
                "picture_url": (
                    f"https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/{f}/1280px-{f}"
                ),
                "original_url": f"https://upload.wikimedia.org/wikipedia/commons/1/1e/{f}",
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
        "answered_by": "mcode-judge-cand-0001",
        "model": "MiniMax-M3.1-Flash-Preview",
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

    def test_an_answer_without_the_model_stamp_is_refused(self, tmp_path: Path) -> None:
        """A verdict nobody can attribute cannot be audited, and the audit of a wrong picture is
        what this stage exists for."""
        site = _site("a", ["x.jpg"])
        answer = _answer(site, [CJ.DEPICTS])
        answer["model"] = ""
        summary = CJ.import_answers(tmp_path / "run", {"a": answer}, {"a": site})
        assert summary["sites_refused"] == 1
        assert "model" in (tmp_path / "run" / CJ.REFUSED).read_text(encoding="utf-8")

    def test_a_kept_verdict_carries_the_agent_and_the_model_that_made_it(
        self, tmp_path: Path
    ) -> None:
        site = _site("a", ["x.jpg"])
        CJ.import_answers(tmp_path / "run", {"a": _answer(site, [CJ.DEPICTS])}, {"a": site})
        row = json.loads(
            (tmp_path / "run" / CJ.VERDICTS).read_text(encoding="utf-8").splitlines()[0]
        )
        assert row["model"] == "MiniMax-M3.1-Flash-Preview"
        assert row["answered_by"] == "mcode-judge-cand-0001"


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


class TestTheDownloadPace:
    """`judge-export` asks for one rendering per candidate: 190 for the pilot, 5,809 for the full run.

    The `PACE` in `judge_run.py` was defined and never used, so a full export would have sent 5,809
    requests back to back to a host whose robot policy asks for serial ones - and every `HTTP 429`
    would have been recorded as a refused candidate, the site losing a picture for a reason that was
    never about the picture.
    """

    def _client(self) -> object:
        class _Answer:
            status_code = 200
            content = b"bytes"

        class _Client:
            def get(self, url: str) -> _Answer:
                return _Answer()

        return _Client()

    def test_a_second_download_to_the_same_host_waits_the_pace(self, tmp_path: Path) -> None:
        waited: list[float] = []
        now = [100.0]
        paced = JR.PacedDownloads(
            self._client(),
            tmp_path / "cache",
            pace=1.0,
            sleep=waited.append,
            clock=lambda: now[0],
        )
        paced.get("https://upload.wikimedia.org/a.jpg")
        now[0] += 0.2  # the first download took 0.2 s, so 0.8 s of the second are still owed
        paced.get("https://upload.wikimedia.org/b.jpg")
        assert waited == [pytest.approx(0.8)], waited

    def test_a_download_that_is_refused_is_an_answer_and_not_an_exception(
        self, tmp_path: Path
    ) -> None:
        class _Answer:
            status_code = 429
            content = b""

        class _Client:
            def get(self, url: str) -> _Answer:
                return _Answer()

        paced = JR.PacedDownloads(_Client(), tmp_path / "cache", sleep=lambda _s: None)
        answer = paced.get("https://upload.wikimedia.org/c.jpg")
        assert answer.status_code == 429, (
            "judge.download turns this into a refused candidate by name"
        )


class TestTheInsertHandover:
    """`TARGETS.jsonl` is a judgement's result; the INSERT wave reads two other files.

    `import_hero/run.py fetch --target insert` takes the Commons file out of `IMPORT_CLAIMS.json`
    and `insert-plan` reads `IMPORT_HERO_REFUSALS.jsonl`. Both belong to the 2025 import until
    something writes them for this run - and without that step the fetch refuses the wave by name
    and the whole search ends in a file nobody reads.
    """

    def _run(self, tmp_path: Path, sites: list[dict], targets: list[dict]) -> Path:
        out = tmp_path / "candidates"
        out.mkdir()
        (out / CJ.CANDIDATES).write_text(
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sites), encoding="utf-8"
        )
        (out / CJ.TARGETS).write_text(
            "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in targets), encoding="utf-8"
        )
        return out

    def test_a_target_becomes_a_claim_and_a_no_target_row_refusal(self, tmp_path: Path) -> None:
        site = _site("a", ["Tomb.jpg"])
        out = self._run(
            tmp_path,
            [site],
            [{"site_id": "a", "commons_file": "Tomb.jpg", "width": 1600, "height": 1200}],
        )
        insert_run = tmp_path / "insert"
        result = CJ.insert_claims(out, insert_run)
        assert result["sites_prepared"] == 1 and result["refused_targets"] == []
        claims = json.loads((insert_run / "IMPORT_CLAIMS.json").read_text(encoding="utf-8"))
        assert claims == {
            "a": {"image": "https://upload.wikimedia.org/wikipedia/commons/1/1e/Tomb.jpg"}
        }
        refusals = [
            json.loads(line)
            for line in (insert_run / "IMPORT_HERO_REFUSALS.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        assert [(r["site_id"], r["reason"]) for r in refusals] == [("a", "no_target_row")]

    def test_a_target_the_search_recorded_no_url_for_is_refused_by_name(
        self, tmp_path: Path
    ) -> None:
        site = _site("a", ["Tomb.jpg"])
        site["candidates"][0]["original_url"] = ""
        site["candidates"][0]["picture_url"] = ""
        out = self._run(
            tmp_path,
            [site],
            [{"site_id": "a", "commons_file": "Tomb.jpg", "width": 1600, "height": 1200}],
        )
        result = CJ.insert_claims(out, tmp_path / "insert")
        assert result["sites_prepared"] == 0
        assert [r["reason"] for r in result["refused_targets"]] == ["no_candidate_url"]

    def test_a_second_claim_for_one_site_never_overwrites_the_first(self, tmp_path: Path) -> None:
        site = _site("a", ["Tomb.jpg", "Mound.jpg"])
        out = self._run(
            tmp_path,
            [site],
            [
                {"site_id": "a", "commons_file": "Tomb.jpg", "width": 1600, "height": 1200},
                {"site_id": "a", "commons_file": "Mound.jpg", "width": 1600, "height": 1200},
            ],
        )
        insert_run = tmp_path / "insert"
        CJ.insert_claims(out, insert_run)
        result = CJ.insert_claims(out, insert_run)
        claims = json.loads((insert_run / "IMPORT_CLAIMS.json").read_text(encoding="utf-8"))
        assert claims == {
            "a": {"image": "https://upload.wikimedia.org/wikipedia/commons/1/1e/Tomb.jpg"}
        }
        assert [r["reason"] for r in result["refused_targets"]] == ["claim_conflict"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
