"""Calibration pools of the identity questions (`scripts/remediation/identity/calibration.py`).

DB-less and offline: the discovery's export is a fixture, the earlier judgements are small files, and
the calibration runs through `calibrate_claude.py` end to end - seal, prepare, compare, verdict - on a
pool whose gold is the pilot judge's. No model is called.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import calibrate_claude as CC  # noqa: E402
import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from identity import calibration as CAL  # noqa: E402
from identity import names_judge as NJ  # noqa: E402
from identity import retarget as RT  # noqa: E402
from identity import rounds as R  # noqa: E402
from identity import scope_judge as SJ  # noqa: E402

from tests.remediation.identity_b_fixtures import NOW, WP  # noqa: E402
from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402

CHANIA = next(iter(CAL.KNOWN_DEFECTS))
EXPORTED = "2026-10-08 20:35:11+00"


def fake_cache(tmp_path: Path, sites: list[str]) -> Path:
    cache = tmp_path / "wiki_cache"
    cache.mkdir()
    (cache / "INDEX.jsonl").write_text(
        "".join(
            json.dumps({"site_id": s, "lang": "en", "title": "T", "file": "en\\x.json"}) + "\n"
            for s in sites
        ),
        encoding="utf-8",
    )
    return cache


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A run directory with a funnel of one, N7 records of both kinds and clean sites."""
    shown = [site(id=CHANIA, name="Chania")]
    shown += [site(name=f"Plain {i}") for i in range(20)]
    n7 = [
        {"class": "N7", "n7": "anchor-is-locality" if i % 2 else "anchor-is-a-site", "site_id": shown[i + 1]["id"],
         "name": shown[i + 1]["name"], "en_label": f"Label {i}", "p31": ["village"]}
        for i in range(8)
    ]  # fmt: skip
    run = tmp_path / "identity"
    run.mkdir()
    monkeypatch.setattr(
        CAL.export, "load_export",
        lambda path: export_of(shown, ext_ids=[ext(CHANIA, "wikidata_qid", "Q100")]),
    )  # fmt: skip
    funnel_row = {"id": CHANIA, "tier": "A+rx", "p31": ["city"], "p31_modern": ["city"], "sentence1": "Chania is a city.",
                  "opening_match": "city", "shared_with": []}  # fmt: skip
    (run / "IDENTITY_FUNNEL.jsonl").write_text(json.dumps(funnel_row) + "\n", encoding="utf-8")
    bcases = tmp_path / "names.jsonl"
    bcases.write_text("".join(json.dumps(r) + "\n" for r in n7), encoding="utf-8")
    cache = fake_cache(tmp_path, [s["id"] for s in shown])
    monkeypatch.setattr(CAL, "wiki_cache_dir", lambda root=None: cache)
    return {"run": run, "shown": shown, "bcases": bcases, "tmp": tmp_path}


