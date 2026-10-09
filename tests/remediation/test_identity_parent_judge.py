"""D25: the parent question, its adversarial recheck and the decisions the parent lanes read.

`identity/parent_judge.py` asks one question per parent with its candidate children (a web verifier
gives each PART with a quote, NOT_PART or DUPLICATE), asks every PART again with the first answer in
front of the reader, and builds `PARENT_DECISIONS.jsonl`: one record per child, decided only when both
readers agree and every quote is found on its page.
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
from identity import parent_judge as J  # noqa: E402
from identity import label_rounds as rounds  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_fixtures import (  # noqa: E402
    CALIBRATED,
    entity,
    passed_calibrations,
    site,
)

PARENT = "99999999-0000-4000-8000-000000000001"
KID_A = "aaaaaaaa-0000-4000-8000-000000000002"
KID_B = "bbbbbbbb-0000-4000-8000-000000000003"
KID_C = "cccccccc-0000-4000-8000-000000000004"
URL = "https://en.wikipedia.org/wiki/Pompeii"
TEXT = "The Theatre Area is a part of Pompeii, near the Forum."
NOW = "2026-10-12T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _calibrated(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every role has a sealed, passed calibration under a temporary calibration root."""
    root = tmp_path_factory.mktemp("calibration")
    monkeypatch.setattr(rounds.CC, "CALIBRATION_ROOT", root)
    passed_calibrations(root)


