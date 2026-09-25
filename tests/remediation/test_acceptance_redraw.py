"""PROTOCOL.md section 10: the fresh draw after a FAIL or VOID (`acceptance/redraw.py`).

"then a fresh acceptance on a new draw - `draw.py` sealed again with seed 20260926 (its canaries
20260927), excluding this draw's 60 - under these same thresholds". `draw.py` stays as it was sealed
for the first draw: the fresh draw imports it and adds the next seed and the previous draws' samples.
Offline: the production reads are faked, as in `test_acceptance_draw.py`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "scripts" / "remediation", REPO / "scripts" / "remediation" / "gallery_audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from acceptance import draw as D  # noqa: E402
from acceptance import redraw as R  # noqa: E402
from phase4.audit4 import draw_sample  # noqa: E402

ACCEPTANCE = REPO / "output" / "remediation" / "acceptance"
FIRST = ACCEPTANCE / "draw-2026-09-25"


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def _frame(n: int = 240) -> list[dict[str, Any]]:
    """n sites alternating two countries far apart (the draw tests' frame)."""
    return [
        {
            "site_id": _uuid(i),
            "name": f"Site {i}",
            "country": "Peru" if i % 2 == 0 else "Japan",
            "lat": -13.0 + (i % 7) if i % 2 == 0 else 35.0 + (i % 7),
            "lon": -72.0 if i % 2 == 0 else 139.0,
        }
        for i in range(n)
    ]


def _previous(
    tmp_path: Path,
    name: str = "draw-2026-09-25",
    *,
    seed: int = 20260925,
    ids: list[str] | None = None,
    result: bool = True,
    extra: str = "",
) -> Path:
    """A finished draw directory: SAMPLE.jsonl pinned by DRAW.json, and its RESULT.md."""
    run = tmp_path / name
    run.mkdir()
    ids = ids if ids is not None else [_uuid(i) for i in range(10, 70)]
    sample = "".join(
        json.dumps({"site_id": i, "name": "x", "scope_reason": extra}) + "\n" for i in ids
    )
    (run / "SAMPLE.jsonl").write_text(sample, encoding="utf-8", newline="\n")
    draw = {
        "seed": seed,
        "sample_size": len(ids),
        "sha256": {"SAMPLE.jsonl": hashlib.sha256(sample.encode("utf-8")).hexdigest()},
    }
    (run / "DRAW.json").write_text(json.dumps(draw), encoding="utf-8")
    if result:
        (run / "RESULT.md").write_text("# FAIL\n", encoding="utf-8")
    return run


def _fake_production(monkeypatch: pytest.MonkeyPatch, frame: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(D, "read_frame", lambda: frame)

    def values(ids: list[str]) -> list[dict[str, Any]]:
        by_id = {r["site_id"]: r for r in frame}
        return [dict(by_id[i], description="text") for i in sorted(ids)]

    monkeypatch.setattr(D, "read_values", values)
    monkeypatch.setattr(
        D, "read_journal_mark", lambda: {"max_id": 73500, "max_applied_at": "t", "rows": 9}
    )
    monkeypatch.setattr(D, "FIXED_EXCLUSIONS", ())


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *after: Path) -> tuple[int, Path]:
    _fake_production(monkeypatch, _frame())
    p4 = tmp_path / "p4-samples.txt"
    p4.write_text(_uuid(1) + "\n", encoding="utf-8")
    out = tmp_path / "draw-2026-09-26"
    args = ["--out", str(out), "--phase4-audit-samples", str(p4)]
    for run in after:
        args += ["--after", str(run)]
    return R.main(args), out


def _drawn(out: Path) -> list[str]:
    lines = (out / "SAMPLE.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["site_id"] for line in lines]


# ------------------------------------------------------------------------ the previous draws
class TestThePreviousDraws:
    def test_the_next_seed_is_one_past_the_highest_previous_seed(self, tmp_path: Path) -> None:
        first = R.previous_draw(_previous(tmp_path))
        assert R.next_seed([first]) == 20260926
        second = R.previous_draw(_previous(tmp_path, "draw-2026-09-26", seed=20260926))
        assert R.next_seed([second, first]) == 20260927

    def test_there_is_no_fresh_draw_without_a_previous_one(self) -> None:
        with pytest.raises(D.DrawError, match="previous"):
            R.next_seed([])

    def test_a_previous_draw_is_read_from_its_pinned_sample(self, tmp_path: Path) -> None:
        run = _previous(tmp_path)
        drawn = R.previous_draw(run)
        assert drawn.seed == 20260925 and drawn.name == "draw-2026-09-25"
        assert drawn.site_ids == frozenset(_uuid(i) for i in range(10, 70))

    def test_a_sample_that_is_not_the_one_its_draw_pins_refuses(self, tmp_path: Path) -> None:
        run = _previous(tmp_path)
        with (run / "SAMPLE.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"site_id": _uuid(99)}) + "\n")
        with pytest.raises(D.DrawError, match="pins"):
            R.previous_draw(run)

    def test_a_previous_draw_without_its_result_refuses(self, tmp_path: Path) -> None:
        with pytest.raises(D.DrawError, match="RESULT.md"):
            R.previous_draw(_previous(tmp_path, result=False))

    def test_a_sample_that_is_not_its_draw_s_size_refuses(self, tmp_path: Path) -> None:
        run = _previous(tmp_path, ids=[_uuid(3), _uuid(3)])
        with pytest.raises(D.DrawError, match="sites"):
            R.previous_draw(run)

    def test_the_first_draw_is_the_one_the_fresh_draw_follows(self) -> None:
        """The committed draw-2026-09-25: its 60, pinned, its result written, seed 20260926 next."""
        first = R.previous_draw(FIRST)
        sample = FIRST.joinpath("SAMPLE.jsonl").read_text(encoding="utf-8").splitlines()
        assert first.site_ids == frozenset(json.loads(line)["site_id"] for line in sample)
        assert len(first.site_ids) == 60 and first.seed == 20260925
        assert R.next_seed([first]) == 20260926


# ------------------------------------------------------------------------------ the draw
class TestTheFreshDraw:
    def test_only_the_previous_draws_own_sites_are_excluded_and_recorded(
        self, tmp_path: Path
    ) -> None:
        """Another frame id a sample's values happen to name (a duplicate's survivor) stays in."""
        previous = R.previous_draw(_previous(tmp_path, extra=f"duplicate_of:{_uuid(200)}"))
        frame = _frame()
        taken = R.take_redraw(frame, [], [previous], seed=20260926)
        assert taken["excluded"] == set(previous.site_ids)
        (record,) = taken["records"]
        assert record["label"] == "previous-draw-draw-2026-09-25"
        assert record["frame_ids_removed"] == sorted(previous.site_ids)
        assert record["sha256"] == previous.sample_sha256
        assert not set(taken["drawn"]) & previous.site_ids

    def test_the_draw_is_the_project_s_seeded_draw_with_the_next_seed(self, tmp_path: Path) -> None:
        previous = R.previous_draw(_previous(tmp_path))
        frame = _frame()
        taken = R.take_redraw(frame, [], [previous], seed=20260926)
        ids = sorted(r["site_id"] for r in frame)
        expected = draw_sample(ids, seed=20260926, count=60, exclude=set(previous.site_ids))
        assert taken["drawn"] == expected
        assert taken["drawn"] != draw_sample(ids, seed=20260925, count=60, exclude=set())

    def test_a_pool_smaller_than_the_sample_refuses(self, tmp_path: Path) -> None:
        previous = R.previous_draw(_previous(tmp_path))
        with pytest.raises(D.DrawError, match="remain"):
            R.take_redraw(_frame(100), [], [previous], seed=20260926)


# ---------------------------------------------------------------------------- the command
class TestTheCommand:
    def test_a_fresh_draw_writes_the_files_the_judging_reads_and_pins_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        previous = _previous(tmp_path)
        code, out = _run(tmp_path, monkeypatch, previous)
        assert code == 0
        summary = json.loads((out / "DRAW.json").read_text(encoding="utf-8"))
        for name, digest in summary["sha256"].items():
            assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest, name
        assert set(summary["sha256"]) == {
            "FRAME.jsonl",
            "EXCLUDED.json",
            "SAMPLE.jsonl",
            "CANARIES.jsonl",
        }
        assert summary["seed"] == 20260926 and summary["canary_seed"] == 20260927
        assert summary["sample_size"] == 60 and summary["canaries"] == 10
        assert summary["journal_at_draw"]["max_id"] == 73500
        assert summary["after"] == [
            {
                "draw": "draw-2026-09-25",
                "seed": 20260925,
                "sample_sha256": R.previous_draw(previous).sample_sha256,
            }
        ]
        assert summary["draw_py_sha256"] == D.sha256_of(Path(D.__file__))
        assert summary["redraw_py_sha256"] == D.sha256_of(Path(R.__file__))
        drawn = _drawn(out)
        assert not set(drawn) & R.previous_draw(previous).site_ids
        assert _uuid(1) not in drawn  # the Phase-4 audit sample stays excluded

    def test_the_canaries_are_picked_with_the_seed_after_the_draw_s(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code, out = _run(tmp_path, monkeypatch, _previous(tmp_path))
        assert code == 0
        values = [
            json.loads(line) for line in (out / "SAMPLE.jsonl").read_text("utf-8").splitlines()
        ]
        canaries = [
            json.loads(line) for line in (out / "CANARIES.jsonl").read_text("utf-8").splitlines()
        ]
        assert canaries == D.canaries(values, _frame(), seed=20260926)
        assert canaries != D.canaries(values, _frame(), seed=20260925)

    def test_a_fresh_draw_is_taken_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        previous = _previous(tmp_path)
        assert _run(tmp_path, monkeypatch, previous)[0] == 0
        assert _run(tmp_path, monkeypatch, previous)[0] == 1

    def test_the_phase4_audit_samples_are_still_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(D, "read_frame", lambda: pytest.fail("read before the refusal"))
        args = ["--out", str(tmp_path / "draw-x"), "--after", str(_previous(tmp_path))]
        assert R.main(args) == 1
        assert "Phase-4 audit" in capsys.readouterr().err

    def test_a_previous_draw_is_required(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            R.main(["--out", str(tmp_path / "draw-x"), "--phase4-audit-samples", "x.txt"])

    def test_a_previous_draw_without_its_result_refuses_before_any_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(D, "read_frame", lambda: pytest.fail("read before the refusal"))
        p4 = tmp_path / "p4.txt"
        p4.write_text(_uuid(1) + "\n", encoding="utf-8")
        args = ["--out", str(tmp_path / "draw-x"), "--phase4-audit-samples", str(p4)]
        args += ["--after", str(_previous(tmp_path, result=False))]
        assert R.main(args) == 1
        assert "RESULT.md" in capsys.readouterr().err