class TestTheSelection:
    def test_the_seeded_draw_is_the_same_for_the_same_seed(self) -> None:
        items = list(range(50))
        assert CAL.seeded(items, 1, 5) == CAL.seeded(items, 1, 5)
        assert CAL.seeded(items, 1, 5) != CAL.seeded(items, 2, 5)
        assert CAL.seeded([3, 1, 2], 1, 5) == [1, 2, 3]

    def test_the_retarget_pool_holds_the_defects_both_n7_kinds_and_clean_sites(
        self, world: dict[str, Any]
    ) -> None:
        cases = CAL.select_retarget(
            world["run"], bcases_names=world["bcases"], n7_site=2, n7_locality=2, clean=3
        )
        by_source: dict[str, int] = {}
        for c in cases:
            key = c.source.split(":")[0] + (
                ":" + c.source.split(":")[1] if c.source.startswith("bcases") else ""
            )
            by_source[key] = by_source.get(key, 0) + 1
        assert by_source == {
            "known-defect": 1,
            "bcases-n7:anchor-is-a-site": 2,
            "bcases-n7:anchor-is-locality": 2,
            "not-in-funnel": 3,
        }
        chania = cases[0]
        assert chania.site_id == CHANIA and chania.context["why"]["tier"] == "A+rx"
        assert chania.context["qids"] == ["Q100"] and "audit" in chania.hint
        other = next(c for c in cases if c.source == "not-in-funnel")
        assert other.context["why"]["tier"] == "calibration"
        assert "calibration case" in RT.render_web(other.context)
        assert "locality" in next(c for c in cases if "locality" in c.source).hint

    def test_a_hint_never_reaches_a_prompt(self, world: dict[str, Any]) -> None:
        cases = CAL.select_retarget(
            world["run"], bcases_names=world["bcases"], n7_site=2, n7_locality=2, clean=1
        )
        for c in cases:
            text = RT.render_web(c.context)
            assert c.hint not in text and "bcases" not in text and "sample audit" not in text

    def test_the_names_pool_samples_hard_and_comma_only_records(
        self, world: dict[str, Any]
    ) -> None:
        shown = world["shown"]
        triage = [
            {"id": shown[i + 1]["id"], "name": shown[i + 1]["name"], "country": "Greece", "site_type": "Temple",
             "defects": ["parenthesis"] if i % 2 else ["comma_qualifier"], "differs_from_label": False, "enwiki": [],
             "label": None, "aliases": [], "severity": "hard" if i % 2 else "comma_only", "suggestion": None,
             "needs_model": i != 0}
            for i in range(10)
        ]  # fmt: skip
        (world["run"] / NJ.TRIAGE_FILE).write_text(
            "".join(json.dumps(t) + "\n" for t in triage), encoding="utf-8"
        )
        cases = CAL.select_names(world["run"], hard=3, comma=2)
        assert sorted(c.source for c in cases) == ["triage:comma_only"] * 2 + ["triage:hard"] * 3
        assert all(c.context["site_id"] == c.site_id for c in cases)
        assert "it holds a (parenthesis)" in NJ.render_clean(
            next(c for c in cases if c.source == "triage:hard").context
        )

    def test_the_scope_pool_is_the_e4_decisions_and_the_reviews_counted_answers(
        self, world: dict[str, Any], tmp_path: Path
    ) -> None:
        from tests.remediation import test_scope_review as TSR

        rows = [
            TSR.site("a1000000-0000-4000-8000-00000000000a", "Ali Masjid Fort", "Fortress/citadel", country="Pakistan", lon=71.2, lat=34.0, start=1837),
            TSR.site("a1000000-0000-4000-8000-00000000000b", "Some Museum", "Museum", country="Greece", lon=23.7, lat=38.0, start=1959),
            TSR.site("a1000000-0000-4000-8000-00000000000c", "Baltic Sea Anomaly", "Underwater structures", country="Sweden", lon=18.4, lat=61.3, start=-1000),
            TSR.site("a1000000-0000-4000-8000-00000000000d", "No longitude", "Fortress/citadel", country="Peru", lon=None, lat=-12.0, start=1200),
        ]  # fmt: skip
        TSR.write_export(tmp_path / "scope", rows)
        snapshot = TSR.R.export_path(tmp_path / "scope")
        decisions = tmp_path / "DECISIONS.json"
        decisions.write_text(json.dumps({"decisions": [
            {"site_id": rows[0]["id"], "rule": "a", "status": "pending", "quote": "built in the 4th century", "note": "dated inside"},
            {"site_id": rows[1]["id"], "rule": "d", "status": "in_scope", "quote": "ancient finds"},
            {"site_id": rows[3]["id"], "rule": "a", "status": "pending", "quote": "x"},
        ]}), encoding="utf-8")  # fmt: skip
        answers = tmp_path / "NONSITE_R0.jsonl"
        answers.write_text(
            json.dumps({"site_id": rows[2]["id"], "decision": "not_a_site", "counted": True, "kind": "natural_formation", "reason": "a rock"}) + "\n"
            + json.dumps({"site_id": rows[0]["id"], "decision": "site", "counted": True, "kind": None, "reason": "x"}) + "\n",
            encoding="utf-8",
        )  # fmt: skip
        cases = CAL.select_scope(
            world["run"],
            scope_decisions=decisions,
            review_snapshot=snapshot,
            review_answers=answers,
        )
        assert [(c.source, c.site_id[-1]) for c in cases] == [
            ("scope-e4:a:pending", "a"), ("scope-e4:d:in_scope", "b"), ("scope-review:not_a_site", "c"),
        ]  # fmt: skip
        fort, museum, baltic = (c.context for c in cases)
        assert (
            fort["groups"] == ["outside_window"]
            and fort["cutoff"] == 500
            and fort["origin"] == "import"
        )
        assert museum["museum_question"] is True and baltic["groups"] == ["calibration"]
        assert "calibration case" in SJ.render_web(baltic)
        assert SJ.render_web(fort).count("withdrawn by owner decision D10") == 0

    def test_the_hints_say_which_verdicts_an_earlier_judgement_makes_likely(self) -> None:
        assert CAL._hint_verdicts("known-defect:Chania") == {"RETARGET", "MERGE"}
        assert CAL._hint_verdicts("scope-e4:d:in_scope") == {"MUSEUM_KEEP"}
        assert CAL._hint_verdicts("triage:hard") == set()


