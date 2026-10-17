"""The repair of the web verifier's calibration (diagnosis of teaser-2026-10-09, 2026-10-09).

Brief and measure failed, not the model: a verifier never looked outside the site's cached article,
true quotes were refused for footnote markers the cache drops, the claim measure paired claims one to
one, and nothing held a recorded answer to its shape. Each rule of the repair is asserted here by
the refusal or the number it produces: the cache map with opaque labels, the claims floor, coverage
instead of pairing, disputed gold, not-found-by-machine against fabricated, `check-answer`, the
`opus_handoff answer --check` hook, `void`, and the seal over the code that judges.
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

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from teaser import answers as A  # noqa: E402
from teaser import calibrate as K  # noqa: E402

from tests.remediation import teaser_cases as T  # noqa: E402
from tests.remediation.test_teaser_calibrate import (  # noqa: E402, F401
    PAGE,
    PAGE_TEXT,
    QUOTE,
    TINY,
    UUID4,
    answer_role,
    base_cards,
    check_record,
    export_file,
    fixed_dir,
    jobs_of,
    judge_client,
    modules_root,
    recorded_run,
    sealed_dir,
    site_row,
    wiki_cache,
)
from tests.remediation.test_teaser_shorts_run import check_json  # noqa: E402


def covered(recorded: list[tuple[str, str]], fresh: list[tuple[str, str]]) -> K.ClaimCoverage:
    return K.claim_coverage(
        [{"claim": c, "verdict": v} for c, v in recorded],
        [{"claim": c, "verdict": v} for c, v in fresh],
    )


# ------------------------------------------------------------------------------ the measure
class TestCoverage:
    def test_the_five_claims_of_the_undavalli_card_are_covered_by_the_three_the_agent_listed(
        self,
    ) -> None:
        """Real case: one-to-one pairing could not exceed 0.535 although every verdict agreed."""
        recorded = [
            ("The Undavalli Caves are rock-cut caves in Guntur district, Andhra Pradesh, India",
             "SUPPORTED"),
            ("The caves lie south west of Vijayawada", "SUPPORTED"),
            ("The caves later sheltered Buddhist monks", "SUPPORTED"),
            ("The caves eventually became Hindu temples", "SUPPORTED"),
            ("The caves were carved out of solid sandstone hills", "SUPPORTED"),
        ]  # fmt: skip
        fresh = [
            ("Undavalli Caves are rock-cut cave temples/monasteries in Andhra Pradesh, south west "
             "of Vijayawada", "SUPPORTED"),
            ("The caves were carved out of solid sandstone hills in the 4th-5th centuries CE",
             "SUPPORTED"),
            ("The caves later sheltered Buddhist monks and eventually became Hindu temples",
             "SUPPORTED"),
        ]  # fmt: skip
        result = covered(recorded, fresh)
        assert (result.recorded, result.covered, result.agreed) == (5, 5, 5)
        assert result.coverage == result.agreement == 1.0

    def test_one_fresh_claim_may_cover_several_recorded_ones(self) -> None:
        result = covered(
            [("a ridge fort", "SUPPORTED"), ("a fort on a ridge", "SUPPORTED")],
            [("The site is a ridge fort", "SUPPORTED")],
        )
        assert (result.covered, result.agreed) == (2, 2)

    def test_a_recorded_claim_nobody_lists_is_not_covered_and_is_no_disagreement(self) -> None:
        result = covered(
            [("a ridge fort", "SUPPORTED"), ("a bronze mirror was found", "SUPPORTED")],
            [("a ridge fort", "SUPPORTED")],
        )
        assert (result.recorded, result.covered, result.agreed) == (2, 1, 1)
        assert result.coverage == 0.5 and result.agreement == 1.0

    def test_a_covered_claim_with_another_verdict_disagrees(self) -> None:
        result = covered(
            [("a ridge fort", "SUPPORTED"), ("a bronze mirror was found", "SUPPORTED")],
            [("a ridge fort", "SUPPORTED"), ("a bronze mirror was found", "CONTRADICTED")],
        )
        assert (result.covered, result.agreed) == (2, 1) and result.agreement == 0.5

    def test_unrelated_wording_does_not_cover(self) -> None:
        result = covered(
            [("built by the Inca", "SUPPORTED")], [("lived in from 3180 BC", "SUPPORTED")]
        )
        assert result.covered == 0

    def test_counts_add_up_over_cases(self) -> None:
        total = K.ClaimCoverage(2, 1, 1) + K.ClaimCoverage(3, 3, 2)
        assert (total.recorded, total.covered, total.agreed) == (5, 4, 3)
        assert total.to_dict()["claim_coverage"] == 0.8


# ------------------------------------------------------------------------------ the cache map
class TestTheCacheMap:
    def test_each_web_batch_gets_a_map_from_its_opaque_labels_to_the_cached_pages(
        self,
        tmp_path: Path,
        wiki_cache: Path,  # noqa: F811
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-ver"
        exported = K.export_role(run_dir, "card_web_verifier", handoff)
        jobs = {j["key"]: j for j in K.sealed_jobs(run_dir)}
        for batch, count in exported["batches"].items():
            lines = [
                json.loads(raw)
                for raw in (handoff / batch / K.WIKI_MAP).read_text("utf-8").splitlines()
            ]
            assert len(lines) == count
            assert {line["label"] for line in lines} == {k["label"] for k in OH.manifest(handoff)
                                                          if k["batch_id"] == batch}  # fmt: skip
            for line in lines:
                assert set(line) == {"label", "pages"}
                site = jobs[line["label"]]["site_id"]
                cached = [
                    r for r in (wiki_cache / "INDEX.jsonl").read_text("utf-8").splitlines()
                    if site in r
                ]  # fmt: skip
                assert len(line["pages"]) == len(cached)
                for page in line["pages"]:
                    assert set(page) == {"lang", "title", "file"}
                    assert (wiki_cache / page["file"]).is_file()
                    assert chr(92) not in page["file"]  # the agent's shell reads forward slashes

    def test_a_site_without_a_cached_page_has_a_line_with_no_pages(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-ver"
        K.export_role(run_dir, "card_web_verifier", handoff)
        lines = [
            json.loads(raw)
            for batch in K._handoffs(run_dir)["card_web_verifier"]["batches"]
            for raw in (handoff / batch / K.WIKI_MAP).read_text("utf-8").splitlines()
        ]
        assert any(line["pages"] == [] for line in lines)  # the recorded sites 4-8 have none
        assert any(len(line["pages"]) == 2 for line in lines)  # site 1: en and fr

    def test_the_map_names_no_site_no_set_and_no_number(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-ver"
        K.export_role(run_dir, "card_web_verifier", handoff)
        text = "".join(
            (handoff / batch / K.WIKI_MAP).read_text("utf-8")
            for batch in K._handoffs(run_dir)["card_web_verifier"]["batches"]
        )
        jobs = K.sealed_jobs(run_dir)
        assert not any(j["site_id"] in text for j in jobs)
        assert not any(name in text for name in K.SET_ROLE)
        for line in text.splitlines():
            assert json.loads(line)["label"] and UUID4

    def test_a_role_without_web_gets_no_map(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-checker"
        exported = K.export_role(run_dir, "card_fact_checker", handoff)
        assert not any((handoff / batch / K.WIKI_MAP).exists() for batch in exported["batches"])

    def test_a_web_role_cannot_be_exported_without_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        monkeypatch.setattr(K.R, "WIKI_CACHE", str(tmp_path / "no-cache"))
        with pytest.raises(Exception, match="INDEX.jsonl does not exist"):
            K.export_role(run_dir, "card_web_verifier", tmp_path / "h-ver")

    def test_the_brief_points_at_the_map_of_its_own_batch(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-ver"
        K.export_role(run_dir, "card_web_verifier", handoff)
        job = K.agent_jobs(run_dir, "card_web_verifier")[0]
        assert f"{K._shown(handoff)}/{job['batch_id']}/WIKI_MAP.jsonl" in job["brief"]
        assert "opaque" in job["brief"]


# ------------------------------------------------------------------------------ the floor
def run_with_claims(tmp_path: Path, count: int) -> Path:
    """A calibration whose recorded checks list `count` claims each (the floor of a verifier)."""
    claims = [{"claim": f"claim {n}", "support": ["S1"]} for n in range(count)]
    run = recorded_run(tmp_path, claims=claims)
    run_dir = sealed_dir(tmp_path)
    jobs = K.build_jobs(
        K.sealed(run_dir)[0], runs=[run], export=export_file(tmp_path), base_cards=base_cards()
    )
    K.fix_jobs(run_dir, jobs)
    return run_dir


def judge_text(claims: int) -> str:
    return json.dumps(
        {
            "claims": [
                {
                    "claim": f"a claim {n}",
                    "verdict": "SUPPORTED",
                    "url": PAGE,
                    "quote": QUOTE,
                }
                for n in range(claims)
            ]
        }
    )


class TestTheClaimsFloor:
    def test_a_verifier_case_carries_the_number_of_claims_the_accepting_check_listed(
        self, tmp_path: Path
    ) -> None:
        run_dir = run_with_claims(tmp_path, 3)
        floors = {j["floor"] for j in K.sealed_jobs(run_dir) if j["prompt_kind"] == "judge_v1"}
        assert floors == {3}

    def test_check_answer_names_the_floor_of_a_short_answer(self, tmp_path: Path) -> None:
        run_dir = run_with_claims(tmp_path, 3)
        K.export_role(run_dir, "card_web_verifier", tmp_path / "h-ver")
        job = next(j for j in K.sealed_jobs(run_dir) if j["role"] == "card_web_verifier")
        batch = next(
            b for b, keys in K._handoffs(run_dir)["card_web_verifier"]["batches"].items()
            if job["key"] in keys
        )  # fmt: skip
        short = K.check_answer(run_dir, batch, job["key"], judge_text(2))
        assert short["ok"] is False and (short["floor"], short["listed"]) == (3, 2)
        assert "lists 2 claim(s); the card makes at least 3" in short["problems"][0]
        enough = K.check_answer(run_dir, batch, job["key"], judge_text(3))
        assert enough["ok"] is True and enough["problems"] == []

    def test_evaluate_holds_a_recorded_answer_to_the_floor_as_the_import_does(
        self, tmp_path: Path
    ) -> None:
        run_dir = run_with_claims(tmp_path, 3)
        answer_role(
            run_dir,
            "card_web_verifier",
            {"verifier_contradicted": lambda job: judge_text(2),
             "verifier_verified": lambda job: judge_text(3)},
        )  # fmt: skip
        with pytest.raises(K.CalibrationError, match="malformed answer.*at least 3"):
            K.evaluate(run_dir, "card_web_verifier", client=judge_client())

    def test_a_short_answer_passes_no_floor_it_was_not_given(self) -> None:
        job = {"prompt_kind": "judge_v1", "floor": 1}
        assert len(K.parse_case(job, judge_text(1))) == 1
        with pytest.raises(A.AnswerError, match="lists 1 claim"):
            K.parse_case({**job, "floor": 2}, judge_text(1))


# ------------------------------------------------------------------------------ disputed gold
def disputed_table(site_ids: list[str]) -> dict[str, Any]:
    table = json.loads(json.dumps(TINY))
    rule = table["roles"]["card_web_verifier"]["sets"]["verifier_contradicted"]
    rule.update(cases=2, caught_min=2, disputed={sid: f"why {sid[-2:]}" for sid in site_ids})
    return table


def verified_text(job: dict[str, Any]) -> str:
    return json.dumps(
        {
            "claims": [
                {"claim": c["claim"], "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE}
                for c in job["recorded"]["claims"]
            ]
        }
    )


def miss_all(job: dict[str, Any]) -> str:
    return json.dumps(
        {
            "claims": [
                {
                    "claim": "lived in from roughly 3180 BC",
                    "verdict": "SUPPORTED",
                    "url": PAGE,
                    "quote": QUOTE,
                }
            ]
        }  # fmt: skip
    )


class TestDisputedGold:
    def test_the_real_table_marks_the_five_disputed_contradictions(self) -> None:
        reasons = K.DISPUTED_CONTRADICTIONS
        assert len(reasons) == 5 and all(len(why) > 20 for why in reasons.values())
        names = " ".join(reasons.values())
        for name in ("Undavalli", "Viera", "Lot's Cave", "Mormont", "Beacon Hill"):
            assert name in names

    def test_the_real_table_is_keyed_by_the_site_ids_of_the_contradicted_set(self) -> None:
        """The first table was keyed by case labels and excluded nothing in a real evaluation."""
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "teaser_calibration_contradicted_sites.json")
            .read_text(encoding="utf-8")
        )  # fmt: skip
        drawn = {c["site_id"]: c["name"] for c in fixture["cases"]}
        assert len(drawn) == 20
        assert set(K.DISPUTED_CONTRADICTIONS) <= set(drawn)
        for site_id, why in K.DISPUTED_CONTRADICTIONS.items():
            assert drawn[site_id].split(",")[0] in why

    def test_a_disputed_entry_that_is_no_site_of_the_contradicted_set_is_refused(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path, disputed_table(["00000000-0000-4000-8000-000000000000"]))
        answer_role(
            run_dir, "card_web_verifier",
            {"verifier_contradicted": miss_all, "verifier_verified": verified_text},
        )  # fmt: skip
        with pytest.raises(K.CalibrationError, match="no site id of the contradicted set"):
            K.evaluate(run_dir, "card_web_verifier", client=judge_client())

    def test_a_disputed_contradiction_the_verifier_missed_leaves_the_denominator(
        self, tmp_path: Path
    ) -> None:
        sites = sorted({j["site_id"] for j in K.build_jobs(
            K.sealed(sealed_dir(tmp_path / "x"))[0], runs=[recorded_run(tmp_path)],
            export=export_file(tmp_path), base_cards=base_cards())
            if j["set"] == "verifier_contradicted"})  # fmt: skip
        assert len(sites) == 2
        table = disputed_table(sites[:1])
        run_dir = fixed_dir(tmp_path / "y", table)
        by_site = {j["site_id"]: j for j in jobs_of(run_dir, "verifier_contradicted")}

        # catches only the not-disputed contradiction
        def contradicted(job: dict[str, Any]) -> str:
            if job["site_id"] == sites[0]:
                return miss_all(job)
            return json.dumps({"claims": [
                {"claim": "lived in from roughly 3180 BC", "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE},
                {"claim": "built by the Inca", "verdict": "CONTRADICTED", "url": PAGE, "quote": QUOTE},
            ]})  # fmt: skip

        answer_role(
            run_dir, "card_web_verifier",
            {"verifier_contradicted": contradicted, "verifier_verified": verified_text},
        )  # fmt: skip
        result = K.evaluate(run_dir, "card_web_verifier", client=judge_client())["sets"][
            "verifier_contradicted"
        ]
        assert (result["cases"], result["counted"], result["caught"]) == (2, 1, 1)
        assert result["caught_required"] == 1 and result["passed"] is True
        # kept in the report, with the reason and what the verifier made of it
        [(key, entry)] = result["disputed"].items()
        assert by_site[sites[0]]["key"] == key
        assert entry["reason"].startswith("why ") and entry["fresh_verdict"] == "VERIFIED"
        assert result["missed"] == []

    def test_an_undisputed_miss_still_fails_the_role(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path, disputed_table([]))
        answer_role(
            run_dir, "card_web_verifier",
            {"verifier_contradicted": miss_all, "verifier_verified": verified_text},
        )  # fmt: skip
        result = K.evaluate(run_dir, "card_web_verifier", client=judge_client())["sets"][
            "verifier_contradicted"
        ]
        assert result["passed"] is False and len(result["missed"]) == 2
        assert result["disputed"] == {}

    def test_the_minimum_scales_with_the_cases_that_count(self) -> None:
        # 18 of 20 sealed; 15 count after the five disputed: ceil(18 * 15 / 20) = 14
        import math

        assert math.ceil(18 * 15 / 20) == 14


# ------------------------------------------------------------------------------ the sources
def text_verified(quote: str):
    def make(job: dict[str, Any]) -> str:
        return json.dumps(
            {
                "claims": [
                    {"claim": c["claim"], "verdict": "SUPPORTED", "url": PAGE, "quote": quote}
                    for c in job["recorded"]["claims"]
                ]
            }
        )

    return make


def contradicted_ok(job: dict[str, Any]) -> str:
    return json.dumps({"claims": [
        {"claim": "lived in from roughly 3180 BC", "verdict": "SUPPORTED", "url": PAGE, "quote": QUOTE},
        {"claim": "built by the Inca", "verdict": "CONTRADICTED", "url": PAGE, "quote": QUOTE},
    ]})  # fmt: skip


class _Page:
    def __init__(self, text: str) -> None:
        self.texts = (("reading", text),)


class _Library:
    def __init__(self, text: str) -> None:
        self.page = _Page(text)

    def url(self, url: str) -> _Page:
        return self.page


class TestALoosenedNumberIsFabricated:
    @staticmethod
    def standing(quote: str, page: str) -> str | None:
        claim = {"quote": quote, "url": PAGE, "quote_outcome": K.Q.NOT_FOUND}
        return K.quote_standing(claim, _Library(page))  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("quote", "page"),
        [
            ("the cave is 3.5 m deep", "The cave is 35 m deep."),
            ("dated 10-15 BC", "It is dated 1015 BC."),
            ("1,000 men", "about 1000 men"),
            ("rebuilt in [1854]", "The temple was rebuilt in 1923 by the bishop."),
        ],
    )
    def test_a_changed_number_is_not_the_machines_miss(self, quote: str, page: str) -> None:
        assert self.standing(quote, page) == K.FABRICATED

    @pytest.mark.parametrize(
        ("quote", "page"),
        [
            ("The cave is 3.5 m deep", "the cave is 3.5 m deep"),
            ("dated 10–15 BC", "It is dated 10-15 BC."),
            ("dated 10 - 15 BC", "It is dated 10–15 BC."),
            ("“the Inca” built it", 'The "Inca" built it'),
            ("café at 3.5 km", "Cafe at 3.5 km"),
        ],
    )
    def test_typography_alone_is_the_machines_miss(self, quote: str, page: str) -> None:
        assert self.standing(quote, page) == K.MACHINE_MISS


class TestTheQuoteStanding:
    def evaluate(self, tmp_path: Path, quote: str) -> dict[str, Any]:
        run_dir = fixed_dir(tmp_path)
        answer_role(
            run_dir,
            "card_web_verifier",
            {"verifier_contradicted": contradicted_ok, "verifier_verified": text_verified(quote)},
        )
        return K.evaluate(run_dir, "card_web_verifier", client=judge_client())["sets"][
            "verifier_verified"
        ]

    def test_a_quote_that_differs_from_the_page_in_typography_is_not_found_by_machine(
        self, tmp_path: Path
    ) -> None:
        # case is compared as it is by the strict check; the page holds the words
        result = self.evaluate(tmp_path, "Occupied from roughly 3180 BC to around 2500 BC")
        assert result["false_sources"] == []
        assert len(result["not_found_by_machine"]) >= 2
        assert result["passed"] is True

    def test_a_quote_the_page_never_says_is_fabricated(self, tmp_path: Path) -> None:
        result = self.evaluate(tmp_path, "a sentence that the page never says at all")
        assert len(result["false_sources"]) >= 2 and result["not_found_by_machine"] == []
        assert result["passed"] is False

    def test_a_quote_found_is_neither(self, tmp_path: Path) -> None:
        result = self.evaluate(tmp_path, QUOTE)
        assert result["false_sources"] == [] and result["not_found_by_machine"] == []

    def test_a_page_that_could_not_be_read_is_unreadable_not_fabricated(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)

        def missing(job: dict[str, Any]) -> str:
            return text_verified(QUOTE)(job).replace(PAGE, "https://example.org/gone")

        answer_role(
            run_dir, "card_web_verifier",
            {"verifier_contradicted": contradicted_ok, "verifier_verified": missing},
        )  # fmt: skip
        result = K.evaluate(run_dir, "card_web_verifier", client=judge_client())["sets"][
            "verifier_verified"
        ]
        assert result["false_sources"] == [] and result["unreadable_pages"]

    def test_the_card_level_verdict_is_reported_beside_the_claims(self, tmp_path: Path) -> None:
        result = self.evaluate(tmp_path, QUOTE)
        assert result["card_verdict_agreement"] == 1.0
        assert result["claim_coverage"] == 1.0 and result["claim_agreement"] == 1.0
        assert result["claims_recorded"] == result["claims_covered"] > 0


# ------------------------------------------------------------------------------ check-answer
class TestCheckAnswer:
    def exported(self, tmp_path: Path, role: str) -> tuple[Path, dict[str, str]]:
        run_dir = fixed_dir(tmp_path)
        K.export_role(run_dir, role, tmp_path / f"h-{role}")
        batch_of = {
            key: batch
            for batch, keys in K._handoffs(run_dir)[role]["batches"].items()
            for key in keys
        }
        return run_dir, batch_of

    def test_an_answer_in_the_old_five_field_schema_is_refused_for_a_shorts_case(
        self, tmp_path: Path
    ) -> None:
        """The seven card_fact_checker answers of teaser-2026-10-09 were recorded in v1's 5-field shape
        for shorts-v1 questions; the recorder never read them."""
        run_dir, batch_of = self.exported(tmp_path, "card_fact_checker")
        case = next(
            j for j in K.sealed_jobs(run_dir)
            if j["role"] == "card_fact_checker" and j["prompt_kind"] == "checker_shorts"
        )  # fmt: skip
        old = T.checker_answer("PASS", [("a ridge fort", ["S1"])])
        result = K.check_answer(run_dir, batch_of[case["key"]], case["key"], old)
        assert result["ok"] is False and result["problems"]
        new = K.check_answer(run_dir, batch_of[case["key"]], case["key"], check_json("PASS"))
        assert new["ok"] is True and new["verdict"] == "PASS"

    def test_a_v1_case_is_read_as_a_v1_check(self, tmp_path: Path) -> None:
        run_dir, batch_of = self.exported(tmp_path, "card_fact_checker")
        case = next(
            j for j in K.sealed_jobs(run_dir)
            if j["role"] == "card_fact_checker" and j["prompt_kind"] == "checker_v1"
        )  # fmt: skip
        assert K.check_answer(
            run_dir, batch_of[case["key"]], case["key"], T.checker_answer("PASS")
        )["ok"]
        bad = K.check_answer(run_dir, batch_of[case["key"]], case["key"], "not json at all")
        assert bad["ok"] is False and bad["problems"]

    def test_a_hook_rating_is_read_as_the_evaluation_reads_it(self, tmp_path: Path) -> None:
        run_dir, batch_of = self.exported(tmp_path, "hook_rater")
        case = jobs_of(run_dir, "hook_pairs")[0]
        good = json.dumps({"ratings": [{"number": 1, "hook": 7, "reason": "a clear opening"}],
                           "best": 1})  # fmt: skip
        key, batch = case["key"], batch_of[case["key"]]
        assert K.check_answer(run_dir, batch, key, "{}")["ok"] is False
        assert isinstance(K.check_answer(run_dir, batch, key, good)["ok"], bool)

    def test_a_question_of_no_batch_is_refused(self, tmp_path: Path) -> None:
        run_dir, batch_of = self.exported(tmp_path, "card_fact_checker")
        key = next(iter(batch_of))
        with pytest.raises(K.CalibrationError, match="is no question"):
            K.check_answer(run_dir, "fact-checker-999", key, "{}")

    def test_the_check_and_the_evaluation_read_one_parser(self) -> None:
        """Mutation case: both go through `parse_case`."""
        source = (REPO / "scripts/remediation/teaser/calibrate.py").read_text(encoding="utf-8")
        assert source.count("parse_case(") >= 4
        assert "A.parse_judge(answer.text)" not in source
        assert "AS.parse_rater(answer.text" not in source

    def test_the_command_prints_json_and_exits_one_for_an_answer_that_is_not_ok(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_dir, batch_of = self.exported(tmp_path, "card_fact_checker")
        case = next(
            j for j in K.sealed_jobs(run_dir)
            if j["role"] == "card_fact_checker" and j["prompt_kind"] == "checker_v1"
        )  # fmt: skip
        file = tmp_path / "a.json"
        file.write_text(T.checker_answer("PASS"), encoding="utf-8")
        args = ["check-answer", "--run-dir", str(run_dir), "--batch-id", batch_of[case["key"]],
                "--label", case["key"], "--text-file", str(file)]  # fmt: skip
        assert K.main(args) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True
        file.write_text("{}", encoding="utf-8")
        assert K.main(args) == 1
        assert json.loads(capsys.readouterr().out)["ok"] is False

    def test_the_brief_has_the_check_step_before_the_record_step(self, tmp_path: Path) -> None:
        run_dir = fixed_dir(tmp_path)
        K.export_role(run_dir, "card_fact_checker", tmp_path / "h-checker")
        brief = K.agent_jobs(run_dir, "card_fact_checker")[0]["brief"]
        check = brief.index("calibrate.py check-answer")
        record = brief.index("opus_handoff.py answer")
        assert check < record and '"ok": true' in brief
        assert (
            '--check "./.venv/Scripts/python.exe scripts/remediation/teaser/calibrate.py' in brief
        )


# ------------------------------------------------------------------------------ the recorder's hook
class TestTheRecorderHook:
    def prepare(self, tmp_path: Path) -> tuple[Path, str, str, str]:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-checker"
        K.export_role(run_dir, "card_fact_checker", handoff)
        line = OH.manifest(handoff)[0]
        return handoff, line["batch_id"], line["label"], line["stage"]

    def record(
        self, handoff: Path, batch: str, label: str, stage: str, file: Path, *extra: str
    ) -> int:
        return OH.main(
            ["answer", "--dir", str(handoff), "--batch-id", batch, "--stage", stage,
             "--label", label, "--answered-by", "agent", "--role", "card_fact_checker",
             "--model", "claude-opus-5-5", "--text-file", str(file), *extra]
        )  # fmt: skip

    def test_a_failing_check_stops_the_record(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handoff, batch, label, stage = self.prepare(tmp_path)
        file = tmp_path / "a.json"
        file.write_text("{}", encoding="utf-8")
        check = f'{Path(sys.executable).as_posix()} -c "import sys; print(open(sys.argv[1]).read()); sys.exit(1)" {file.as_posix()}'
        with pytest.raises(SystemExit):
            self.record(handoff, batch, label, stage, file, "--check", check)
        assert not (handoff / OH.answer_relpath(batch, stage, label)).exists()

    def test_a_passing_check_lets_it_through(self, tmp_path: Path) -> None:
        handoff, batch, label, stage = self.prepare(tmp_path)
        file = tmp_path / "a.json"
        file.write_text("{}", encoding="utf-8")
        check = f'{Path(sys.executable).as_posix()} -c "import sys; sys.exit(0)"'
        assert self.record(handoff, batch, label, stage, file, "--check", check) == 0
        assert (handoff / OH.answer_relpath(batch, stage, label)).is_file()

    def test_without_the_hook_the_record_is_as_before(self, tmp_path: Path) -> None:
        handoff, batch, label, stage = self.prepare(tmp_path)
        file = tmp_path / "a.json"
        file.write_text("{}", encoding="utf-8")
        assert self.record(handoff, batch, label, stage, file) == 0


# ------------------------------------------------------------------------------ void
class TestVoid:
    def answered(self, tmp_path: Path) -> tuple[Path, Path, list[str]]:
        run_dir = fixed_dir(tmp_path)
        handoff = answer_role(
            run_dir,
            "card_fact_checker",
            {s: (lambda j: T.checker_answer("PASS")) for s in
             ("checker_agreement", "checker_fail_again", "checker_defects", "checker_good")},
        )  # fmt: skip
        keys = [line["label"] for line in OH.manifest(handoff)]
        return run_dir, handoff, keys

    def test_the_named_answers_move_aside_and_the_prompts_and_manifest_stay(
        self, tmp_path: Path
    ) -> None:
        run_dir, handoff, keys = self.answered(tmp_path)
        before = {line["label"]: line for line in OH.manifest(handoff)}
        manifest = (handoff / before[keys[0]]["batch_id"] / "MANIFEST.jsonl").read_bytes()
        voided = K.void_answers(run_dir, "card_fact_checker", keys[:2], "old five-field schema")
        assert [v["label"] for v in voided] == keys[:2]
        for key in keys[:2]:
            line = before[key]
            assert not (handoff / line["answer_path"]).exists()
            moved = handoff.parent / f"{handoff.name}-void" / line["answer_path"]
            assert moved.is_file()
            assert (handoff / line["prompt_path"]).is_file()  # the question is still asked
        assert (handoff / before[keys[0]]["batch_id"] / "MANIFEST.jsonl").read_bytes() == manifest
        assert (handoff / before[keys[2]]["answer_path"]).is_file()  # the rest stays

    def test_every_void_is_a_line_of_the_log(self, tmp_path: Path) -> None:
        run_dir, handoff, keys = self.answered(tmp_path)
        K.void_answers(
            run_dir, "card_fact_checker", keys[:2], "old five-field schema", now=lambda: "T"
        )
        lines = [json.loads(x) for x in (run_dir / K.VOID_FILE).read_text("utf-8").splitlines()]
        assert [x["label"] for x in lines] == keys[:2]
        for entry in lines:
            assert (
                entry["role"] == "card_fact_checker" and entry["reason"] == "old five-field schema"
            )
            assert entry["voided_at"] == "T" and len(entry["answer_sha256"]) == 64
            assert entry["answered_by"].startswith("card_fact_checker:cal-")

    def test_the_seal_is_untouched_and_the_question_can_be_answered_again(
        self, tmp_path: Path
    ) -> None:
        run_dir, handoff, keys = self.answered(tmp_path)
        files = [K.THRESHOLDS_FILE, K.SEAL_LOG, K.JOBS_FILE, K.HANDOFFS_FILE]
        before = {f: (run_dir / f).read_bytes() for f in files}
        K.void_answers(run_dir, "card_fact_checker", keys[:1], "again")
        assert {f: (run_dir / f).read_bytes() for f in files} == before
        K.sealed(run_dir)  # still the sealed calibration
        line = next(x for x in OH.manifest(handoff) if x["label"] == keys[0])
        assert OH.write_answer(
            handoff, batch_id=line["batch_id"], stage=K.STAGE, label=keys[0],
            text=T.checker_answer("PASS"), answered_by=RO.answered_by("card_fact_checker", "again"),
            model=OH.ANSWER_MODELS[RO.role("card_fact_checker").model],
        )  # fmt: skip

    def test_an_answer_of_another_role_is_refused(self, tmp_path: Path) -> None:
        run_dir, handoff, keys = self.answered(tmp_path)
        line = next(x for x in OH.manifest(handoff) if x["label"] == keys[0])
        path = handoff / line["answer_path"]
        stored = json.loads(path.read_text("utf-8"))
        stored["answered_by"] = RO.answered_by("card_web_verifier", "intruder")
        path.write_text(json.dumps(stored), encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="not in role card_fact_checker"):
            K.void_answers(run_dir, "card_fact_checker", keys[:2], "no")
        assert (
            path.is_file() and not (handoff.parent / f"{handoff.name}-void").exists()
        )  # nothing moved

    def test_a_question_of_another_role_is_refused(self, tmp_path: Path) -> None:
        run_dir, handoff, keys = self.answered(tmp_path)
        other = next(j["key"] for j in K.sealed_jobs(run_dir) if j["role"] == "card_web_verifier")
        K.export_role(run_dir, "card_web_verifier", tmp_path / "h-ver")
        with pytest.raises(K.CalibrationError, match="is no question of role card_fact_checker"):
            K.void_answers(run_dir, "card_fact_checker", [other], "wrong role")

    def test_a_question_without_an_answer_a_missing_reason_and_a_repeat_are_refused(
        self, tmp_path: Path
    ) -> None:
        run_dir = fixed_dir(tmp_path)
        handoff = tmp_path / "h-checker"
        K.export_role(run_dir, "card_fact_checker", handoff)
        label = OH.manifest(handoff)[0]["label"]
        with pytest.raises(K.CalibrationError, match="no recorded answer"):
            K.void_answers(run_dir, "card_fact_checker", [label], "x")
        run_dir2, handoff2, keys = self.answered(tmp_path / "second")
        with pytest.raises(K.CalibrationError, match="needs its reason"):
            K.void_answers(run_dir2, "card_fact_checker", keys[:1], "  ")
        with pytest.raises(K.CalibrationError, match="once"):
            K.void_answers(run_dir2, "card_fact_checker", [keys[0], keys[0]], "x")

    def test_a_role_never_exported_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(K.CalibrationError, match="was never exported"):
            K.void_answers(fixed_dir(tmp_path), "card_fact_checker", ["k"], "x")

    def test_an_answer_is_voided_once(self, tmp_path: Path) -> None:
        """A question voided, answered again and voided again would overwrite the first void."""
        run_dir, handoff, keys = self.answered(tmp_path)
        K.void_answers(run_dir, "card_fact_checker", keys[:1], "first")
        line = next(x for x in OH.manifest(handoff) if x["label"] == keys[0])
        OH.write_answer(
            handoff, batch_id=line["batch_id"], stage=K.STAGE, label=keys[0],
            text=T.checker_answer("PASS"), answered_by=RO.answered_by("card_fact_checker", "again"),
            model=OH.ANSWER_MODELS[RO.role("card_fact_checker").model],
        )  # fmt: skip
        with pytest.raises(K.CalibrationError, match="is voided once"):
            K.void_answers(run_dir, "card_fact_checker", keys[:1], "second")
        assert (handoff / line["answer_path"]).is_file()  # the new answer stays

    def test_the_command_voids_and_prints_the_log_lines(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_dir, handoff, keys = self.answered(tmp_path)
        code = K.main(["void", "--run-dir", str(run_dir), "--role", "card_fact_checker",
                       "--labels", ",".join(keys[:2]), "--reason", "schema"])  # fmt: skip
        assert code == 0
        assert [x["label"] for x in json.loads(capsys.readouterr().out)] == keys[:2]


# ------------------------------------------------------------------------------ the seal
class TestTheSealCoversTheCodeThatJudges:
    NEEDED = (
        "scripts/remediation/teaser/run.py",
        "scripts/remediation/teaser/calibrate.py",
        "scripts/remediation/opus_audit/quotes.py",
        "scripts/remediation/wc/answers.py",
        "scripts/remediation/quote_check.py",
        "scripts/remediation/web_rules.py",
        "scripts/remediation/phase4/licences.py",  # the rule behind `url_problem`
        "pipeline/utils/card_provenance.py",  # MAX_UNPROVEN_CLAIMS: VERIFIED against UNPROVEN
        "scripts/remediation/image_roles/wiki_cache.py",  # the WIKI_MAP the agents read
    )

    def test_the_modules_hash_the_question_builder_the_judge_and_the_quote_check(self) -> None:
        assert set(self.NEEDED) <= set(K.MODULES)
        assert set(self.NEEDED) <= set(K.module_hashes())

    @pytest.mark.parametrize("name", NEEDED)
    def test_a_change_to_any_of_them_after_the_seal_refuses_the_calibration(
        self, tmp_path: Path, name: str
    ) -> None:
        root = modules_root(tmp_path)
        run_dir = tmp_path / "calibration" / "teaser-mod"
        K.seal(run_dir, thresholds=TINY, root=root)
        target = root / name
        target.write_text(target.read_text("utf-8") + "\n# edited\n", encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="changed after the seal"):
            K.sealed(run_dir, root=root)


# ------------------------------------------------------------------------------ an older seal
class TestAnOlderSeal:
    def test_a_void_serves_a_calibration_whose_modules_moved_after_the_seal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The repair of teaser-2026-10-09 runs from a newer checkout: the seal's modules moved, and
        moving an answer aside reads no prompt and judges nothing."""
        run_dir, handoff, keys = TestVoid().answered(tmp_path)
        monkeypatch.setattr(K, "module_hashes", lambda root=K.ROOT, names=None: dict.fromkeys(names or K.MODULES, "moved"))  # fmt: skip
        with pytest.raises(K.CalibrationError, match="changed after the seal"):
            K.sealed(run_dir)
        assert [
            v["label"] for v in K.void_answers(run_dir, "card_fact_checker", keys[:1], "x")
        ] == keys[:1]

    def test_a_tampered_seal_still_stops_a_void(self, tmp_path: Path) -> None:
        run_dir, handoff, keys = TestVoid().answered(tmp_path)
        path = run_dir / K.THRESHOLDS_FILE
        path.write_text(path.read_text("utf-8").replace('"seed": 7', '"seed": 9'), encoding="utf-8")
        with pytest.raises(K.CalibrationError, match="changed after it was sealed"):
            K.void_answers(run_dir, "card_fact_checker", keys[:1], "x")

    def test_a_seal_made_before_the_new_modules_are_checked_for_the_modules_it_has(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """teaser-2026-10-09 sealed seven modules; the module list has since grown. The seal checks
        what it recorded - a clean refusal when one moved, never a KeyError for one it never had."""
        old = tuple(K.MODULES[:7])
        monkeypatch.setattr(K, "MODULES", old)
        run_dir = sealed_dir(tmp_path)
        monkeypatch.undo()
        assert len(K.MODULES) > 7
        assert set(json.loads((run_dir / K.THRESHOLDS_FILE).read_text("utf-8"))["modules"]) == set(
            old
        )
        assert K.sealed(run_dir)[0]["seed"] == 7


# ------------------------------------------------------------------------------ claims that differ
def flipped_support(job: dict[str, Any]) -> str:
    """The recorded verdict, over the recorded claims worded alike with the support turned over."""
    from tests.remediation.test_teaser_calibrate import checker_text  # noqa: F401

    recorded = job["recorded"]
    if recorded["verdict"] == "PASS":
        return T.checker_answer(
            "PASS", [(c["claim"], c["support"]) for c in recorded["claims"]], []
        )
    return T.checker_answer(
        "FAIL", [(c["claim"], [] if c["support"] else ["S1"]) for c in recorded["claims"]], ["No."]
    )


class TestClaimsThatDifferInVerdict:
    def test_claims_covered_with_the_other_support_fail_the_checker_alone(
        self, tmp_path: Path
    ) -> None:
        from tests.remediation.test_teaser_calibrate import checker_text

        run_dir = fixed_dir(tmp_path)
        answer_role(
            run_dir,
            "card_fact_checker",
            {
                "checker_agreement": flipped_support,
                "checker_fail_again": checker_text("FAIL"),
                "checker_defects": checker_text("FAIL"),
                "checker_good": checker_text("PASS"),
            },
        )
        agreement = K.evaluate(run_dir, "card_fact_checker")["sets"]["checker_agreement"]
        assert agreement["verdict_agreement"] == 1.0 and agreement["false_pass"] == []
        assert agreement["claim_coverage"] == 1.0 and agreement["claim_agreement"] < 0.9
        assert agreement["passed"] is False


# ------------------------------------------------------------------------------ the verifier's gates
class TestTheVerifierMeasureGates:
    def verdict(self, tmp_path: Path, verified) -> dict[str, Any]:
        run_dir = fixed_dir(tmp_path)
        answer_role(
            run_dir,
            "card_web_verifier",
            {"verifier_contradicted": contradicted_ok, "verifier_verified": verified},
        )
        return K.evaluate(run_dir, "card_web_verifier", client=judge_client())["sets"][
            "verifier_verified"
        ]

    def test_a_verifier_that_lists_too_few_claims_covers_too_little(self, tmp_path: Path) -> None:
        def one_claim(job: dict[str, Any]) -> str:
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "lived in from roughly 3180 BC",
                            "verdict": "SUPPORTED",
                            "url": PAGE,
                            "quote": QUOTE,
                        }
                    ]
                }
            )

        result = self.verdict(tmp_path, one_claim)
        assert result["claim_coverage"] < 0.8 and result["claim_agreement"] == 1.0
        assert result["falsely_contradicted"] == [] and result["false_sources"] == []
        assert result["passed"] is False

    def test_covered_claims_with_another_verdict_fail_the_verifier(self, tmp_path: Path) -> None:
        def unverifiable(job: dict[str, Any]) -> str:
            return json.dumps(
                {
                    "claims": [
                        {"claim": c["claim"], "verdict": "UNVERIFIABLE", "url": None, "quote": None}
                        for c in job["recorded"]["claims"]
                    ]
                }
            )

        result = self.verdict(tmp_path, unverifiable)
        assert result["claim_coverage"] == 1.0 and result["claim_agreement"] == 0.0
        assert result["falsely_contradicted"] == [] and result["false_sources"] == []
        assert result["card_verdict_agreement"] == 0.0  # UNPROVEN, not VERIFIED
        assert result["passed"] is False
