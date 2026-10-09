"""The calibration of the card lane's roles: the seal, the fixed cases, the questions, the measures.

The recorded runs are written by hand (a handful of sites), the sealed table is a small one with the
same keys, the answers go through `opus_handoff.write_answer` in the role of the set and the web is a
`httpx.MockTransport`. Each rule is asserted by the refusal or the number it produces.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from teaser import calibrate as K  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import run as R  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

from tests.remediation import shorts_cases as S  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.test_teaser_shorts_run import (  # noqa: E402
    MP,
    check_json,
    make_run,
    sid,
    step,
    writes,
)

TINY: dict[str, Any] = {
    "version": "tiny",
    "source": "test",
    "seed": 7,
    "roles": {
        "fact_checker": {
            "sets": {
                "checker_agreement": {
                    "pass_cases": 2,
                    "fail_cases": 1,
                    "verdict_agreement_min": 0.9,
                    "claim_agreement_min": 0.9,
                    "false_pass_max": 0,
                },
                "checker_fail_again": {"cases": 2, "fail_min": 2},
                "checker_defects": {"cases": 3, "caught_min": 3},
                "checker_good": {"cases": 3, "pass_min": 3},
            }
        },
        "web_verifier": {
            "sets": {
                "verifier_contradicted": {"cases": 2, "caught_min": 2},
                "verifier_verified": {
                    "cases": 2,
                    "falsely_contradicted_max": 0,
                    "claim_agreement_min": 0.9,
                    "false_sources_max": 0,
                },
            }
        },
        "hook_rater": {
            "sets": {
                "hook_pairs": {
                    "strong": 2,
                    "weak": 2,
                    "ordered_right_min": 1.0,
                    "reference_within_one_min": 0.75,
                }
            }
        },
        "card_writer": {"sets": {"writer_pilot": {"sites": 2, "clean_first_min": 0.5}}},
        "adversarial": {
            "sets": {
                "adversarial_contradicted": {"cases": 2},
                "adversarial_clean": {"cases": 2},
                "adversarial_agreement": {"agreement_min": 0.75},
            }
        },
    },
}
PAGE = "https://example.org/skara-brae"
PAGE_TEXT = b"<html><body><p>The site was occupied from roughly 3180 BC to around 2500 BC.</p></body></html>"
QUOTE = "occupied from roughly 3180 BC to around 2500 BC"
SUPPORTED = {
    "claim": "lived in from roughly 3180 BC",
    "verdict": "SUPPORTED",
    "url": PAGE,
    "quote": QUOTE,
    "proven": True,
    "quote_outcome": "found",
}
CONTRADICTED = {**SUPPORTED, "claim": "built by the Inca", "verdict": "CONTRADICTED"}
DESCRIPTION = (
    "Zorgat Hill is a ridge fort [1]. It was occupied until 1200 BC [1]. A mirror was found [1]."
)


def site_row(n: int) -> dict[str, Any]:
    return {
        "site_id": f"0a000000-0000-4000-8000-{n:012d}",
        "name": f"Zorgat {n}",
        "country": "Atlantis",
        "description": DESCRIPTION,
        "alt_names": [],
        "lane": "W",
        "basis": "W",
        "card": None,
        "desc_sha256": T.sha(DESCRIPTION),
    }


def check_record(n: int, verdict: str, **over: Any) -> dict[str, Any]:
    support = ["S1"] if verdict == "PASS" else []
    return {
        "site_id": site_row(n)["site_id"],
        "stage": "check",
        "kind": "check",
        "card": f"Card {n} of the recorded run.",
        "claims": [{"claim": "a ridge fort", "support": support or ["S1"]}]
        + ([] if verdict == "PASS" else [{"claim": "the oldest fort", "support": []}]),
        "tone_ok": True,
        "this_site": True,
        "verdict": verdict,
        "reasons": [] if verdict == "PASS" else ["No sentence says it is the oldest."],
        "answered_by": f"teaser-check-{n}",
        "answered_at": "2026-09-28T10:00:00+00:00",
        **over,
    }


def verify_record(
    n: int, claims: list[dict[str, Any]], verdict: str, **over: Any
) -> dict[str, Any]:
    return {
        "site_id": site_row(n)["site_id"],
        "stage": "verify",
        "kind": "verify",
        "card": f"Card {n} of the recorded run.",
        "claims": claims,
        "verdict": verdict,
        "unproven": 0,
        "answered_by": f"teaser-verify-{n}",
        "answered_at": "2026-09-28T11:00:00+00:00",
        **over,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


def recorded_run(tmp_path: Path, name: str = "wb-recorded", **kw: Any) -> Path:
    """Eight sites of an Opus-era run: s1-s2 checked and VERIFIED, s3-s4 checked and
    CONTRADICTED on the web, s5 checked, s6-s8 failed by their checker."""
    run = tmp_path / "recorded" / name
    run.mkdir(parents=True, exist_ok=True)
    (run / "RUN.json").write_text(json.dumps({"contract": {"min_chars": 160}}), encoding="utf-8")
    write_jsonl(run / "SITES.jsonl", [site_row(n) for n in range(1, 9)])
    checks = [check_record(n, "PASS") for n in range(1, 6)]
    checks += [check_record(n, "FAIL") for n in range(6, 9)]
    write_jsonl(run / "STAGE-check.jsonl", [{**c, **kw} for c in checks])
    write_jsonl(
        run / "STAGE-verify.jsonl",
        [
            verify_record(1, [SUPPORTED], "VERIFIED"),
            verify_record(2, [SUPPORTED, {**SUPPORTED, "claim": "an occupation"}], "VERIFIED"),
            verify_record(3, [SUPPORTED, CONTRADICTED], "CONTRADICTED"),
            verify_record(4, [SUPPORTED, CONTRADICTED], "CONTRADICTED"),
        ],
    )
    return run


def base_cards() -> list[dict[str, Any]]:
    rows = []
    for name in (MP, "Huaca del Sol", "Denbury Hill"):
        sample = S.BY_NAME[name]
        rows.append(
            {
                "site_id": sample["site_id"],
                "name": name,
                "country": sample["country"],
                "description": sample["description"],
                "alt_names": sample["aliases"],
                "pool_images": sample["pool_images"],
                "image_titles": ["A", "B"],
                "card": sample["card"],
                "anchors": sample["anchors"],
                "sample": name != "Denbury Hill",
            }
        )
    return rows


def export_file(tmp_path: Path) -> Path:
    rows = [
        T.row(T.SKARA, card="On Orkney lie stone houses, a Neolithic village of hearths and beds."),
        T.row(T.NEWGRANGE, card="In County Meath a great mound rises above the River Boyne."),
        T.row(T.STONEHENGE, card="Stones weighing around 25 tons stand in a ring."),
    ]
    path = tmp_path / "EXPORT.jsonl"
    path.write_text(T.tagged({"site": rows}), encoding="utf-8")
    return path


def modules_root(tmp_path: Path) -> Path:
    root = tmp_path / "modules"
    for name in K.MODULES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / name, target)
    return root


def sealed_dir(tmp_path: Path, thresholds: dict[str, Any] = TINY) -> Path:
    run_dir = tmp_path / "calibration" / "teaser-test"
    K.seal(run_dir, thresholds=thresholds)
    return run_dir


def fixed_dir(tmp_path: Path, thresholds: dict[str, Any] = TINY) -> Path:
    run_dir = sealed_dir(tmp_path, thresholds)
    jobs = K.build_jobs(
        K.sealed(run_dir)[0],
        runs=[recorded_run(tmp_path)],
        export=export_file(tmp_path),
        base_cards=base_cards(),
    )
    K.fix_jobs(run_dir, jobs)
    return run_dir


UUID4 = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"


def answer_role(
    run_dir: Path,
    role: str,
    by_set: dict[str, Any],
    *,
    as_role: str | None = None,
    model: str | None = None,
) -> Path:
    """Export the role's cases and answer every one as an agent of `as_role` (default: the role); the
    text of a case comes from the function registered for its set."""
    handoff = run_dir.parent / f"handoff-{role}"
    K.export_role(run_dir, role, handoff)
    chosen = as_role or role
    jobs = {j["key"]: j for j in K.sealed_jobs(run_dir)}
    for batch, keys in K._handoffs(run_dir)[role]["batches"].items():
        for key in keys:
            OH.write_answer(
                handoff,
                batch_id=batch,
                stage=K.STAGE,
                label=key,
                text=by_set[jobs[key]["set"]](jobs[key]),
                answered_by=RO.answered_by(chosen, f"cal-{batch}"),
                model=OH.ANSWER_MODELS[model or RO.role(chosen).model],
            )
    return handoff


def jobs_of(run_dir: Path, set_name: str) -> list[dict[str, Any]]:
    """The cases of one set, in their number order (the keys say nothing)."""
    return sorted(
        (j for j in K.sealed_jobs(run_dir) if j["set"] == set_name), key=lambda j: j["number"]
    )


def checker_text(verdict: str):
    def make(job: dict[str, Any]) -> str:
        if job["prompt_kind"] == "checker_shorts":
            return check_json(verdict) if verdict == "PASS" else check_json("FAIL", name_leak=True)
        return T.checker_answer(
            verdict,
            [("a ridge fort", ["S1"])] if verdict == "PASS" else [("x", [])],
            [] if verdict == "PASS" else ["No."],
        )

    return make


def judge_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == PAGE:
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=PAGE_TEXT)
        return httpx.Response(404, content=b"no")

    return httpx.Client(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------------------ the seal
class TestTheSeal:
    def test_the_real_table_is_the_plan_s(self) -> None:
        roles = K.THRESHOLDS["roles"]
        sets = roles["fact_checker"]["sets"]
        assert sets["checker_agreement"] == {
            "pass_cases": 30, "fail_cases": 15, "verdict_agreement_min": 0.9,
            "claim_agreement_min": 0.9, "false_pass_max": 0
        }  # fmt: skip
        assert (
            sets["checker_fail_again"]["fail_min"] == 27
            and sets["checker_defects"]["caught_min"] == 27
        )
        assert sets["checker_good"]["pass_min"] == 27
        web = roles["web_verifier"]["sets"]
        assert web["verifier_contradicted"] == {"cases": 20, "caught_min": 18}
        assert web["verifier_verified"]["falsely_contradicted_max"] == 2
        hooks = roles["hook_rater"]["sets"]["hook_pairs"]
        assert (hooks["strong"], hooks["weak"], hooks["ordered_right_min"]) == (11, 13, 1.0)
        assert hooks["reference_within_one_min"] == 0.8
        assert roles["card_writer"]["sets"]["writer_pilot"] == {"sites": 40, "clean_first_min": 0.8}
        adv = roles["adversarial"]["sets"]
        assert adv["adversarial_contradicted"]["cases"] == adv["adversarial_clean"]["cases"] == 25
        assert adv["adversarial_agreement"]["agreement_min"] == 0.9
        assert set(roles) == {
            "fact_checker",
            "web_verifier",
            "hook_rater",
            "card_writer",
            "adversarial",
        }

    def test_a_seal_writes_the_thresholds_the_modules_and_the_registry(
        self, tmp_path: Path
    ) -> None:
        run_dir = sealed_dir(tmp_path)
        digest = K._sha((run_dir / K.THRESHOLDS_FILE).read_text("utf-8"))
        assert (
            json.loads((run_dir / K.SEAL_LOG).read_text("utf-8").splitlines()[0])[K.SEALED_KEY]
            == digest
        )
        thresholds, again = K.sealed(run_dir)
        assert again == digest and thresholds["seed"] == 7
        assert set(thresholds["modules"]) == set(K.MODULES)
        assert thresholds["registry"]["fact_checker"]["model"] == "claude-sonnet-5-5"
        assert thresholds["registry"]["pilot_judge"]["effort"] == "xhigh"

    def test_a_directory_with_a_case_or_a_verdict_cannot_be_sealed(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        with pytest.raises(K.CalibrationError, match="sealed before the first case"):
            K.seal(run_dir, thresholds=TINY)
        other = tmp_path / "other"
        other.mkdir()
        (other / "VERDICT-fact_checker.json").write_text("{}", encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="sealed before the first case"):
            K.seal(other, thresholds=TINY)

    def test_a_sealed_file_is_never_rewritten(self, tmp_path: Path) -> None:
        run_dir = sealed_dir(tmp_path)
        with pytest.raises(K.CalibrationError, match="holds other thresholds"):
            K.seal(run_dir, thresholds={**TINY, "seed": 8})

    def test_the_thresholds_cannot_change_after_the_seal(self, tmp_path: Path) -> None:
        run_dir = sealed_dir(tmp_path)
        path = run_dir / K.THRESHOLDS_FILE
        path.write_text(path.read_text("utf-8").replace('"seed": 7', '"seed": 9'), encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="changed after it was sealed"):
            K.sealed(run_dir)

    def test_a_prompt_that_changed_after_the_seal_refuses_the_calibration(
        self, tmp_path: Path
    ) -> None:
        root = modules_root(tmp_path)
        run_dir = tmp_path / "calibration" / "teaser-mod"
        K.seal(run_dir, thresholds=TINY, root=root)
        assert K.sealed(run_dir, root=root)[0]["seed"] == 7
        prompts = root / "scripts/remediation/teaser/prompts_shorts.py"
        prompts.write_text(prompts.read_text("utf-8") + "\n# edited\n", encoding="utf-8")
        with pytest.raises(K.CalibrationError, match=r"prompts_shorts.py.*changed after the seal"):
            K.sealed(run_dir, root=root)

    def test_a_role_registry_that_changed_after_the_seal_refuses_the_calibration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run_dir = sealed_dir(tmp_path)
        monkeypatch.setattr(RO, "role_sha256", lambda name: "moved")
        with pytest.raises(
            K.CalibrationError, match="registry entry of role .* changed after the seal"
        ):
            K.sealed(run_dir)

    def test_an_unsealed_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(K.CalibrationError, match="is not sealed"):
            K.sealed(tmp_path)


# ------------------------------------------------------------------------------ the cases
class TestTheCases:
    def jobs(self, tmp_path: Path, **over: Any) -> list[dict[str, Any]]:
        kw: dict[str, Any] = {
            "runs": [recorded_run(tmp_path)],
            "export": export_file(tmp_path),
            "base_cards": base_cards(),
        }
        return K.build_jobs(TINY, **{**kw, **over})

    def test_every_set_has_its_sealed_number_of_cases(self, tmp_path: Path) -> None:
        jobs = self.jobs(tmp_path)
        counts = {s: sum(1 for j in jobs if j["set"] == s) for s in K.SET_ROLE}
        assert counts == {
            "checker_agreement": 3, "checker_fail_again": 2, "checker_defects": 3, "checker_good": 3,
            "verifier_contradicted": 2, "verifier_verified": 2, "hook_pairs": 4, K.HOOK_REFERENCE: 4,
            "adversarial_contradicted": 2, "adversarial_clean": 2,
        }  # fmt: skip
        assert len({j["key"] for j in jobs}) == len(jobs)
        assert {j["role"] for j in jobs} == {
            "fact_checker",
            "web_verifier",
            "hook_rater",
            "pilot_judge",
            "adversarial",
        }

    def test_a_key_says_nothing_of_its_case(self, tmp_path: Path) -> None:
        jobs = self.jobs(tmp_path)
        for job in jobs:
            assert re.fullmatch(UUID4, job["key"])
            assert job["set"] not in job["key"] and job["set"].split("_")[0] not in job["key"]
        keys = [j["key"] for j in sorted(jobs, key=lambda j: (j["set"], j["number"]))]
        assert keys != sorted(keys)  # the key order is not the set order either

    def test_the_draw_is_seeded_and_the_failures_do_not_overlap(self, tmp_path: Path) -> None:
        first, again = self.jobs(tmp_path), self.jobs(tmp_path)
        assert K.jobs_text(first) == K.jobs_text(again)
        fails = [
            j
            for j in first
            if j["set"] in ("checker_agreement", "checker_fail_again")
            and j["recorded"]["verdict"] == "FAIL"
        ]
        assert len({j["site_id"] for j in fails}) == len(fails) == 3
        other = K.build_jobs(
            {**TINY, "seed": 8},
            runs=[recorded_run(tmp_path, "wb-other")],
            export=export_file(tmp_path),
            base_cards=base_cards(),
        )
        assert K.jobs_text(other) != K.jobs_text(first)

    def test_a_minimax_record_is_no_ground_truth(self, tmp_path: Path) -> None:
        run = recorded_run(tmp_path, "wb-minimax", model=OH.MINIMAX_MODEL)
        with pytest.raises(K.CalibrationError, match="recorded checker PASS"):
            K.build_jobs(TINY, runs=[run], export=export_file(tmp_path), base_cards=base_cards())
        late = recorded_run(tmp_path, "wb-late", answered_at="2026-10-04T10:00:00+00:00")
        with pytest.raises(K.CalibrationError, match="recorded checker PASS"):
            K.build_jobs(TINY, runs=[late], export=export_file(tmp_path), base_cards=base_cards())
        opus = recorded_run(
            tmp_path, "wb-opus", model=OH.OPUS_MODEL, answered_at="2026-10-05T10:00:00+00:00"
        )
        assert self.jobs(tmp_path, runs=[opus])

    def test_the_ground_truth_rule(self) -> None:
        assert K.ground_truth({"answered_at": "2026-09-30T00:00:00+00:00"})
        assert not K.ground_truth({"answered_at": "2026-10-03T00:00:00+00:00"})
        assert K.ground_truth(
            {"model": OH.SONNET_MODEL, "answered_at": "2026-10-09T00:00:00+00:00"}
        )
        assert not K.ground_truth(
            {"model": OH.MINIMAX_MODEL, "answered_at": "2026-09-01T00:00:00+00:00"}
        )

    def test_a_pool_smaller_than_the_sealed_set_is_refused(self, tmp_path: Path) -> None:
        big = {**TINY, "roles": {**TINY["roles"], "web_verifier": {"sets": {
            "verifier_contradicted": {"cases": 5, "caught_min": 5}, "verifier_verified": TINY["roles"]["web_verifier"]["sets"]["verifier_verified"]}}}}  # fmt: skip
        with pytest.raises(K.CalibrationError, match="recorded contradictions: 2 recorded case"):
            K.build_jobs(
                big,
                runs=[recorded_run(tmp_path)],
                export=export_file(tmp_path),
                base_cards=base_cards(),
            )

    def test_the_base_cards_are_as_many_as_sealed_and_the_samples_exactly(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(K.CalibrationError, match="base cards: 2 vetted card"):
            self.jobs(tmp_path, base_cards=base_cards()[:2])
        unmarked = [{**c, "sample": False} for c in base_cards()]
        with pytest.raises(K.CalibrationError, match="0 card.s. marked sample, 2 sealed"):
            self.jobs(tmp_path, base_cards=unmarked)

    def test_a_base_card_that_breaks_the_contract_is_refused(self, tmp_path: Path) -> None:
        good = base_cards()
        path = tmp_path / "BASE.jsonl"
        write_jsonl(path, good)
        assert len(K.read_base_cards(path, fit=T.fit)) == 3
        named = [
            {**good[0], "card": "Machu Picchu is a citadel of the Inca, high above a river valley."}
        ]
        write_jsonl(path, named)
        with pytest.raises(K.CalibrationError, match="breaks the contract"):
            K.read_base_cards(path, fit=T.fit)
        assert K.read_base_cards(path)[0]["name"] == MP

    def test_the_weak_openers_are_live_cards_that_open_with_a_place_word(
        self, tmp_path: Path
    ) -> None:
        jobs = self.jobs(tmp_path)
        weak = [j for j in jobs if j["set"] == "hook_pairs" and j["grade"] == "weak"]
        assert sorted(j["card"].split()[0] for j in weak) == ["In", "On"]
        strong = [j for j in jobs if j["set"] == "hook_pairs" and j["grade"] == "strong"]
        assert len(strong) == 2 and all(j["name"] in (MP, "Huaca del Sol") for j in strong)

    def test_a_defect_case_is_a_base_card_with_one_flaw_and_a_good_case_the_card_itself(
        self, tmp_path: Path
    ) -> None:
        jobs = self.jobs(tmp_path)
        defects = {j["site_id"]: j for j in jobs if j["set"] == "checker_defects"}
        good = {j["site_id"]: j for j in jobs if j["set"] == "checker_good"}
        assert set(defects) == set(good)
        for site, bad in defects.items():
            assert (
                bad["card"] != good[site]["card"] and bad["recorded"]["defect"] in SV.DEFECT_KINDS
            )
            assert good[site]["card"] == C.final_card(good[site]["card"])

    def test_the_adversary_is_not_shown_what_the_web_found(self, tmp_path: Path) -> None:
        jobs = self.jobs(tmp_path)
        contradicted = next(j for j in jobs if j["set"] == "adversarial_contradicted")
        assert contradicted["expected"] == "FAIL"
        assert [c["verdict"] for c in contradicted["verify"]["claims"]] == ["SUPPORTED"]
        clean = next(j for j in jobs if j["set"] == "adversarial_clean")
        assert clean["expected"] == "PASS" and "CONTRADICTED" not in json.dumps(clean["verify"])

    def test_a_card_checked_and_verified_is_one_card(self, tmp_path: Path) -> None:
        run = recorded_run(tmp_path, "wb-moved")
        rows = R.read_jsonl(run / "STAGE-verify.jsonl")
        rows[0]["card"] = "Another card than the one checked."
        write_jsonl(run / "STAGE-verify.jsonl", rows)
        verified, _ = K.recorded_verifications([run])
        assert [v["record"]["site_id"] for v in verified] == [site_row(2)["site_id"]]


class TestFixingTheCases:
    def test_the_cases_are_fixed_once_and_logged(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        entries = [
            json.loads(line) for line in (run_dir / K.SEAL_LOG).read_text("utf-8").splitlines()
        ]
        fixed = [e for e in entries if K.FIXED_KEY in e]
        assert len(fixed) == 1 and fixed[0]["jobs"] == len(K.sealed_jobs(run_dir))
        again = K.build_jobs(
            K.sealed(run_dir)[0],
            runs=[recorded_run(tmp_path, "wb-recorded2")],
            export=export_file(tmp_path),
            base_cards=base_cards(),
        )
        # the same cases again change nothing; other cases are refused
        K.fix_jobs(run_dir, K.sealed_jobs(run_dir))
        with pytest.raises(K.CalibrationError, match="never rewritten"):
            K.fix_jobs(run_dir, again[:-1])

    def test_cases_cannot_be_fixed_after_a_role_was_exported(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        K.export_role(run_dir, "fact_checker", tmp_path / "h-good")
        with pytest.raises(K.CalibrationError, match="exists: the cases are fixed first"):
            K.fix_jobs(run_dir, K.sealed_jobs(run_dir))

    def test_cases_cannot_be_fixed_before_the_seal(self, tmp_path: Path) -> None:
        with pytest.raises(K.CalibrationError, match="is not sealed"):
            K.fix_jobs(tmp_path / "x", [])

    def test_a_case_file_changed_after_it_was_fixed_is_refused(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        path = run_dir / K.JOBS_FILE
        path.write_text(path.read_text("utf-8").replace("Zorgat", "Zorgit", 1), encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="not the sample the seal log fixed"):
            K.sealed_jobs(run_dir)

    def test_no_case_is_exported_before_it_is_fixed(self, tmp_path: Path) -> None:
        run_dir = sealed_dir(tmp_path)
        with pytest.raises(K.CalibrationError, match="not the sample the seal log fixed"):
            K.export_role(run_dir, "fact_checker", tmp_path / "h")


# ------------------------------------------------------------------------------ the questions
class TestTheQuestions:
    def test_each_case_is_asked_with_the_lane_s_own_prompt(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        agreement = jobs_of(run_dir, "checker_agreement")[0]
        assert K.job_prompt(agreement) == P.checker_prompt(
            K.job_basis(agreement), agreement["card"]
        )
        good = jobs_of(run_dir, "checker_good")[0]
        assert K.job_prompt(good) == PS.checker_prompt(
            K.job_basis(good), good["card"], good["anchors"]
        )
        verifier = jobs_of(run_dir, "verifier_verified")[0]
        assert K.job_prompt(verifier) == P.judge_prompt(
            verifier["name"], verifier["country"], verifier["card"]
        )
        hook = jobs_of(run_dir, "hook_pairs")[0]
        assert K.job_prompt(hook) == PS.rate_prompt(
            hook["name"], hook["country"], [(1, hook["card"])]
        )
        assert K.job_prompt(jobs_of(run_dir, K.HOOK_REFERENCE)[0]) == K.job_prompt(hook)
        adversary = jobs_of(run_dir, "adversarial_clean")[0]
        assert "find the reason it must NOT stay public" in K.job_prompt(adversary)

    def test_a_role_is_exported_once_into_a_directory_of_its_own(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        exported = K.export_role(run_dir, "fact_checker", tmp_path / "h-checker")
        assert exported["cases"] == 11 and exported["role"] == "fact_checker"
        assert sum(exported["batches"].values()) == 11
        assert len(OH.manifest(tmp_path / "h-checker")) == 11
        with pytest.raises(K.CalibrationError, match="exported already"):
            K.export_role(run_dir, "fact_checker", tmp_path / "h-checker2")
        with pytest.raises(K.CalibrationError, match="not empty"):
            K.export_role(run_dir, "hook_rater", tmp_path / "h-checker")

    def test_the_questions_do_not_tell_the_role_what_kind_of_case_each_is(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-checker"
        exported = K.export_role(run_dir, "fact_checker", handoff)
        lines = OH.manifest(handoff)
        sets = {j["set"] for j in K.sealed_jobs(run_dir) if j["role"] == "fact_checker"}
        assert len(sets) == 4  # all the role's sets travel together, in one handoff
        for line in lines:
            assert line["stage"] == K.STAGE == "calibration"
            assert re.fullmatch(UUID4, line["label"])
            shown = " ".join([line["batch_id"], line["stage"], line["label"], line["prompt_path"]])
            assert not any(name.split("_")[-1] in shown for name in sets), shown
            assert not any(name in shown for name in sets)
        assert all(not any(name in batch for name in sets) for batch in exported["batches"])
        # shuffled: the cases of a batch are in no order of the sets
        by_key = {j["key"]: j["set"] for j in K.sealed_jobs(run_dir)}
        per_batch = [
            [by_key[line["label"]] for line in lines if line["batch_id"] == batch]
            for batch in exported["batches"]
        ]
        assert any(sequence != sorted(sequence) for sequence in per_batch)
        # a good card and its flawed twin (one site) are never in one batch
        for batch in K._handoffs(run_dir)["fact_checker"]["batches"].values():
            sites = [j["site_id"] for j in K.sealed_jobs(run_dir) if j["key"] in batch]
            assert len(sites) == len(set(sites))

    def test_the_deal_is_seeded(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        one = fixed_dir(tmp_path / "a")
        two = fixed_dir(tmp_path / "b")
        first = K.export_role(one, "fact_checker", tmp_path / "ha")
        second = K.export_role(two, "fact_checker", tmp_path / "hb")
        assert first == second
        assert (
            K._handoffs(one)["fact_checker"]["batches"]
            == K._handoffs(two)["fact_checker"]["batches"]
        )

    def test_a_web_role_is_asked_five_to_a_batch(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        exported = K.export_role(run_dir, "web_verifier", tmp_path / "h-ver")
        assert exported["batches"] == {"web-verifier-001": 4}
        assert K.WEB_SETS >= {"verifier_verified", "adversarial_clean"}

    def test_the_agents_of_a_role_are_workflow_ready_jobs(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        K.export_role(run_dir, "web_verifier", tmp_path / "h-ver")
        jobs = K.agent_jobs(run_dir, "web_verifier")
        assert len(jobs) == 1
        job = jobs[0]
        assert (job["role"], job["model"], job["effort"]) == (
            "web_verifier",
            "claude-sonnet-5-5",
            "high",
        )
        assert job["cases"] == 4 and job["max_parallel"] == 3
        assert job["batch_id"] == "web-verifier-001"
        brief = job["brief"]
        assert (
            "answering as the role **web_verifier**" in brief and "**claude-sonnet-5-5**" in brief
        )
        assert "--stage calibration" in brief and "--role web_verifier" in brief
        assert (
            "--model claude-sonnet-5-5" in brief and "--answered-by cal-web-verifier-001" in brief
        )
        assert not any(name in brief for name in K.SET_ROLE)
        assert "wiki_cache/INDEX.jsonl" in brief and "A 403 or 429 is NEVER a finding" in brief
        json.dumps(jobs)
        K.export_role(run_dir, "fact_checker", tmp_path / "h-good")
        plain = K.agent_jobs(run_dir, "fact_checker")[0]
        assert plain["max_parallel"] is None and "Wikipedia cache" not in plain["brief"]
        assert (plain["role"], plain["model"]) == ("fact_checker", "claude-sonnet-5-5")
        assert not any(name in plain["brief"] for name in K.SET_ROLE)

    def test_the_reference_is_answered_by_the_pilot_judge(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        K.export_role(run_dir, "pilot_judge", tmp_path / "h-ref")
        job = K.agent_jobs(run_dir, "pilot_judge")[0]
        assert (job["role"], job["model"], job["effort"]) == (
            "pilot_judge",
            "claude-opus-5-5",
            "xhigh",
        )

    def test_a_role_never_exported_has_no_agents(self, tmp_path: Path) -> None:
        with pytest.raises(K.CalibrationError, match="was never exported"):
            K.agent_jobs(fixed_dir(tmp_path), "fact_checker")

    def test_a_role_without_cases_is_refused(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        with pytest.raises(K.CalibrationError, match="no case of role"):
            K.export_role(run_dir, "card_writer", tmp_path / "h")


# ------------------------------------------------------------------------------ the fact checker
ALL_FAIL = {
    name: checker_text("FAIL")
    for name in ("checker_agreement", "checker_fail_again", "checker_defects", "checker_good")
}


class TestTheFactChecker:
    def all_sets(self, run_dir: Path, **verdicts: Any) -> None:
        good = verdicts.get("good", "PASS")
        recorded = verdicts.get("agreement", None)

        def agreement(job: dict[str, Any]) -> str:
            verdict = recorded or job["recorded"]["verdict"]
            if verdict == job["recorded"]["verdict"] and not verdicts.get("other_claims"):
                claims = [(c["claim"], c["support"]) for c in job["recorded"]["claims"]]
                reasons = job["recorded"]["reasons"]
                return T.checker_answer(verdict, claims, reasons)
            return checker_text(verdict)(job)

        answer_role(
            run_dir,
            "fact_checker",
            {
                "checker_agreement": agreement,
                "checker_fail_again": checker_text(verdicts.get("again", "FAIL")),
                "checker_defects": checker_text(verdicts.get("defects", "FAIL")),
                "checker_good": checker_text(good),
            },
        )

    def test_a_checker_that_agrees_catches_and_passes_the_good_ones_passes(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir)
        verdict = K.evaluate(run_dir, "fact_checker")
        assert verdict["passed"] is True and verdict["tier_move"] is None
        assert verdict["model"] == "claude-sonnet-5-5" and verdict["effort"] == "high"
        sets = verdict["sets"]
        assert (
            sets["checker_agreement"]["verdict_agreement"] == 1.0
            and sets["checker_agreement"]["claim_agreement"] == 1.0
            and sets["checker_agreement"]["false_pass"] == []
        )
        assert (
            sets["checker_fail_again"]["failed_again"] == 2
            and sets["checker_defects"]["caught"] == 3
        )
        assert sets["checker_good"]["passed_cards"] == 3
        assert (run_dir / "VERDICT-fact_checker.json").is_file()
        assert json.loads((run_dir / "VERDICT-fact_checker.json").read_text("utf-8")) == verdict

    def test_a_verdict_is_written_once(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir)
        K.evaluate(run_dir, "fact_checker")
        with pytest.raises(K.CalibrationError, match="a verdict is written once"):
            K.evaluate(run_dir, "fact_checker")

    def test_a_pass_of_a_card_with_an_unsupported_claim_is_a_false_pass_and_fails_the_role(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir, agreement="PASS")
        verdict = K.evaluate(run_dir, "fact_checker")
        agreement = verdict["sets"]["checker_agreement"]
        assert len(agreement["false_pass"]) == 1 and agreement["passed"] is False
        assert verdict["passed"] is False
        assert verdict["tier_move"] == {
            "role": "fact_checker", "from": "claude-sonnet-5-5", "to": "claude-opus-5-5",
            "calibration_id": "teaser-test", "reason": "failed: checker_agreement",
        }  # fmt: skip

    def test_one_false_pass_fails_the_role_even_when_agreement_is_high(
        self, tmp_path: Path
    ) -> None:
        lenient = json.loads(json.dumps(TINY))
        lenient["roles"]["fact_checker"]["sets"]["checker_agreement"]["verdict_agreement_min"] = 0.6
        run_dir = fixed_dir(tmp_path, lenient)
        self.all_sets(run_dir, agreement="PASS")
        agreement = K.evaluate(run_dir, "fact_checker")["sets"]["checker_agreement"]
        assert agreement["verdict_agreement"] == pytest.approx(0.6667, abs=1e-3)
        assert len(agreement["false_pass"]) == 1 and agreement["passed"] is False

    def test_verdicts_that_agree_with_claims_that_do_not_fail_the_role(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir, other_claims=True)
        agreement = K.evaluate(run_dir, "fact_checker")["sets"]["checker_agreement"]
        # every verdict equals the recorded one, but the recorded failures' claims are not found
        assert agreement["verdict_agreement"] == 1.0 and agreement["false_pass"] == []
        assert agreement["claim_agreement"] < 0.9 and agreement["passed"] is False

    def test_the_claim_agreement_is_sealed_in_the_table(self) -> None:
        rule = K.THRESHOLDS["roles"]["fact_checker"]["sets"]["checker_agreement"]
        assert rule["claim_agreement_min"] == 0.9

    def test_a_checker_that_fails_the_recorded_passes_disagrees(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir, agreement="FAIL")
        agreement = K.evaluate(run_dir, "fact_checker")["sets"]["checker_agreement"]
        assert agreement["false_pass"] == [] and agreement["verdict_agreement"] < 0.9
        assert agreement["passed"] is False

    def test_a_checker_that_passes_the_recorded_failures_fails(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir, again="PASS")
        verdict = K.evaluate(run_dir, "fact_checker")
        assert verdict["sets"]["checker_fail_again"] == {
            "cases": 2,
            "failed_again": 0,
            "passed": False,
        }
        assert verdict["passed"] is False

    def test_a_defect_the_checker_passes_is_named_by_its_kind(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir, defects="PASS")
        verdict = K.evaluate(run_dir, "fact_checker")
        missed = verdict["sets"]["checker_defects"]["missed_by_defect"]
        assert sum(missed.values()) == 3 and set(missed) <= set(SV.DEFECT_KINDS)
        assert verdict["tier_move"]["reason"] == "failed: checker_defects"

    def test_a_checker_that_fails_the_good_cards_fails(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        self.all_sets(run_dir, good="FAIL")
        assert K.evaluate(run_dir, "fact_checker")["sets"]["checker_good"]["passed"] is False

    def test_the_answers_must_be_the_roles_and_the_sealed_models(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "fact_checker", ALL_FAIL, as_role="hook_rater")
        with pytest.raises(K.CalibrationError, match="did not answer as role fact_checker"):
            K.evaluate(run_dir, "fact_checker")

    def test_a_stamp_that_is_not_the_sealed_model_is_refused(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "fact_checker", ALL_FAIL, model="claude-opus-5-5")
        with pytest.raises(
            K.CalibrationError, match="role fact_checker is sealed to claude-sonnet-5-5"
        ):
            K.evaluate(run_dir, "fact_checker")

    def test_an_unanswered_case_is_no_agreement(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = answer_role(run_dir, "fact_checker", ALL_FAIL)
        answer = next(handoff.glob("*/*/*.answer.json"))
        answer.unlink()
        with pytest.raises(K.CalibrationError, match="1 missing"):
            K.evaluate(run_dir, "fact_checker")

    def test_a_role_never_exported_is_refused(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        with pytest.raises(K.CalibrationError, match="was never exported"):
            K.evaluate(run_dir, "fact_checker")


# ------------------------------------------------------------------------------ the web verifier
def verifier_text(contradict: bool, quote: str = QUOTE, url: str = PAGE):
    def make(job: dict[str, Any]) -> str:
        claim = {
            "claim": "lived in from roughly 3180 BC",
            "verdict": "SUPPORTED",
            "url": url,
            "quote": quote,
        }
        claims = [claim]
        if contradict and job["set"] == "verifier_contradicted":
            claims.append({**claim, "claim": "built by the Inca", "verdict": "CONTRADICTED"})
        return json.dumps({"claims": claims})

    return make


class TestTheWebVerifier:
    def test_a_verifier_that_catches_the_contradictions_and_agrees_passes(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)

        def verified(job: dict[str, Any]) -> str:
            recorded = job["recorded"]["claims"]
            return json.dumps({"claims": [
                {"claim": c["claim"], "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE} for c in recorded
            ]})  # fmt: skip

        answer_role(
            run_dir,
            "web_verifier",
            {"verifier_contradicted": verifier_text(True), "verifier_verified": verified},
        )
        verdict = K.evaluate(run_dir, "web_verifier", client=judge_client())
        assert verdict["passed"] is True and verdict["model"] == "claude-sonnet-5-5"
        assert verdict["sets"]["verifier_contradicted"]["caught"] == 2
        assert verdict["sets"]["verifier_verified"]["claim_agreement"] == 1.0
        assert verdict["sets"]["verifier_verified"]["false_sources"] == []

    def test_a_quote_the_page_does_not_hold_is_a_false_source(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(
            run_dir,
            "web_verifier",
            {
                "verifier_contradicted": verifier_text(True),
                "verifier_verified": lambda job: json.dumps(
                    {
                        "claims": [
                            {
                                "claim": c["claim"],
                                "verdict": "SUPPORTED",
                                "url": PAGE,
                                "quote": "a sentence that the page never says",
                            }
                            for c in job["recorded"]["claims"]
                        ]
                    }
                ),
            },
        )
        verdict = K.evaluate(run_dir, "web_verifier", client=judge_client())
        verified = verdict["sets"]["verifier_verified"]
        assert len(verified["false_sources"]) >= 2 and verified["passed"] is False
        assert verdict["passed"] is False and verdict["tier_move"]["to"] == "claude-opus-5-5"

    def test_a_verifier_that_misses_a_contradiction_fails(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "web_verifier", {"verifier_contradicted": verifier_text(False), "verifier_verified": lambda job: json.dumps({"claims": [
            {"claim": c["claim"], "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE} for c in job["recorded"]["claims"]
        ]})})  # fmt: skip
        verdict = K.evaluate(run_dir, "web_verifier", client=judge_client())
        assert verdict["sets"]["verifier_contradicted"] == {
            "cases": 2,
            "caught": 0,
            "passed": False,
        }

    def test_a_good_card_called_contradicted_is_counted(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "web_verifier", {"verifier_contradicted": verifier_text(True), "verifier_verified": lambda job: json.dumps({"claims": [
            *({"claim": c["claim"], "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE} for c in job["recorded"]["claims"]),
            {"claim": "an extra claim", "verdict": "CONTRADICTED", "url": PAGE, "quote": QUOTE},
        ]})})  # fmt: skip
        verified = K.evaluate(run_dir, "web_verifier", client=judge_client())["sets"][
            "verifier_verified"
        ]
        # every recorded claim agrees; only the card's verification is wrong
        assert len(verified["falsely_contradicted"]) == 2 and verified["claim_agreement"] == 1.0
        assert verified["passed"] is False

    def test_the_claim_agreement_matches_wording_once(self) -> None:
        recorded = [
            {"claim": "a ridge fort", "verdict": "SUPPORTED"},
            {"claim": "the mirror", "verdict": "SUPPORTED"},
        ]
        fresh = [
            {"claim": "A ridge fort.", "verdict": "SUPPORTED"},
            {"claim": "a mirror was found", "verdict": "CONTRADICTED"},
        ]
        assert K.claim_agreement(recorded, fresh) == (1, 2)
        assert K.claim_agreement(recorded, []) == (0, 2)
        twice = [{"claim": "a ridge fort", "verdict": "SUPPORTED"}] * 2
        assert K.claim_agreement(twice, [fresh[0]]) == (1, 2)


# ------------------------------------------------------------------------------ the hook rater
def hook_text(strong: int, weak: int, shift: int = 0):
    def make(job: dict[str, Any]) -> str:
        hook = (strong if job["grade"] == "strong" else weak) + shift
        return json.dumps(
            {
                "ratings": [
                    {"variant": 1, "first5": " ".join(job["card"].split()[:5]), "hook": hook}
                ],
                "best": 1,
            }
        )

    return make


class TestTheHookRater:
    def test_strong_openers_rated_above_weak_ones_and_near_the_reference_pass(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "hook_rater", {"hook_pairs": hook_text(5, 2)})
        answer_role(run_dir, "pilot_judge", {K.HOOK_REFERENCE: hook_text(4, 2)})
        verdict = K.evaluate(run_dir, "hook_rater")
        hooks = verdict["sets"]["hook_pairs"]
        assert hooks["pairs_ordered_right"] == 1.0 and hooks["within_one_of_reference"] == 1.0
        assert verdict["passed"] is True and verdict["effort"] == "medium"

    def test_one_misordered_pair_fails_the_role(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "hook_rater", {"hook_pairs": hook_text(3, 3)})
        answer_role(run_dir, "pilot_judge", {K.HOOK_REFERENCE: hook_text(3, 3)})
        verdict = K.evaluate(run_dir, "hook_rater")
        assert verdict["sets"]["hook_pairs"]["pairs_ordered_right"] == 0.0
        assert verdict["passed"] is False and verdict["held"].endswith("the owner decides")
        assert verdict["tier_move"] is None

    def test_a_rater_far_from_the_reference_fails(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "hook_rater", {"hook_pairs": hook_text(5, 1)})
        answer_role(run_dir, "pilot_judge", {K.HOOK_REFERENCE: hook_text(3, 3)})
        hooks = K.evaluate(run_dir, "hook_rater")["sets"]["hook_pairs"]
        assert hooks["pairs_ordered_right"] == 1.0 and hooks["within_one_of_reference"] == 0.0
        assert hooks["passed"] is False

    def test_the_reference_is_the_pilot_judge_s(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(run_dir, "hook_rater", {"hook_pairs": hook_text(5, 2)})
        wrong = answer_role(
            run_dir, "pilot_judge", {K.HOOK_REFERENCE: hook_text(4, 2)}, as_role="hook_rater"
        )
        assert wrong.is_dir()
        with pytest.raises(K.CalibrationError, match="did not answer as role pilot_judge"):
            K.evaluate(run_dir, "hook_rater")


# ------------------------------------------------------------------------------ the adversary
class TestTheAdversary:
    def test_a_reviewer_that_fails_the_contradicted_and_passes_the_clean_passes(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        answer_role(
            run_dir,
            "adversarial",
            {
                "adversarial_contradicted": lambda job: T.checker_answer(
                    "FAIL", [("x", [])], ["The web says otherwise."]
                ),
                "adversarial_clean": lambda job: T.checker_answer(),
            },
        )
        verdict = K.evaluate(run_dir, "adversarial")
        assert verdict["passed"] is True and verdict["model"] == "claude-opus-5-5"
        assert verdict["sets"]["adversarial_agreement"]["agreement"] == 1.0

    def test_a_reviewer_that_passes_everything_fails_the_role(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        passes = {
            "adversarial_contradicted": lambda job: T.checker_answer(),
            "adversarial_clean": lambda job: T.checker_answer(),
        }
        answer_role(run_dir, "adversarial", passes)
        verdict = K.evaluate(run_dir, "adversarial")
        assert verdict["sets"]["adversarial_agreement"]["agreement"] == 0.5
        assert verdict["passed"] is False and "held" in verdict


# ------------------------------------------------------------------------------ the writer
class TestTheCardWriter:
    def run_with_writes(self, tmp_path: Path, bad: bool) -> Path:
        run = make_run(tmp_path, [MP, "Denbury Hill"])
        answers = writes([MP, "Denbury Hill"])
        if bad:
            broken = json.loads(answers[sid(MP)])
            broken["variants"][0]["card"] = "Machu Picchu: " + broken["variants"][0]["card"]
            answers[sid(MP)] = json.dumps(broken, ensure_ascii=False)
        step(run, tmp_path, "write", answers)
        return run

    def test_the_share_of_clean_first_answers_is_measured(self, tmp_path: Path) -> None:
        run = self.run_with_writes(tmp_path, bad=False)
        sealed_for_writer = sealed_dir(tmp_path)
        verdict = K.evaluate(sealed_for_writer, "card_writer", writer_run=run)
        assert (
            verdict["passed"] is True
            and verdict["sets"]["writer_pilot"]["clean_first_share"] == 1.0
        )
        assert verdict["effort"] == "high" and verdict["model"] == "claude-opus-5-5"

    def test_a_writer_below_the_floor_is_held_at_the_top_tier(self, tmp_path: Path) -> None:
        strict = {
            **TINY,
            "roles": {
                **TINY["roles"],
                "card_writer": {"sets": {"writer_pilot": {"sites": 2, "clean_first_min": 1.0}}},
            },
        }
        run = self.run_with_writes(tmp_path, bad=True)
        run_dir = tmp_path / "calibration" / "teaser-strict"
        K.seal(run_dir, thresholds=strict)
        verdict = K.evaluate(run_dir, "card_writer", writer_run=run)
        assert verdict["sets"]["writer_pilot"]["clean_first"] == 1 and verdict["passed"] is False
        assert verdict["tier_move"] is None and "no higher tier" in verdict["held"]

    def test_a_pilot_written_by_another_model_is_refused(self, tmp_path: Path) -> None:
        run = self.run_with_writes(tmp_path, bad=False)
        rows = R.read_jsonl(run / "STAGE-write.jsonl")
        rows[0]["model"] = OH.SONNET_MODEL
        R.write_jsonl(run / "STAGE-write.jsonl", rows)
        with pytest.raises(
            K.CalibrationError, match=r"1 first answer.s. are not stamped claude-opus-5-5"
        ):
            K.evaluate(sealed_dir(tmp_path), "card_writer", writer_run=run)

    def test_the_pilot_must_have_its_sealed_number_of_sites(self, tmp_path: Path) -> None:
        run = make_run(tmp_path, [MP])
        step(run, tmp_path, "write", writes([MP]))
        with pytest.raises(K.CalibrationError, match="1 first answer.s., 2 sealed"):
            K.evaluate(sealed_dir(tmp_path), "card_writer", writer_run=run)

    def test_a_pilot_run_is_needed_and_must_be_shorts_v1(self, tmp_path: Path) -> None:
        run_dir = sealed_dir(tmp_path)
        with pytest.raises(K.CalibrationError, match="--writer-run"):
            K.evaluate(run_dir, "card_writer")
        with pytest.raises(K.CalibrationError, match="is not a shorts-v1 run"):
            K.evaluate(run_dir, "card_writer", writer_run=recorded_run(tmp_path))


# ------------------------------------------------------------------------------ the CLI
class TestTheCommandLine:
    def test_a_refusal_exits_2_and_a_failed_verdict_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            K.main(
                [
                    "export",
                    "--run-dir",
                    str(tmp_path / "x"),
                    "--role",
                    "fact_checker",
                    "--handoff",
                    str(tmp_path / "h"),
                ]
            )
            == 2
        )
        assert "REFUSED" in capsys.readouterr().err

    def test_seal_prints_its_hash(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert K.main(["seal", "--run-dir", str(tmp_path / "teaser-cli")]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert len(printed["thresholds_sha256"]) == 64
        assert (
            K.sealed(tmp_path / "teaser-cli")[0]["roles"]["card_writer"]["sets"]["writer_pilot"][
                "sites"
            ]
            == 40
        )

    def test_every_role_of_the_table_is_a_command_line_choice(self) -> None:
        assert set(K.THRESHOLDS["roles"]) == set(K.ROLE_SETS) | {"card_writer"}
        assert set(K.SET_ROLE) == {s for sets in K.ROLE_SETS.values() for s in sets}
        assert set(K.SET_ROLE.values()) == set(K.ROLE_SETS) | {"pilot_judge"}