def labelled_pool(
    world: dict[str, Any], *, answer_all: bool = True, role: str = "pilot_judge"
) -> Path:
    pool, handoff = world["tmp"] / "pool", world["tmp"] / "pool-h"
    cases = CAL.select_retarget(
        world["run"], bcases_names=world["bcases"], n7_site=1, n7_locality=1, clean=1
    )
    CAL.export_pool(pool, "retarget", handoff, cases, seed=7)
    spec = CAL.spec_of("retarget")
    record = R.find_round(pool, "r1")
    for batch_id, sids in record.batches.items():
        for sid in sids[: None if answer_all else 1]:
            verdict = "RETARGET" if sid == CHANIA else "KEEP"
            OH.write_answer(
                handoff, batch_id=batch_id, stage=spec.stage, label=sid,
                text=json.dumps({"site_id": sid, "verdict": verdict, "why": "gold"}),
                answered_by=RO.answered_by(role, batch_id), model=OH.OPUS_MODEL, now=lambda: NOW,
            )  # fmt: skip
    return pool


class TestThePool:
    def test_an_empty_pool_is_refused(self, world: dict[str, Any]) -> None:
        with pytest.raises(CAL.PoolError, match="no case"):
            CAL.export_pool(world["tmp"] / "p", "retarget", world["tmp"] / "h", [], seed=1)

    def test_the_pool_is_the_lane_s_own_questions_and_a_manifest_of_hints(
        self, world: dict[str, Any]
    ) -> None:
        pool = labelled_pool(world, answer_all=False)
        manifest = CAL.load_manifest(pool)
        assert manifest["stage"] == "retarget-web" and len(manifest["cases"]) == 4
        assert manifest["cases"][0]["source"].startswith("known-defect")
        contexts = R.load_contexts(pool)
        assert set(contexts) == {c["site_id"] for c in manifest["cases"]}
        prompt = next(Path(manifest["handoff"]).glob("*/retarget-web/*.prompt.txt")).read_text(
            "utf-8"
        )
        assert "audit" not in prompt
        with pytest.raises(CAL.PoolError, match="export the pool first"):
            CAL.load_manifest(world["tmp"])

    def test_a_pool_is_fit_to_seal_only_when_the_pilot_judge_answered_every_question(
        self, world: dict[str, Any]
    ) -> None:
        part = labelled_pool(world, answer_all=False)
        got = CAL.status(part)
        assert got["fit_to_seal"] is False and len(got["unanswered"]) >= 1 and got["answered"] >= 1
        world2 = {**world, "tmp": world["tmp"] / "two"}
        world2["tmp"].mkdir()
        full = labelled_pool(world2)
        assert CAL.status(full) == {"questions": 4, "answered": 4, "unanswered": [], "stale_or_malformed": 0,
                                    "not_the_pilot_judge": [], "fit_to_seal": True}  # fmt: skip

    def test_a_gold_by_another_role_is_not_fit(self, world: dict[str, Any]) -> None:
        pool = labelled_pool(world, role="web_verifier")
        got = CAL.status(pool)
        assert got["fit_to_seal"] is False and len(got["not_the_pilot_judge"]) == 4

    def test_a_label_that_disagrees_with_its_hint_is_listed_for_the_orchestrator(
        self, world: dict[str, Any]
    ) -> None:
        pool = labelled_pool(world)
        got = CAL.disagreements(pool)
        # the fixture labels everything but Chania KEEP: an N7 locality record is expected to move
        assert [d["source"] for d in got] == ["bcases-n7:anchor-is-locality"]
        assert got[0]["label"] == "KEEP" and "RETARGET" in got[0]["expected_one_of"]


