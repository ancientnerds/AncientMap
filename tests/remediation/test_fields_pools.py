"""Lane wd5, the calibration pools (`scripts/remediation/fields/pools.py`, D6 of 2026-10-08).

The map names three pools: 60 WD1 sites stratified by field (the field researcher, answers hidden),
about 25 sites whose earlier reasoning named an age in years before the present (the same role, the
BP reader), 40 audit cells (the adversarial checker). Offline: the run tree is a miniature built in a
temporary directory, no model is called, no page is fetched.
"""

# ruff: noqa: S311 - the draws are seeded and recorded, they must repeat; nothing here is a secret
from __future__ import annotations

import dataclasses
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import calibrate_claude as CC  # noqa: E402
import mcode_driver as D  # noqa: E402
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from fields import adversarial as AD  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import pools as PL  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation import test_fields_handoff as TH  # noqa: E402
from tests.remediation import test_fields_wd3 as TW  # noqa: E402

NOW = "2026-10-09T09:00:00+00:00"


def site_id(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


# ------------------------------------------------------------------------------ a WD1 world
def wd1_line(site: str, fields: list[str], name: str) -> dict[str, Any]:
    line = TH.classified_line(site, name, "Greece", fields)
    line["name"] = name
    return line


def decision(site: str, field: str, verdict: str = "keep", *, via: str = "counted", round_: int = 0,
             value: Any = None, name: str = "S") -> dict[str, Any]:  # fmt: skip
    return {"site_id": site, "name": name, "field": field, "status": "MISSING", "stored": None,
            "asked": 1, "decision": verdict, "value": value, "via": via, "round": round_,
            "counted_rounds": [round_], "answered_by": "b", "model": None, "quotes": [],
            "reasoning": "r", "value_page": None}  # fmt: skip


def answer_text(**fields: tuple[str, Any]) -> str:
    return json.dumps(
        {
            "fields": {
                f: {"decision": d, "value": v, "quotes": [{"url": TH.WIKI, "quote": "q"}] if d in
                    ("keep", "replace") else [], "reasoning": "r"}
                for f, (d, v) in fields.items()
            }
        }
    )  # fmt: skip


class World:
    """`fields/<run>/` for the four WD1 runs, each with one round 0 whose handoff is under `handoff/`."""

    def __init__(self, tmp_path: Path) -> None:
        self.base = tmp_path / "checkout"
        self.fields = self.base / "output" / "remediation" / "fields"
        self.handoff = self.base / "output" / "remediation" / "handoff"
        self.sites = 0

    def run(self, name: str, specs: list[tuple[list[str], str]], *, model: str = OH.OPUS_MODEL,
            counted: bool = True, decided_round: int = 0) -> Path:  # fmt: skip
        """One WD1 run asking `specs = [(fields, name)]`: every field answered `keep`/`replace`."""
        run = self.fields / name
        run.mkdir(parents=True)
        lines, decisions = [], []
        for fields, label in specs:
            self.sites += 1
            site = site_id(self.sites)
            lines.append(wd1_line(site, fields, label))
            decisions += [decision(site, f, "replace" if f == "site_type" else "keep",
                                   via="counted" if counted else "exhausted",
                                   round_=decided_round if counted else 2,
                                   value="Temple" if f == "site_type"
                                   else None, name=label) for f in fields]  # fmt: skip
        HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
        HO._write_jsonl(run / HO.DECISIONS_FILE, decisions)
        handoff = self.handoff / f"fields-{name}-r0"
        result = HO.export(run, handoff)
        assert result["round"] == 0
        for batch_id, labels in HO.read_rounds(run)[0]["batches"].items():
            for label in labels:
                fields = HO.read_rounds(run)[0]["fields"][label]
                OH.write_answer(
                    handoff, batch_id=batch_id, stage=HO.STAGE, label=label,
                    text=answer_text(**{f: (("replace", "Temple") if f == "site_type" else
                                            ("keep", None)) for f in fields}),
                    answered_by=batch_id, model=model,
                )  # fmt: skip
        return run

    def standard(self) -> None:
        """Two sites per field in each of the four runs: eight sites asked the field in all."""
        for name in POP.WD1_RUN_NAMES:
            self.run(name, [(["coordinates", "period_start"], f"{name} A"),
                            (["site_type", "source_url"], f"{name} B")])  # fmt: skip


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


class TestTheGeneralPool:
    def test_the_recorded_handoff_is_read_in_the_checkout_that_ran_it(self, tmp_path: Path) -> None:
        fields = tmp_path / "output" / "remediation" / "fields"
        assert PL.recorded_handoff({"handoff": "output/remediation/handoff/x"}, fields) == (
            tmp_path / "output" / "remediation" / "handoff" / "x"
        )
        absolute = tmp_path / "elsewhere"
        assert PL.recorded_handoff({"handoff": str(absolute)}, fields) == absolute

    def test_a_site_is_eligible_when_every_asked_field_counted_in_round_zero(
        self, world: World
    ) -> None:
        world.standard()
        eligible = PL.wd1_eligible(world.fields)
        assert len(eligible) == 8
        first = next(iter(eligible.values()))
        assert first.handoff.name.startswith("fields-wd1") and first.batch.startswith("wd1-r0-b")

    def test_a_field_that_ended_exhausted_makes_its_site_ineligible(self, world: World) -> None:
        for name in POP.WD1_RUN_NAMES[:3]:
            world.run(name, [(["period_start"], name)])
        world.run(POP.WD1_RUN_NAMES[3], [(["period_start"], "late")], counted=False)
        assert len(PL.wd1_eligible(world.fields)) == 3

    def test_a_field_counted_only_after_a_re_ask_makes_its_site_ineligible(
        self, world: World
    ) -> None:
        for name in POP.WD1_RUN_NAMES[:3]:
            world.run(name, [(["period_start"], name)])
        world.run(POP.WD1_RUN_NAMES[3], [(["period_start"], "late")], decided_round=1)
        assert len(PL.wd1_eligible(world.fields)) == 3

    def test_an_answer_that_carries_no_known_stamp_is_no_gold(self, world: World) -> None:
        for name in POP.WD1_RUN_NAMES[:3]:
            world.run(name, [(["period_start"], name)])
        run = world.run(POP.WD1_RUN_NAMES[3], [(["period_start"], "odd")])
        [answer_file] = (world.handoff / f"fields-{run.name}-r0").rglob("*.answer.json")
        body = json.loads(answer_file.read_text(encoding="utf-8"))
        answer_file.write_text(json.dumps({**body, "model": "a-model-nobody-registered"}), "utf-8")
        assert len(PL.wd1_eligible(world.fields)) == 3

    def test_a_run_that_asked_nothing_is_refused_by_name(self, world: World) -> None:
        for name in POP.WD1_RUN_NAMES[:3]:
            world.run(name, [(["period_start"], name)])
        silent = world.fields / POP.WD1_RUN_NAMES[3]
        silent.mkdir()
        HO._write_jsonl(silent / HO.ROUNDS_FILE, [])
        with pytest.raises(PL.PoolError, match="has no round 0"):
            PL.wd1_eligible(world.fields)

    def test_a_site_a_minimax_model_answered_is_never_ground_truth(self, world: World) -> None:
        for name in POP.WD1_RUN_NAMES[:3]:
            world.run(name, [(["period_start"], name)])
        world.run(POP.WD1_RUN_NAMES[3], [(["period_start"], "m")], model=OH.MINIMAX_MODEL)
        assert len(PL.wd1_eligible(world.fields)) == 3

    def test_the_draw_goes_round_robin_over_the_fields(self, world: World) -> None:
        world.standard()
        eligible = PL.wd1_eligible(world.fields)
        picked = PL.stratify(eligible, 6, random.Random(1))
        assert len(picked) == 6
        # every field has sites that ask it: the draw takes one of each before it takes a second
        assert {picked[s] for s in picked} == set(C.FIELDS)
        assert sorted(PL.stratify(eligible, 6, random.Random(1))) == sorted(picked)

    def test_a_field_with_no_sites_left_gives_its_turn_to_the_others(self, world: World) -> None:
        world.standard()
        picked = PL.stratify(PL.wd1_eligible(world.fields), 8, random.Random(1))
        assert len(picked) == 8
        # a site drawn for one field is not drawn again for another: two sites each
        assert dict(Counter(picked.values())) == dict.fromkeys(C.FIELDS, 2)

    def test_more_sites_than_are_eligible_is_refused_by_name(self, world: World) -> None:
        world.standard()
        with pytest.raises(PL.PoolError, match="only 8 WD1 sites are eligible, 9 are wanted"):
            PL.stratify(PL.wd1_eligible(world.fields), 9, random.Random(1))

    def test_the_pool_is_the_copied_questions_and_their_recorded_answers(
        self, world: World, tmp_path: Path
    ) -> None:
        world.standard()
        out = tmp_path / "pool"
        result = PL.build_general(out, seed=3, size=8, fields_dir=world.fields)
        assert result["sites"] == 8 and result["pool"] == "frg"
        assert result["batches"] == ["frg-r0-b0001"]
        assert OH.validate(out / "handoff").ok  # every recorded answer names its prompt's digest
        manifest = OH.manifest(out / "handoff")
        assert len(manifest) == 8 and {m["stage"] for m in manifest} == {"wd1"}
        assert len(list((out / "handoff").rglob("*.answer.json"))) == 8
        assert R.read_rule(out / "run") is R.TWO_FAMILIES
        assert len(HO._read_jsonl(out / "run" / C.CLASSIFIED_FILE)) == 8
        [record] = HO.read_rounds(out / "run")
        assert record["round"] == 0 and len(record["fields"]) == 8
        strata = json.loads((out / "run" / PL.STRATA_FILE).read_text(encoding="utf-8"))
        assert strata["seed"] == 3 and sum(strata["drawn_for"].values()) == 8

    def test_a_pool_is_built_once_in_a_directory_of_its_own(
        self, world: World, tmp_path: Path
    ) -> None:
        world.standard()
        PL.build_general(tmp_path / "pool", seed=3, size=8, fields_dir=world.fields)
        with pytest.raises(PL.PoolError, match="is not empty"):
            PL.build_general(tmp_path / "pool", seed=3, size=8, fields_dir=world.fields)

    def test_the_seal_command_names_the_roles_comparison_and_bounds(
        self, world: World, tmp_path: Path
    ) -> None:
        world.standard()
        result = PL.build_general(tmp_path / "pool", seed=3, size=8, fields_dir=world.fields)
        for word in ("--role field_researcher", "--threshold 0.9", "--max-undecided-excess 0.1",
                     "--comparison fields-decided", "--batches frg-r0-b0001"):  # fmt: skip
            assert word in result["seal"]
        assert "--truth" not in result["seal"]

    def test_the_pool_seals_prepares_and_agrees_with_itself(
        self, world: World, tmp_path: Path
    ) -> None:
        world.standard()
        out = tmp_path / "pool"
        built = PL.build_general(out, seed=3, size=8, fields_dir=world.fields)
        root = tmp_path / "calibration"
        seal = CC.seal(root, calibration_id="fr-general-001", role="field_researcher",
                       handoff=out / "handoff", batches=built["batches"], threshold=0.9,
                       max_undecided_excess=0.1, comparison=PL.COMPARISON_DECIDED,
                       now=lambda: NOW)  # fmt: skip
        assert len(seal["case_ids"]) == 8
        report = PL.prepare(root, calibration_id="fr-general-001", run=out / "run")
        assert report["questions"] == 8
        copy = root / "fr-general-001"
        assert not list((copy / "frg-r0-b0001").rglob("*.answer.json"))  # the answers are hidden
        assert PL.recorded_handoff  # the calibration run reads like any run:
        cal_run = D.calibration_run(copy)
        round_ = HO.read_rounds(cal_run)[0]
        assert round_["notes"] == {} and round_["calibration"] is True
        text = HO.brief(cal_run, copy, "frg-r0-b0001")
        assert "frg-r0-b0001" in text and "wd1" in text
        recorded = json.loads((copy / "RECORDED.json").read_text(encoding="utf-8"))
        again = PL.compare_decided(seal, recorded, dict(recorded), copy)
        assert again["agreement"] == 1.0 and again["undecided_excess"] == 0.0


class TestComparingAnAnsweredPool:
    @pytest.mark.parametrize(
        ("field", "old", "new", "same"),
        [
            ("coordinates", "replace: 35.1000, 33.4000", "replace: 35.1050, 33.4000", True),
            ("coordinates", "replace: 35.1000, 33.4000", "replace: 35.2000, 33.4000", False),
            ("period_start", "replace: -449", "replace: -480", True),
            ("period_start", "replace: -449", "replace: 1", False),
            ("site_type", "replace: Temple", "replace: temple", True),
            ("site_type", "replace: Temple", "replace: Tomb", False),
            ("source_url", "replace: https://a.org/x%20y", "replace: https://A.org/x y", True),
            ("source_url", "replace: https://a.org/x", "replace: https://a.org/y", False),
            ("period_start", "keep", "keep", True),
            ("period_start", "keep", "replace: -449", False),
            ("period_start", "clear", "unresolved", False),
        ],
    )
    def test_two_decisions_are_the_same_in_the_terms_the_database_keeps_the_value(
        self, field: str, old: str, new: str, same: bool
    ) -> None:
        assert PL.units_equal(field, old, new) is same

    def sealed(self) -> dict[str, Any]:
        return {"role": "field_researcher"}

    def compare(self, recorded: dict[str, str], fresh: dict[str, str]) -> dict[str, Any]:
        return PL.compare_decided(self.sealed(), recorded, fresh, Path("."))

    def test_only_the_cells_both_sides_decide_are_agreement(self) -> None:
        gold = {"a": answer_text(site_type=("replace", "Temple"), period_start=("clear", None))}
        fresh = {"a": answer_text(site_type=("replace", "Tomb"), period_start=("replace", "-449"))}
        report = self.compare(gold, fresh)
        assert report["units"] == 1 and report["agreed"] == 0  # the clear is not a cell to agree on
        assert report["disagreements"][0]["unit"] == "site_type"
        assert report["disagreements"][0]["fresh_sources"] == [TH.WIKI]

    def test_the_fresh_share_of_undecided_cells_is_measured_against_the_golds(self) -> None:
        gold = {"a": answer_text(site_type=("replace", "Temple"), period_start=("keep", None)),
                "b": answer_text(site_type=("replace", "Temple"))}  # fmt: skip
        fresh = {"a": answer_text(site_type=("unresolved", None), period_start=("keep", None)),
                 "b": answer_text(site_type=("clear", None))}  # fmt: skip
        report = self.compare(gold, fresh)
        assert report["undecided"] == {"gold": 0.0, "fresh": round(2 / 3, 4), "gold_units": 3,
                                       "fresh_units": 3}  # fmt: skip
        assert report["undecided_excess"] == round(2 / 3, 4)
        assert report["units"] == 1 and report["agreed"] == 1

    def test_a_question_without_a_fresh_answer_is_unanswered(self) -> None:
        gold = {"a": answer_text(site_type=("replace", "Temple")),
                "b": answer_text(site_type=("replace", "Temple"))}  # fmt: skip
        report = self.compare(gold, {"a": answer_text(site_type=("replace", "Temple"))})
        assert report["unanswered"] == ["b"] and report["agreement"] == 1.0

    def test_an_answer_that_is_not_the_field_shape_is_unanswered_not_agreement(self) -> None:
        gold = {"a": answer_text(site_type=("replace", "Temple"))}
        assert self.compare(gold, {"a": "not json"})["unanswered"] == ["a"]

    def test_a_gold_that_decided_nothing_is_a_rate_of_its_own(self) -> None:
        gold = {"a": answer_text(site_type=("clear", None))}
        fresh = {"a": answer_text(site_type=("clear", None))}
        report = self.compare(gold, fresh)
        assert report["undecided"]["gold"] == 1.0 and report["undecided_excess"] == 0.0
        assert report["units"] == 0 and report["agreement"] == 0.0


# ------------------------------------------------------------------------------ the BP pool
def bp_world(tmp_path: Path, ages: dict[str, tuple[Any, ...]]) -> Path:
    """`wd3` with a site per `name -> (reasoning, final decision[, answering model])`: an unresolved
    period whose agent named an age in years before the present. Every other run of the lanes holds
    empty files (`bp_candidates` refuses a run that is not there)."""
    fields = tmp_path / "output" / "remediation" / "fields"
    for name in (*POP.WD1_RUN_NAMES, *PL.LATER_RUNS):
        for file in (HO.DECISIONS_FILE, HO.ATTEMPTS_FILE, C.CLASSIFIED_FILE):
            HO._write_jsonl(fields / name / file, [])
    run = fields / "wd3"
    lines, decisions, attempts = [], [], []
    for number, (name, (reasoning, final, *model)) in enumerate(ages.items(), start=1):
        site = site_id(number)
        line = TW.wd3_line(site, ["period_start"])
        line["name"], line["country"] = name, "Spain"
        lines.append(line)
        decisions.append(
            decision(site, "period_start", final, via="exhausted", round_=2, name=name)
        )
        attempts.append({"site_id": site, "field": "period_start", "round": 2,
                         "answer": {"decision": "unresolved", "reasoning": reasoning},
                         **({"model": model[0]} if model else {})})  # fmt: skip
    HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
    HO._write_jsonl(run / HO.DECISIONS_FILE, decisions)
    HO._write_jsonl(run / HO.ATTEMPTS_FILE, attempts)
    return fields


OLD = "The article dates the cave to about 40,000 years ago, a figure that is not read as a year."
EDGE_TEXT = "Only 'about 7000 years ago' is given, which cannot be read as a year."
BRONZE = "The page says 'built 4,000 years ago', an elapsed-years figure that is not read."
DISPUTE = "Sources disagree: 40,000 years ago in one, 12,000 years ago in another; not read."
NO_AGE = "No source dates the site at all."


class TestTheBpCandidates:
    def test_the_buckets_an_age_reaches_and_the_edge_of_the_first_one(self) -> None:
        assert PL.bp_buckets([OLD]) == (frozenset({"< 4500 BC"}), (40000,), False)
        buckets, ages, edge = PL.bp_buckets([EDGE_TEXT])
        assert buckets == {"< 4500 BC", "4500 - 3000 BC"} and ages == (7000,) and edge is True
        buckets, _, edge = PL.bp_buckets([BRONZE])
        assert buckets == {"3000 - 1500 BC"} and edge is False

    def test_an_age_near_another_buckets_edge_is_no_edge_case(self) -> None:
        buckets, _, edge = PL.bp_buckets(["about 2,000 years ago, not read."])
        assert len(buckets) == 2 and edge is False

    def test_a_site_is_clean_when_one_bucket_holds_and_the_reader_was_the_obstacle(
        self, tmp_path: Path
    ) -> None:
        fields = bp_world(
            tmp_path,
            {
                "Old Cave": (OLD, "unresolved"),
                "Edge Cave": (EDGE_TEXT, "unresolved"),
                "Disputed Cave": (DISPUTE, "unresolved"),
                "Plain Cave": ("Wikipedia dates the cave to about 40,000 years ago.", "unresolved"),
                "Quiet Cave": (NO_AGE, "unresolved"),
                "Bronze Barrow": (BRONZE, "held"),
                "Settled Cave": (OLD, "replace"),
            },
        )
        found = {c.name: c for c in PL.bp_candidates(fields).values()}
        assert set(found) == {
            "Old Cave", "Edge Cave", "Disputed Cave", "Plain Cave", "Bronze Barrow"
        }  # fmt: skip
        assert found["Old Cave"].clean and found["Bronze Barrow"].clean
        assert not found["Plain Cave"].clean  # no word says the reader was the obstacle
        assert found["Edge Cave"].clean and found["Edge Cave"].edge
        assert not found["Disputed Cave"].clean
        assert found["Old Cave"].snippet == OLD

    def test_the_question_is_the_latest_classification_that_asked_the_period(
        self, tmp_path: Path
    ) -> None:
        fields = bp_world(tmp_path, {"Old Cave": (OLD, "unresolved")})
        run4 = fields / "wd4"
        line = HO._read_jsonl(fields / "wd3" / C.CLASSIFIED_FILE)[0]
        HO._write_jsonl(run4 / C.CLASSIFIED_FILE, [{**line, "country": "France"}])
        [candidate] = PL.bp_candidates(fields).values()
        assert candidate.line["country"] == "France"


class TestTheBpReaderWasTheObstacle:
    def test_a_year_worked_out_from_an_age_that_is_not_accepted_says_the_reader_was_the_obstacle(
        self, tmp_path: Path
    ) -> None:
        said = "Sources give 'about 7000 years ago'; a year worked out from an age is not accepted."
        [candidate] = PL.bp_candidates(
            bp_world(tmp_path, {"Elk Cave": (said, "unresolved")})
        ).values()
        assert candidate.clean


class TestTheBpCandidatesAreClaudes:
    MINIMAX = "minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)"
    CLAUDE = "anthropic/claude-sonnet-5-5 (Claude Code agent)"

    def test_a_site_only_a_minimax_reasoning_dates_is_no_candidate(self, tmp_path: Path) -> None:
        fields = bp_world(tmp_path, {"Old Cave": (OLD, "unresolved", self.MINIMAX)})
        assert PL.bp_candidates(fields) == {}

    def test_a_minimax_reasoning_neither_dates_nor_cleans_a_claude_candidate(
        self, tmp_path: Path
    ) -> None:
        fields = bp_world(tmp_path, {"Old Cave": ("Wikipedia dates it to about 40,000 years ago.",
                                                  "unresolved", self.CLAUDE)})  # fmt: skip
        run = fields / "wd3"
        site = HO._read_jsonl(run / HO.DECISIONS_FILE)[0]["site_id"]
        HO._write_jsonl(run / HO.ATTEMPTS_FILE, [
            *HO._read_jsonl(run / HO.ATTEMPTS_FILE),
            {"site_id": site, "field": "period_start", "round": 2, "model": self.MINIMAX,
             "answer": {"decision": "unresolved", "reasoning": BRONZE}},
        ])  # fmt: skip
        [candidate] = PL.bp_candidates(fields).values()
        assert candidate.ages == (40000,) and candidate.reasonings == (
            "Wikipedia dates it to about 40,000 years ago.",
        )
        assert not candidate.clean  # BRONZE's "not read" does not make a Claude text clean

    def test_a_run_file_that_is_not_there_is_refused_not_skipped(self, tmp_path: Path) -> None:
        fields = bp_world(tmp_path, {"Old Cave": (OLD, "unresolved")})
        (fields / "wd1-rest" / HO.ATTEMPTS_FILE).unlink()
        with pytest.raises(POP.PopulationError, match="is missing"):
            PL.bp_candidates(fields)


class TestThePick:
    def candidates(self, tmp_path: Path) -> dict[str, PL.BpCandidate]:
        ages = {f"Cave {n}": (OLD, "unresolved") for n in range(10)}
        ages["Edge Cave"] = (EDGE_TEXT, "unresolved")
        ages["Le Moustier"] = (NO_AGE + " 100,000 years ago, not read.", "unresolved")
        return PL.bp_candidates(bp_world(tmp_path, ages))

    def test_the_named_sites_the_edge_case_and_a_seeded_fill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PL, "NAMED_BP_SITES", ("Le Moustier",))
        candidates = self.candidates(tmp_path)
        picked = PL.pick_bp(candidates, 6, random.Random(1))
        by_name = {candidates[s].name: v for s, v in picked.items()}
        assert by_name["Le Moustier"] == (PL.AUDIT_CONFIRMED, frozenset({"< 4500 BC"}))
        assert by_name["Edge Cave"][0] == PL.EDGE and len(by_name["Edge Cave"][1]) == 2
        assert len(picked) == 6 and {v[0] for v in picked.values()} == {
            PL.AUDIT_CONFIRMED, PL.EDGE, PL.EARLIER_REASONING
        }  # fmt: skip
        again = PL.pick_bp(candidates, 6, random.Random(1))
        assert sorted(again) == sorted(picked)
        assert sorted(PL.pick_bp(candidates, 6, random.Random(2))) != sorted(picked)

    def test_a_named_site_the_candidates_lack_is_refused_by_name(self, tmp_path: Path) -> None:
        with pytest.raises(PL.PoolError, match="Bruniquel: no candidate"):
            PL.pick_bp(self.candidates(tmp_path), 6, random.Random(1))

    def test_a_pool_without_an_edge_case_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PL, "NAMED_BP_SITES", ())
        candidates = PL.bp_candidates(bp_world(tmp_path, {"Old Cave": (OLD, "unresolved")}))
        with pytest.raises(PL.PoolError, match="no clean bucket-edge case"):
            PL.pick_bp(candidates, 1, random.Random(1))

    def test_too_few_clean_candidates_is_refused_by_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PL, "NAMED_BP_SITES", ())
        with pytest.raises(PL.PoolError, match="only 12 clean BP candidates, 99 are wanted"):
            PL.pick_bp(self.candidates(tmp_path), 99, random.Random(1))

    def test_the_pool_is_wd5_questions_without_an_answer_and_a_truth_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PL, "NAMED_BP_SITES", ("Le Moustier",))
        ages = {f"Cave {n}": (OLD, "unresolved") for n in range(10)}
        ages["Edge Cave"] = (EDGE_TEXT, "unresolved")
        ages["Le Moustier"] = (OLD, "unresolved")
        fields = bp_world(tmp_path, ages)
        out = tmp_path / "pool"
        result = PL.build_bp(out, seed=5, size=6, fields_dir=fields)
        assert result["sites"] == 6 and result["basis"] == {
            "audit-confirmed": 1, "earlier-reasoning": 4, "edge": 1
        }  # fmt: skip
        assert R.read_rule(out / "run") is R.RECHECK
        assert not list((out / "handoff").rglob("*.answer.json"))
        manifest = OH.manifest(out / "handoff")
        assert len(manifest) == 6 and {m["stage"] for m in manifest} == {"wd5"}
        assert {m["field"] for m in manifest} == {"period_start"}
        record = HO.read_rounds(out / "run")[0]
        assert record["model"] == "claude-sonnet-5-5"
        truth = json.loads((out / PL.TRUTH_FILE).read_text(encoding="utf-8"))
        assert set(truth) == {m["label"] for m in manifest}
        named = next(v for v in truth.values() if v["basis"] == PL.AUDIT_CONFIRMED)
        assert named["expected"] == ["< 4500 BC"] and named["name"] == "Le Moustier"
        assert "--truth" in result["seal"] and "--comparison bp-bucket" in result["seal"]
        assert "--max-undecided-excess" not in result["seal"]  # an unresolved is a miss here
        # the prompt is wd5's: the BP reader is taught in it
        prompt = (out / "handoff" / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
        assert "years before the present" in prompt and "lane wd5" in prompt

    def test_the_pool_seals_and_prepares_as_a_truth_pool(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PL, "NAMED_BP_SITES", ())
        ages = {f"Cave {n}": (OLD, "unresolved") for n in range(4)}
        ages["Edge Cave"] = (EDGE_TEXT, "unresolved")
        out = tmp_path / "pool"
        built = PL.build_bp(out, seed=5, size=5, fields_dir=bp_world(tmp_path, ages))
        root = tmp_path / "calibration"
        seal = CC.seal(root, calibration_id="fr-bp-001", role="field_researcher",
                       handoff=out / "handoff", batches=built["batches"], threshold=0.9,
                       comparison=PL.COMPARISON_BP, truth=out / PL.TRUTH_FILE,
                       now=lambda: NOW)  # fmt: skip
        assert len(seal["case_ids"]) == 5
        PL.prepare(root, calibration_id="fr-bp-001", run=out / "run")
        cal_run = D.calibration_run(root / "fr-bp-001")
        assert R.read_rule(cal_run) is R.RECHECK
        assert HO.read_rounds(cal_run)[0]["model"] == "claude-sonnet-5-5"


# ------------------------------------------------------------------------------ comparing the BP pool
def attempt(site: str, decision_: str, value: Any, counted: bool = True,
            reason: str | None = None) -> dict[str, Any]:  # fmt: skip
    answer = None if decision_ == "malformed" else {"decision": decision_, "value": value}
    return {"site_id": site, "field": "period_start", "round": 0, "counted": counted,
            "reason": reason, "answer": answer, "problem": "bad" if answer is None else None}  # fmt: skip


class TestComparingTheBpPool:
    def prepared(
        self, tmp_path: Path, attempts: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], Path]:
        tmp_path.mkdir(exist_ok=True)
        truth = tmp_path / "TRUTH.json"
        truth.write_text(
            json.dumps(
                {
                    site_id(1): {"expected": ["< 4500 BC"], "basis": "audit-confirmed"},
                    site_id(2): {"expected": ["< 4500 BC", "4500 - 3000 BC"], "basis": "edge"},
                    site_id(3): {"expected": ["3000 - 1500 BC"], "basis": "earlier-reasoning"},
                }
            ),
            encoding="utf-8",
        )
        copy = tmp_path / "cal"
        run = D.calibration_run(copy)
        run.mkdir(parents=True)
        HO._write_jsonl(run / HO.ATTEMPTS_FILE, attempts)
        return {"role": "field_researcher", "truth": str(truth)}, copy

    def compare(
        self, tmp_path: Path, attempts: list[dict[str, Any]], answered: int = 3
    ) -> dict[str, Any]:
        sealed, copy = self.prepared(tmp_path, attempts)
        fresh = {site_id(n): '{"fields": {}}' for n in range(1, answered + 1)}
        return PL.compare_bp(sealed, {}, fresh, copy)

    def test_a_counted_answer_in_an_accepted_bucket_is_a_hit(self, tmp_path: Path) -> None:
        report = self.compare(tmp_path, [
            attempt(site_id(1), "replace", "-38050"),
            attempt(site_id(2), "replace", "-4501"),
            attempt(site_id(3), "replace", "-2050"),
        ])  # fmt: skip
        assert report["units"] == 3 and report["agreed"] == 3 and report["agreement"] == 1.0
        assert report["agreed_by_basis"] == {
            "audit-confirmed": 1,
            "earlier-reasoning": 1,
            "edge": 1,
        }

    def test_the_edge_case_accepts_either_bucket_and_no_other(self, tmp_path: Path) -> None:
        report = self.compare(tmp_path, [
            attempt(site_id(1), "replace", "-38050"),
            attempt(site_id(2), "replace", "-4400"),
            attempt(site_id(3), "replace", "-2050"),
        ])  # fmt: skip
        assert report["agreed"] == 3
        wrong = self.compare(tmp_path / "w", [
            attempt(site_id(1), "replace", "-38050"),
            attempt(site_id(2), "replace", "-2000"),
            attempt(site_id(3), "replace", "-2050"),
        ])  # fmt: skip
        assert wrong["agreed"] == 2 and wrong["disagreements"][0]["label"] == site_id(2)

    def test_every_other_outcome_is_a_miss_with_its_reason(self, tmp_path: Path) -> None:
        report = self.compare(tmp_path, [
            attempt(site_id(1), "unresolved", None),
            attempt(site_id(2), "replace", "-4501", counted=False, reason="quote not found: x"),
            attempt(site_id(3), "malformed", None),
        ])  # fmt: skip
        assert report["agreed"] == 0
        said = {d["label"]: d["fresh"] for d in report["disagreements"]}
        assert said[site_id(1)] == "unresolved"
        assert "not counted (quote not found: x)" in said[site_id(2)]
        assert said[site_id(3)].startswith("not in shape")

    def test_a_site_nobody_answered_is_unanswered_never_a_hit(self, tmp_path: Path) -> None:
        report = self.compare(tmp_path, [attempt(site_id(1), "replace", "-38050")], answered=1)
        assert report["unanswered"] == [site_id(2), site_id(3)]
        assert report["units"] == 1 and report["agreed"] == 1

    def test_the_calibration_run_must_have_been_imported(self, tmp_path: Path) -> None:
        sealed, copy = self.prepared(tmp_path, [])
        (D.calibration_run(copy) / HO.ATTEMPTS_FILE).unlink()
        with pytest.raises(CC.CalibrationError, match="import the calibration run first"):
            PL.compare_bp(sealed, {}, {}, copy)


