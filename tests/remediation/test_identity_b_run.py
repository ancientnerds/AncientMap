"""The identity package's command line, end to end on fixtures (`scripts/remediation/identity/run.py`).

DB-less and offline: the discovery's population functions are replaced by fixed questions, the live
read is a fake reader that answers by the statement it is sent, every cited page and title is stored
beforehand, and the plan directories are redirected into a temporary tree. What is tested is the
wiring - the export, the brief, the role and calibration gates at the import, the results, the waves,
the plans, the read-back and the chain - never a model.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import qid_repair as QR  # noqa: E402
import roles as RO  # noqa: E402
from identity import common  # noqa: E402
from identity import retarget as RT  # noqa: E402
from identity import retarget_plan as RP  # noqa: E402
from identity import rounds as R  # noqa: E402
from identity import run as RUN  # noqa: E402
from identity import scope_judge as SJ  # noqa: E402
from mechanical import apply as A  # noqa: E402

from tests.remediation import test_identity_b_retarget as TR  # noqa: E402
from tests.remediation import test_identity_b_scope as TS  # noqa: E402
from tests.remediation.identity_b_fixtures import (  # noqa: E402
    ENT,
    WP,
    answer_all,
    entity,
    html,
    store,
    write_calibration,
)
from tests.remediation.identity_fixtures import export_of  # noqa: E402


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A run directory, a calibration root and redirected plan directories."""
    run = tmp_path / "identity"
    run.mkdir()
    monkeypatch.setattr(A, "lane_dir", lambda lane: tmp_path / "lanes" / lane.out_dir_name)
    monkeypatch.setattr(QR, "OUT", tmp_path / "qid_repair")
    return tmp_path


def seal(root: Path, calibration_id: str, role: str, stage: str = "scope-window-web") -> None:
    write_calibration(root, calibration_id, role, stage)


def go(tree: Path, *argv: str) -> int:
    return RUN.main(["--run-dir", str(tree / "identity"), "--root", str(tree), *argv])


def seed_pages(
    stage_dir: Path, pages: dict[str, bytes], content_types: dict[str, str] | None = None
) -> None:
    for url, body in pages.items():
        store(
            stage_dir / "pages", url, body, content_type=(content_types or {}).get(url, "text/html")
        )


# ------------------------------------------------------------------------------ the scope lane
def scope_prod(rows: list[dict[str, Any]]):
    def reader(sql: str) -> list[dict[str, Any]]:
        assert sql.lstrip().upper().startswith("SELECT"), sql
        return rows

    return reader


