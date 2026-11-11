"""The command line of the picture research (`image_roles/run.py`) and of the calibration: the glue
between the files of a run directory and the tested functions - exit codes, refusals, the printed
instruction of an agent."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
from image_roles import calibrate as CAL  # noqa: E402
from image_roles import flow as FL  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import run as CLI  # noqa: E402
from image_roles import stage as SG  # noqa: E402


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 300), (120, 120, 120)).save(out, format="JPEG")
    return out.getvalue()


def _exported(tmp_path: Path) -> tuple[Path, Path]:
    run, handoff = tmp_path / "run", tmp_path / "handoff"
    flat = [
        {"site_id": "s", "file": "a.jpg", "path": "/x"},
        {"site_id": "s", "file": "b.jpg", "path": "/y"},
    ]
    questions, pictures = PF.build_questions(flat, lambda c: jpeg())
    SG.export(run, handoff, PF.SPEC, questions, pictures)
    return run, handoff


def _args(run: Path, handoff: Path, *extra: str) -> list[str]:
    return ["--run-dir", str(run), "--handoff", str(handoff), "--stage", "image-prefilter", *extra]


GOOD = json.dumps(
    {
        "items": {
            "C01": {"kind": "site_photo", "usable": True},
            "C02": {"kind": "other", "usable": False},
        }
    }
)


class TestTheStageCommands:
    def test_brief_prints_the_agent_s_instruction_in_the_stage_s_role(
        self, tmp_path: Path, capsys
    ) -> None:
        run, handoff = _exported(tmp_path)
        assert CLI.main(["brief", *_args(run, handoff, "--batch-id", "pre-0001")]) == 0
        text = capsys.readouterr().out
        assert "role image_prefilter at effort low" in text and "--role image_prefilter" in text

    def test_check_answer_exits_0_for_a_good_shape_and_1_for_a_bad_one(
        self, tmp_path: Path, capsys
    ) -> None:
        run, handoff = _exported(tmp_path)
        good, bad = tmp_path / "good.json", tmp_path / "bad.json"
        good.write_text(GOOD, encoding="utf-8")
        bad.write_text('{"items": {}}', encoding="utf-8")
        base = [
            "check-answer",
            *_args(run, handoff, "--batch-id", "pre-0001", "--label", "pre-0001"),
        ]
        assert CLI.main([*base, "--text-file", str(good)]) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True
        assert CLI.main([*base, "--text-file", str(bad)]) == 1
        assert "exactly C01..C02" in json.loads(capsys.readouterr().out)["problem"]

    def test_import_records_the_answers_and_a_second_import_is_refused(
        self, tmp_path: Path, capsys
    ) -> None:
        run, handoff = _exported(tmp_path)
        OH.write_answer(
            handoff, batch_id="pre-0001", stage="image-prefilter", label="pre-0001", text=GOOD,
            answered_by="image_prefilter:pre-0001", model=OH.OPUS_MODEL, now=lambda: "2026-10-09T03:00:00+00:00",
        )  # fmt: skip
        assert CLI.main(["import", *_args(run, handoff)]) == 0
        assert json.loads(capsys.readouterr().out)["answers"] == 1
        assert CLI.main(["import", *_args(run, handoff)]) == 1
        assert "written once" in capsys.readouterr().err

    def test_an_unanswered_handoff_is_a_refusal_not_a_crash(self, tmp_path: Path, capsys) -> None:
        run, handoff = _exported(tmp_path)
        assert CLI.main(["import", *_args(run, handoff)]) == 1
        assert "REFUSED" in capsys.readouterr().err

    def test_the_stages_and_their_roles(self) -> None:
        assert {name: spec.role for name, spec in CLI.STAGES.items()} == {
            "identity-verify": "web_verifier",
            "identity-research": "web_verifier",
            "image-prefilter": "image_prefilter",
            "image-depicts": "image_depicts",
            "image-recheck": "image_adversarial",
            "image-depicts-calibration": "image_depicts",
            "image-adjudicate": "pilot_judge",
            # D117: the clean gold's labellers (two independent, a third on the disputes)
            **{f"image-gold-label-{w}": "pilot_judge" for w in "abc"},
            **{f"image-kind-label-{w}": "pilot_judge" for w in "abc"},
        }

    def test_a_recheck_round_selects_its_own_files(self, tmp_path: Path) -> None:
        args = CLI.build_parser().parse_args(
            [
                "brief",
                "--run-dir",
                "r",
                "--handoff",
                "h",
                "--stage",
                "image-recheck",
                "--round",
                "2",
                "--batch-id",
                "b",
            ]
        )
        assert CLI._spec(args).questions_file == "QUESTIONS_RECHECK_02.jsonl"


class TestTheOtherCommands:
    def test_targets_are_refused_while_nothing_was_judged(self, tmp_path: Path, capsys) -> None:
        assert CLI.main(["write-targets", "--run-dir", str(tmp_path)]) == 1
        assert "run the step before it" in capsys.readouterr().err

    def test_prune_is_refused_without_targets(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "pictures").mkdir()
        assert CLI.main(["prune-pictures", "--run-dir", str(tmp_path)]) == 1
        assert "targets are not written yet" in capsys.readouterr().err

    def test_applying_the_identity_needs_a_stage(self, tmp_path: Path, capsys) -> None:
        assert CLI.main(["identity-apply", "--run-dir", str(tmp_path)]) == 1
        assert "at least one --stage" in capsys.readouterr().err

    def _pool_picks(self, tmp_path: Path, heroes: dict[str, list[tuple[int, str]]]) -> list[str]:
        """A stage whose one site (`a`) holds an old target without a rendering, which the
        re-download gave up on, and a served run whose read shows `heroes`."""
        from tests.remediation.test_candidate_routes import _pool_run
        from tests.remediation.test_image_flow import read_line, served_state

        old = _pool_run(tmp_path)
        for picture in (old / "pictures").iterdir():
            picture.unlink()
        line = {"site_id": "a", "file": "Here.jpg", "status": "refused", "reason": "960 px"}
        (old / "REPICTURE_recheck.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        run = tmp_path / "stage"
        FL.write_population(run, [read_line("a", "Site a")])
        served_state(tmp_path, heroes)
        return ["pool-picks", "--run-dir", str(run), "--old-run", str(old), "--served-run",
                str(tmp_path / "served"), "--out", str(tmp_path / "d10" / "POOL_PICKS.jsonl")]  # fmt: skip

    def test_pool_picks_names_the_target_it_could_not_show_beside_its_picks(
        self, tmp_path: Path, capsys
    ) -> None:
        argv = self._pool_picks(tmp_path, {"a": []})
        assert CLI.main(argv) == 0
        printed = json.loads(capsys.readouterr().out)
        left = {"site_id": "a", "file": "Here.jpg", "reason": "refused: 960 px"}
        assert printed["picks"] == 0 and printed["left_out"] == [left]
        out = tmp_path / "d10" / "POOL_PICKS.jsonl"
        assert out.read_text(encoding="utf-8") == ""
        beside = CLI.left_out_file(out)
        assert beside.name == "POOL_PICKS_LEFT_OUT.jsonl"
        assert [json.loads(x) for x in beside.read_text(encoding="utf-8").splitlines()] == [left]
        assert CLI.main(argv) == 1  # both files are written once
        assert "written once" in capsys.readouterr().err

    def test_pool_picks_writes_neither_file_when_one_of_them_exists(
        self, tmp_path: Path, capsys
    ) -> None:
        argv = self._pool_picks(tmp_path, {"a": []})
        out = tmp_path / "d10" / "POOL_PICKS.jsonl"
        CLI.left_out_file(out).parent.mkdir()
        CLI.left_out_file(out).write_text("", encoding="utf-8")
        assert CLI.main(argv) == 1
        assert "POOL_PICKS_LEFT_OUT.jsonl exists" in capsys.readouterr().err
        assert not out.exists()

    def test_pool_picks_stop_on_a_live_hero_without_a_rendering(
        self, tmp_path: Path, capsys
    ) -> None:
        argv = self._pool_picks(tmp_path, {"a": [(5, "Here.jpg")]})
        assert CLI.main(argv) == 1
        assert "the picture of target 'Here.jpg' is gone" in capsys.readouterr().err
        assert not (tmp_path / "d10").exists()

    def test_the_search_floor_defaults_to_the_owners(self) -> None:
        args = CLI.build_parser().parse_args(["search", "--run-dir", "r"])
        assert (args.min_width, args.min_height, args.workers) == (800, 300, 1)

    def test_the_wiki_cache_default_is_the_shared_one_of_the_main_checkout(self) -> None:
        assert CLI.WIKI_CACHE.name == "wiki_cache"
        assert CLI.WIKI_CACHE.parent.name == "final-2026-10-08"
        assert not CLI.WIKI_CACHE.is_absolute()


class TestTheCalibrationCommands:
    def test_seal_prints_the_hash_and_a_second_seal_is_idempotent(
        self, tmp_path: Path, capsys
    ) -> None:
        assert CAL.main(["seal", "--dir", str(tmp_path)]) == 0
        first = json.loads(capsys.readouterr().out)["thresholds_sha256"]
        assert CAL.main(["seal", "--dir", str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out)["thresholds_sha256"] == first

    def test_a_step_out_of_order_exits_2(self, tmp_path: Path, capsys) -> None:
        assert CAL.main(["evaluate", "--dir", str(tmp_path), "--role", "image_prefilter"]) == 2
        assert "not sealed" in capsys.readouterr().err

    def test_the_measured_roles_and_the_exported_ones(self) -> None:
        assert CAL.MEASURED == ("image_prefilter", "image_depicts", "adversarial", "web_verifier")
        assert set(CAL.ROLE_SPECS) == set(CAL.MEASURED) | {"pilot_judge"}


def test_the_flow_module_names_every_file_of_the_run() -> None:
    assert FL.PICTURES == "PICTURES.jsonl" and FL.POPULATION_2 == "POPULATION_2.jsonl"


class TestTheBriefOfARoundedStage:
    """A stage with one file set per round (the re-check) is checked with `--round N`: the brief's
    check-answer command must carry it, or every agent's check is refused for a missing export
    record (image-roles-v2, 2026-11-06)."""

    def _rounded(self, tmp_path: Path) -> tuple[Path, Path]:
        from image_roles import hero_recheck as HR

        run, handoff = tmp_path / "run", tmp_path / "handoff"
        flat = [{"site_id": "s", "file": "a.jpg", "path": "/x"}]
        questions, pictures = PF.build_questions(flat, lambda c: jpeg())
        SG.export(run, handoff, HR.spec_for_round(1), questions, pictures)
        return run, handoff

    def test_the_brief_of_a_round_names_the_round_in_its_check_command(
        self, tmp_path: Path, capsys
    ) -> None:
        run, handoff = self._rounded(tmp_path)
        argv = ["brief", "--run-dir", str(run), "--handoff", str(handoff)]
        argv += ["--stage", "image-recheck", "--round", "1", "--batch-id", "pre-0001"]
        assert CLI.main(argv) == 0
        text = capsys.readouterr().out
        assert "--stage image-recheck --round 1 --batch-id pre-0001" in text

    def test_a_brief_without_a_round_names_none(self, tmp_path: Path, capsys) -> None:
        run, handoff = _exported(tmp_path)
        assert CLI.main(["brief", *_args(run, handoff, "--batch-id", "pre-0001")]) == 0
        text = capsys.readouterr().out
        assert "--stage image-prefilter --batch-id pre-0001" in text and "--round" not in text