def import_round(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """`J.import_round` with every role calibrated (`TestTheCalibrationGate` calls `J.import_round`)."""
    return J.import_round(*args, calibrations=CALIBRATED, **kwargs)


SONNET = OH.ANSWER_MODELS["claude-sonnet-5-5"]
OPUS = OH.ANSWER_MODELS["claude-opus-5-5"]


def brief_of(row: dict[str, Any], qids: list[str]) -> dict[str, Any]:
    return J._brief(row, qids)


def make_ctx(store: Any = None) -> J.Context:
    shown = [
        site(id=PARENT, name="Pompeii", lat=40.75, lon=14.48, images=20, links=5),
        site(id=KID_A, name="Theatre Area of Pompeii", lat=40.7501, lon=14.4861, images=3, links=5),
        site(id=KID_B, name="Pompeii Amphitheatre", lat=40.7515, lon=14.4955, images=20, links=5),
        site(id=KID_C, name="Pompeii Museum", lat=40.76, lon=14.49, images=2, links=0),
    ]
    rows = {s["id"]: s for s in shown}
    qids = {PARENT: ["Q5586"], KID_A: ["Q23640637"], KID_B: ["Q1128"], KID_C: ["Q9"]}
    candidates = [
        {
            "parent": brief_of(rows[PARENT], qids[PARENT]),
            "parent_is_child": False,
            "children": [
                {
                    **brief_of(rows[k], qids[k]),
                    "metres": m,
                    "shared_qid": False,
                    "competing_parents": [],
                }
                for k, m in ((KID_A, 120.0), (KID_B, 900.0), (KID_C, 1500.0))
            ],
        }
    ]
    questions = J.merge_questions(candidates, [], rows, qids, set())
    return J.Context(
        questions=questions, shown=rows, names={}, qids={k: tuple(v) for k, v in qids.items()},
        wiki=None, store=store, basis="2026-10-08 20:00:00+00",
    )  # fmt: skip


CTX = make_ctx()
QUESTION = CTX.questions[PARENT]


def child(site_id: str, verdict: str = "NOT_PART", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"site_id": site_id, "verdict": verdict, "why": "because", "quotes": []}
    if verdict in ("PART", "DUPLICATE"):
        base["quotes"] = [{"source": URL, "quote": "part of Pompeii"}]
    return {**base, **over}


def answer(children: list[dict[str, Any]], parent_id: str = PARENT) -> str:
    return json.dumps({"parent_id": parent_id, "children": children})


def a_part_answer() -> str:
    return answer([child(KID_A, "PART"), child(KID_B), child(KID_C)])


def library(tmp_path: Path, pages: dict[str, str] | None = None) -> Q.Library:
    store = tmp_path / "pages"
    for url, text in (pages or {URL: TEXT}).items():
        Q.store_page(
            store,
            url,
            status=200,
            final_url=url,
            content_type="text/plain",
            body=text.encode(),
            error="",
            fetched_at="t",
        )
    return Q.Library(REPO, store)


# ---------------------------------------------------------------------------------- questions
class TestTheQuestions:
    def test_a_candidate_becomes_a_child_of_its_parent_question(self) -> None:
        assert list(CTX.questions) == [PARENT]
        assert [c["id"] for c in QUESTION["children"]] == [KID_A, KID_B, KID_C]
        assert QUESTION["parent_is_child"] is False

    def candidates(self) -> list[dict[str, Any]]:
        rows = CTX.shown
        return [{"parent": brief_of(rows[PARENT], ["Q5586"]), "parent_is_child": False,
                 "children": [{**brief_of(rows[KID_A], ["Q1"]), "metres": 10.0, "shared_qid": False, "competing_parents": []}]}]  # fmt: skip

    def test_a_site_a_merge_retires_is_asked_about_neither_way(self) -> None:
        for lost in (PARENT, KID_A):
            assert J.merge_questions(self.candidates(), [], CTX.shown, {}, {lost}) == {}

    def test_a_part_of_verdict_names_a_site_a_merge_retires_or_one_not_shown(self) -> None:
        part = [{"site_id": KID_C, "target": PARENT}]
        assert J.merge_questions([], part, CTX.shown, {}, {KID_C}) == {}
        assert J.merge_questions([], part, CTX.shown, {}, {PARENT}) == {}
        gone = {k: v for k, v in CTX.shown.items() if k != KID_C}
        assert J.merge_questions([], part, gone, {}, set()) == {}
        without_parent = {k: v for k, v in CTX.shown.items() if k != PARENT}
        assert J.merge_questions([], part, without_parent, {}, set()) == {}
        assert list(J.merge_questions([], part, CTX.shown, {}, set())) == [PARENT]

    def test_a_part_of_child_that_names_a_parent_already_is_not_asked(self) -> None:
        part = [{"site_id": KID_C, "target": PARENT}]
        shown = {**CTX.shown, KID_C: {**CTX.shown[KID_C], "parent_site_id": KID_A}}
        assert J.merge_questions([], part, shown, {}, set()) == {}

    def test_a_child_that_names_a_parent_already_is_not_asked(self) -> None:
        shown = {**CTX.shown, KID_A: {**CTX.shown[KID_A], "parent_site_id": PARENT}}
        candidates = self.candidates()
        candidates[0]["children"][0]["parent_site_id"] = PARENT
        assert J.merge_questions(candidates, [], shown, {}, set()) == {}

    def test_a_part_of_verdict_of_the_duplicate_question_adds_its_child(self) -> None:
        part = {"site_id": KID_C, "target": PARENT}
        questions = J.merge_questions(
            self.candidates(), [part], CTX.shown, {PARENT: ["Q1"], KID_C: ["Q1"]}, set()
        )
        kids = {c["id"]: c for c in questions[PARENT]["children"]}
        assert set(kids) == {KID_A, KID_C} and kids[KID_C]["sources"] == ["dup-part-of"]
        assert kids[KID_C]["shared_qid"] is True and kids[KID_C]["metres"] > 0

    def test_a_child_that_two_parents_ask_for_sees_its_competitor(self) -> None:
        other = {**self.candidates()[0], "parent": brief_of(CTX.shown[KID_B], ["Q2"])}
        questions = J.merge_questions([*self.candidates(), other], [], CTX.shown, {}, set())
        assert questions[PARENT]["children"][0]["competing_parents"] == [KID_B]
        assert questions[KID_B]["children"][0]["competing_parents"] == [PARENT]

    def test_a_parent_that_is_a_candidate_child_is_flagged(self) -> None:
        other = {"parent": brief_of(CTX.shown[KID_B], ["Q2"]), "parent_is_child": False,
                 "children": [{**brief_of(CTX.shown[PARENT], ["Q1"]), "metres": 5.0, "shared_qid": False, "competing_parents": []}]}  # fmt: skip
        questions = J.merge_questions([*self.candidates(), other], [], CTX.shown, {}, set())
        assert questions[PARENT]["parent_is_child"] is True


class TestThePrompt:
    def test_it_names_the_parent_the_children_and_their_distances(self) -> None:
        text = J.verdict_prompt(QUESTION, CTX)
        for needle in (
            PARENT,
            "Pompeii",
            KID_A,
            "Theatre Area of Pompeii",
            "120 m from the parent",
            "900 m from the parent",
            "images 3, content links 5",
            "Q5586",
            "Q23640637",
        ):
            assert needle in text, needle

    def test_it_states_the_rules(self) -> None:
        text = J.verdict_prompt(QUESTION, CTX)
        assert "PART - the record is a COMPONENT of the parent" in text
        assert (
            "NOT_PART - a neighbour, a namesake" in text
            and "DUPLICATE - the child and the parent are ONE site" in text
        )
        assert "The shared words in the names are no proof" in text
        assert 'answer NOT_PART: a wrong parent puts a false "part of" line on a page' in text
        assert "403 or 429 is a throttle" in text and "Never cite ancientnerds.com" in text

    def test_a_parent_that_is_itself_a_candidate_component_says_so(self) -> None:
        question = {**QUESTION, "parent_is_child": True}
        assert "itself a candidate component of another record" in J.verdict_prompt(question, CTX)
        assert "itself a candidate component" not in J.verdict_prompt(QUESTION, CTX)

    def test_a_competing_parent_is_named_beside_the_child(self) -> None:
        kids = [
            {**QUESTION["children"][0], "competing_parents": [KID_B]},
            *QUESTION["children"][1:],
        ]
        text = J.verdict_prompt({**QUESTION, "children": kids}, CTX)
        assert f"also a candidate of Pompeii Amphitheatre ({KID_B})" in text or f"({KID_B})" in text

    def test_a_reask_carries_why(self) -> None:
        assert "NOT COUNTED\n  a quote does not count" in J.verdict_prompt(
            QUESTION, CTX, "a quote does not count"
        )

    def test_the_recheck_shows_the_relations_with_the_outcome_of_each_quote(
        self, tmp_path: Path
    ) -> None:
        decision = J.decide_verdict(
            QUESTION,
            J.parse_verdict(a_part_answer(), QUESTION),
            CTX,
            round_name="r1",
            answered_by="x",
            library=library(tmp_path),
        )
        text = J.recheck_prompt(QUESTION, CTX, decision)
        assert f"PART: Theatre Area of Pompeii ({KID_A}) is part of Pompeii ({PARENT})" in text
        assert (
            "quote [found" in text
            and "try to REFUTE" in text
            and KID_B not in text.partition("THE RELATIONS")[2]
        )


# ------------------------------------------------------------------------------------ answers
class TestTheShape:
    def test_a_part_with_its_quote_parses(self) -> None:
        children = J.parse_verdict(a_part_answer(), QUESTION)
        assert children[KID_A].verdict == "PART" and children[KID_B].verdict == "NOT_PART"

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("nope", "not JSON"),
            (json.dumps({"parent_id": PARENT}), "the answer carries"),
            (json.dumps({"parent_id": KID_A, "children": []}), "is not this question's"),
            (json.dumps({"parent_id": PARENT, "children": "x"}), "children is not a list"),
            (answer([child(KID_A), child(KID_B)]), "missing"),
            (answer([child(KID_A), child(KID_A), child(KID_B), child(KID_C)]), "answered twice"),
            (answer([child("zzz"), child(KID_B), child(KID_C)]), "no candidate child"),
            (answer([{"site_id": KID_A}, child(KID_B), child(KID_C)]), "exactly"),
            (answer([child(KID_A, verdict="MAYBE"), child(KID_B), child(KID_C)]), "is not one of"),
            (answer([child(KID_A, why=""), child(KID_B), child(KID_C)]), "why is empty"),
            (
                answer([child(KID_A, "PART", quotes=[]), child(KID_B), child(KID_C)]),
                "needs at least one quote",
            ),
            (
                answer([child(KID_A, "DUPLICATE", quotes=[]), child(KID_B), child(KID_C)]),
                "needs at least one quote",
            ),
            (
                answer(
                    [
                        child(KID_A, "PART", quotes=[{"source": "x", "quote": "y"}]),
                        child(KID_B),
                        child(KID_C),
                    ]
                ),
                "must be the URL",
            ),
        ],
    )
    def test_each_shape_error_is_named(self, text: str, message: str) -> None:
        with pytest.raises(J.AnswerError, match=message):
            J.parse_verdict(text, QUESTION)

    def test_a_not_part_needs_no_quote(self) -> None:
        J.parse_verdict(answer([child(KID_A), child(KID_B), child(KID_C)]), QUESTION)

    ASKED = {KID_A: {"site_id": KID_A}}

    def test_the_recheck_confirms_or_rejects_each_relation(self) -> None:
        rows = [
            {
                "site_id": KID_A,
                "decision": "CONFIRM",
                "why": "w",
                "quotes": [{"source": URL, "quote": "q"}],
            }
        ]
        assert J.parse_recheck(answer(rows), QUESTION, self.ASKED)[KID_A].decision == "CONFIRM"
        rows[0]["decision"] = "REJECT"
        assert J.parse_recheck(answer(rows), QUESTION, self.ASKED)[KID_A].decision == "REJECT"

    @pytest.mark.parametrize(
        ("rows", "message"),
        [
            ([], "missing"),
            (
                [{"site_id": KID_B, "decision": "CONFIRM", "why": "w", "quotes": []}],
                "no relation this recheck asks",
            ),
            (
                [{"site_id": KID_A, "decision": "RETARGET", "why": "w", "quotes": []}],
                "not CONFIRM or REJECT",
            ),
            (
                [
                    {
                        "site_id": KID_A,
                        "decision": "CONFIRM",
                        "why": "",
                        "quotes": [{"source": URL, "quote": "q"}],
                    }
                ],
                "why is empty",
            ),
            (
                [{"site_id": KID_A, "decision": "CONFIRM", "why": "w", "quotes": []}],
                "needs at least one quote",
            ),
            ([{"site_id": KID_A}], "exactly"),
        ],
    )
    def test_each_recheck_shape_error_is_named(
        self, rows: list[dict[str, Any]], message: str
    ) -> None:
        with pytest.raises(J.AnswerError, match=message):
            J.parse_recheck(answer(rows), QUESTION, self.ASKED)

    def test_a_relation_answered_twice_is_refused(self) -> None:
        row = {
            "site_id": KID_A,
            "decision": "CONFIRM",
            "why": "w",
            "quotes": [{"source": URL, "quote": "q"}],
        }
        with pytest.raises(J.AnswerError, match="answered twice"):
            J.parse_recheck(answer([row, row]), QUESTION, self.ASKED)