class TestTheCalibrationEndToEnd:
    def test_the_role_is_sealed_against_the_pool_re_answers_a_copy_and_is_measured(
        self, world: dict[str, Any]
    ) -> None:
        pool = labelled_pool(world)
        manifest = CAL.load_manifest(pool)
        root = world["tmp"] / "cal"
        CC.seal(root, calibration_id="retarget-web", role="web_verifier", handoff=Path(manifest["handoff"]),
                batches=manifest["batches"], threshold=0.9)  # fmt: skip
        prepared = CAL.prepare(root, "retarget-web", pool)
        copy = Path(prepared["stage_dir"])
        assert prepared["questions"] == 4 and (copy / R.CONTEXTS_DIR / "r1.jsonl").exists()

        # the copy is a stage directory: the role under test is briefed and shape-checked from it
        spec = CAL.spec_of("retarget")
        record = R.find_round(copy, "r1")
        assert record.name == "r1" and sorted(record.batches) == manifest["batches"]
        text = R.brief(copy, spec, "r1", manifest["batches"][0])
        assert (
            "--role web_verifier --model claude-sonnet-5-5" in text
            and f"--stage-dir {copy.resolve().as_posix()}" in text
        )
        labels = [s for sids in record.batches.values() for s in sids]
        ok = json.dumps({"site_id": labels[0], "verdict": "KEEP", "why": "x", "quotes": [{"url": WP + "X", "quote": "q"}],
                         "target": None, "merge_with": None})  # fmt: skip
        assert R.check_answer(copy, spec, "r1", manifest["batches"][0], labels[0], ok) is None

        out = Path(prepared["prepared"])
        for batch_id, sids in record.batches.items():
            for sid in sids:
                verdict = "RETARGET" if sid == CHANIA else "KEEP"
                OH.write_answer(out, batch_id=batch_id, stage=spec.stage, label=sid,
                                text=json.dumps({"site_id": sid, "verdict": verdict}),
                                answered_by=RO.answered_by("web_verifier", batch_id), model=OH.SONNET_MODEL,
                                now=lambda: NOW)  # fmt: skip
        report = CC.compare(root, calibration_id="retarget-web")
        assert (report["units"], report["agreed"], report["unanswered"]) == (4, 4, [])
        verdict = CC.verdict(root, calibration_id="retarget-web", false_sources=0)
        assert verdict["passed"] is True and verdict["role"] == "web_verifier"

        # ... and the verdict opens the import gate of the stage
        assert R.require_calibration(root, "retarget-web", "web_verifier")["passed"] is True

    def test_a_role_that_disagrees_fails_and_moves_up_one_tier(self, world: dict[str, Any]) -> None:
        pool = labelled_pool(world)
        manifest = CAL.load_manifest(pool)
        root = world["tmp"] / "cal"
        CC.seal(root, calibration_id="c", role="web_verifier", handoff=Path(manifest["handoff"]),
                batches=manifest["batches"], threshold=0.9)  # fmt: skip
        prepared = CAL.prepare(root, "c", pool)
        spec = CAL.spec_of("retarget")
        for batch_id, sids in R.find_round(Path(prepared["stage_dir"]), "r1").batches.items():
            for sid in sids:
                OH.write_answer(Path(prepared["prepared"]), batch_id=batch_id, stage=spec.stage, label=sid,
                                text=json.dumps({"site_id": sid, "verdict": "KEEP"}),
                                answered_by=RO.answered_by("web_verifier", batch_id), model=OH.SONNET_MODEL,
                                now=lambda: NOW)  # fmt: skip
        CC.compare(root, calibration_id="c")
        verdict = CC.verdict(root, calibration_id="c", false_sources=0)
        assert verdict["passed"] is False and verdict["agreement"] == 0.75
        assert verdict["tier_move"]["to"] == "claude-opus-5-5"
        with pytest.raises(R.RoundError, match="did not pass"):
            R.require_calibration(root, "c", "web_verifier")

    def test_a_pool_the_gold_of_which_is_a_minimax_answer_cannot_be_sealed(
        self, world: dict[str, Any]
    ) -> None:
        pool = labelled_pool(world, answer_all=False)
        manifest = CAL.load_manifest(pool)
        handoff = Path(manifest["handoff"])
        first = next(handoff.glob("*/retarget-web/*.answer.json"))
        body = json.loads(first.read_text("utf-8"))
        body["model"] = OH.MINIMAX_MODEL
        first.write_text(json.dumps(body), encoding="utf-8")
        with pytest.raises(CC.CalibrationError, match="answered by MiniMax"):
            CC.seal(world["tmp"] / "cal", calibration_id="m", role="web_verifier", handoff=handoff,
                    batches=manifest["batches"], threshold=0.9)  # fmt: skip