# ------------------------------------------------------------------------------ the known-truth pool
SENTENCE = "The Temple of Hephaestus was built in 449 BC."  # in TH.WIKI's page
REGISTER_QUOTE = "Hephaisteion, a temple of the 5th century BC."  # in TH.REGISTER's page
ARTICLE_QUOTE = "The cave was lived in about 40,000 years ago."
ARTICLE = f"Cave {{n}} is a cave in France. {ARTICLE_QUOTE} It was excavated in 1900."
SMALL = {"period_start": 1, "site_type": 1, "coordinates": 1}


def wiki_cache(root: Path, pages: dict[str, str]) -> Path:
    """A Wikipedia cache (`fields/wiki.py`) with one English article per `{site: text}`."""
    (root / "en").mkdir(parents=True)
    index = []
    for number, (site, text) in enumerate(sorted(pages.items())):
        name = f"en/{number}.json"
        (root / name).write_text(
            json.dumps({"lang": "en", "title": f"Cave {number}", "resolved_title": f"Cave {number}",
                        "revid": 1, "text": text}), encoding="utf-8")  # fmt: skip
        index.append({"site_id": site, "lang": "en", "title": f"Cave {number}", "file": name})
    HO._write_jsonl(root / "INDEX.jsonl", index)
    return root


class TruthWorld:
    """The miniature of the run tree the known-truth pool reads: four WD1 runs of sites that each
    kept all three fields on two quotes (their pages kept), the wd5 classification and a Wikipedia
    cache of two audit sites."""

    FIELD_VALUES = {"period_start": (-449, "-449"), "site_type": ("Temple", "Temple"),
                    "coordinates": ("37.9755, 23.7215", "37.9755, 23.7215")}  # fmt: skip

    def __init__(self, tmp_path: Path, per_run: int = 3) -> None:
        self.fields = tmp_path / "checkout" / "output" / "remediation" / "fields"
        self.wiki_root = tmp_path / "wiki"
        self.sites = 0
        self.audit = [(site_id(900 + n), f"Cave {n}") for n in range(2)]
        self.known = tuple(PL.KnownWrong(site, name, -500, PL.BAND_RULE, ARTICLE_QUOTE,
                                         "stored -500; about 40,000 years")
                           for site, name in self.audit)  # fmt: skip
        wd5 = self.fields / "wd5"
        wd5.mkdir(parents=True)
        lines = []
        for site, name in self.audit:
            line = wd1_line(site, ["period_start"], name)
            line["fields"]["period_start"]["stored"] = -500
            # the real wd5 lines of these sites carry the rule-made open reason
            line["open"] = {"period_start": {"why": "rule-made", "made": "-500", "wd1": None}}
            lines.append(line)
        HO._write_jsonl(wd5 / C.CLASSIFIED_FILE, lines)
        wiki_cache(self.wiki_root, {site: ARTICLE.format(n=n) for n, (site, _) in
                                    enumerate(self.audit)})  # fmt: skip
        for name in POP.WD1_RUN_NAMES:
            self.run(name, per_run)

    def run(self, name: str, count: int) -> Path:
        run = self.fields / name
        run.mkdir(parents=True)
        lines, decisions = [], []
        for _ in range(count):
            self.sites += 1
            site = site_id(self.sites)
            lines.append(wd1_line(site, list(self.FIELD_VALUES), f"Site {self.sites}"))
            for field, (stored, value) in self.FIELD_VALUES.items():
                row = decision(site, field, "keep", value=value, name=f"Site {self.sites}")
                row["stored"] = stored
                row["quotes"] = [
                    {"source": TH.WIKI, "quote": SENTENCE, "outcome": "found", "detail": ""},
                    {"source": TH.REGISTER, "quote": REGISTER_QUOTE, "outcome": "found",
                     "detail": ""},
                ]  # fmt: skip
                decisions.append(row)
        HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
        HO._write_jsonl(run / HO.DECISIONS_FILE, decisions)
        for url in (TH.WIKI, TH.REGISTER):
            Q.store_page(run / "pages", url, status=200, final_url=url, content_type="text/html",
                         body=TH.PAGES[url].encode(), error="", fetched_at="t")  # fmt: skip
        return run

    def build(self, out: Path, seed: int = 1, **kw: Any) -> dict[str, Any]:
        kw.setdefault("perturbed", SMALL)
        kw.setdefault("right", SMALL)
        kw.setdefault("known_wrong", self.known)
        return PL.build_adversarial_truth(out, seed=seed, fields_dir=self.fields,
                                          wiki_root=self.wiki_root, **kw)  # fmt: skip