class TestTheScopeLane:
    def test_a_question_stage_a_calibration_gate_a_wave_a_plan_and_a_read_back(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = tree / "identity"
        monkeypatch.setattr(
            SJ, "questions", lambda run_, root=None: [R.Question(TS.FORT, TS.context())]
        )
        handoff = tree / "h-web"
        assert (
            go(
                tree,
                "--lane",
                "scope-window",
                "export",
                "--stage",
                "scope-window-web",
                "--handoff",
                str(handoff),
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out) == {"batches": 1, "round": "r1", "sites": 1}
        assert (
            go(
                tree,
                "--lane",
                "scope-window",
                "export",
                "--stage",
                "scope-window-web",
                "--handoff",
                str(tree / "h2"),
            )
            == 1
        )
        assert "nothing to export" in capsys.readouterr().err

        assert (
            go(
                tree,
                "--lane",
                "scope-window",
                "brief",
                "--stage",
                "scope-window-web",
                "--round",
                "r1",
                "--batch-id",
                "r1-b01",
            )
            == 0
        )
        brief = capsys.readouterr().out
        assert (
            "--role web_verifier --model claude-sonnet-5-5" in brief and "scope-window-web" in brief
        )

        out = R.stage_dir(run, SJ.web_spec())
        answer_file = tree / "answer.json"
        answer_file.write_text(json.dumps(TS.answer("OUT_OF_WINDOW")), encoding="utf-8")
        check = [
            "--lane",
            "scope-window",
            "check-answer",
            "--stage",
            "scope-window-web",
            "--round",
            "r1",
            "--batch-id",
            "r1-b01",
            "--label",
            TS.FORT,
        ]
        assert go(tree, *check, "--text-file", str(answer_file)) == 0
        answer_file.write_text("{}", encoding="utf-8")
        capsys.readouterr()
        assert go(tree, *check, "--text-file", str(answer_file)) == 1

        record = R.find_round(out, "r1")
        answer_all(handoff, record, SJ.web_spec(), {TS.FORT: TS.answer("OUT_OF_WINDOW")})
        seed_pages(out, {TS.FORT_PAGE: html(TS.FORT_TEXT)})
        capsys.readouterr()
        importing = ["--lane", "scope-window", "import", "--stage", "scope-window-web", "--round", "r1",
                     "--calibration", "scope-web", "--calibration-root", str(tree / "cal")]  # fmt: skip
        assert go(tree, *importing) == 1, "no verdict yet"
        assert "has no verdict" in capsys.readouterr().err
        seal(tree / "cal", "scope-web", "web_verifier")
        assert go(tree, *importing) == 0
        summary = json.loads(capsys.readouterr().out)
        assert (summary["decided"], summary["held"], summary["calibration"]) == (1, 0, "scope-web")

        # the re-check of the retirement
        rhandoff = tree / "h-re"
        assert (
            go(
                tree,
                "--lane",
                "scope-window",
                "export",
                "--stage",
                "scope-window-recheck",
                "--handoff",
                str(rhandoff),
            )
            == 0
        )
        rout = R.stage_dir(run, SJ.recheck_spec())
        confirm = {
            "site_id": TS.FORT,
            "verdict": "CONFIRM",
            "why": "read the pages",
            "quotes": [TS.q(TS.FORT_PAGE, TS.FORT_TEXT)],
        }
        answer_all(rhandoff, R.find_round(rout, "r1"), SJ.recheck_spec(), {TS.FORT: confirm})
        seed_pages(rout, {TS.FORT_PAGE: html(TS.FORT_TEXT)})
        seal(tree / "cal", "scope-re", "adversarial")
        capsys.readouterr()
        assert go(tree, "--lane", "scope-window", "import", "--stage", "scope-window-recheck", "--round", "r1",
                  "--calibration", "scope-re", "--calibration-root", str(tree / "cal")) == 0  # fmt: skip

        capsys.readouterr()
        assert go(tree, "--lane", "scope-window", "result") == 0
        result = json.loads(capsys.readouterr().out)
        assert (
            result["by_verdict_and_state"] == {"OUT_OF_WINDOW:confirmed": 1}
            and result["owner_list"] == 0
        )

        assert go(tree, "--lane", "scope-window", "wave", "--wave", "2026-10-12") == 0
        assert json.loads(capsys.readouterr().out)["sites"] == [TS.FORT]
        monkeypatch.setattr(RUN, "read_only_reader", lambda: scope_prod([TS.live_row()]))
        assert go(tree, "--lane", "scope-window", "plan", "--wave", "2026-10-12") == 0
        planned = json.loads(capsys.readouterr().out)
        assert planned["NULL->retired"] == 1 and planned["lane"] == "scope-window-2026-10-12"
        lane_out = tree / "lanes" / "mechanical_scope_window" / "2026-10-12"
        assert {p.name for p in lane_out.iterdir()} == {
            "PLAN.jsonl",
            "SKIPPED.jsonl",
            "PLAN.md",
            "ROLLBACK.sql",
        }
        records = [
            json.loads(line) for line in (lane_out / "PLAN.jsonl").read_text("utf-8").splitlines()
        ]
        assert {r["column"] for r in records} == {"scope_status", "scope_reason"}
        assert (run / "scope-window" / "waves" / "2026-10-12" / "PERIOD_WRONG.jsonl").exists()

        # the read-back: production holds what the plan wrote
        landed = TS.live_row(scope_status="retired", scope_reason=records[1]["new_value"])
        monkeypatch.setattr(
            RUN,
            "read_only_reader",
            lambda: scope_prod(
                [{"site_id": TS.FORT, **{k: landed[k] for k in ("scope_status", "scope_reason")}}]
            ),
        )
        assert go(tree, "--lane", "scope-window", "verify", "--wave", "2026-10-12") == 0
        assert json.loads(capsys.readouterr().out)["accepted"] is True
        monkeypatch.setattr(
            RUN,
            "read_only_reader",
            lambda: scope_prod([{"site_id": TS.FORT, "scope_status": None, "scope_reason": None}]),
        )
        assert go(tree, "--lane", "scope-window", "verify", "--wave", "2026-10-12") == 1
        assert json.loads(capsys.readouterr().out)["deviations"] == 2

    def test_the_import_refuses_an_answer_under_the_wrong_role(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = tree / "identity"
        monkeypatch.setattr(
            SJ, "questions", lambda run_, root=None: [R.Question(TS.FORT, TS.context())]
        )
        handoff = tree / "h"
        go(
            tree,
            "--lane",
            "scope-window",
            "export",
            "--stage",
            "scope-window-web",
            "--handoff",
            str(handoff),
        )
        out = R.stage_dir(run, SJ.web_spec())
        OH.write_answer(
            handoff, batch_id="r1-b01", stage="scope-window-web", label=TS.FORT,
            text=json.dumps(TS.answer("OUT_OF_WINDOW")), answered_by=RO.answered_by("adversarial", "r1-b01"),
            model=OH.OPUS_MODEL, now=lambda: "2026-10-09T02:00:00+00:00",
        )  # fmt: skip
        seed_pages(out, {TS.FORT_PAGE: html(TS.FORT_TEXT)})
        seal(tree / "cal", "c", "web_verifier")
        capsys.readouterr()
        code = go(tree, "--lane", "scope-window", "import", "--stage", "scope-window-web", "--round", "r1",
                  "--calibration", "c", "--calibration-root", str(tree / "cal"))  # fmt: skip
        assert code == 1 and "recorded under adversarial" in capsys.readouterr().err

    def test_the_import_refuses_answers_given_before_the_calibration_and_another_lane_s_pool(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = tree / "identity"
        monkeypatch.setattr(
            SJ, "questions", lambda run_, root=None: [R.Question(TS.FORT, TS.context())]
        )
        handoff = tree / "h"
        go(
            tree,
            "--lane",
            "scope-window",
            "export",
            "--stage",
            "scope-window-web",
            "--handoff",
            str(handoff),
        )
        out = R.stage_dir(run, SJ.web_spec())
        answer_all(
            handoff, R.find_round(out, "r1"), SJ.web_spec(), {TS.FORT: TS.answer("OUT_OF_WINDOW")}
        )
        seed_pages(out, {TS.FORT_PAGE: html(TS.FORT_TEXT)})
        importing = ["--lane", "scope-window", "import", "--stage", "scope-window-web", "--round", "r1",
                     "--calibration", "c", "--calibration-root", str(tree / "cal")]  # fmt: skip
        write_calibration(
            tree / "cal",
            "c",
            "web_verifier",
            "scope-window-web",
            decided_at="2026-10-10T00:00:00+00:00",
        )
        capsys.readouterr()
        assert go(tree, *importing) == 1
        assert "given before the calibration was decided (2026-10-10" in capsys.readouterr().err
        assert not (out / R.DECISIONS_FILE).exists()
        # a calibration measured on the retarget lane's questions is no gate of the scope window
        write_calibration(tree / "cal", "other", "web_verifier", "retarget-web")
        assert (
            go(
                tree,
                *importing[:-4],
                "--calibration",
                "other",
                "--calibration-root",
                str(tree / "cal"),
            )
            == 1
        )
        assert "not on the lane's own scope-window-web" in capsys.readouterr().err

    def test_the_rest_of_the_population_is_exported_after_a_pilot_was_imported(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = tree / "identity"
        sites = [f"{i:08d}-0000-4000-8000-000000000000" for i in range(4)]
        monkeypatch.setattr(
            SJ, "questions",
            lambda run_, root=None: [R.Question(s, {**TS.context(), "site_id": s}) for s in sites],
        )  # fmt: skip
        export = ["--lane", "scope-window", "export", "--stage", "scope-window-web"]
        assert go(tree, *export, "--handoff", str(tree / "h1"), "--pilot", "2") == 0
        pilot = json.loads(capsys.readouterr().out)
        assert (pilot["round"], pilot["sites"]) == ("r1", 2)
        out = R.stage_dir(run, SJ.web_spec())
        assert go(tree, *export, "--handoff", str(tree / "h2")) == 1
        assert "not imported" in capsys.readouterr().err
        (out / R.ANSWERS_DIR).mkdir()
        (out / R.ANSWERS_DIR / "r1.jsonl").write_text("", encoding="utf-8")
        assert go(tree, *export, "--handoff", str(tree / "h2")) == 0
        rest = json.loads(capsys.readouterr().out)
        assert (rest["round"], rest["sites"]) == ("r2", 2)
        asked = [s for r in R.load_rounds(out) for s in r.sites]
        assert sorted(asked) == sites and len(set(asked)) == 4
        assert go(tree, *export, "--handoff", str(tree / "h3")) == 1

    def test_a_stage_that_does_not_exist_is_refused(
        self, tree: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert go(tree, "--lane", "scope-window", "status", "--stage", "nope") == 1
        assert "no stage 'nope' in lane 'scope-window'" in capsys.readouterr().err

    def test_a_sites_file_and_a_pilot_choose_the_questions(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        many = [R.Question(f"s{i:02d}", {"site_id": f"s{i:02d}"}) for i in range(10)]
        args = RUN.build_parser().parse_args(
            ["--lane", "scope-window", "export", "--stage", "x", "--handoff", "h", "--pilot", "5"]
        )
        assert [q.site_id for q in RUN._pick(many, args)] == ["s00", "s02", "s04", "s06", "s08"]
        listed = tree / "sites.txt"
        listed.write_text("s03\ns01\n\n", encoding="utf-8")
        args = RUN.build_parser().parse_args(
            [
                "--lane",
                "scope-window",
                "export",
                "--stage",
                "x",
                "--handoff",
                "h",
                "--sites-file",
                str(listed),
            ]
        )
        assert [q.site_id for q in RUN._pick(many, args)] == ["s03", "s01"]
        listed.write_text("s99\n", encoding="utf-8")
        with pytest.raises(RUN.UsageError, match="not in the population still to ask"):
            RUN._pick(many, args)


# ------------------------------------------------------------------------------ the retarget lane
PAGES = {
    ENT.format("Q200"): entity(
        "Q200", "Kydonia", 35.5190, 24.0150, {"en": ["Cydonia"]}, "ancient city in Crete"
    ),
    WP + "Kydonia": html(TR.KYDONIA_TEXT, TR.COORD_TEXT),
    WP + "Chania": html("Chania is a city on the island of Crete, Greece."),
}
CONTENT_TYPES = {ENT.format("Q200"): "application/json"}


class FakeProduction:
    """Production as the retarget plan reads it: before the link step, and after the whole chain."""

    def __init__(self) -> None:
        self.stage = "before"

    def site(self) -> dict[str, Any]:
        if self.stage == "before":
            return {"site_id": TR.CHANIA, "source_id": "ancient_nerds", "name": "Chania", "name_normalized": "chania",
                    "country": "Greece", "lat": "35.5135", "lon": "24.018", "source_url": WP + "Chania", "scope_status": None,
                    "ext": [{"kind": "enwiki_title", "value": "Chania"}, {"kind": "wikidata_qid", "value": "Q100"}],
                    "premise": "enwiki_title=Chania, wikidata_qid=Q100"}  # fmt: skip
        landed = {"site_id": TR.CHANIA, "source_id": "ancient_nerds", "country": "Greece", "lat": "35.5135", "lon": "24.018",
                  "source_url": WP + "Kydonia", "scope_status": None,
                  "ext": [{"kind": "enwiki_title", "value": "Kydonia"}, {"kind": "wikidata_qid", "value": "Q200"}],
                  "premise": "enwiki_title=Kydonia, wikidata_qid=Q200"}  # fmt: skip
        if self.stage == "links":
            return {**landed, "name": "Chania", "name_normalized": "chania"}
        return {**landed, "name": "Kydonia", "name_normalized": "kydonia"}

    def name_rows(self) -> list[dict[str, Any]]:
        kind = "alias" if self.stage == "done" else "label"
        rows = [
            {
                "id": 7,
                "site_id": TR.CHANIA,
                "name": "Chania",
                "name_normalized": "chania",
                "name_type": kind,
            }
        ]
        if self.stage == "done":
            rows.append(
                {
                    "id": 8,
                    "site_id": TR.CHANIA,
                    "name": "Kydonia",
                    "name_normalized": "kydonia",
                    "name_type": "label",
                }
            )
        return rows

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        assert sql.lstrip().upper().startswith("SELECT"), sql
        if "FROM unified_sites u WHERE u.id IN" in sql:
            return [self.site()]
        if "e.kind = 'wikidata_qid'" in sql:
            return []
        if "FROM (VALUES" in sql:
            return [{"name": "Kydonia", "key": "kydonia"}]
        if "u.name_normalized IN" in sql:
            return []
        if "FROM unified_site_names n" in sql:
            return self.name_rows()
        raise AssertionError(sql)


def run_json(tree: Path, capsys: Any, *argv: str) -> tuple[int, Any, str]:
    """One command: its exit code, its JSON output (None when it printed none) and its stderr."""
    capsys.readouterr()
    code = go(tree, *argv)
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if captured.out.strip() else None), captured.err


class TestTheRetargetLane:
    def run_stage(
        self,
        tree: Path,
        stage: str,
        spec: R.StageSpec,
        texts: dict[str, Any],
        role_id: str,
        capsys: Any,
    ) -> None:
        run = tree / "identity"
        out = R.stage_dir(run, spec)
        record = R.find_round(out, "r1")
        answer_all(Path(record.handoff), record, spec, texts)
        seed_pages(out, PAGES, CONTENT_TYPES)
        (out / R.TITLES_FILE).write_text(json.dumps({"titles": TR.TITLES}), encoding="utf-8")
        seal(tree / "cal", role_id, spec.role, "retarget-web")
        capsys.readouterr()
        code = go(tree, "--lane", "retarget", "import", "--stage", stage, "--round", "r1",
                  "--calibration", role_id, "--calibration-root", str(tree / "cal"))  # fmt: skip
        assert code == 0, capsys.readouterr().err

    def test_the_whole_chain_from_the_question_to_the_hand_off_lists(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = tree / "identity"
        W = "2026-10-12"
        monkeypatch.setattr(RUN.export, "load_export", lambda path: export_of([]))
        monkeypatch.setattr(
            RT, "web_questions",
            lambda run_, root=None, sites=None, exclude=(): [R.Question(TR.CHANIA, TR.context())],
        )  # fmt: skip
        code, _, _ = run_json(
            tree,
            capsys,
            "--lane",
            "retarget",
            "export",
            "--stage",
            "retarget-web",
            "--handoff",
            str(tree / "h1"),
        )
        assert code == 0
        self.run_stage(
            tree, "retarget-web", RT.web_spec({}), {TR.CHANIA: TR.answer()}, "web", capsys
        )
        code, status, _ = run_json(
            tree, capsys, "--lane", "retarget", "status", "--stage", "retarget-web"
        )
        assert (code, status["decided"], status["held"], status["model"]) == (
            0,
            1,
            0,
            "claude-sonnet-5-5",
        )

        code, _, _ = run_json(
            tree,
            capsys,
            "--lane",
            "retarget",
            "export",
            "--stage",
            "retarget-recheck",
            "--handoff",
            str(tree / "h2"),
        )
        assert code == 0
        confirm = {"site_id": TR.CHANIA, "verdict": "CONFIRM", "why": "read the article",
                   "quotes": [TR.q(WP + "Kydonia", TR.KYDONIA_TEXT)]}  # fmt: skip
        self.run_stage(
            tree, "retarget-recheck", RT.recheck_spec(), {TR.CHANIA: confirm}, "adv", capsys
        )

        code, result, _ = run_json(tree, capsys, "--lane", "retarget", "result")
        assert code == 0 and result["by_verdict_and_state"] == {"RETARGET:confirmed": 1}
        assert (run / "retarget" / "RESULT.jsonl").exists()
        assert (run / "retarget" / "OWNER_LIST.jsonl").read_text("utf-8") == ""

        code, wave, _ = run_json(tree, capsys, "--lane", "retarget", "wave", "--wave", W)
        assert code == 0 and wave["sites"] == [TR.CHANIA]

        # the links step, planned against production before the write
        prod = FakeProduction()
        monkeypatch.setattr(RUN, "read_only_reader", lambda: prod)
        code, planned, _ = run_json(tree, capsys, "--lane", "retarget", "plan-links", "--wave", W)
        assert (code, planned["links"], planned["sites"], planned["skipped"]) == (0, 3, 1, 0)
        step = tree / "qid_repair" / "d13" / W / "step-001"
        assert (step / "APPLY.sql").exists() and (step / "ROLLBACK.sql").exists()

        # the name waits for its link step
        code, waiting, _ = run_json(tree, capsys, "--lane", "retarget", "plan-names", "--wave", W)
        assert (code, waiting["cells"], waiting["skipped"]) == (0, 0, 1)
        name_out = tree / "lanes" / "mechanical_names" / "retarget-name" / W
        assert "links-not-landed" in (name_out / "SKIPPED.jsonl").read_text("utf-8")

        # a site a wave skipped is not selected again: the result lists it, with the wave and why
        code, listed, _ = run_json(tree, capsys, "--lane", "retarget", "result")
        assert code == 0 and listed["wave_skips"] == 1 and listed["owner_list"] == 1
        (skip,) = common.read_jsonl(run / "retarget" / "WAVE_SKIPS.jsonl")
        assert (skip["wave"], skip["site_id"], skip["reason"]) == (W, TR.CHANIA, "links-not-landed")
        (owner,) = common.read_jsonl(run / "retarget" / "OWNER_LIST.jsonl")
        assert (
            owner["state"] == "skipped-in-wave" and f"wave {W}: links-not-landed" in owner["reason"]
        )

        # the links landed: the name and its alias are planned
        prod.stage = "links"
        assert not (name_out / "PLAN.jsonl").exists(), "a plan that writes nothing leaves no plan"
        code, named, _ = run_json(tree, capsys, "--lane", "retarget", "plan-names", "--wave", W)
        assert (code, named["cells"], named["aliases"]) == (0, 2, 1) and len(
            named["alias_chunks"]
        ) == 1
        assert (name_out / "alias" / "chunk-001" / "APPLY.sql").exists()

        # nothing has finished the chain yet: no hand-off
        code, _, err = run_json(tree, capsys, "--lane", "retarget", "handoffs", "--wave", W)
        assert code == 1 and "has finished links, name and alias" in err

        def chain_done(stage: str, stamp: str) -> tuple[int, str]:
            code_, _, err_ = run_json(tree, capsys, "--lane", "retarget", "chain-done", "--wave", W,
                                      "--stage-name", stage, "--stamp", stamp)  # fmt: skip
            return code_, err_

        # a stage is recorded against production, not on trust: before the link step, and for the
        # name while only the links landed, the record is refused
        prod.stage = "before"
        code, err = chain_done("links", f"{W}_d13-links-001")
        assert code == 1 and "links has not landed" in err
        prod.stage = "links"
        skips = run / "retarget" / "waves" / W / "LINKS_SKIPPED.jsonl"
        kept = skips.read_text("utf-8")
        skips.write_text(
            json.dumps({"site_id": TR.CHANIA, "reason": "name-key-taken", "note": "n"}) + "\n",
            encoding="utf-8",
        )
        code, err = chain_done("links", f"{W}_d13-links-001")
        assert code == 1 and "a plan skipped it: name-key-taken" in err
        skips.write_text(kept, encoding="utf-8")
        assert chain_done("links", f"{W}_d13-links-001")[0] == 0
        code, err = chain_done("name", f"{W}_mechanical-retarget-name")
        assert code == 1 and "name has not landed" in err
        prod.stage = "done"
        assert chain_done("name", f"{W}_mechanical-retarget-name")[0] == 0
        assert chain_done("alias", f"retarget-name-alias-{W}-001")[0] == 0
        code, ready, _ = run_json(
            tree, capsys, "--lane", "retarget", "chain-ready", "--stage-name", "point_type"
        )
        assert (code, ready) == (0, [TR.CHANIA])

        code, verified, _ = run_json(tree, capsys, "--lane", "retarget", "verify", "--wave", W)
        assert (code, verified["landed"], verified["deviations"]) == (0, 1, 0)
        prod.stage = "links"
        code, verified, _ = run_json(tree, capsys, "--lane", "retarget", "verify", "--wave", W)
        assert code == 1 and verified["deviations"] == 1

        # a site that finished the chain but no longer reads back as landed is handed on to no lane
        code, _, err = run_json(tree, capsys, "--lane", "retarget", "handoffs", "--wave", W)
        assert code == 1 and "reads back as landed" in err
        assert not (run / "retarget" / "waves" / W / RP.HANDOFF_FILES["point_type"]).exists()
        prod.stage = "done"
        code, counts, _ = run_json(tree, capsys, "--lane", "retarget", "handoffs", "--wave", W)
        assert code == 0 and counts == {**dict.fromkeys(RP.HANDOFF_FILES, 1), "withheld": 0}
        code, table, _ = run_json(tree, capsys, "--lane", "retarget", "chain-status")
        assert code == 0 and table[0]["next"] == "point_type"
        code, _, err = run_json(
            tree,
            capsys,
            "--lane",
            "retarget",
            "chain-done",
            "--wave",
            W,
            "--stage-name",
            "card",
            "--stamp",
            "x",
        )
        assert code == 1 and "card waits for point_type" in err


# ------------------------------------------------------------------------------ the names lane
class TestTheNamesLane:
    def test_the_clean_name_export_can_leave_out_the_records_d13_has_not_left_alone(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import common
        from identity import names_judge as NJ

        from tests.remediation import test_identity_b_names as TN

        run = tree / "identity"
        seen: dict[str, Any] = {}

        def fake(
            run_: Path, root: Path | None = None, exclude: Any = (), rule_made: bool = False
        ) -> list[R.Question]:
            seen["exclude"] = sorted(exclude)
            return [R.Question(TN.DOLMEN, TN.context())]

        monkeypatch.setattr(NJ, "clean_questions", fake)
        export = ["--lane", "names", "export", "--stage", "name-clean-web"]
        code, _, err = run_json(
            tree, capsys, *export, "--handoff", str(tree / "h0"), "--exclude-retarget"
        )
        assert code == 1 and "run `--lane retarget result` first" in err

        (run / "retarget").mkdir()
        common.write_jsonl(
            run / "retarget" / "RESULT.jsonl",
            [{"site_id": "a", "state": "keep", "verdict": "KEEP"},
             {"site_id": "b", "state": "confirmed", "verdict": "RETARGET"},
             {"site_id": "c", "state": "held", "verdict": None}],
        )  # fmt: skip
        code, out, _ = run_json(
            tree, capsys, *export, "--handoff", str(tree / "h1"), "--exclude-retarget"
        )
        assert code == 0 and out["sites"] == 1 and seen["exclude"] == ["b", "c"]
        (tree / "identity" / "names" / "name-clean-web" / "ROUNDS.jsonl").unlink()
        shutil.rmtree(tree / "identity" / "names" / "name-clean-web" / "contexts")
        code, _, _ = run_json(tree, capsys, *export, "--handoff", str(tree / "h2"))
        assert code == 0 and seen["exclude"] == []

    def test_the_rule_made_renames_leave_out_the_records_d13_has_not_left_alone_too(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import common
        from identity import names_judge as NJ

        from tests.remediation import test_identity_b_names as TN

        seen: dict[str, Any] = {}

        def fake(
            run_: Path, root: Path | None = None, exclude: Any = (), rule_made: bool = False
        ) -> list[R.Question]:
            seen["exclude"], seen["rule_made"] = sorted(exclude), rule_made
            return [R.Question(TN.ALBANIANA, TN.rule_ctx())]

        monkeypatch.setattr(NJ, "clean_questions", fake)
        (tree / "identity" / "retarget").mkdir()
        common.write_jsonl(
            tree / "identity" / "retarget" / "RESULT.jsonl",
            [{"site_id": "a", "state": "keep", "verdict": "KEEP"},
             {"site_id": "b", "state": "confirmed", "verdict": "RETARGET"}],
        )  # fmt: skip
        code, out, _ = run_json(
            tree, capsys, "--lane", "names", "export", "--stage", "name-clean-recheck",
            "--handoff", str(tree / "h"), "--exclude-retarget",
        )  # fmt: skip
        assert code == 0 and out["sites"] == 1
        assert seen == {"exclude": ["b"], "rule_made": True}

    def test_a_spoken_name_is_not_made_for_a_site_whose_name_another_lane_still_changes(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from identity import common
        from identity import names_judge as NJ

        run = tree / "identity"
        monkeypatch.setattr(NJ, "clean_questions", lambda *a, **k: [R.Question("rule", {})])
        (run / "retarget").mkdir()
        common.write_jsonl(
            run / "retarget" / "RESULT.jsonl",
            [{"site_id": "kept", "state": "keep", "verdict": "KEEP"},
             {"site_id": "moved", "state": "confirmed", "verdict": "RETARGET"}],
        )  # fmt: skip
        common.write_jsonl(
            run / NJ.TRIAGE_FILE, [{"id": i} for i in ("settled", "renamed", "rule", "moved")]
        )
        web = R.stage_dir(run, NJ.clean_spec())
        R.write_jsonl(
            web / R.DECISIONS_FILE,
            [{"site_id": "settled", "status": R.DECIDED, "data": {"verdict": "KEEP"}}],
        )
        # a record D13 holds, a name defect no one settled and a rule-made rename are left out;
        # a KEEP and a record D13 leaves alone are not
        assert RUN.spoken_exclusions(run, None) == ["moved", "renamed", "rule"]

    def test_the_spoken_names_to_write_leave_out_the_sites_another_lane_still_renames(
        self, tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import names_judge as NJ

        rule = [{"id": s, "name": "Tiverton, Devon", "spoken": "Tiverton", "source": "name", "steps": []}
                for s in ("a", "b")]  # fmt: skip
        monkeypatch.setattr(NJ, "rule_spoken", lambda run_: rule)
        monkeypatch.setattr(RUN, "spoken_exclusions", lambda run_, root: ["a"])
        code, got, _ = run_json(tree, capsys, "--lane", "names", "--kind", "spoken", "result")
        assert code == 0 and got["to_write"] == 1 and got["left_out"] == 1

    def test_a_names_command_needs_its_kind(
        self, tree: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, _, err = run_json(tree, capsys, "--lane", "names", "result")
        assert code == 1 and "needs --kind clean or --kind spoken" in err


def test_a_wave_label_is_a_date_and_an_optional_letter() -> None:
    import argparse

    assert (
        RUN.wave_label("2026-10-12") == "2026-10-12"
        and RUN.wave_label("2026-10-12b") == "2026-10-12b"
    )
    for bad in ("2026-10-1", "x", "2026-10-12bb", "2026-10-12-s001", ""):
        with pytest.raises(argparse.ArgumentTypeError, match="not a wave label"):
            RUN.wave_label(bad)


def test_a_pilot_answered_twice_is_compared_through_the_command_line(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = tree / "first", tree / "second"
    for out, verdict in ((first, "OUT_OF_WINDOW"), (second, "NOT_A_SITE")):
        out.mkdir()
        R.write_jsonl(
            out / R.DECISIONS_FILE,
            [{"site_id": TS.FORT, "status": R.DECIDED, "data": {"verdict": verdict}}],
        )
    code, got, _ = run_json(
        tree, capsys, "--lane", "scope-window", "agreement", "--stage", "scope-window-web",
        "--stage-dir", str(first), "--other-stage-dir", str(second),
    )  # fmt: skip
    assert code == 0 and got["shared"] == 1 and got["agree"] == 0
    assert got["disagree"][0]["first"] == "OUT_OF_WINDOW"


def test_every_documented_run_command_line_parses() -> None:
    """The command lines of the docstrings of `run.py` and `calibration.py` are the operator's: a
    stage option before the subcommand, an alternative or an optional part left undeclared, would
    exit 2 on the day it is typed."""
    import re
    import shlex

    from identity import calibration as CAL

    placeholders = {"L": "retarget", "S": "retarget-web", "W": "2026-10-12", "N": "20"}
    lines = [
        raw.strip()
        for doc in (RUN.__doc__, CAL.__doc__)
        for raw in (doc or "").splitlines()
        if raw.strip().startswith("$PY $I/run.py")
    ]
    assert len(lines) >= 20
    for line in lines:
        words = shlex.split(re.sub(r"\[[^\]]*\]", "", line.split("  #")[0]))[2:]
        argv = [placeholders.get(w, w.split("|")[0]) for w in words]
        argv = [
            "x" if w.isupper() and w not in ("L", "S") and not w.startswith("-") else w
            for w in argv
        ]
        args = RUN.build_parser().parse_args(argv)
        assert args.command in argv, line