# ------------------------------------------------------------------------------------ machine
class TestTheMachineChecks:
    def decide(
        self,
        tmp_path: Path,
        text: str | None = None,
        pages: dict[str, str] | None = None,
        ctx: J.Context | None = None,
    ):
        return J.decide_verdict(QUESTION, J.parse_verdict(text or a_part_answer(), QUESTION), ctx or CTX, round_name="r1", answered_by="web_verifier:b1", library=library(tmp_path, pages))  # fmt: skip

    def test_a_part_whose_quote_is_found_is_decided_with_its_distance(self, tmp_path: Path) -> None:
        decision = self.decide(tmp_path)
        assert (
            decision["status"] == J.DECIDED and decision["label"] == PARENT == decision["parent_id"]
        )
        part = next(m for m in decision["members"] if m["verdict"] == "PART")
        assert part["metres"] == 120.0 and part["status"] == J.DECIDED and part["p361"] is False

    def test_a_quote_that_is_not_on_the_page_holds_the_parent(self, tmp_path: Path) -> None:
        decision = self.decide(tmp_path, pages={URL: "something else"})
        assert decision["status"] == J.HELD and "a quote does not count" in decision["reason"]

    def test_the_wikidata_part_of_statement_is_evidence_on_top_of_the_quote(
        self, tmp_path: Path
    ) -> None:
        class Store:
            def get(self, qid: str):
                if qid == "Q23640637":
                    return (
                        {
                            "id": qid,
                            "claims": {
                                "P361": [
                                    {
                                        "mainsnak": {
                                            "snaktype": "value",
                                            "datavalue": {"value": {"id": "Q5586"}},
                                        },
                                        "rank": "normal",
                                    }
                                ]
                            },
                        },
                        "harvest",
                    )
                return None, None

        decision = self.decide(tmp_path, ctx=make_ctx(Store()))
        part = next(m for m in decision["members"] if m["verdict"] == "PART")
        assert part["p361"] is True
        assert next(m for m in decision["members"] if m["site_id"] == KID_B)["p361"] is False

    def test_a_missing_item_is_no_proof(self) -> None:
        class Store:
            def get(self, qid: str):
                return None, None

        assert J.p361_proved(make_ctx(Store()), KID_A, PARENT) is False
        assert J.p361_proved(CTX, KID_A, PARENT) is False

    def test_the_recheck_is_decided_on_its_quotes(self, tmp_path: Path) -> None:
        relations = J.parse_recheck(
            answer(
                [
                    {
                        "site_id": KID_A,
                        "decision": "CONFIRM",
                        "why": "w",
                        "quotes": [{"source": URL, "quote": "part of Pompeii"}],
                    }
                ]
            ),
            QUESTION,
            {KID_A: {"site_id": KID_A}},
        )
        ok = J.decide_recheck(
            QUESTION, relations, round_name="r1", answered_by="x", library=library(tmp_path)
        )
        assert ok["status"] == J.DECIDED and ok["members"][0]["decision"] == "CONFIRM"
        bad = J.decide_recheck(
            QUESTION,
            relations,
            round_name="r1",
            answered_by="x",
            library=library(tmp_path, {URL: "other"}),
        )
        assert bad["status"] == J.HELD