@pytest.fixture
def truth_world(tmp_path: Path) -> TruthWorld:
    return TruthWorld(tmp_path)


def read_truth(out: Path) -> dict[str, Any]:
    return json.loads((out / PL.TRUTH_FILE).read_text(encoding="utf-8"))


def read_cells(out: Path) -> dict[str, Any]:
    return AD.read_cells(out / "run")


class TestThePerturbations:
    def test_a_wrong_start_lies_at_least_three_buckets_from_the_true_one(self) -> None:
        for year in (-6000, -449, 250, 1700):
            for seed in range(20):
                wrong = PL.wrong_year(year, random.Random(seed))
                gap = abs(C.BUCKETS.index(C.bucket(wrong)) - C.BUCKETS.index(C.bucket(year)))
                assert gap >= PL.MIN_BUCKET_GAP

    def test_every_bucket_has_a_year_that_lies_in_it(self) -> None:
        assert set(PL.BUCKET_YEARS) == set(C.BUCKETS)
        assert all(C.bucket(year) == name for name, year in PL.BUCKET_YEARS.items())

    def test_every_wrong_type_is_a_canonical_type(self) -> None:
        from pipeline.normalizers.site_type import CANONICAL_TYPES

        assert set(PL.WRONG_TYPES) <= set(CANONICAL_TYPES)

    def test_a_wrong_type_is_none_a_quote_holds_a_word_of_nor_one_the_item_names(self) -> None:
        line = wd1_line(site_id(1), ["site_type"], "S")
        line["fields"]["site_type"]["evidence"]["types"] = ["Harbor"]
        quotes = [{"quote": "a stone bridge over the stadium", "passage": "x", "head": "mine"}]
        for seed in range(40):
            wrong = PL.wrong_type("Temple", line, quotes, random.Random(seed))
            assert wrong not in {"Temple", "Harbor", "Bridge", "Stadium", "Mine/quarry"}

    def test_a_site_whose_quotes_hold_every_wrong_type_is_left_out_by_name(self) -> None:
        line = wd1_line(site_id(1), ["site_type"], "S")
        everything = " ".join(PL.WRONG_TYPES).replace("/", " ")
        with pytest.raises(PL.PerturbationError, match="no wrong type free of the quotes"):
            PL.wrong_type("Temple", line, [{"quote": everything, "passage": "", "head": ""}],
                          random.Random(1))  # fmt: skip

    def test_a_moved_point_is_forty_to_one_hundred_twenty_km_away(self) -> None:
        for seed in range(50):
            moved = PL.moved_point((37.9755, 23.7215), random.Random(seed))
            km = PL.A._km((37.9755, 23.7215), PL._point(moved))
            assert PL.MIN_MOVE_KM - 0.5 <= km <= PL.MAX_MOVE_KM + 0.5 and km >= 30

    def test_a_point_moved_over_the_antimeridian_is_still_a_longitude(self) -> None:
        for seed in range(30):
            lat, lon = PL._point(PL.moved_point((10.0, 179.9), random.Random(seed)))
            assert -180 <= lon <= 180 and -90 <= lat <= 90


