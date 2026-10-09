"""The calibration of the image roles (`image_roles/calibrate.py`): sealed first, measured after.

Offline: the sample is invented, the answers are written in the stamp of the role's registered model,
and the interval is a stub (the project's Clopper-Pearson lives in the main checkout's run data).
"""

from __future__ import annotations

import functools
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from image_roles import calibrate as CAL  # noqa: E402
from image_roles import depicts as DP  # noqa: E402
from image_roles import identity as ID  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402
from served_image import state as ST  # noqa: E402

FIXED = "2026-10-09T01:00:00Z"
NOW = "2026-10-09T03:00:00+00:00"


def cp(k: int, n: int) -> tuple[float, float]:
    """A stub interval: the evaluation only carries it."""
    return (max(0.0, k / n - 0.05) if n else 0.0, min(1.0, k / n + 0.05) if n else 1.0)


@functools.cache
def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 300), (100, 100, 100)).save(out, format="JPEG")
    return out.getvalue()


def read(case: Any) -> bytes:
    return jpeg()


def answer(handoff: Path, spec: SG.Spec, texts: dict[str, str]) -> None:
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff, batch_id=line["batch_id"], stage=spec.name, label=line["label"],
            text=texts[line["label"]], answered_by=f"{spec.role}:{line['batch_id']}",
            model=OH.ANSWER_MODELS[RO.role(spec.role).model], now=lambda: NOW,
        )  # fmt: skip


def site(site_id: str = "s1") -> dict[str, Any]:
    return {
        "site_id": site_id, "name": f"Site {site_id}", "country": "Greece", "site_type": "Tomb",
        "lat": 40.0, "lon": 24.0, "description": "A tomb.", "wikipedia_lead": None,
    }  # fmt: skip


def case(
    case_id: str,
    role: str,
    group: str,
    truth: str | None,
    file: str,
    site_id: str = "s1",
    **over: Any,
) -> dict[str, Any]:
    return {
        "case_id": case_id, "role": role, "group": group, "site": site(site_id), "file": file,
        "path": "/x", "truth": truth, **over,
    }  # fmt: skip


