"""The adjudicated gold of the card lane's calibration (`teaser/calibrate.py`), 2026-10-10.

Calibration teaser-2026-10-09b/c measured the fact checker against one unadjudicated recorded answer:
the recorded FAILs concentrate on a hair-splitting boundary (the recording model reproduces 9 of 30),
so `fail_again 27 of 30` could not be met by construction. An orchestrator-made, committed and sealed
`ADJUDICATION.json` labels each recorded FAIL substantive, hair-split or wrong, and each recorded
VERIFIED card clean, disputed or contradicted: only substantive FAILs are scored, either verdict is
accepted on a hair-split, a wrong one is dropped, and a verifier's DISPUTED verdict is scored apart
from a contradiction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from teaser import calibrate as K  # noqa: E402

from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.test_teaser_calibrate import (  # noqa: E402
    PAGE,
    QUOTE,
    TINY,
    answer_role,
    base_cards,
    checker_text,
    defect_text,
    export_file,
    judge_client,
    recorded_run,
    wiki_cache,  # noqa: F401 - the autouse fixture: a web role is exported with a cache
)
from tests.remediation.test_teaser_shorts_run import check_json  # noqa: E402


# ------------------------------------------------------------------------------ the fixture
def draw(tmp_path: Path) -> list[dict[str, Any]]:
    """The fixed cases of the tiny table, before anything is sealed (the draw is pure)."""
    return K.build_jobs(
        TINY, runs=[recorded_run(tmp_path)], export=export_file(tmp_path), base_cards=base_cards()
    )


def recorded_fails(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        j
        for j in jobs
        if j["set"] in ("checker_agreement", "checker_fail_again")
        and j["recorded"]["verdict"] == "FAIL"
    ]


def write_adjudication(
    tmp_path: Path,
    jobs: list[dict[str, Any]],
    fails: dict[str, str] | str = K.SUBSTANTIVE,
    cards: str | None = None,
    **extra: Any,
) -> Path:
    """The adjudication file for this draw: `fails` is one label for every recorded FAIL, or a map
    from the case's set and position to its label (the agreement set has one FAIL, the fail-again
    set two); `cards` is one label for every recorded VERIFIED card the draw holds (none: unlabelled,
    which reads clean)."""
    entries = []
    seen = {"checker_agreement": 0, "checker_fail_again": 0}
    for job in sorted(recorded_fails(jobs), key=lambda j: (j["set"], j["number"])):
        seen[job["set"]] += 1
        label = fails if isinstance(fails, str) else fails[f"{job['set']}/{seen[job['set']]}"]
        recorded = job["recorded"]
        entries.append(
            {
                "run": recorded["run"],
                "stage": recorded["stage"],
                "site_id": job["site_id"],
                "name": job["name"],
                "card": job["card"],
                "label": label,
                "note": "",
            }
        )
    verified = {}
    for job in jobs:
        if cards is not None and job["set"] in ("verifier_verified", "adversarial_clean"):
            verified[job["site_id"]] = {
                "site_id": job["site_id"],
                "name": job["name"],
                "card": job["card"],
                "label": cards,
                "note": "",
            }
    document = {
        "version": K.ADJUDICATION_VERSION,
        "checker_fails": entries,
        "verified_cards": list(verified.values()),
        **extra,
    }
    path = tmp_path / "ADJUDICATION.json"
    path.write_text(json.dumps(document, indent=1), encoding="utf-8")
    return path


def adjudicated_dir(tmp_path: Path, adjudication: Path) -> Path:
    run_dir = tmp_path / "calibration" / "teaser-test"
    K.seal(run_dir, thresholds=TINY, adjudication=adjudication)
    jobs = K.build_jobs(
        K.sealed(run_dir)[0],
        runs=[recorded_run(tmp_path)],
        export=export_file(tmp_path),
        base_cards=base_cards(),
    )
    K.fix_jobs(run_dir, jobs)
    return run_dir


def mirror(job: dict[str, Any]) -> str:
    recorded = job["recorded"]
    claims = [(c["claim"], c["support"]) for c in recorded["claims"]]
    return T.checker_answer(recorded["verdict"], claims, recorded["reasons"])


def flipped(job: dict[str, Any]) -> str:
    """The opposite verdict of the recorded one (a PASS for a recorded FAIL)."""
    return checker_text("PASS" if job["recorded"]["verdict"] == "FAIL" else "FAIL")(job)


def answer_checker(
    run_dir: Path,
    *,
    agreement: Any = mirror,
    again: Any = checker_text("FAIL"),
    defects: Any = defect_text("FAIL"),
) -> None:
    answer_role(
        run_dir,
        "card_fact_checker",
        {
            "checker_agreement": agreement,
            "checker_fail_again": again,
            "checker_defects": defects,
            "checker_good": checker_text("PASS"),
        },
    )


# ------------------------------------------------------------------------------ the file
class TestTheFile:
    def test_a_version_other_than_the_known_one_is_refused(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path), version="v0")
        with pytest.raises(K.CalibrationError, match="not teaser-gold-adjudication-v1"):
            K.read_adjudication(path)

    def test_an_unknown_label_is_refused(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path), fails="dubious")
        with pytest.raises(K.CalibrationError, match="is labelled 'dubious'"):
            K.read_adjudication(path)

    def test_an_unknown_card_label_is_refused(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path), cards="mostly fine")
        with pytest.raises(K.CalibrationError, match="is labelled 'mostly fine'"):
            K.read_adjudication(path)

    def test_a_recorded_fail_labelled_twice_is_refused(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path))
        document = json.loads(path.read_text("utf-8"))
        document["checker_fails"].append(document["checker_fails"][0])
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="is labelled twice"):
            K.read_adjudication(path)

    def test_the_committed_gold_adjudication_reads_and_labels_all_45_recorded_fails(self) -> None:
        adjudication = K.read_adjudication(K.ADJUDICATION_FILE)
        assert len(adjudication.fails) == 45
        labels = [label for label, _ in adjudication.fails.values()]
        assert {label: labels.count(label) for label in K.FAIL_LABELS} == {
            K.SUBSTANTIVE: 26,
            K.HAIR_SPLIT: 17,
            K.WRONG: 2,
        }
        # the diagnosis's own lists: the two cases it names wrong, and a sample of each class
        by_name = {
            e["name"]: e["label"]
            for e in json.loads(K.ADJUDICATION_FILE.read_text("utf-8"))["checker_fails"]
        }
        assert by_name["Lohra Megalithic Tomb"] == K.WRONG
        assert by_name["Roman Thermae, Varna"] == K.WRONG
        assert by_name["Kit's Coty House"] == K.SUBSTANTIVE
        assert by_name["Knossos"] == K.HAIR_SPLIT


# ------------------------------------------------------------------------------ the seal
class TestTheSeal:
    def test_the_seal_records_the_file_it_was_sealed_with(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path))
        run_dir = adjudicated_dir(tmp_path, path)
        sealed = json.loads((run_dir / K.THRESHOLDS_FILE).read_text("utf-8"))["adjudication"]
        assert sealed["path"] == path.resolve().as_posix()
        assert len(sealed["sha256"]) == 64

    def test_a_seal_without_a_file_records_none(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "calibration" / "teaser-test"
        K.seal(run_dir, thresholds=TINY)
        assert json.loads((run_dir / K.THRESHOLDS_FILE).read_text("utf-8"))["adjudication"] is None
        assert K.sealed_adjudication(K.sealed(run_dir)[0]) is None

    def test_a_malformed_file_is_refused_before_the_seal(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path), fails="dubious")
        with pytest.raises(K.CalibrationError, match="dubious"):
            K.seal(tmp_path / "calibration" / "teaser-test", thresholds=TINY, adjudication=path)
        assert not (tmp_path / "calibration").exists()

    def test_a_file_changed_after_the_seal_is_refused(self, tmp_path: Path) -> None:
        path = write_adjudication(tmp_path, draw(tmp_path))
        run_dir = adjudicated_dir(tmp_path, path)
        document = json.loads(path.read_text("utf-8"))
        document["checker_fails"][0]["label"] = K.WRONG
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="changed after the seal"):
            K.sealed(run_dir)

    def test_the_real_table_asks_for_a_disputed_maximum(self) -> None:
        assert (
            K.THRESHOLDS["roles"]["card_web_verifier"]["sets"]["verifier_verified"][
                "falsely_disputed_max"
            ]
            == 2
        )


# ------------------------------------------------------------------------------ the fact checker
class TestTheAdjudicatedFactChecker:
    def test_a_hair_split_accepts_either_verdict(self, tmp_path: Path) -> None:
        jobs = draw(tmp_path)
        fails = {
            "checker_agreement/1": K.HAIR_SPLIT,
            "checker_fail_again/1": K.SUBSTANTIVE,
            "checker_fail_again/2": K.SUBSTANTIVE,
        }
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, jobs, fails))
        # the checker passes the hair-split card the record failed, and agrees on all the rest
        answer_checker(run_dir, agreement=lambda j: flipped(j) if is_fail(j) else mirror(j))
        verdict = K.evaluate(run_dir, "card_fact_checker")
        agreement = verdict["sets"]["checker_agreement"]
        assert agreement["passed"] is True and agreement["verdict_agreement"] == 1.0
        (name,) = agreement["unscored"][K.HAIR_SPLIT]
        assert agreement["unscored"][K.HAIR_SPLIT][name] == "PASS"
        assert verdict["passed"] is True

    def test_without_the_adjudication_the_same_answers_fail(self, tmp_path: Path) -> None:
        from tests.remediation.test_teaser_calibrate import fixed_dir  # noqa: PLC0415

        run_dir = fixed_dir(tmp_path)
        answer_checker(run_dir, agreement=lambda j: flipped(j) if is_fail(j) else mirror(j))
        agreement = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_agreement"]
        assert agreement["passed"] is False and agreement["verdict_agreement"] < 1.0

    def test_a_substantive_fail_the_checker_passes_still_fails_the_role(
        self, tmp_path: Path
    ) -> None:
        jobs = draw(tmp_path)
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, jobs))
        answer_checker(run_dir, agreement=lambda j: flipped(j) if is_fail(j) else mirror(j))
        agreement = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_agreement"]
        assert agreement["passed"] is False and agreement["false_pass"]

    def test_a_wrong_record_is_dropped_and_reported_by_name(self, tmp_path: Path) -> None:
        jobs = draw(tmp_path)
        fails = {
            "checker_agreement/1": K.SUBSTANTIVE,
            "checker_fail_again/1": K.WRONG,
            "checker_fail_again/2": K.SUBSTANTIVE,
        }
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, jobs, fails))
        wrong = min(
            (j for j in jobs if j["set"] == "checker_fail_again"), key=lambda j: j["number"]
        )
        # the checker passes the dropped case and fails the other one
        answer_checker(
            run_dir,
            again=lambda j: checker_text("PASS" if j["number"] == wrong["number"] else "FAIL")(j),
        )
        again = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_fail_again"]
        assert again["counted"] == 1 and again["failed_again"] == 1
        assert again["failed_again_required"] == 1 and again["passed"] is True
        assert again["unscored"][K.WRONG] == [wrong["name"]]

    def test_the_minimum_scales_with_the_substantive_cases_only(self, tmp_path: Path) -> None:
        jobs = draw(tmp_path)
        fails = {
            "checker_agreement/1": K.SUBSTANTIVE,
            "checker_fail_again/1": K.HAIR_SPLIT,
            "checker_fail_again/2": K.SUBSTANTIVE,
        }
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, jobs, fails))
        answer_checker(run_dir, again=checker_text("PASS"))
        again = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_fail_again"]
        assert (again["counted"], again["failed_again_required"], again["failed_again"]) == (
            1,
            1,
            0,
        )
        assert again["passed"] is False

    def test_a_recorded_fail_nobody_labelled_is_refused(self, tmp_path: Path) -> None:
        jobs = draw(tmp_path)
        path = write_adjudication(tmp_path, jobs)
        document = json.loads(path.read_text("utf-8"))
        document["checker_fails"].pop()
        path.write_text(json.dumps(document), encoding="utf-8")
        run_dir = adjudicated_dir(tmp_path, path)
        answer_checker(run_dir)
        with pytest.raises(K.CalibrationError, match="does not label the recorded FAIL"):
            K.evaluate(run_dir, "card_fact_checker")

    def test_a_label_for_a_case_the_draw_does_not_hold_is_refused(self, tmp_path: Path) -> None:
        jobs = draw(tmp_path)
        path = write_adjudication(tmp_path, jobs)
        document = json.loads(path.read_text("utf-8"))
        document["checker_fails"].append(
            {**document["checker_fails"][0], "site_id": "0b000000-0000-4000-8000-000000000099"}
        )
        path.write_text(json.dumps(document), encoding="utf-8")
        run_dir = adjudicated_dir(tmp_path, path)
        answer_checker(run_dir)
        with pytest.raises(K.CalibrationError, match="which the fixed draw does not hold"):
            K.evaluate(run_dir, "card_fact_checker")

    def test_a_label_on_another_card_than_the_case_is_refused(self, tmp_path: Path) -> None:
        jobs = draw(tmp_path)
        path = write_adjudication(tmp_path, jobs)
        document = json.loads(path.read_text("utf-8"))
        document["checker_fails"][0]["card"] = "Another card entirely."
        path.write_text(json.dumps(document), encoding="utf-8")
        run_dir = adjudicated_dir(tmp_path, path)
        answer_checker(run_dir)
        with pytest.raises(K.CalibrationError, match="names another card"):
            K.evaluate(run_dir, "card_fact_checker")


def is_fail(job: dict[str, Any]) -> bool:
    return bool(job["recorded"]["verdict"] == "FAIL")


# ------------------------------------------------------------------------------ the seeded defects
class TestTheSubtleDefectsAreCaughtOnlyWhenTheClaimIsNamed:
    def run_dir(self, tmp_path: Path) -> Path:
        return adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))

    def test_the_jobs_record_what_a_checker_must_name(self, tmp_path: Path) -> None:
        defects = [j for j in draw(tmp_path) if j["set"] == "checker_defects"]
        subtle = [j for j in defects if j["recorded"]["subtle"]]
        assert subtle, "the tiny base cards carry words a subtle defect can change"
        for job in subtle:
            assert job["recorded"]["sentence"] in job["card"]
            assert job["recorded"]["witness"]

    def test_a_checker_that_names_the_claim_catches_every_defect(self, tmp_path: Path) -> None:
        run_dir = self.run_dir(tmp_path)
        answer_checker(run_dir)
        defects = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_defects"]
        assert defects["caught"] == 3 and defects["caught_subtle"] == defects["subtle_cases"] > 0
        assert defects["failed_without_naming_the_claim"] == []

    def test_a_fail_that_names_nothing_catches_no_subtle_defect(self, tmp_path: Path) -> None:
        run_dir = self.run_dir(tmp_path)
        answer_checker(run_dir, defects=defect_text("FAIL", naming=False))
        defects = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_defects"]
        assert defects["caught"] == 3 - defects["subtle_cases"]
        assert len(defects["failed_without_naming_the_claim"]) == defects["subtle_cases"]
        assert defects["passed"] is False

    def test_a_blunt_defect_is_caught_by_any_fail(self, tmp_path: Path) -> None:
        jobs = [j for j in draw(tmp_path) if j["set"] == "checker_defects"]
        blunt = [j for j in jobs if not j["recorded"]["subtle"]]
        if not blunt:
            pytest.skip("every tiny base card took a subtle defect")
        run_dir = self.run_dir(tmp_path)
        answer_checker(run_dir, defects=defect_text("FAIL", naming=False))
        defects = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_defects"]
        assert defects["caught"] >= len(blunt)


# ------------------------------------------------------------------------------ the web verifier
def verified_answer(verdict: str):
    """The verifier's answer to a recorded VERIFIED card: its claims as recorded, one of them with
    `verdict` (a dispute or a contradiction) when it is not SUPPORTED."""

    def make(job: dict[str, Any]) -> str:
        recorded = job["recorded"]["claims"]
        claims = [
            {"claim": c["claim"], "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE}
            for c in recorded
        ]
        if verdict != "SUPPORTED":
            claims.append(
                {"claim": "a second claim", "verdict": verdict, "url": PAGE, "quote": QUOTE}
            )
        return json.dumps({"claims": claims})

    return make


def contradicted_answer(job: dict[str, Any]) -> str:
    claim = {"claim": "lived in", "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE}
    return json.dumps(
        {"claims": [claim, {**claim, "claim": "built by the Inca", "verdict": "CONTRADICTED"}]}
    )


class TestTheDisputedVerdictIsScoredApart:
    def verifier(self, tmp_path: Path, label: str | None, verdict: str) -> dict[str, Any]:
        """The verifier's measure on the two recorded VERIFIED cards of the tiny draw, all labelled
        `label`, when it answers every one of them with a claim of `verdict`."""
        run_dir = adjudicated_dir(
            tmp_path, write_adjudication(tmp_path, draw(tmp_path), cards=label)
        )
        answer_role(
            run_dir,
            "card_web_verifier",
            {
                "verifier_contradicted": contradicted_answer,
                "verifier_verified": verified_answer(verdict),
            },
        )
        return K.evaluate(run_dir, "card_web_verifier", client=judge_client())["sets"][
            "verifier_verified"
        ]

    def test_a_dispute_of_a_clean_card_is_a_false_dispute_not_a_false_contradiction(
        self, tmp_path: Path
    ) -> None:
        result = self.verifier(tmp_path, None, "DISPUTED")
        assert len(result["falsely_disputed"]) == 2 and result["falsely_contradicted"] == []
        assert result["passed"] is False

    def test_a_dispute_of_a_card_the_sources_really_dispute_is_right(self, tmp_path: Path) -> None:
        result = self.verifier(tmp_path, K.DISPUTED_CARD, "DISPUTED")
        assert len(result["rightly_disputed"]) == 2
        assert result["falsely_disputed"] == [] and result["falsely_contradicted"] == []
        assert result["card_verdict_agreement"] == 0.0  # no clean card was asked

    def test_a_contradiction_of_a_disputed_card_is_a_false_contradiction(
        self, tmp_path: Path
    ) -> None:
        result = self.verifier(tmp_path, K.DISPUTED_CARD, "CONTRADICTED")
        assert len(result["falsely_contradicted"]) == 2 and result["passed"] is False

    def test_a_contradiction_of_a_card_whose_gold_is_wrong_is_not_false(
        self, tmp_path: Path
    ) -> None:
        result = self.verifier(tmp_path, K.CONTRADICTED_CARD, "CONTRADICTED")
        assert result["falsely_contradicted"] == [] and len(result["gold_wrong"]) == 2

    def test_a_contradiction_of_an_unlabelled_card_is_false(self, tmp_path: Path) -> None:
        result = self.verifier(tmp_path, None, "CONTRADICTED")
        assert len(result["falsely_contradicted"]) == 2 and result["falsely_disputed"] == []


# ------------------------------------------------------------------------------ the adversary
class TestTheAdjudicatedAdversary:
    def adversary(self, tmp_path: Path, label: str, verdict: str) -> dict[str, Any]:
        path = write_adjudication(tmp_path, draw(tmp_path), cards=label)
        run_dir = adjudicated_dir(tmp_path, path)

        def fail_all(job: dict[str, Any]) -> str:
            return checker_text("FAIL")(job)

        answer_role(
            run_dir,
            "card_adversarial",
            {
                "adversarial_contradicted": fail_all,
                "adversarial_clean": checker_text(verdict),
            },
        )
        return K.evaluate(run_dir, "card_adversarial")["sets"]

    def test_a_clean_card_failed_is_wrong(self, tmp_path: Path) -> None:
        sets = self.adversary(tmp_path, K.CLEAN, "FAIL")
        assert sets["adversarial_clean"]["right"] == 0

    def test_a_card_the_sources_dispute_accepts_either_verdict(self, tmp_path: Path) -> None:
        for verdict in ("PASS", "FAIL"):
            sets = self.adversary(tmp_path / verdict, K.DISPUTED_CARD, verdict)
            assert sets["adversarial_clean"]["cases"] == 0
            assert len(sets["adversarial_clean"]["unscored_disputed"]) == 2

    def test_a_card_whose_gold_is_wrong_should_fail(self, tmp_path: Path) -> None:
        assert (
            self.adversary(tmp_path / "a", K.CONTRADICTED_CARD, "FAIL")["adversarial_clean"][
                "right"
            ]
            == 2
        )
        assert (
            self.adversary(tmp_path / "b", K.CONTRADICTED_CARD, "PASS")["adversarial_clean"][
                "right"
            ]
            == 0
        )


# ------------------------------------------------------------------------------ the dispute list
class TestTheDisputeList:
    def test_it_lists_the_cards_a_verifier_contradicted_with_their_sources(
        self, tmp_path: Path
    ) -> None:
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))
        answer_role(
            run_dir,
            "card_web_verifier",
            {
                "verifier_contradicted": contradicted_answer,
                "verifier_verified": contradicted_answer,
            },
        )
        K.evaluate(run_dir, "card_web_verifier", client=judge_client())  # keeps the cited pages
        listed = K.dispute_list(run_dir, "card_web_verifier")
        assert len(listed) == 2
        entry = listed[0]
        assert entry["contradicted"] == [
            {
                "claim": "built by the Inca",
                "url": PAGE,
                "quote": QUOTE,
                "quote_outcome": entry["contradicted"][0]["quote_outcome"],
                "proven": entry["contradicted"][0]["proven"],
            }
        ]
        assert entry["fresh_verdict"] == "CONTRADICTED" and entry["recorded_verification"]
        assert entry["label_template"] == {
            "site_id": entry["site_id"],
            "name": entry["name"],
            "card": entry["card"],
            "label": None,
            "note": "",
        }

    def test_it_lists_the_clean_cards_an_adversary_failed_with_their_reasons(
        self, tmp_path: Path
    ) -> None:
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))

        def cites(job: dict[str, Any]) -> str:
            return T.checker_answer(
                "FAIL", [("x", [])], [f"The dating differs at {PAGE}: 'a quote'."]
            )

        answer_role(
            run_dir,
            "card_adversarial",
            {"adversarial_contradicted": cites, "adversarial_clean": cites},
        )
        listed = K.dispute_list(run_dir, "card_adversarial")
        assert len(listed) == 2
        assert listed[0]["sources_cited"] == [PAGE]
        assert listed[0]["unsupported_claims"] == ["x"]

    def test_it_reads_and_changes_nothing(self, tmp_path: Path) -> None:
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))
        answer_role(
            run_dir,
            "card_web_verifier",
            {
                "verifier_contradicted": contradicted_answer,
                "verifier_verified": contradicted_answer,
            },
        )
        K.evaluate(run_dir, "card_web_verifier", client=judge_client())  # keeps the cited pages
        before = sorted((p, p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file())
        K.dispute_list(run_dir, "card_web_verifier")
        assert before == sorted((p, p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file())

    def test_it_serves_a_calibration_whose_modules_moved_after_the_seal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))
        answer_role(
            run_dir,
            "card_web_verifier",
            {
                "verifier_contradicted": contradicted_answer,
                "verifier_verified": contradicted_answer,
            },
        )
        K.evaluate(run_dir, "card_web_verifier", client=judge_client())  # keeps the cited pages
        # the checkout's prompts are no longer the sealed ones: a judgement would be refused
        monkeypatch.setattr(
            K, "module_hashes", lambda root=K.ROOT, names=None: dict.fromkeys(names, "0" * 64)
        )
        with pytest.raises(K.CalibrationError, match="changed after the seal"):
            K.sealed(run_dir)
        assert K.dispute_list(run_dir, "card_web_verifier")

    def test_only_the_web_roles_are_listed(self, tmp_path: Path) -> None:
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))
        with pytest.raises(K.CalibrationError, match="only the web verifier and the adversarial"):
            K.dispute_list(run_dir, "card_fact_checker")

    def test_a_role_never_exported_is_refused(self, tmp_path: Path) -> None:
        run_dir = adjudicated_dir(tmp_path, write_adjudication(tmp_path, draw(tmp_path)))
        with pytest.raises(K.CalibrationError, match="was never exported"):
            K.dispute_list(run_dir, "card_adversarial")


def test_check_json_is_the_shorts_shape() -> None:
    """The defect answers of this file are shorts-v1's checker shape."""
    assert json.loads(check_json("FAIL"))["verdict"] == "FAIL"