# ----------------------------------------------------------------------------------- decisions
def verdict(
    tmp_path: Path, text: str | None = None, ctx: J.Context | None = None
) -> dict[str, Any]:
    return J.decide_verdict(QUESTION, J.parse_verdict(text or a_part_answer(), QUESTION), ctx or CTX, round_name="r1", answered_by="web_verifier:b1", library=library(tmp_path))  # fmt: skip


def recheck(
    tmp_path: Path, decision: str = "CONFIRM", pages: dict[str, str] | None = None
) -> dict[str, Any]:
    relations = J.parse_recheck(
        answer(
            [
                {
                    "site_id": KID_A,
                    "decision": decision,
                    "why": "rw",
                    "quotes": [{"source": URL, "quote": "part of Pompeii"}],
                }
            ]
        ),
        QUESTION,
        {KID_A: {"site_id": KID_A}},
    )
    return J.decide_recheck(
        QUESTION,
        relations,
        round_name="r1",
        answered_by="adversarial:b1",
        library=library(tmp_path, pages),
    )


class TestTheDecisions:
    def test_a_confirmed_part_is_decided(self, tmp_path: Path) -> None:
        [record] = J.build_decisions(CTX, {PARENT: verdict(tmp_path)}, {PARENT: recheck(tmp_path)})
        assert (record["child"], record["parent"], record["status"], record["reason"]) == (
            KID_A,
            PARENT,
            "decided",
            "",
        )
        assert (
            record["child_name"] == "Theatre Area of Pompeii" and record["parent_name"] == "Pompeii"
        )
        assert (
            record["metres"] == 120.0
            and record["recheck_why"] == "rw"
            and len(record["quotes"]) == 2
        )

    def test_a_part_waits_for_its_recheck(self, tmp_path: Path) -> None:
        [record] = J.build_decisions(CTX, {PARENT: verdict(tmp_path)}, {})
        assert record["status"] == "pending-recheck"

    def test_a_reject_or_a_held_recheck_holds_it(self, tmp_path: Path) -> None:
        [rejected] = J.build_decisions(
            CTX, {PARENT: verdict(tmp_path)}, {PARENT: recheck(tmp_path, "REJECT")}
        )
        assert rejected["status"] == "held" and "the recheck REJECTs (rw)" in rejected["reason"]
        [held] = J.build_decisions(
            CTX, {PARENT: verdict(tmp_path)}, {PARENT: recheck(tmp_path, pages={URL: "other"})}
        )
        assert held["status"] == "held" and "the recheck is held" in held["reason"]

    def test_a_held_verdict_holds_the_part(self, tmp_path: Path) -> None:
        decision = J.decide_verdict(QUESTION, J.parse_verdict(a_part_answer(), QUESTION), CTX, round_name="r1", answered_by="x", library=library(tmp_path, {URL: "nope"}))  # fmt: skip
        [record] = J.build_decisions(CTX, {PARENT: decision}, {})
        assert record["status"] == "held" and "a quote does not count" in record["reason"]

    def test_only_a_part_makes_a_record(self, tmp_path: Path) -> None:
        text = answer([child(KID_A), child(KID_B), child(KID_C, "DUPLICATE")])
        assert J.build_decisions(CTX, {PARENT: verdict(tmp_path, text)}, {}) == []
        assert J.build_decisions(CTX, {}, {}) == []

    def test_a_child_that_two_parents_confirm_is_a_conflict(self, tmp_path: Path) -> None:
        other = "dddddddd-0000-4000-8000-000000000005"
        shown = {**CTX.shown, other: site(id=other, name="Forum of Pompeii")}
        question2 = {
            "parent": brief_of(shown[other], []),
            "parent_is_child": False,
            "children": [QUESTION["children"][0]],
        }
        ctx = J.Context(
            {**CTX.questions, other: question2}, shown, {}, CTX.qids, None, None, CTX.basis
        )
        v1 = verdict(tmp_path)
        v2 = J.decide_verdict(question2, J.parse_verdict(json.dumps({"parent_id": other, "children": [child(KID_A, "PART")]}), question2), ctx, round_name="r1", answered_by="x", library=library(tmp_path))  # fmt: skip
        r1 = recheck(tmp_path)
        r2 = J.decide_recheck(question2, J.parse_recheck(answer([{"site_id": KID_A, "decision": "CONFIRM", "why": "rw", "quotes": [{"source": URL, "quote": "part of Pompeii"}]}], other), question2, {KID_A: {"site_id": KID_A}}), round_name="r1", answered_by="x", library=library(tmp_path))  # fmt: skip
        records = J.build_decisions(ctx, {PARENT: v1, other: v2}, {PARENT: r1, other: r2})
        assert [(r["child"], r["status"]) for r in records] == [(KID_A, "conflict")]
        assert "PART of" in records[0]["reason"]