# ======================================================================================= the seal
class TestTheSeal:
    def test_the_thresholds_are_the_maps_and_name_every_role_s_registry_entry(self) -> None:
        document = json.loads(CAL.thresholds_text())
        roles = document["roles"]
        assert roles["image_prefilter"]["photo_agreement_min"] == 0.92
        assert roles["image_prefilter"]["depicts_capable_recall_min"] == 0.98
        assert roles["image_depicts"]["sensitivity_min"] == 0.90
        assert roles["image_depicts"]["false_depicts_max"] == 0.03
        assert roles["image_depicts"]["precision_min"] == 0.95
        assert roles["adversarial"]["agreement_min"] == 0.95
        assert roles["web_verifier"]["correct_min"] == 0.90
        assert (
            roles["web_verifier"]["wrong_links"] == 5 and roles["web_verifier"]["good_links"] == 20
        )
        assert set(document["role_registry"]) == set(roles)
        assert document["role_registry"]["image_prefilter"]["model"] == "claude-haiku-5-5"
        assert document["interval"].startswith("Clopper-Pearson")

    def test_a_seal_is_written_once_and_logged(self, tmp_path: Path) -> None:
        digest = CAL.seal(tmp_path, now=lambda: FIXED)
        assert (
            CAL.seal(tmp_path, now=lambda: FIXED) == digest
        )  # the same seal again changes nothing
        entries = [json.loads(x) for x in (tmp_path / CAL.SEAL_LOG).read_text().splitlines()]
        assert entries[0]["thresholds_sha256"] == digest
        _, again, at = CAL.sealed(tmp_path)
        assert again == digest and at == FIXED

    def test_other_thresholds_are_never_written_over_a_seal(self, tmp_path: Path) -> None:
        CAL.seal(tmp_path)
        (tmp_path / CAL.THRESHOLDS_FILE).write_text("{}", encoding="utf-8")
        with pytest.raises(CAL.CalibrationError, match="already holds other thresholds"):
            CAL.seal(tmp_path)
        with pytest.raises(CAL.CalibrationError, match="changed after it was sealed"):
            CAL.sealed(tmp_path)

    def test_a_directory_with_a_sample_cannot_be_sealed(self, tmp_path: Path) -> None:
        (tmp_path / CAL.GOLD_FILE).write_text("", encoding="utf-8")
        with pytest.raises(CAL.CalibrationError, match="sealed first"):
            CAL.seal(tmp_path)

    def test_nothing_is_measured_in_an_unsealed_directory(self, tmp_path: Path) -> None:
        with pytest.raises(CAL.CalibrationError, match="not sealed"):
            CAL.fix_gold(tmp_path, [case("a", "image_prefilter", "kind", "site_photo", "a.jpg")])

    def test_a_role_that_moved_after_the_seal_invalidates_it(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        CAL.seal(tmp_path)
        monkeypatch.setattr(RO, "role_sha256", lambda name: "0" * 64)
        with pytest.raises(CAL.CalibrationError, match="changed after the seal"):
            CAL.sealed(tmp_path)


# ======================================================================================== the gold
class TestTheSample:
    def _sealed(self, tmp_path: Path) -> Path:
        CAL.seal(tmp_path, now=lambda: "2026-10-09T00:00:00Z")
        return tmp_path

    def test_the_truth_stays_in_the_gold_and_out_of_the_jobs(self, tmp_path: Path) -> None:
        directory = self._sealed(tmp_path)
        cases = [case("a", "image_prefilter", "kind", "site_photo", "a.jpg")]
        CAL.fix_gold(directory, cases, now=lambda: FIXED)
        assert json.loads((directory / CAL.GOLD_FILE).read_text())["truth"] == "site_photo"
        assert "truth" not in json.loads((directory / CAL.JOBS_FILE).read_text())

    def test_the_same_sample_again_changes_nothing_another_is_refused(self, tmp_path: Path) -> None:
        directory = self._sealed(tmp_path)
        cases = [case("a", "image_prefilter", "kind", "site_photo", "a.jpg")]
        digest = CAL.fix_gold(directory, cases, now=lambda: FIXED)
        assert CAL.fix_gold(directory, cases, now=lambda: FIXED) == digest
        assert len([e for e in CAL._log(directory) if "gold_sha256" in e]) == 1
        with pytest.raises(CAL.CalibrationError, match="never rewritten"):
            CAL.fix_gold(
                directory,
                cases + [case("b", "image_prefilter", "kind", "map_or_document", "b.jpg")],
            )

    def test_a_case_twice_or_an_empty_sample_is_refused(self, tmp_path: Path) -> None:
        directory = self._sealed(tmp_path)
        one = case("a", "image_prefilter", "kind", "other", "a.jpg")
        with pytest.raises(CAL.CalibrationError, match="no case twice"):
            CAL.fix_gold(directory, [one, one])
        with pytest.raises(CAL.CalibrationError, match="at least one case"):
            CAL.fix_gold(directory, [])

    def test_a_sample_edited_after_it_was_fixed_is_refused(self, tmp_path: Path) -> None:
        directory = self._sealed(tmp_path)
        CAL.fix_gold(
            directory, [case("a", "image_prefilter", "kind", "other", "a.jpg")], now=lambda: FIXED
        )
        (directory / CAL.GOLD_FILE).write_text("{}\n", encoding="utf-8")
        with pytest.raises(CAL.CalibrationError, match="changed after it was fixed"):
            CAL.fixed_gold(directory)

    def test_the_stratified_draw_is_equal_per_class_and_deterministic(self) -> None:
        items = [{"k": "a", "i": i} for i in range(100)] + [{"k": "b", "i": i} for i in range(100)]
        got = CAL.stratified(items, "k", 20, seed=7)
        assert sum(1 for r in got if r["k"] == "a") == sum(1 for r in got if r["k"] == "b") == 10
        assert CAL.stratified(items, "k", 20, seed=7) == got
        assert CAL.stratified(items, "k", 20, seed=8) != got

    def test_a_small_class_gives_its_shortfall_to_the_others(self) -> None:
        items = [{"k": "a", "i": i} for i in range(3)] + [{"k": "b", "i": i} for i in range(50)]
        got = CAL.stratified(items, "k", 20, seed=1)
        assert len(got) == 20 and sum(1 for r in got if r["k"] == "a") == 3

    def test_fewer_items_than_asked_gives_them_all(self) -> None:
        assert len(CAL.stratified([{"k": "a"}, {"k": "b"}], "k", 20, seed=1)) == 2
        assert len(CAL.sample([{"i": 1}], 5, 1)) == 1

    def test_the_kind_gold_is_opus_s_c1_kind_without_errors(self) -> None:
        jobs = [
            {"image_id": i, "site_id": "s", "site_name": "S", "filename": f"{i}.webp"}
            for i in range(1, 7)
        ]
        verdicts = [
            {"image_id": 1, "parsed": {"kind": "site_photo"}, "error": None},
            {"image_id": 2, "parsed": {"kind": "map_or_document"}, "error": None},
            {"image_id": 3, "parsed": {"kind": "nonsense"}, "error": None},
            {"image_id": 4, "parsed": {"kind": "site_photo"}, "error": "timeout"},
            {"image_id": 5, "parsed": None, "error": None},
        ]
        got = CAL.kind_cases(jobs, verdicts, lambda j: f"/img/{j['filename']}", n=10, seed=1)
        assert sorted((c["case_id"], c["truth"]) for c in got) == [
            ("kind-1", "site_photo"),
            ("kind-2", "map_or_document"),
        ]
        assert got[0]["role"] == "image_prefilter" and got[0]["path"].startswith("/img/")

    def test_the_identity_cases_are_sites_with_a_known_label(self) -> None:
        population = {"s1": {**site("s1"), "qid": "Q1", "enwiki_title": "S"}}
        got = CAL.identity_cases([{"site_id": "s1", "label": "wrong"}], population)
        assert got[0]["truth"] == "wrong" and got[0]["group"] == "identity_wrong"
        assert got[0]["site"]["flags"] == ["calibration case"]
        with pytest.raises(CAL.CalibrationError, match="not in the population"):
            CAL.identity_cases([{"site_id": "zz", "label": "good"}], population)
        with pytest.raises(CAL.CalibrationError, match="not wrong/good"):
            CAL.identity_cases([{"site_id": "s1", "label": "maybe"}], population)


class TestBuildingTheGold:
    """`build_gold` over a small invented world, with the sealed numbers scaled down."""

    def _world(self, tmp_path: Path) -> dict[str, Any]:
        rows, sites = [], []
        for n in range(1, 9):
            sid = f"site{n}"
            sites.append(
                {
                    "id": sid,
                    "name": f"Site {n}",
                    "country": "Greece",
                    "site_type": "Tomb",
                    "lat": 1.0,
                    "lon": 2.0,
                    "thumbnail_url": None,
                }
            )
            rows.append(
                {
                    "id": 100 + n, "site_id": sid, "filename": f"hero{n}.webp", "title": f"Hero {n}",
                    "original_url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/Hero_{n}.jpg",
                    "commons_page_url": None, "is_hero": True, "is_lead": False, "is_excluded": False,
                    "sort_order": 0, "file_size_bytes": 1,
                }
            )  # fmt: skip
        ST.write_read(
            tmp_path / "READ.json", {"read_at": "x", "sites": sites, "images": rows, "retired": []}
        )
        return {"state": ST.load_read(tmp_path / "READ.json"), "rows": rows}

    def test_every_group_is_chosen_by_its_own_rule(self, tmp_path: Path) -> None:
        world = self._world(tmp_path)
        thresholds = json.loads(CAL.thresholds_text())
        for key in ("positives", "foreign_labelled", "claude_other_site"):
            thresholds["roles"]["image_depicts"][key] = 2
        thresholds["roles"]["image_prefilter"]["kind_cases"] = 2
        thresholds["roles"]["pilot_judge"]["per_class"] = 1
        pool = [
            {"site_id": "pool1", "name": "Pool 1", "country": "Italy", "candidates": [
                {"file": "P1.jpg", "picture_url": "u1", "why": "a search"},
                {"file": "P2.jpg", "picture_url": "u2", "why": "a search"},
            ]}
        ]  # fmt: skip
        pool_verdicts = [
            {"site_id": "pool1", "file": "P1.jpg", "verdict": "depicts"},
            {"site_id": "pool1", "file": "P2.jpg", "verdict": "other_site"},
        ]
        for url in ("u1", "u2"):  # the pictures of the pool are on disk
            (tmp_path / url).write_bytes(b"x")
        cases = CAL.build_gold(
            state=world["state"], context={}, lead=lambda sid: None,
            path_of=lambda sid, filename: f"/img/{sid}/{filename}",
            c1_jobs=[{"image_id": 101, "site_id": "site1", "site_name": "S", "filename": "hero1.webp"}],
            c1_verdicts=[{"image_id": 101, "parsed": {"kind": "site_photo"}, "error": None}],
            labelled=[{"image_id": 102, "labels": ["fremde_staette"]}, {"image_id": 103, "labels": ["sonstiges"]}],
            gold_rows=[type("G", (), {"image_id": 104, "foreign": True})(), type("G", (), {"image_id": 105, "foreign": False})()],
            owner_links={f"site{n}": {"image": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/Hero_{n}.jpg"} for n in (1, 2, 3, 4)},
            excluded_images={101},
            served_checks=[{"served": {"image_id": 106, "file": "x"}, "verdict": "other_site", "site_id": "site6", "answered_by": "a", "model": "m", "shows": "s", "basis": "b"}],
            served_replaces=[], pool_candidates=pool, pool_verdicts=pool_verdicts,
            pool_path=lambda c: str(tmp_path / c["picture_url"]),
            identity_gold=[{"site_id": "site7", "label": "wrong"}, {"site_id": "site8", "label": "good"}],
            population={f"site{n}": {**site(f"site{n}")} for n in (7, 8)},
            thresholds=thresholds,
        )  # fmt: skip
        groups = {}
        for c in cases:
            if c["role"] != "adversarial":
                groups.setdefault(c["group"], []).append(c)
        assert [c["truth"] for c in groups["kind"]] == ["site_photo"]
        # the owner-linked heroes, but not the excluded one (101)
        assert {c["case_id"] for c in groups["positive"]} <= {"pos-102", "pos-103", "pos-104"}
        assert len(groups["positive"]) == 2 and all(
            c["truth"] == "depicts" for c in groups["positive"]
        )
        assert [c["case_id"] for c in groups["positive_gold"]] == ["gpos-105"]
        assert [c["case_id"] for c in groups["foreign"]] == ["frn-102"]  # 999 is not in the read
        assert [c["case_id"] for c in groups["foreign_gold"]] == ["gfrn-104"]
        assert [c["case_id"] for c in groups["hard_negative"]] == ["cos-106"]
        assert all(
            c["truth"] == "not_depicts"
            for g in ("foreign", "foreign_gold", "hard_negative")
            for c in groups[g]
        )
        # one adjudicated candidate per MiniMax class, with no truth yet
        assert sorted(c["file"] for c in groups["adjudicated"]) == ["P1.jpg", "P2.jpg"]
        assert all(c["truth"] is None for c in groups["adjudicated"])
        assert {c["role"] for c in groups["adjudicated"]} == {"image_depicts"}
        # the production prompt reads the description and the lead
        assert groups["positive"][0]["site"]["wikipedia_lead"] is None
        assert {c["group"] for c in cases if c["role"] == "adversarial"} >= {
            "positive",
            "adjudicated",
        }
        assert {c["truth"] for c in groups["identity_wrong"] + groups["identity_good"]} == {
            "wrong",
            "good",
        }
        ids = [c["case_id"] for c in cases]
        assert len(ids) == len(set(ids))


# ===================================================================================== measuring
def prefilter_results(plan: dict[str, tuple[str, bool]]) -> list[dict[str, Any]]:
    items = [
        {"label": f"C{i:02d}", "site_id": case_id, "file": "f"} for i, case_id in enumerate(plan, 1)
    ]
    return [
        {
            "meta": {"items": items},
            "items": {
                f"C{i:02d}": {"kind": k, "usable": u} for i, (k, u) in enumerate(plan.values(), 1)
            },
            "answered_by": "image_prefilter:pre-0001",
            "model": OH.HAIKU_MODEL,
            "answered_at": NOW,
            "batch_id": "pre-0001",
            "label": "pre-0001",
        }
    ]


class TestMeasuringThePrefilter:
    def _cases(self) -> list[dict[str, Any]]:
        return [
            case(f"k{i}", "image_prefilter", "kind", truth, "f")
            for i, truth in enumerate(
                ["site_photo"] * 6 + ["artifact"] * 2 + ["map_or_document"] * 2
            )
        ]

    def test_agreement_and_recall_are_measured_against_the_c1_kind(self) -> None:
        cases = self._cases()
        plan = {c["case_id"]: (c["truth"], True) for c in cases}  # a perfect prefilter
        got = CAL.measure_prefilter(cases, prefilter_results(plan), cp)
        assert (
            got["photo_agreement"]["rate"] == 1.0 and got["depicts_capable_recall"]["rate"] == 1.0
        )
        assert CAL.decide("image_prefilter", json.loads(CAL.thresholds_text()), got) == []

    def test_a_prefilter_that_drops_a_site_photo_fails_the_recall(self) -> None:
        cases = self._cases()
        plan = {c["case_id"]: (c["truth"], True) for c in cases}
        plan["k0"] = ("people", True)  # one of eight capable pictures lost
        got = CAL.measure_prefilter(cases, prefilter_results(plan), cp)
        assert got["depicts_capable_recall"]["k"] == 7 and got["depicts_capable_recall"]["n"] == 8
        failures = CAL.decide("image_prefilter", json.loads(CAL.thresholds_text()), got)
        assert any("depicts_capable_recall" in f for f in failures)
        assert any("photo_agreement" in f for f in failures)

    def test_an_unusable_picture_is_dropped_even_of_a_good_kind(self) -> None:
        cases = self._cases()
        plan = {c["case_id"]: (c["truth"], True) for c in cases}
        plan["k1"] = ("site_photo", False)
        got = CAL.measure_prefilter(cases, prefilter_results(plan), cp)
        assert got["depicts_capable_recall"]["k"] == 7

    def test_a_case_nobody_answered_is_an_error(self) -> None:
        cases = self._cases()
        plan = {c["case_id"]: (c["truth"], True) for c in cases[:-1]}
        with pytest.raises(CAL.CalibrationError, match="unanswered"):
            CAL.measure_prefilter(cases, prefilter_results(plan), cp)


def depicts_result(site_id: str, verdicts: dict[str, str]) -> dict[str, Any]:
    items = [{"label": f"C{i}", "file": f} for i, f in enumerate(verdicts, 1)]
    return {
        "meta": {"site_id": site_id, "name": "n", "items": items},
        "candidates": {
            f"C{i}": {"verdict": v, "quality": 4 if v == "depicts" else None, "note": "n"}
            for i, v in enumerate(verdicts.values(), 1)
        },
        "answered_by": "x", "model": "m", "answered_at": NOW, "batch_id": "dep-0001", "label": site_id,
    }  # fmt: skip


class TestMeasuringTheDepictsRole:
    def _cases(self) -> list[dict[str, Any]]:
        out = [
            case(f"p{i}", "image_depicts", "positive", "depicts", f"p{i}.jpg") for i in range(10)
        ]
        out += [
            case(f"f{i}", "image_depicts", "foreign", "not_depicts", f"f{i}.jpg") for i in range(5)
        ]
        out += [
            case(f"h{i}", "image_depicts", "hard_negative", "not_depicts", f"h{i}.jpg")
            for i in range(5)
        ]
        return out

    def _results(self, called_depicts: set[str]) -> list[dict[str, Any]]:
        verdicts = {
            c["file"]: ("depicts" if c["file"] in called_depicts else "other_site")
            for c in self._cases()
        }
        return [depicts_result("s1", verdicts)]

    def test_a_judge_that_gets_it_right_passes(self) -> None:
        called = {f"p{i}.jpg" for i in range(10)}
        got = CAL.measure_depicts(self._cases(), self._results(called), [], cp)
        assert got["sensitivity"]["rate"] == 1.0 and got["false_depicts"]["rate"] == 0.0
        assert got["precision"]["rate"] == 1.0 and got["foreign_called_depicts"] == []
        assert CAL.decide("image_depicts", json.loads(CAL.thresholds_text()), got) == []

    def test_one_foreign_row_called_depicts_fails_whatever_the_rates_are(self) -> None:
        called = {f"p{i}.jpg" for i in range(10)} | {"f0.jpg"}
        got = CAL.measure_depicts(self._cases(), self._results(called), [], cp)
        assert got["foreign_called_depicts"] == ["f0"]
        failures = CAL.decide("image_depicts", json.loads(CAL.thresholds_text()), got)
        assert any("foreign row" in f for f in failures)

    def test_a_missed_hero_lowers_the_sensitivity(self) -> None:
        called = {f"p{i}.jpg" for i in range(8)}
        got = CAL.measure_depicts(self._cases(), self._results(called), [], cp)
        assert got["sensitivity"]["k"] == 8
        assert any(
            "sensitivity" in f
            for f in CAL.decide("image_depicts", json.loads(CAL.thresholds_text()), got)
        )

    def test_the_adjudicated_candidates_take_the_pilot_judge_s_word_as_truth(self) -> None:
        cases = self._cases() + [
            case("a1", "image_depicts", "adjudicated", None, "a1.jpg"),
            case("a2", "image_depicts", "adjudicated", None, "a2.jpg"),
        ]
        adjudication = [depicts_result("s1", {"a1.jpg": "depicts", "a2.jpg": "other_site"})]
        verdicts = {
            c["file"]: ("depicts" if c["file"].startswith("p") else "other_site") for c in cases
        }
        verdicts["a2.jpg"] = "depicts"  # the role called a negative depicts
        got = CAL.measure_depicts(cases, [depicts_result("s1", verdicts)], adjudication, cp)
        assert (
            got["false_depicts"]["k"] == 1 and got["false_depicts"]["n"] == 11
        )  # 10 labelled + a2
        assert got["precision"]["k"] == 10 and got["precision"]["n"] == 11

    def test_a_false_depicts_rate_above_its_ceiling_fails_even_when_the_precision_holds(
        self,
    ) -> None:
        """100 labelled heroes all found, 40 negatives of which two are called depicts: precision
        0.98 passes its floor, the false-depicts rate 0.05 does not pass its ceiling."""
        cases = [
            case(f"p{i}", "image_depicts", "positive", "depicts", f"p{i}.jpg") for i in range(100)
        ]
        cases += [
            case(f"n{i}", "image_depicts", "hard_negative", "not_depicts", f"n{i}.jpg")
            for i in range(40)
        ]
        verdicts = {
            c["file"]: ("depicts" if c["file"].startswith("p") else "other_site") for c in cases
        }
        verdicts["n0.jpg"] = verdicts["n1.jpg"] = "depicts"
        got = CAL.measure_depicts(cases, [depicts_result("s1", verdicts)], [], cp)
        assert got["precision"]["rate"] >= 0.95 and got["false_depicts"]["rate"] == 0.05
        failures = CAL.decide("image_depicts", json.loads(CAL.thresholds_text()), got)
        assert failures == ["false_depicts 0.05 is above 0.03"]

    def test_an_adjudicated_case_without_the_pilot_judge_is_an_error(self) -> None:
        cases = [case("a1", "image_depicts", "adjudicated", None, "a1.jpg")]
        with pytest.raises(CAL.CalibrationError, match="has not adjudicated"):
            CAL.adjudicated_truth(cases, [])

    def test_an_unanswered_case_is_an_error(self) -> None:
        with pytest.raises(CAL.CalibrationError, match="unanswered"):
            CAL.measure_depicts(
                self._cases(), [depicts_result("s1", {"p0.jpg": "depicts"})], [], cp
            )


class TestMeasuringTheRecheckAndTheIdentity:
    def _recheck(self, verdicts: dict[tuple[str, str], str]) -> list[dict[str, Any]]:
        return [
            {"verdict": v, "meta": {"site_id": case_id, "file": f}, "answered_by": "x", "model": "m", "answered_at": NOW, "batch_id": "b", "label": f}
            for (case_id, f), v in verdicts.items()
        ]  # fmt: skip

    def test_agreement_with_the_labelled_truth(self) -> None:
        cases = [
            case("r1", "adversarial", "positive", "depicts", "a.jpg"),
            case("r2", "adversarial", "foreign", "not_depicts", "b.jpg"),
        ]
        got = CAL.measure_adversarial(
            cases,
            self._recheck({("r1", "a.jpg"): "depicts", ("r2", "b.jpg"): "other_site"}),
            [],
            cp,
        )
        assert got["agreement"]["rate"] == 1.0
        bad = CAL.measure_adversarial(
            cases, self._recheck({("r1", "a.jpg"): "depicts", ("r2", "b.jpg"): "depicts"}), [], cp
        )
        assert bad["agreement"]["rate"] == 0.5
        assert CAL.decide("adversarial", json.loads(CAL.thresholds_text()), bad)

    def test_the_adjudicated_cases_are_judged_against_the_pilot_judge(self) -> None:
        cases = [case("r1", "adversarial", "adjudicated", None, "a.jpg")]
        adjudication = [depicts_result("s1", {"a.jpg": "other_site"})]
        got = CAL.measure_adversarial(
            cases, self._recheck({("r1", "a.jpg"): "other_site"}), adjudication, cp
        )
        assert got["agreement"]["rate"] == 1.0

    def _identity(self, statuses: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
        sites = {
            sid: {"qid": None, "qid_status": q, "enwiki_title": None, "enwiki_status": e, "commons_category": None, "local_names": [], "evidence": [], "note": "n"}
            for sid, (q, e) in statuses.items()
        }  # fmt: skip
        return [{"sites": sites, "answered_by": "x", "model": "m"}]

    def _cases(self) -> list[dict[str, Any]]:
        return [
            case("w1", "web_verifier", "identity_wrong", "wrong", "", "w1"),
            case("w2", "web_verifier", "identity_wrong", "wrong", "", "w2"),
            case("g1", "web_verifier", "identity_good", "good", "", "g1"),
            case("g2", "web_verifier", "identity_good", "good", "", "g2"),
        ]

    def test_a_wrong_link_is_correct_when_flagged_and_a_good_one_when_confirmed(self) -> None:
        results = self._identity(
            {
                "w1": ("wrong", "confirmed"),
                "w2": ("confirmed", "wrong"),
                "g1": ("confirmed", "confirmed"),
                "g2": ("confirmed", "confirmed"),
            }
        )
        got = CAL.measure_identity(self._cases(), results, cp)
        assert got["correct"]["rate"] == 1.0 and got["wrong_not_flagged"] == []
        assert CAL.decide("web_verifier", json.loads(CAL.thresholds_text()), got) == []

    def test_a_missed_wrong_link_fails_even_with_a_high_rate(self) -> None:
        results = self._identity(
            {
                "w1": ("confirmed", "confirmed"),
                "w2": ("wrong", "wrong"),
                "g1": ("confirmed", "confirmed"),
                "g2": ("confirmed", "confirmed"),
            }
        )
        got = CAL.measure_identity(self._cases(), results, cp)
        assert got["wrong_not_flagged"] == ["w1"]
        assert any(
            "not flagged" in f
            for f in CAL.decide("web_verifier", json.loads(CAL.thresholds_text()), got)
        )

    def test_an_undecided_good_link_is_not_correct(self) -> None:
        results = self._identity(
            {
                "w1": ("wrong", "wrong"),
                "w2": ("wrong", "wrong"),
                "g1": ("unknown", "confirmed"),
                "g2": ("confirmed", "confirmed"),
            }
        )
        assert CAL.measure_identity(self._cases(), results, cp)["correct"]["k"] == 3

    def test_an_unmeasured_role_is_refused(self) -> None:
        with pytest.raises(CAL.CalibrationError, match="not measured"):
            CAL.decide("card_writer", json.loads(CAL.thresholds_text()), {})


# ===================================================================================== evaluating
class TestEvaluating:
    def _prepared(
        self, tmp_path: Path, truth_for_two: tuple[str, str] = ("site_photo", "map_or_document")
    ) -> Path:
        directory = tmp_path / "cal"
        CAL.seal(directory, now=lambda: "2026-10-09T00:00:00Z")
        cases = [
            case(f"k{i}", "image_prefilter", "kind", t, "f")
            for i, t in enumerate(truth_for_two * 5)
        ]
        CAL.fix_gold(directory, cases, now=lambda: FIXED)
        handoff = tmp_path / "h"
        questions, pictures = CAL.questions_for("image_prefilter", cases, read)
        SG.export(directory, handoff, PF.SPEC, questions, pictures)
        self.handoff = handoff
        self.cases = cases
        return directory

    def _answer(self, directory: Path, got_kind: dict[str, str]) -> None:
        question = next(iter(SG.load_questions(directory, PF.SPEC).values()))
        items = {
            item["label"]: {"kind": got_kind[item["site_id"]], "usable": True}
            for item in question.meta["items"]
        }
        answer(self.handoff, PF.SPEC, {question.label: json.dumps({"items": items})})
        SG.import_answers(directory, self.handoff, PF.SPEC)

    def test_the_depicts_role_is_evaluated_from_a_calibration_directory(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "cal"
        CAL.seal(directory, now=lambda: "2026-10-09T00:00:00Z")
        cases = [
            case(f"p{i}", "image_depicts", "positive", "depicts", f"p{i}.jpg") for i in range(10)
        ]
        cases += [
            case(f"f{i}", "image_depicts", "foreign", "not_depicts", f"f{i}.jpg") for i in range(4)
        ]
        CAL.fix_gold(directory, cases, now=lambda: FIXED)
        spec = CAL.ROLE_SPECS["image_depicts"]
        assert spec.name == "image-depicts-calibration" and spec.role == "image_depicts"
        questions, pictures = CAL.questions_for("image_depicts", cases, read)
        handoff = tmp_path / "h-dep"
        SG.export(directory, handoff, spec, questions, pictures)
        text = json.dumps(
            {
                "candidates": {
                    f"C{i}": (
                        {"verdict": "depicts", "quality": 4, "note": "the tomb"}
                        if c["truth"] == "depicts"
                        else {"verdict": "other_site", "quality": None, "note": "elsewhere"}
                    )
                    for i, c in enumerate(cases, 1)
                }
            }
        )
        answer(handoff, spec, {q.label: text for q in questions})
        SG.import_answers(
            directory, handoff, spec
        )  # the generic import: no VERDICTS.jsonl of a lane
        assert not (directory / "VERDICTS.jsonl").exists()
        verdict = CAL.evaluate(directory, "image_depicts", cp=cp)
        assert verdict["passed"] and verdict["metrics"]["foreign_called_depicts"] == []

    def test_a_role_that_passes_is_written_once(self, tmp_path: Path) -> None:
        directory = self._prepared(tmp_path)
        self._answer(directory, {c["case_id"]: c["truth"] for c in self.cases})
        verdict = CAL.evaluate(directory, "image_prefilter", cp=cp)
        assert (
            verdict["passed"]
            and verdict["tier_move"] is None
            and verdict["model"] == "claude-haiku-5-5"
        )
        assert json.loads((directory / "verdicts" / "image_prefilter.json").read_text())["passed"]
        with pytest.raises(CAL.CalibrationError, match="written once"):
            CAL.evaluate(directory, "image_prefilter", cp=cp)

    def test_a_failing_haiku_moves_up_to_sonnet(self, tmp_path: Path) -> None:
        directory = self._prepared(tmp_path)
        self._answer(directory, {c["case_id"]: "people" for c in self.cases})
        verdict = CAL.evaluate(directory, "image_prefilter", cp=cp)
        assert not verdict["passed"]
        assert (
            verdict["tier_move"]["from"] == "claude-haiku-5-5"
            and verdict["tier_move"]["to"] == "claude-sonnet-5-5"
        )
        assert verdict["failures"]

    def test_an_answer_older_than_the_sample_is_refused(self, tmp_path: Path) -> None:
        directory = self._prepared(tmp_path)
        self._answer(directory, {c["case_id"]: c["truth"] for c in self.cases})
        (directory / CAL.SEAL_LOG).write_text(
            "".join(
                json.dumps(
                    {**e, "fixed_at": "2026-10-10T00:00:00Z"} if "gold_sha256" in e else e,
                    sort_keys=True,
                )
                + "\n"
                for e in CAL._log(directory)
            ),
            encoding="utf-8",
        )
        with pytest.raises(CAL.CalibrationError, match="judged before the sample was fixed"):
            CAL.evaluate(directory, "image_prefilter", cp=cp)

    def test_the_pilot_judge_is_the_gold_not_a_measured_role(self, tmp_path: Path) -> None:
        directory = self._prepared(tmp_path)
        with pytest.raises(CAL.CalibrationError, match="not measured"):
            CAL.evaluate(directory, "pilot_judge", cp=cp)

    def test_a_role_at_the_top_tier_is_held_for_the_owner(self, tmp_path: Path) -> None:
        directory = tmp_path / "cal"
        CAL.seal(directory, now=lambda: "2026-10-09T00:00:00Z")
        cases = [
            case("r1", "adversarial", "positive", "depicts", "a.jpg"),
            case("r2", "adversarial", "foreign", "not_depicts", "b.jpg"),
        ]
        CAL.fix_gold(directory, cases, now=lambda: FIXED)
        spec = CAL.RECHECK_SPEC
        questions, pictures = CAL.questions_for("adversarial", cases, read)
        handoff = tmp_path / "h-rck"
        SG.export(directory, handoff, spec, questions, pictures)
        wrong = json.dumps({"verdict": "depicts", "shows": "x", "basis": "y"})
        answer(handoff, spec, {q.label: wrong for q in questions})
        SG.import_answers(directory, handoff, spec)
        verdict = CAL.evaluate(directory, "adversarial", cp=cp)
        assert not verdict["passed"] and verdict["tier_move"] is None
        assert "no higher tier" in verdict["held"] and "the owner decides" in verdict["held"]


class TestTheProductionQuestions:
    def test_the_prefilter_cases_use_the_production_prompt_and_batches(self) -> None:
        cases = [case(f"k{i}", "image_prefilter", "kind", "other", f"{i}.jpg") for i in range(61)]
        questions, pictures = CAL.questions_for("image_prefilter", cases, read)
        assert [len(q.images) for q in questions] == [60, 1] and len(pictures) == 61
        assert questions[0].prompt.startswith("You sort candidate pictures")

    def test_the_depicts_cases_of_one_site_are_one_question(self) -> None:
        cases = [
            case("a", "image_depicts", "positive", "depicts", "a.jpg"),
            case("b", "image_depicts", "foreign", "not_depicts", "b.jpg"),
            case("c", "image_depicts", "positive", "depicts", "c.jpg", site_id="s2"),
        ]
        questions, _ = CAL.questions_for("image_depicts", cases, read)
        assert sorted(q.label for q in questions) == ["s1", "s2"]
        assert "A refusal is better than a wrong depicts" in questions[0].prompt

    def test_the_adjudication_asks_the_same_question_in_the_pilot_judge_s_role(self) -> None:
        assert CAL.ADJUDICATE_SPEC.role == "pilot_judge" and CAL.ADJUDICATE_SPEC.web is True
        assert (RO.role("pilot_judge").model, RO.role("pilot_judge").effort) == (
            "claude-opus-5-5",
            "xhigh",
        )
        assert CAL.ADJUDICATE_SPEC.parse is DP.SPEC.parse

    def test_the_recheck_cases_use_the_hero_recheck_prompt(self) -> None:
        cases = [case("r", "adversarial", "positive", "depicts", "a.jpg")]
        (q,), _ = CAL.questions_for("adversarial", cases, read)
        assert q.prompt.startswith("You re-check a verdict.")

    def test_the_identity_cases_are_verify_questions_with_their_flags(self) -> None:
        wrong = case("w", "web_verifier", "identity_wrong", "wrong", "")
        wrong["site"] = {
            **site("w"),
            "qid": "Q1",
            "enwiki_title": "W",
            "flags": ["calibration case"],
        }
        cases = [wrong]
        (q,), pictures = CAL.questions_for("web_verifier", cases, read)
        assert "flagged because: calibration case" in q.prompt and pictures == {}
        assert ID.VERIFY_SPEC.role == "web_verifier"

    def test_a_role_without_cases_or_questions_is_refused(self) -> None:
        with pytest.raises(CAL.CalibrationError, match="no case for role"):
            CAL.questions_for("image_prefilter", [], read)
        with pytest.raises(CAL.CalibrationError, match="no case for role"):
            CAL.questions_for("card_writer", [case("a", "image_prefilter", "kind", "x", "f")], read)
