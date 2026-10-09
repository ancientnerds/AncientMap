"""Lane wd5, the calibration pools (`scripts/remediation/fields/pools.py`, D6 of 2026-10-08).

The map names three pools: 60 WD1 sites stratified by field (the field researcher, answers hidden),
about 25 sites whose earlier reasoning named an age in years before the present (the same role, the
BP reader), 40 audit cells (the adversarial checker). Offline: the run tree is a miniature built in a
temporary directory, no model is called, no page is fetched.
"""

# ruff: noqa: S311 - the draws are seeded and recorded, they must repeat; nothing here is a secret
from __future__ import annotations

import json
import random
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


# ------------------------------------------------------------------------------ the audit pool
def audit_world(tmp_path: Path, per: int = 2) -> tuple[Path, Path]:
    """`opus_audit/` with `per` keeps and `per` reverts of each column, their evidence files under a
    stand-in repository."""
    repo = tmp_path / "repo"
    audit = tmp_path / "opus_audit"
    audit.mkdir()
    decisions, inputs = [], []
    number = 0
    for verdict in ("keep", "revert"):
        for column in ("period_start", "site_type"):
            for _ in range(per):
                number += 1
                key = f"phase3:{number:04d}"
                rel = f"evidence/{number}.txt"
                (repo / "evidence").mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(f"Page {number}. The temple was built in 449 BC. More.",
                                        encoding="utf-8")  # fmt: skip
                decisions.append({"change_key": key, "column": column, "decision": verdict,
                                  "superseded": False})  # fmt: skip
                inputs.append({
                    "change_key": key, "site_id": site_id(number), "site_name": f"Site {number}",
                    "column": column, "old_value": "-1500" if column == "period_start" else "Ruin",
                    "written_value": "-449" if column == "period_start" else "Temple",
                    "country_now": "Greece", "reviewer_reason": "r", "evidence_files": [rel],
                    "finder_quote": [{"quote": "The temple was built in 449 BC.",
                                      "url": "https://api/x"}],
                })  # fmt: skip
    HO._write_jsonl(audit / "DECISIONS.jsonl", decisions)
    HO._write_jsonl(audit / "INPUT.jsonl", inputs)
    return audit, repo


class TestTheAdversarialPool:
    def test_only_a_decided_unsuperseded_row_of_a_wd5_column_with_a_quote_is_a_candidate(
        self, tmp_path: Path
    ) -> None:
        audit, _ = audit_world(tmp_path, per=2)
        rows = HO._read_jsonl(audit / "DECISIONS.jsonl")
        rows[0]["superseded"] = True
        rows[1]["decision"] = "wrong-both"
        rows[2]["column"] = "country"
        HO._write_jsonl(audit / "DECISIONS.jsonl", rows)
        assert len(PL.audit_candidates(audit)) == 5
        inputs = HO._read_jsonl(audit / "INPUT.jsonl")
        inputs[3]["finder_quote"] = []
        HO._write_jsonl(audit / "INPUT.jsonl", inputs)
        assert len(PL.audit_candidates(audit)) == 4

    def test_a_cell_is_the_written_value_under_the_finders_quote_and_its_page(
        self, tmp_path: Path
    ) -> None:
        audit, repo = audit_world(tmp_path, per=1)
        cell = PL.audit_cell(PL.audit_candidates(audit)[0], repo)
        assert cell["decision"] == "replace" and cell["value"] == "-449"
        assert cell["stored"] == "-1500" and cell["stored_point"] is None and cell["wiki"] is None
        [quote] = cell["quotes"]
        assert quote["url"] == "https://api/x" and "449 BC" in quote["passage"]
        text = AD.render_prompt(cell)
        assert "stored point" not in text and "the checker found it in the page's as served" in text

    def test_a_row_whose_quote_is_in_none_of_its_files_is_refused(self, tmp_path: Path) -> None:
        audit, repo = audit_world(tmp_path, per=1)
        row = PL.audit_candidates(audit)[0]
        (repo / row["evidence_files"][0]).write_text("nothing here", encoding="utf-8")
        with pytest.raises(AD.AdversarialError, match="no finder quote"):
            PL.audit_cell(row, repo)

    def test_the_pool_is_keeps_and_reverts_in_equal_halves_with_a_truth_file(
        self, tmp_path: Path
    ) -> None:
        audit, repo = audit_world(tmp_path, per=4)
        out = tmp_path / "pool"
        result = PL.build_adversarial(out, seed=1, per_class=4, audit_dir=audit, repo=repo)
        assert result["cells"] == 8 and result["expected"] == {"confirm": 4, "reject": 4}
        truth = json.loads((out / PL.TRUTH_FILE).read_text(encoding="utf-8"))
        assert {t["column"] for t in truth.values()} == {"period_start", "site_type"}
        assert sum(1 for t in truth.values() if t["audit_decision"] == "keep") == 4
        assert all(t["expected"] == ("confirm" if t["audit_decision"] == "keep" else "reject")
                   for t in truth.values())  # fmt: skip
        manifest = OH.manifest(out / "handoff")
        assert {m["label"] for m in manifest} == set(truth)
        assert not list((out / "handoff").rglob("*.answer.json"))
        assert "--role adversarial" in result["seal"] and "--comparison adv-truth" in result["seal"]
        assert "--max-undecided-excess 0.1" in result["seal"]

    def test_the_draw_is_seeded(self, tmp_path: Path) -> None:
        audit, repo = audit_world(tmp_path, per=4)

        def cells(seed: int, sub: str) -> list[str]:
            PL.build_adversarial(tmp_path / sub, seed=seed, per_class=4, audit_dir=audit, repo=repo)
            return sorted(json.loads((tmp_path / sub / PL.TRUTH_FILE).read_text("utf-8")))

        assert cells(1, "a") == cells(1, "b")
        assert cells(1, "c") != cells(2, "d")

    def test_too_few_usable_rows_are_refused_by_count(self, tmp_path: Path) -> None:
        audit, repo = audit_world(tmp_path, per=1)
        with pytest.raises(PL.PoolError, match="only 1 usable keep rows of period_start, 2 wanted"):
            PL.build_adversarial(tmp_path / "p", seed=1, per_class=4, audit_dir=audit, repo=repo)

    def test_an_odd_class_size_does_not_split_in_two_columns(self, tmp_path: Path) -> None:
        with pytest.raises(PL.PoolError, match="do not split"):
            PL.build_adversarial(tmp_path / "p", seed=1, per_class=3)

    def test_the_calibration_run_gets_the_frozen_cells_and_can_be_imported_and_compared(
        self, tmp_path: Path
    ) -> None:
        audit, repo = audit_world(tmp_path, per=2)
        out = tmp_path / "pool"
        built = PL.build_adversarial(out, seed=1, per_class=4, audit_dir=audit, repo=repo)
        root = tmp_path / "calibration"
        seal = CC.seal(root, calibration_id="adv-001", role="adversarial", handoff=out / "handoff",
                       batches=built["batches"], threshold=0.9, max_undecided_excess=0.1,
                       comparison=PL.COMPARISON_ADV, truth=out / PL.TRUTH_FILE,
                       now=lambda: NOW)  # fmt: skip
        PL.prepare(root, calibration_id="adv-001", run=out / "run")
        copy = root / "adv-001"
        cal_run = D.calibration_run(copy)
        assert (cal_run / AD.CELLS_FILE).exists()
        truth = json.loads((out / PL.TRUTH_FILE).read_text(encoding="utf-8"))
        # an Opus agent answers each question, recorded under the role
        for line in OH.manifest(copy):
            expected = truth[line["label"]]["expected"]
            field = line["label"].rsplit(".", 1)[1]
            body = {"fields": {field: {"decision": expected, "value": None, "quotes": [],
                                       "reasoning": "x" * 40}}}  # fmt: skip
            OH.write_answer(copy, batch_id=line["batch_id"], stage=AD.STAGE, label=line["label"],
                            text=json.dumps(body), answered_by=f"adversarial:{line['batch_id']}",
                            model=OH.OPUS_MODEL)  # fmt: skip
        imported = AD.import_answers(cal_run, pace=0)
        assert imported["states"] == {"confirm": 4, "reject": 4}
        report = CC.compare(root, calibration_id="adv-001", comparators=PL.COMPARATORS)
        assert report["agreement"] == 1.0 and report["units"] == 8
        assert report["undecided_excess"] == 0.0
        verdict = CC.verdict(root, calibration_id="adv-001", false_sources=0, now=lambda: NOW)
        assert verdict["passed"] is True and seal["comparison"] == "adv-truth"