class TestTheRounds:
    def test_the_whole_flow_runs_through_the_handoff(self, tmp_path: Path) -> None:
        def fetch(urls: list[str], store: Path) -> dict[str, int]:
            for url in urls:
                Q.store_page(
                    store,
                    url,
                    status=200,
                    final_url=url,
                    content_type="text/plain",
                    body=TEXT.encode(),
                    error="",
                    fetched_at="t",
                )
            return {"fetched": len(urls)}

        run = tmp_path / "run"
        record = J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        assert record.labels == [PARENT]
        OH.write_answer(
            tmp_path / "h1",
            batch_id="r1-b01",
            stage=J.STAGE_VERDICT,
            label=PARENT,
            text=a_part_answer(),
            answered_by="web_verifier:b1",
            model=SONNET,
        )
        summary = import_round(run, J.STAGE_VERDICT, "r1", CTX, fetch, now=lambda: NOW)
        assert summary["decided"] == 1
        J.export_rechecks(run, CTX, tmp_path / "h2", now=lambda: NOW)
        rows = [
            {
                "site_id": KID_A,
                "decision": "CONFIRM",
                "why": "rw",
                "quotes": [{"source": URL, "quote": "part of Pompeii"}],
            }
        ]
        OH.write_answer(
            tmp_path / "h2",
            batch_id="r1-b01",
            stage=J.STAGE_RECHECK,
            label=PARENT,
            text=answer(rows),
            answered_by="adversarial:b1",
            model=OPUS,
        )
        assert import_round(run, J.STAGE_RECHECK, "r1", CTX, fetch, now=lambda: NOW)["decided"] == 1
        assert J.write_decisions(run, CTX) == {"children": 1, "decided": 1}
        [written] = [
            json.loads(x)
            for x in (run / J.PARENT_DECISIONS).read_text(encoding="utf-8").splitlines()
        ]
        assert (written["child"], written["parent"], written["status"]) == (
            KID_A,
            PARENT,
            "decided",
        )

    def test_a_web_verifier_may_not_recheck(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        OH.write_answer(
            tmp_path / "h1",
            batch_id="r1-b01",
            stage=J.STAGE_VERDICT,
            label=PARENT,
            text=a_part_answer(),
            answered_by="adversarial:b1",
            model=OPUS,
        )
        with pytest.raises(rounds.RoundError, match="this stage asks web_verifier"):
            import_round(run, J.STAGE_VERDICT, "r1", CTX, lambda urls, store: {}, now=lambda: NOW)

    def test_the_brief_and_the_shape_check(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        text = J.brief(run, J.STAGE_VERDICT, "r1", "r1-b01")
        assert (
            "role web_verifier" in text
            and "parent_judge.py check-answer --stage parent-verdict" in text
        )
        assert "check-answer" not in J.brief(run, J.STAGE_VERDICT, "r1", "r1-b01", check=False)
        assert J.check_answer(run, CTX, J.STAGE_VERDICT, "r1", PARENT, a_part_answer()) is None
        assert "missing" in str(
            J.check_answer(run, CTX, J.STAGE_VERDICT, "r1", PARENT, answer([child(KID_A)]))
        )
        with pytest.raises(rounds.RoundError, match="is no batch"):
            J.brief(run, J.STAGE_VERDICT, "r1", "r1-b09")
        with pytest.raises(rounds.RoundError, match="is no question of"):
            J.check_answer(run, CTX, J.STAGE_VERDICT, "r1", "nope", "{}")

    def test_a_brief_names_a_role_of_its_stage(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="adversarial is no role of parent-verdict"):
            J.brief(run, J.STAGE_VERDICT, "r1", "r1-b01", role="adversarial")
        text = J.brief(
            run, J.STAGE_VERDICT, "r1", "r1-b01", handoff="calibration/copy", check=False
        )
        assert "calibration/copy/r1-b01/MANIFEST.jsonl" in text and "check-answer" not in text

    def test_no_recheck_without_a_decided_part(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        with pytest.raises(rounds.RoundError, match="no parent has a decided PART"):
            J.export_rechecks(run, CTX, tmp_path / "h")


def test_the_entity_helper_of_the_fixtures_is_what_the_harvest_reads() -> None:
    assert entity("Q1", p31=("Q2",))["id"] == "Q1"


class TestTheContext:
    def run_dir(self, tmp_path: Path, *, decisions: bool) -> Path:
        from identity import common

        from tests.remediation.identity_fixtures import export_of

        run = tmp_path / "run"
        run.mkdir()
        shown = [site(id=PARENT, name="Pompeii"), site(id=KID_A, name="Theatre Area of Pompeii")]
        exported = export_of(shown)
        lines = [json.dumps({"kind": "shown", "row": row}) for row in exported.shown]
        lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": exported.exported_at}}))
        (run / common.EXPORT_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        common.write_jsonl(run / "PARENT_CANDIDATES.jsonl", [])
        if decisions:
            common.write_jsonl(run / "DUP_DECISIONS.jsonl", [])
        cache = tmp_path / "output" / "remediation" / "final-2026-10-08" / "wiki_cache"
        cache.mkdir(parents=True)
        (cache / "INDEX.jsonl").write_text("", encoding="utf-8")
        return run

    def test_the_parents_come_after_the_duplicates(self, tmp_path: Path) -> None:
        from identity import common

        run = self.run_dir(tmp_path, decisions=False)
        with pytest.raises(common.IdentityError, match="the parents come after the duplicates"):
            J.load_context(run, root=tmp_path)

    def test_the_context_needs_the_wikipedia_cache(self, tmp_path: Path) -> None:
        from identity import common

        run = self.run_dir(tmp_path, decisions=True)
        ctx = J.load_context(run, root=tmp_path)
        assert ctx.questions == {} and ctx.wiki is not None and set(ctx.shown) == {PARENT, KID_A}
        (
            tmp_path / "output" / "remediation" / "final-2026-10-08" / "wiki_cache" / "INDEX.jsonl"
        ).unlink()
        with pytest.raises(common.IdentityError, match="tools/wiki_cache.py first"):
            J.load_context(run, root=tmp_path)