class TestTheKnownTruthPool:
    def test_the_audit_cells_are_the_stored_rule_value_under_the_articles_own_sentence(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        wiki = PL.W.WikiCache(truth_world.wiki_root)
        pairs = PL.known_wrong_cells(truth_world.fields, wiki, truth_world.known)
        assert len(pairs) == 2
        cell, truth = pairs[0]
        assert (
            cell["field"] == "period_start" and cell["stored"] == -500 and cell["value"] == "-500"
        )
        assert cell["decision"] == "keep" and cell["reasoning"] == PL.NEUTRAL_REASONING
        [quote] = cell["quotes"]
        assert (
            quote["url"] == "https://en.wikipedia.org/wiki/Cave_0"
            and ARTICLE_QUOTE in quote["passage"]
        )
        assert cell["wiki"]["lead"].startswith("Cave 0 is a cave")
        assert truth["expected"] == "reject" and truth["class"] == PL.KNOWN_WRONG
        assert truth["basis"] == PL.BAND_RULE and "40,000 years" in truth["why"]

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"name": "Another Cave"}, "is 'Cave 0', not 'Another Cave'"),
            ({"quote": "A sentence the article does not hold."}, "its sentence is in none"),
            ({"site_id": site_id(777)}, "is not in the wd5 classification"),
        ],
    )
    def test_an_entry_that_is_not_the_site_or_the_article_it_names_is_refused(
        self, truth_world: TruthWorld, change: dict[str, Any], message: str
    ) -> None:
        entry = dataclasses.replace(truth_world.known[0], **change)
        with pytest.raises(PL.PoolError, match=message):
            PL.known_wrong_cells(truth_world.fields, PL.W.WikiCache(truth_world.wiki_root), [entry])

    def test_a_site_the_wiki_cache_holds_no_article_of_is_refused(
        self, truth_world: TruthWorld
    ) -> None:
        site = site_id(901)
        index = truth_world.wiki_root / "INDEX.jsonl"
        rows = [r for r in HO._read_jsonl(index) if r["site_id"] != site]
        HO._write_jsonl(index, rows)
        with pytest.raises(PL.PoolError, match="holds no article of the site"):
            PL.known_wrong_cells(truth_world.fields, PL.W.WikiCache(truth_world.wiki_root),
                                 truth_world.known)  # fmt: skip

    def test_the_known_wrong_table_names_nine_sites_of_the_audit_once_each(self) -> None:
        names = sorted(e.name for e in PL.KNOWN_WRONG_PERIODS)
        assert names == sorted([
            "Lake Mungo", "Broadbury Castle", "Tappoch Broch", "Hodson Stone Circle",
            "Le Moustier", "Bruniquel Cave", "Cro-Magnon Rock Shelter", "Apidima Cave",
            "Eartham Pit, Boxgrove",
        ])  # fmt: skip
        assert len({e.site_id for e in PL.KNOWN_WRONG_PERIODS}) == 9
        by_name = {e.name: e.value for e in PL.KNOWN_WRONG_PERIODS}
        assert by_name["Lake Mungo"] == -500 and by_name["Broadbury Castle"] == -4000
        assert by_name["Tappoch Broch"] == -800 and by_name["Hodson Stone Circle"] == -4000
        assert {e.value for e in PL.KNOWN_WRONG_PERIODS if e.basis == PL.BAND_RULE} == {-500}
        assert {e.basis for e in PL.KNOWN_WRONG_PERIODS} == {PL.SAMPLE_AUDIT, PL.BAND_RULE}

    def test_the_default_quotas_make_about_fifty_cells(self) -> None:
        total = (len(PL.KNOWN_WRONG_PERIODS) + sum(PL.PERTURBED_QUOTA.values())
                 + sum(PL.RIGHT_QUOTA.values()))  # fmt: skip
        assert total == 50 and PL.THRESHOLD == 0.9

    def test_wd1_keeps_are_the_counted_two_quote_keeps_whose_quotes_were_found(
        self, truth_world: TruthWorld
    ) -> None:
        run = truth_world.fields / "wd1"
        rows = HO._read_jsonl(run / HO.DECISIONS_FILE)
        rows[0]["quotes"][0]["outcome"] = "not found"
        rows[1]["quotes"] = rows[1]["quotes"][:1]
        rows[2]["decision"] = "replace"
        rows[3]["via"] = "exhausted"
        rows[4]["stored"] = None
        HO._write_jsonl(run / HO.DECISIONS_FILE, rows)
        keeps = PL.wd1_keeps(truth_world.fields)
        everything = sum(len(v) for v in keeps.values())
        assert everything == 4 * 3 * 3 - 5
        assert all(len(k.decision["quotes"]) >= 2 for v in keeps.values() for k in v)

    def test_a_keep_whose_stored_value_is_not_the_quoted_one_is_no_known_right_cell(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        """WD1 keeps a start of the quoted year's bucket and a point within a kilometre; a checker
        that holds the stored value to the quote must reject those, so they are no gold."""
        run = truth_world.fields / "wd1"
        rows = HO._read_jsonl(run / HO.DECISIONS_FILE)
        off: set[tuple[str, str]] = set()
        for row in rows:
            if len([k for k in off if k[1] == row["field"]]) >= 2:
                continue
            if row["field"] == "period_start":
                row["stored"] = 1  # the bucket edge; the quotes say 449 BC
            elif row["field"] == "coordinates":
                row["stored"] = "37.9755, 23.7260"  # 0.4 km from the quoted point
            else:
                continue
            off.add((row["site_id"], row["field"]))
        HO._write_jsonl(run / HO.DECISIONS_FILE, rows)
        for decided in rows:
            keep = next(k for k in PL.wd1_keeps(truth_world.fields)[decided["field"]]
                        if k.decision["site_id"] == decided["site_id"])  # fmt: skip
            if (decided["site_id"], decided["field"]) in off:
                with pytest.raises(PL.InexactKeepError, match="is not the quoted"):
                    PL._right_cell(keep, None)
            else:
                PL._right_cell(keep, None)
        out = tmp_path / "pool"
        truth_world.build(out, right={"period_start": 3, "site_type": 3, "coordinates": 3},
                          perturbed={"period_start": 0, "site_type": 0, "coordinates": 0})  # fmt: skip
        cells = read_cells(out)
        right = {(cells[c]["site_id"], cells[c]["field"]) for c, t in read_truth(out).items()
                 if t["class"] == PL.KNOWN_RIGHT}  # fmt: skip
        assert len(right) == 9 and not right & off

    def test_a_wd1_run_that_is_not_there_is_refused_not_skipped(
        self, truth_world: TruthWorld
    ) -> None:
        (truth_world.fields / "wd1-rest" / C.CLASSIFIED_FILE).unlink()
        with pytest.raises(HO.HandoffStepError, match="missing or empty"):
            PL.wd1_keeps(truth_world.fields)

    def test_the_pool_is_wrong_and_right_cells_a_truth_file_and_no_answer(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        out = tmp_path / "pool"
        result = truth_world.build(out)
        truth = read_truth(out)
        # 2 audit + 3 perturbed (one per field) known wrong; 3 known right
        assert result["cells"] == 8 and result["expected"] == {"confirm": 3, "reject": 5}
        assert result["basis"] == {
            "band-rule-cave": 2, "perturbed-period": 1, "perturbed-point": 1,
            "perturbed-type": 1, "wd1-two-source-keep": 3,
        }  # fmt: skip
        assert {t["class"] for t in truth.values()} == {"known-wrong", "known-right"}
        assert all(t["expected"] == ("confirm" if t["class"] == "known-right" else "reject")
                   for t in truth.values())  # fmt: skip
        assert all(t["why"] and t["name"] and t["column"] for t in truth.values())
        manifest = OH.manifest(out / "handoff")
        assert {m["label"] for m in manifest} == set(truth) == set(read_cells(out))
        assert not list((out / "handoff").rglob("*.answer.json"))
        assert R.read_rule(out / "run") is R.RECHECK

    def test_the_seal_command_is_the_checkers_with_its_own_comparison_and_no_undecided_bound(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        seal = truth_world.build(tmp_path / "pool")["seal"]
        for word in ("--id adv-truth-001", "--role adversarial", "--threshold 0.9",
                     "--comparison adv-known-truth", "--truth ", "--batches adv-r0-b0001"):  # fmt: skip
            assert word in seal
        assert "--max-undecided-excess" not in seal  # an unclear is a miss in its class

    def test_a_cell_tells_nothing_but_its_value_and_its_quotes(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        """Every cell is a keep under the same reasoning, with no open reason and no rule note: the
        class of a cell is not readable from its form."""
        out = tmp_path / "pool"
        truth_world.build(out)
        cells = read_cells(out)
        assert {c["decision"] for c in cells.values()} == {"keep"}
        assert {c["reasoning"] for c in cells.values()} == {PL.NEUTRAL_REASONING}
        assert {c["why_open"] for c in cells.values()} == {None}
        assert {c["made"] for c in cells.values()} == {None}
        assert all(c["quotes"] for c in cells.values())
        for label in cells:
            prompt = next((out / "handoff").rglob(f"{label}.prompt.txt")).read_text("utf-8")
            assert "This is a keep" in prompt

    def test_a_perturbed_cell_keeps_the_original_quotes_and_changes_only_the_value(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        out = tmp_path / "pool"
        truth_world.build(out)
        truth, cells = read_truth(out), read_cells(out)
        perturbed = {c: t for c, t in truth.items() if t["basis"].startswith("perturbed")}
        assert len(perturbed) == 3
        for label, entry in perturbed.items():
            cell = cells[label]
            assert [q["quote"] for q in cell["quotes"]] == [SENTENCE, REGISTER_QUOTE]
            assert cell["stored"] == (cell["value"] if entry["column"] != "period_start"
                                      else int(cell["value"]))  # fmt: skip
            true_stored = TruthWorld.FIELD_VALUES[entry["column"]][0]
            assert cell["stored"] != true_stored
            if entry["column"] == "period_start":
                gap = abs(
                    C.BUCKETS.index(C.bucket(int(cell["value"]))) - C.BUCKETS.index(C.bucket(-449))
                )
                assert gap >= PL.MIN_BUCKET_GAP
            if entry["column"] == "coordinates":
                assert cell["stored_point"] == cell["value"]
                assert PL.A._km(PL._point(cell["value"]), PL._point("37.9755, 23.7215")) >= 30
            else:
                assert cell["stored_point"] == "37.9755, 23.7215"

    def test_a_known_right_cell_is_the_decided_keep_with_its_sources(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        out = tmp_path / "pool"
        truth_world.build(out)
        truth, cells = read_truth(out), read_cells(out)
        right = [c for c, t in truth.items() if t["class"] == PL.KNOWN_RIGHT]
        assert len(right) == 3
        for label in right:
            cell = cells[label]
            stored, value = TruthWorld.FIELD_VALUES[cell["field"]]
            assert (cell["stored"], cell["value"]) == (stored, value)
            assert [q["url"] for q in cell["quotes"]] == [TH.WIKI, TH.REGISTER]

    def test_a_site_is_in_the_pool_once(self, tmp_path: Path) -> None:
        world = TruthWorld(tmp_path, per_run=8)
        out = tmp_path / "pool"
        world.build(out, perturbed={"period_start": 3, "site_type": 3, "coordinates": 3},
                    right={"period_start": 3, "site_type": 3, "coordinates": 3})  # fmt: skip
        sites = [label.split(".")[0] for label in read_truth(out)]
        assert len(sites) == len(set(sites)) == 2 + 9 + 9

    def test_a_table_that_names_a_site_twice_is_refused(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        with pytest.raises(PL.PoolError, match="a cell is in the pool twice"):
            truth_world.build(
                tmp_path / "pool", known_wrong=(*truth_world.known, truth_world.known[0])
            )

    def test_the_draw_is_seeded(self, truth_world: TruthWorld, tmp_path: Path) -> None:
        def pool(seed: int, sub: str) -> dict[str, Any]:
            truth_world.build(tmp_path / sub, seed=seed)
            return {c: (t["basis"], t["why"]) for c, t in read_truth(tmp_path / sub).items()}

        assert pool(1, "a") == pool(1, "b")
        assert pool(1, "c") != pool(2, "d")

    def test_a_pool_is_built_once_in_a_directory_of_its_own(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        truth_world.build(tmp_path / "pool")
        with pytest.raises(PL.PoolError, match="is not empty"):
            truth_world.build(tmp_path / "pool")

    def test_too_few_usable_keeps_are_refused_by_count_and_class(self, tmp_path: Path) -> None:
        world = TruthWorld(tmp_path, per_run=1)  # four sites of each field, 2 + 2 wanted
        with pytest.raises(
            PL.PoolError, match="only 0 usable perturbed period_start cells, 5 wanted"
        ):
            world.build(tmp_path / "p", right={"period_start": 4, "site_type": 0, "coordinates": 0},
                        perturbed={"period_start": 5, "site_type": 0, "coordinates": 0})  # fmt: skip

    def test_a_quote_the_page_no_longer_holds_leaves_its_site_out_and_the_next_one_is_drawn(
        self, tmp_path: Path
    ) -> None:
        world = TruthWorld(tmp_path, per_run=2)
        run = world.fields / POP.WD1_RUN_NAMES[0]
        for url in (TH.WIKI, TH.REGISTER):  # the pages of one run changed under the quotes
            Q.store_page(run / "pages", url, status=200, final_url=url, content_type="text/html",
                         body=b"<html><body><p>Nothing here.</p></body></html>", error="",
                         fetched_at="t2")  # fmt: skip
        out = tmp_path / "pool"
        world.build(out)
        assert len(read_truth(out)) == 8

    def test_a_page_that_was_never_collected_is_refused_not_skipped(self, tmp_path: Path) -> None:
        world = TruthWorld(tmp_path, per_run=2)
        for name in POP.WD1_RUN_NAMES:
            shutil.rmtree(world.fields / name / "pages")
        with pytest.raises(Q.AuditError, match="was not collected"):
            world.build(tmp_path / "pool")


class TestTheKnownTruthPoolEndToEnd:
    """Seal, prepare, answer, import, compare, verdict - the whole path with agents that answer."""

    def prepared(
        self, world: TruthWorld, tmp_path: Path
    ) -> tuple[Path, Path, Path, dict[str, Any]]:
        out = tmp_path / "pool"
        built = world.build(out)
        root = tmp_path / "calibration"
        CC.seal(root, calibration_id=PL.ADV_CALIBRATION_ID, role="adversarial",
                handoff=out / "handoff", batches=built["batches"], threshold=0.9,
                comparison=PL.COMPARISON_ADV_KNOWN, truth=out / PL.TRUTH_FILE,
                now=lambda: NOW)  # fmt: skip
        PL.prepare(root, calibration_id=PL.ADV_CALIBRATION_ID, run=out / "run")
        return out, root, root / PL.ADV_CALIBRATION_ID, read_truth(out)

    @staticmethod
    def answer(copy: Path, label: str, batch: str, verdict: str) -> None:
        field = label.rsplit(".", 1)[1]
        body = {"fields": {field: {"decision": verdict, "value": None, "quotes": [],
                                   "reasoning": "x" * 40}}}  # fmt: skip
        OH.write_answer(copy, batch_id=batch, stage=AD.STAGE, label=label, text=json.dumps(body),
                        answered_by=f"adversarial:{batch}", model=OH.SONNET_MODEL)  # fmt: skip

    def run(self, world: TruthWorld, tmp_path: Path, wrong: str, right: str) -> dict[str, Any]:
        _, root, copy, truth = self.prepared(world, tmp_path)
        for line in OH.manifest(copy):
            expected = truth[line["label"]]["class"]
            self.answer(copy, line["label"], line["batch_id"],
                        wrong if expected == PL.KNOWN_WRONG else right)  # fmt: skip
        AD.import_answers(D.calibration_run(copy), pace=0)
        CC.compare(root, calibration_id=PL.ADV_CALIBRATION_ID, comparators=PL.COMPARATORS)
        return CC.verdict(root, calibration_id=PL.ADV_CALIBRATION_ID, false_sources=0,
                          now=lambda: NOW)  # fmt: skip

    def test_a_checker_that_rejects_the_wrong_and_confirms_the_right_passes(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        verdict = self.run(truth_world, tmp_path, "reject", "confirm")
        assert verdict["passed"] is True and verdict["agreement"] == 1.0 and verdict["units"] == 8
        report = json.loads((tmp_path / "calibration" / PL.ADV_CALIBRATION_ID
                             / CC.COMPARISON_FILE).read_text(encoding="utf-8"))  # fmt: skip
        assert (
            report["reject_rate_known_wrong"] == 1.0 and report["confirm_rate_known_right"] == 1.0
        )
        assert report["lane_failures"] == []

    def test_a_checker_that_confirms_everything_fails_and_names_the_class(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        verdict = self.run(truth_world, tmp_path, "confirm", "confirm")
        assert verdict["passed"] is False and verdict["agreement"] == 0.375
        # Sonnet since D36: a failing checker moves up one tier, to Opus
        assert verdict["tier_move"]["to"] == "claude-opus-5-5" and "held" not in verdict
        report = json.loads((tmp_path / "calibration" / PL.ADV_CALIBRATION_ID
                             / CC.COMPARISON_FILE).read_text(encoding="utf-8"))  # fmt: skip
        assert report["lane_failures"] == [
            "the reject rate on the known-wrong cells 0.0 is below the sealed threshold 0.9"
        ]

    def test_a_checker_that_rejects_everything_fails_on_the_known_right_class(
        self, truth_world: TruthWorld, tmp_path: Path
    ) -> None:
        verdict = self.run(truth_world, tmp_path, "reject", "reject")
        assert verdict["passed"] is False
        report = json.loads((tmp_path / "calibration" / PL.ADV_CALIBRATION_ID
                             / CC.COMPARISON_FILE).read_text(encoding="utf-8"))  # fmt: skip
        assert (
            report["reject_rate_known_wrong"] == 1.0 and report["confirm_rate_known_right"] == 0.0
        )
        assert len(report["lane_failures"]) == 1 and "known-right" in report["lane_failures"][0]


class TestComparingTheKnownTruthPool:
    def truth(self, tmp_path: Path, wrong: int = 5, right: int = 5) -> dict[str, Any]:
        entries = {f"{site_id(n)}.period_start": {"expected": "reject", "class": "known-wrong",
                                                  "basis": "perturbed-period"}
                   for n in range(wrong)}  # fmt: skip
        entries |= {f"{site_id(100 + n)}.period_start": {"expected": "confirm",
                                                         "class": "known-right",
                                                         "basis": "wd1-two-source-keep"}
                    for n in range(right)}  # fmt: skip
        path = tmp_path / "TRUTH.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        return {"role": "adversarial", "truth": str(path), "threshold": 0.9}

    @staticmethod
    def reply(verdict: str) -> str:
        return json.dumps({"fields": {"period_start": {"decision": verdict, "value": None,
                                                       "quotes": [], "reasoning": "x" * 40}}})  # fmt: skip

    def fresh(self, sealed: dict[str, Any], by_cell: dict[str, str]) -> dict[str, str]:
        truth = json.loads(Path(sealed["truth"]).read_text(encoding="utf-8"))
        return {c: self.reply(by_cell.get(c, "confirm" if t["class"] == "known-right" else "reject"))
                for c, t in truth.items()}  # fmt: skip

    def test_the_rate_of_each_class_is_its_own_and_both_must_hold(self, tmp_path: Path) -> None:
        sealed = self.truth(tmp_path, wrong=10, right=10)
        ok = PL.compare_adv_known(sealed, {}, self.fresh(sealed, {}), Path("."))
        assert ok["lane_failures"] == [] and ok["agreement"] == 1.0
        one_wrong = self.fresh(sealed, {f"{site_id(0)}.period_start": "confirm"})
        report = PL.compare_adv_known(sealed, {}, one_wrong, Path("."))
        assert report["reject_rate_known_wrong"] == 0.9 and report["lane_failures"] == []
        two_wrong = self.fresh(sealed, {f"{site_id(n)}.period_start": "confirm" for n in (0, 1)})
        report = PL.compare_adv_known(sealed, {}, two_wrong, Path("."))
        assert report["reject_rate_known_wrong"] == 0.8
        assert report["lane_failures"] == [
            "the reject rate on the known-wrong cells 0.8 is below the sealed threshold 0.9"
        ]
        assert report["agreement"] == 0.9  # the overall bar holds while a class fails
        rights = self.fresh(sealed, {f"{site_id(100 + n)}.period_start": "reject" for n in (0, 1)})
        report = PL.compare_adv_known(sealed, {}, rights, Path("."))
        assert report["confirm_rate_known_right"] == 0.8 and len(report["lane_failures"]) == 1
        assert "known-right" in report["lane_failures"][0]

    def test_an_unclear_or_malformed_answer_is_a_miss_in_its_class(self, tmp_path: Path) -> None:
        sealed = self.truth(tmp_path)
        fresh = self.fresh(sealed, {f"{site_id(0)}.period_start": "unclear"})
        fresh[f"{site_id(1)}.period_start"] = "not json"
        report = PL.compare_adv_known(sealed, {}, fresh, Path("."))
        assert report["units"] == 10 and report["agreed"] == 8 and report["unclear"] == 2
        assert report["reject_rate_known_wrong"] == 0.6
        assert {d["fresh"] for d in report["disagreements"]} == {"unclear"}
        assert report["disagreements"][0]["recorded"] == "reject"

    def test_a_cell_nobody_answered_is_unanswered_and_leaves_the_rates_alone(
        self, tmp_path: Path
    ) -> None:
        sealed = self.truth(tmp_path)
        fresh = self.fresh(sealed, {})
        del fresh[f"{site_id(0)}.period_start"]
        report = PL.compare_adv_known(sealed, {}, fresh, Path("."))
        assert report["unanswered"] == [f"{site_id(0)}.period_start"] and report["units"] == 9
        assert report["reject_rate_known_wrong"] == 1.0

    def test_a_class_nobody_answered_fails_by_name(self, tmp_path: Path) -> None:
        sealed = self.truth(tmp_path)
        truth = json.loads(Path(sealed["truth"]).read_text(encoding="utf-8"))
        fresh = {
            c: r for c, r in self.fresh(sealed, {}).items() if truth[c]["class"] == "known-wrong"
        }
        report = PL.compare_adv_known(sealed, {}, fresh, Path("."))
        assert report["lane_failures"] == ["no known-right cell was answered"]

    def test_the_agreement_by_basis_is_reported(self, tmp_path: Path) -> None:
        sealed = self.truth(tmp_path)
        report = PL.compare_adv_known(sealed, {}, self.fresh(sealed, {}), Path("."))
        assert report["agreed_by_basis"] == {"perturbed-period": 5, "wd1-two-source-keep": 5}


class TestTheWaveGateNeedsTheNewCalibrations:
    def test_the_gate_names_the_researchers_two_pools_and_the_known_truth_checker(self) -> None:
        assert PL.WD5_CALIBRATIONS == (
            ("field_researcher", "fields-decided"),
            ("field_researcher", "bp-bucket"),
            ("adversarial", "adv-known-truth"),
        )
        assert set(PL.COMPARATORS) == {c for _, c in PL.WD5_CALIBRATIONS}

    def test_the_new_calibration_ids_are_the_second_round(self) -> None:
        assert (PL.GENERAL_CALIBRATION_ID, PL.BP_CALIBRATION_ID, PL.ADV_CALIBRATION_ID) == (
            "fr-general-002", "fr-bp-002", "adv-truth-001")  # fmt: skip

    def test_a_calibration_sealed_against_the_other_tiers_entry_does_not_vouch(
        self, tmp_path: Path
    ) -> None:
        """fr-bp-001 passed (0.92) against the Sonnet entry of `field_researcher`, which owner move D36
        put back in the registry: it vouches again (the digest is the one it was sealed with). A pass
        sealed against the Opus entry (fr-bp-002) does not, and the gate refuses it by name."""
        sonnet_entry = "1e00fc31840d778071741f19b48a6165985e1595676532ccb41ec368dd927fec"
        assert RO.role_sha256("field_researcher") == sonnet_entry
        root = tmp_path / "calibration"
        (root / CC.VERDICTS_DIR).mkdir(parents=True)

        def seal(digest: str) -> None:
            (root / CC.THRESHOLDS_FILE).write_text(json.dumps({"fr-bp-001": {
                "role": "field_researcher", "comparison": "bp-bucket", "role_sha256": digest,
            }}), encoding="utf-8")  # fmt: skip

        (root / CC.VERDICTS_DIR / "fr-bp-001.json").write_text(json.dumps({"passed": True}),
                                                               encoding="utf-8")  # fmt: skip
        seal(sonnet_entry)
        assert (
            CC.require_passed(root, [("field_researcher", "bp-bucket")])[0]["standing"] == "passed"
        )
        seal(RO.role_sha256("field_researcher", model="claude-opus-5-5"))
        with pytest.raises(CC.CalibrationError, match="field_researcher/bp-bucket"):
            CC.require_passed(root, [("field_researcher", "bp-bucket")])


class TestTheQuoteAudit:
    def test_it_lists_the_quotes_no_page_holds_and_the_sources_of_each_disagreement(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "calibration"
        root.mkdir()
        (root / CC.THRESHOLDS_FILE).write_text(
            json.dumps({"c-1": {"role": "adversarial"}}), encoding="utf-8"
        )
        copy = root / "c-1"
        copy.mkdir()
        run = D.calibration_run(copy)
        run.mkdir()
        HO._write_jsonl(run / HO.ATTEMPTS_FILE, [{
            "site_id": "s1", "quotes": [{"source": "u1", "quote": "q1", "outcome": Q.FOUND,
                                         "detail": ""},
                                        {"source": "u2", "quote": "q2", "outcome": Q.NOT_FOUND,
                                         "detail": ""}]}])  # fmt: skip
        HO._write_jsonl(run / AD.VERDICTS_FILE, [{
            "cell": "s2.period_start", "quotes": [{"source": "u3", "quote": "q3",
                                                   "outcome": Q.NOT_FOUND}]}])  # fmt: skip
        (copy / CC.COMPARISON_FILE).write_text(
            json.dumps({"disagreements": [{"label": "s1", "unit": "x", "recorded": "a",
                                           "fresh": "b", "recorded_sources": [],
                                           "fresh_sources": ["u2"]}]}),
            encoding="utf-8",
        )  # fmt: skip
        report = PL.audit_quotes(root, calibration_id="c-1")
        assert [(m["cell"], m["source"]) for m in report["quotes_not_found"]] == [
            ("s1", "u2"), ("s2.period_start", "u3")
        ]  # fmt: skip
        assert report["disagreements"][0]["fresh_sources"] == ["u2"]


class TestTheCommandLine:
    def test_a_refusal_prints_and_exits_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # the known-wrong table names sites the miniature run tree does not hold
        world = TruthWorld(tmp_path)
        code = PL.main(["build-adversarial-truth", "--out", str(tmp_path / "p"), "--seed", "1",
                        "--fields-dir", str(world.fields),
                        "--wiki-root", str(world.wiki_root)])  # fmt: skip
        assert code == 1 and "is not in the wd5 classification" in capsys.readouterr().err

    def test_a_build_of_the_known_truth_pool_prints_its_seal_command(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        world = TruthWorld(tmp_path)
        monkeypatch.setattr(PL, "KNOWN_WRONG_PERIODS", world.known)
        monkeypatch.setattr(PL, "PERTURBED_QUOTA", SMALL)
        monkeypatch.setattr(PL, "RIGHT_QUOTA", SMALL)
        code = PL.main(["build-adversarial-truth", "--out", str(tmp_path / "p"), "--seed", "1",
                        "--fields-dir", str(world.fields), "--wiki-root", str(world.wiki_root),
                        "--id", "adv-truth-007"])  # fmt: skip
        assert code == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["cells"] == 8 and "--id adv-truth-007" in printed["seal"]

    def test_a_missing_seal_is_refused_by_the_compare_command(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert PL.main(["compare", "--root", str(tmp_path / "none"), "--id", "x"]) == 1
        assert "not sealed" in capsys.readouterr().err


class TestTheBpPoolEndToEnd:
    """A fresh answer, imported into the calibration run, is read against the truth file."""

    PAGE = "<html><body><p>The cave was occupied about 40,000 years ago.</p></body></html>"

    def client(self) -> httpx.Client:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"Content-Type": "text/html"}, content=self.PAGE.encode("utf-8")
            )

        return httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)

    def reply(self, quote: str) -> str:
        block = {
            "decision": "replace",
            "value": "-38050",
            "quotes": [{"url": TH.WIKI, "quote": quote}],
            "reasoning": "The page gives the occupation as about 40,000 years ago.",
        }
        return json.dumps({"fields": {"period_start": block}})

    def prepared(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
        monkeypatch.setattr(PL, "NAMED_BP_SITES", ())
        ages = {f"Cave {n}": (OLD, "unresolved") for n in range(3)}
        ages["Edge Cave"] = (EDGE_TEXT, "unresolved")
        out = tmp_path / "pool"
        built = PL.build_bp(out, seed=5, size=4, fields_dir=bp_world(tmp_path, ages))
        root = tmp_path / "calibration"
        CC.seal(root, calibration_id="fr-bp-001", role="field_researcher",
                handoff=out / "handoff", batches=built["batches"], threshold=0.9,
                comparison=PL.COMPARISON_BP, truth=out / PL.TRUTH_FILE, now=lambda: NOW)  # fmt: skip
        PL.prepare(root, calibration_id="fr-bp-001", run=out / "run")
        copy = root / "fr-bp-001"
        return root, copy, D.calibration_run(copy)

    def answer_all(self, copy: Path, quote: str, **kw: Any) -> None:
        for line in OH.manifest(copy):
            if line["batch_id"] in {b.name for b in copy.iterdir() if b.is_dir()}:
                OH.write_answer(copy, batch_id=line["batch_id"], stage="wd5", label=line["label"],
                                text=self.reply(quote), model=kw.get("model", OH.SONNET_MODEL),
                                answered_by=kw.get("by", f"field_researcher:{line['batch_id']}"))  # fmt: skip

    def test_a_counted_answer_in_the_right_bucket_passes_the_pool(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, copy, cal_run = self.prepared(tmp_path, monkeypatch)
        self.answer_all(copy, "The cave was occupied about 40,000 years ago.")
        imported = HO.import_rounds(cal_run, client=self.client(), pace=0)
        assert imported["counted"] == 4
        report = CC.compare(root, calibration_id="fr-bp-001", comparators=PL.COMPARATORS)
        assert report["units"] == 4 and report["agreed"] == 4 and report["agreement"] == 1.0
        verdict = CC.verdict(root, calibration_id="fr-bp-001", false_sources=0, now=lambda: NOW)
        assert verdict["passed"] is True

    def test_a_quote_the_page_does_not_hold_is_a_miss_and_a_quote_to_spot_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, copy, cal_run = self.prepared(tmp_path, monkeypatch)
        self.answer_all(copy, "The cave was occupied about 40,000 years ago, said Pericles.")
        HO.import_rounds(cal_run, client=self.client(), pace=0)
        report = CC.compare(root, calibration_id="fr-bp-001", comparators=PL.COMPARATORS)
        assert report["agreed"] == 0 and len(report["disagreements"]) == 4
        assert "not counted (quote not found" in report["disagreements"][0]["fresh"]
        found = PL.audit_quotes(root, calibration_id="fr-bp-001")["quotes_not_found"]
        assert len(found) == 4 and found[0]["source"] == TH.WIKI

    def test_an_answer_recorded_without_the_role_cannot_be_imported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, copy, cal_run = self.prepared(tmp_path, monkeypatch)
        self.answer_all(copy, "The cave was occupied about 40,000 years ago.", by="batch")
        with pytest.raises(HO.HandoffStepError, match="names no field_researcher role"):
            HO.import_rounds(cal_run, client=self.client(), pace=0)