class TestComparingTheAdversarialPool:
    def truth(self, tmp_path: Path) -> dict[str, Any]:
        path = tmp_path / "TRUTH.json"
        path.write_text(
            json.dumps({f"{site_id(n)}.period_start": {"expected": e} for n, e in
                        ((1, "confirm"), (2, "reject"), (3, "reject"), (4, "confirm"))}),
            encoding="utf-8",
        )  # fmt: skip
        return {"role": "adversarial", "truth": str(path)}

    @staticmethod
    def reply(verdict: str) -> str:
        return json.dumps({"fields": {"period_start": {"decision": verdict, "value": None,
                                                       "quotes": [], "reasoning": "x" * 40}}})  # fmt: skip

    def cells(self, *verdicts: str) -> dict[str, str]:
        return {
            f"{site_id(n)}.period_start": self.reply(v) for n, v in enumerate(verdicts, start=1)
        }

    def test_agreement_is_over_the_cells_the_checker_decides(self, tmp_path: Path) -> None:
        report = PL.compare_adv(self.truth(tmp_path), {}, self.cells("confirm", "reject", "confirm",
                                                                    "unclear"), Path("."))  # fmt: skip
        assert report["units"] == 3 and report["agreed"] == 2
        assert report["disagreements"][0]["recorded"] == "reject"
        assert report["undecided"] == {
            "gold": 0.0,
            "fresh": 0.25,
            "gold_units": 4,
            "fresh_units": 4,
        }
        assert report["undecided_excess"] == 0.25

    def test_an_answer_not_in_shape_is_undecided_and_a_missing_one_unanswered(
        self, tmp_path: Path
    ) -> None:
        fresh = self.cells("confirm", "reject", "reject")
        fresh[f"{site_id(4)}.period_start"] = "not json"
        del fresh[f"{site_id(3)}.period_start"]
        report = PL.compare_adv(self.truth(tmp_path), {}, fresh, Path("."))
        assert report["unanswered"] == [f"{site_id(3)}.period_start"]
        assert report["units"] == 2 and report["undecided"]["fresh"] == round(1 / 3, 4)


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
        code = PL.main(["build-adversarial", "--out", str(tmp_path / "p"), "--seed", "1",
                        "--per-class", "3"])  # fmt: skip
        assert code == 1 and "REFUSED" in capsys.readouterr().err

    def test_a_build_prints_the_seal_command(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        audit, repo = audit_world(tmp_path, per=2)
        out = tmp_path / "p"
        PL.build_adversarial(out, seed=1, per_class=4, audit_dir=audit, repo=repo)
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
