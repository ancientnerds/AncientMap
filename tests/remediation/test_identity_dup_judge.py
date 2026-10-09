"""D14: the duplicate question, its adversarial recheck and the decisions the merge lanes read.

`identity/dup_judge.py` asks one question per cluster (a web verifier gives each member DISTINCT,
MERGE, PART_OF or WRONG_ID with quotes), asks it again of every relation with the first answer in
front of the reader (the adversarial recheck), and builds `DUP_DECISIONS.jsonl` from both. The rounds
(`identity/rounds.py`) are the shared part: export, role and model checks, the import. Nothing here
fetches a page or calls a model - the pages are written into the library by hand, the answers into a
handoff directory with `opus_handoff.write_answer`.
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
from identity import common, dup_clusters, rounds  # noqa: E402
from identity import dup_judge as J
from identity.wiki import WikiIndex  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402

A_ID = "aaaaaaaa-0000-4000-8000-000000000001"
B_ID = "bbbbbbbb-0000-4000-8000-000000000002"
C_ID = "cccccccc-0000-4000-8000-000000000003"
TEXT_BANIAS = (
    "Banias, also known as Caesarea Philippi, is an ancient site at the foot of Mount Hermon."
)
URL_BANIAS = "https://en.wikipedia.org/wiki/Banias"
URL_PART = "https://en.wikipedia.org/wiki/Pompeii"
TEXT_PART = "The Theatre Area is a part of Pompeii."
NOW = "2026-10-10T00:00:00+00:00"
SONNET = OH.ANSWER_MODELS["claude-sonnet-5-5"]
OPUS = OH.ANSWER_MODELS["claude-opus-5-5"]


def make_ctx(*, wiki: WikiIndex | None = None) -> J.Context:
    """A cluster of two records that share an item (Banias and Caesarea Philippi) and a third that
    shares it too (a museum)."""
    shown = [
        site(
            id=A_ID,
            name="Banias",
            lat=33.2486,
            lon=35.6944,
            images=20,
            links=4,
            description_lane="L",
            created_at="2026-03-04 21:07:57",
        ),
        site(
            id=B_ID,
            name="Caesarea Philippi",
            lat=33.2472,
            lon=35.6939,
            images=20,
            links=5,
            description_lane="W",
            created_at="2026-03-04 21:07:58",
        ),
        site(
            id=C_ID,
            name="Banias Museum",
            lat=33.2500,
            lon=35.6950,
            images=1,
            links=0,
            description_lane="L",
            created_at="2026-03-04 21:07:59",
        ),
    ]
    exported = export_of(
        shown,
        ext_ids=[ext(s["id"], "wikidata_qid", "Q606295") for s in shown]
        + [ext(A_ID, "enwiki_title", "Banias")],
        names=[{"site_id": B_ID, "name": "Paneas", "name_type": "alias", "language_code": "en"}],
    )
    records, _ = dup_clusters.build(exported, [])
    clusters = {r["cluster_id"]: r for r in records if r["record"] == "cluster"}
    return J.Context(
        clusters=clusters, retired_losers=(), shown=common.rows_by_id(exported.shown),
        names={B_ID: ("Paneas",)}, wiki=wiki, basis=exported.exported_at,
    )  # fmt: skip


CTX = make_ctx()
CLUSTER = next(iter(CTX.clusters.values()))
CID = CLUSTER["cluster_id"]


def member(site_id: str, verdict: str = "DISTINCT", **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": site_id, "verdict": verdict, "survivor": None, "parent": None,
        "why": "because", "quotes": [],
    }  # fmt: skip
    if verdict == "MERGE":
        base |= {
            "survivor": B_ID,
            "quotes": [{"source": URL_BANIAS, "quote": "also known as Caesarea Philippi"}],
        }
    if verdict == "PART_OF":
        base |= {"parent": B_ID, "quotes": [{"source": URL_PART, "quote": "a part of Pompeii"}]}
    if verdict == "WRONG_ID":
        base |= {"quotes": [{"source": URL_BANIAS, "quote": "ancient site at the foot"}]}
    return {**base, **over}


def answer(members: list[dict[str, Any]], cluster_id: str = CID) -> str:
    return json.dumps({"cluster_id": cluster_id, "members": members})


def a_merge_answer() -> str:
    return answer([member(A_ID, "MERGE"), member(B_ID), member(C_ID)])


# ------------------------------------------------------------------------------------- prompts
class TestTheQuestion:
    def test_it_names_every_member_with_the_facts_a_judge_needs(self) -> None:
        text = J.verdict_prompt(CLUSTER, CTX)
        for needle in (
            A_ID,
            B_ID,
            C_ID,
            "Banias",
            "Caesarea Philippi",
            "images 20, content links 4",
            "description lane L",
            "description lane W",
            "Q606295",
            "English names: Paneas",
            f"THE CLUSTER {CID}",
        ):
            assert needle in text, needle
        assert (
            "DISTANCES BETWEEN THE RECORDS" in text
            and "WHY THESE RECORDS ARE ASKED TOGETHER" in text
        )

    def test_it_states_the_owner_s_rules(self) -> None:
        text = J.verdict_prompt(CLUSTER, CTX)
        assert (
            "DISTINCT" in text
            and 'MERGE with "survivor"' in text
            and 'PART_OF with "parent"' in text
            and "WRONG_ID" in text
        )
        assert "do NOT pick the survivor by age or by count alone" in text
        assert "more than 2,000 m apart is held for the owner" in text
        assert "If you cannot PROVE two records are one site with quotes, answer DISTINCT" in text
        assert "403 or 429 is a throttle and never a finding" in text
        assert "never ancientnerds.com" in text

    def test_it_does_not_show_the_owner_case_class(self) -> None:
        cluster = {
            **CLUSTER,
            "edges": [
                *CLUSTER["edges"],
                {"kind": "bcases", "class": "DUP", "metres": 5.0, "sites": [A_ID, B_ID]},
            ],
        }
        text = J.verdict_prompt(cluster, CTX)
        assert "flagged by an earlier owner-case list" in text and "DUP" not in text.replace(
            "DUPLICATE", ""
        )

    def test_a_reask_carries_why_the_earlier_answer_was_held(self) -> None:
        text = J.verdict_prompt(CLUSTER, CTX, "a quote does not count")
        assert (
            "AN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  a quote does not count" in text
        )
        assert "EARLIER ANSWER" not in J.verdict_prompt(CLUSTER, CTX)

    def test_the_prompt_is_a_pure_function_of_its_inputs(self) -> None:
        assert J.verdict_prompt(CLUSTER, CTX) == J.verdict_prompt(CLUSTER, make_ctx())

    def test_the_cached_wikipedia_file_of_a_member_is_named(self, tmp_path: Path) -> None:
        cache = tmp_path / "wiki_cache"
        (cache / "en").mkdir(parents=True)
        page = {
            "lang": "en",
            "title": "Banias",
            "resolved_title": "Banias",
            "fetched_at": "t",
            "text": TEXT_BANIAS,
        }
        (cache / "en" / "abc.json").write_text(json.dumps(page), encoding="utf-8")
        (cache / "INDEX.jsonl").write_text(
            json.dumps({"site_id": A_ID, "lang": "en", "title": "Banias", "file": "en\\abc.json"})
            + "\n",
            encoding="utf-8",
        )
        text = J.verdict_prompt(CLUSTER, make_ctx(wiki=WikiIndex.load(cache)))
        assert "cached Wikipedia (en): https://en.wikipedia.org/wiki/Banias" in text
        assert (cache / "en" / "abc.json").as_posix() in text
        assert "cached Wikipedia: none" in text  # the other two members have no page

    def test_distances_are_listed_for_every_pair(self) -> None:
        assert len(J.metres_between(CLUSTER)) == 3
        assert all(m > 0 for m in J.metres_between(CLUSTER).values())


# ---------------------------------------------------------------------------------- the answer
class TestTheVerdictShape:
    def test_a_merge_with_its_survivor_and_quotes_parses(self) -> None:
        members = J.parse_verdict(a_merge_answer(), CLUSTER)
        assert members[A_ID].verdict == "MERGE" and members[A_ID].survivor == B_ID
        assert members[B_ID].verdict == members[C_ID].verdict == "DISTINCT"

    def test_part_of_and_wrong_id_parse(self) -> None:
        members = J.parse_verdict(
            answer([member(A_ID, "PART_OF"), member(B_ID), member(C_ID, "WRONG_ID")]), CLUSTER
        )
        assert members[A_ID].parent == B_ID and members[C_ID].verdict == "WRONG_ID"

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("not json", "not JSON"),
            (json.dumps([]), "the answer carries list"),
            (json.dumps({"cluster_id": CID}), "the answer carries"),
            (json.dumps({"cluster_id": "dup-x", "members": []}), "is not this question's"),
            (json.dumps({"cluster_id": CID, "members": "x"}), "members is not a list"),
            (answer([member(A_ID), member(B_ID)]), "missing"),
            (answer([member(A_ID), member(A_ID), member(B_ID), member(C_ID)]), "answered twice"),
            (answer([member("zzz"), member(B_ID), member(C_ID)]), "no record of this cluster"),
            (answer([{"site_id": A_ID}, member(B_ID), member(C_ID)]), "exactly"),
            (answer([member(A_ID, verdict="MAYBE"), member(B_ID), member(C_ID)]), "is not one of"),
            (
                answer([member(A_ID, survivor=B_ID), member(B_ID), member(C_ID)]),
                "survivor goes with MERGE",
            ),
            (
                answer([member(A_ID, "MERGE", survivor=None), member(B_ID), member(C_ID)]),
                "survivor goes with MERGE",
            ),
            (
                answer([member(A_ID, "PART_OF", parent=None), member(B_ID), member(C_ID)]),
                "parent goes with PART_OF",
            ),
            (
                answer([member(A_ID, "MERGE", survivor="zzz"), member(B_ID), member(C_ID)]),
                "no record of this cluster",
            ),
            (
                answer([member(A_ID, "MERGE", survivor=A_ID), member(B_ID), member(C_ID)]),
                "not its own survivor",
            ),
            (answer([member(A_ID, why=" "), member(B_ID), member(C_ID)]), "why is empty"),
            (
                answer([member(A_ID, "MERGE", quotes=[]), member(B_ID), member(C_ID)]),
                "needs at least one quote",
            ),
            (
                answer([member(A_ID, "WRONG_ID", quotes=[]), member(B_ID), member(C_ID)]),
                "needs at least one quote",
            ),
            (
                answer([member(A_ID, "MERGE", quotes=["x"]), member(B_ID), member(C_ID)]),
                "not {source, quote}",
            ),
            (
                answer(
                    [
                        member(A_ID, "MERGE", quotes=[{"source": "Wikipedia", "quote": "x"}]),
                        member(B_ID),
                        member(C_ID),
                    ]
                ),
                "must be the URL",
            ),
            (
                answer(
                    [
                        member(
                            A_ID,
                            "MERGE",
                            quotes=[{"source": "https://ancientnerds.com/x", "quote": "x"}],
                        ),
                        member(B_ID),
                        member(C_ID),
                    ]
                ),
                "never fetched here",
            ),
            (
                answer([member(A_ID, "MERGE"), member(B_ID, "MERGE", survivor=C_ID), member(C_ID)]),
                "a chain",
            ),
            (
                answer([member(A_ID, "MERGE"), member(B_ID, "PART_OF", parent=C_ID), member(C_ID)]),
                "a chain",
            ),
        ],
    )
    def test_each_shape_error_is_named(self, text: str, message: str) -> None:
        with pytest.raises(J.AnswerError, match=message):
            J.parse_verdict(text, CLUSTER)

    def test_a_distinct_member_needs_no_quote(self) -> None:
        J.parse_verdict(answer([member(A_ID), member(B_ID), member(C_ID)]), CLUSTER)


class TestTheRecheckShape:
    ASKED = {A_ID: {"site_id": A_ID, "verdict": "MERGE", "survivor": B_ID, "parent": None}}

    def row(self, decision: str = "CONFIRM", **over: Any) -> dict[str, Any]:
        base = {
            "site_id": A_ID,
            "decision": decision,
            "target": B_ID,
            "why": "w",
            "quotes": [{"source": URL_BANIAS, "quote": "also known as"}],
        }
        if decision == "REJECT":
            base["target"] = None
        return {**base, **over}

    def parse(self, rows: list[dict[str, Any]]):
        return J.parse_recheck(answer(rows), CLUSTER, self.ASKED)

    def test_confirm_retarget_and_reject_parse(self) -> None:
        assert self.parse([self.row()])[A_ID].decision == "CONFIRM"
        assert self.parse([self.row("RETARGET", target=C_ID)])[A_ID].target == C_ID
        assert self.parse([self.row("REJECT")])[A_ID].target is None

    @pytest.mark.parametrize(
        ("rows", "message"),
        [
            ([], "missing"),
            ([{"site_id": A_ID}], "exactly"),
            (
                [
                    {
                        "site_id": B_ID,
                        "decision": "CONFIRM",
                        "target": B_ID,
                        "why": "w",
                        "quotes": [],
                    }
                ],
                "no relation this recheck asks",
            ),
            (
                [{"site_id": A_ID, "decision": "MAYBE", "target": None, "why": "w", "quotes": []}],
                "is not one of",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "CONFIRM",
                        "target": None,
                        "why": "w",
                        "quotes": [{"source": URL_BANIAS, "quote": "q"}],
                    }
                ],
                "target goes with CONFIRM",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "REJECT",
                        "target": B_ID,
                        "why": "w",
                        "quotes": [{"source": URL_BANIAS, "quote": "q"}],
                    }
                ],
                "target goes with CONFIRM",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "CONFIRM",
                        "target": C_ID,
                        "why": "w",
                        "quotes": [{"source": URL_BANIAS, "quote": "q"}],
                    }
                ],
                "names the first answer's target",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "RETARGET",
                        "target": B_ID,
                        "why": "w",
                        "quotes": [{"source": URL_BANIAS, "quote": "q"}],
                    }
                ],
                "names another record",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "RETARGET",
                        "target": A_ID,
                        "why": "w",
                        "quotes": [{"source": URL_BANIAS, "quote": "q"}],
                    }
                ],
                "names another record",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "CONFIRM",
                        "target": B_ID,
                        "why": "",
                        "quotes": [{"source": URL_BANIAS, "quote": "q"}],
                    }
                ],
                "why is empty",
            ),
            (
                [
                    {
                        "site_id": A_ID,
                        "decision": "CONFIRM",
                        "target": B_ID,
                        "why": "w",
                        "quotes": [],
                    }
                ],
                "needs at least one quote",
            ),
        ],
    )
    def test_each_shape_error_is_named(self, rows: list[dict[str, Any]], message: str) -> None:
        with pytest.raises(J.AnswerError, match=message):
            self.parse(rows)

    def test_a_relation_answered_twice_is_refused(self) -> None:
        with pytest.raises(J.AnswerError, match="answered twice"):
            self.parse([self.row(), self.row()])


# -------------------------------------------------------------------------------- the machine
def library(tmp_path: Path, pages: dict[str, str]) -> Q.Library:
    store = tmp_path / "pages"
    for url, text in pages.items():
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


PAGES = {URL_BANIAS: TEXT_BANIAS, URL_PART: TEXT_PART}


def decided(
    text: str,
    tmp_path: Path,
    overrides: dict[str, Any] | None = None,
    pages: dict[str, str] | None = None,
) -> dict[str, Any]:
    return J.decide_verdict(
        CLUSTER, J.parse_verdict(text, CLUSTER), round_name="r1", answered_by="web_verifier:b1",
        library=library(tmp_path, pages or PAGES), overrides=overrides or {},
    )  # fmt: skip


class TestTheMachineChecks:
    def test_a_merge_whose_quotes_are_found_and_which_is_near_is_decided(
        self, tmp_path: Path
    ) -> None:
        decision = decided(a_merge_answer(), tmp_path)
        assert (
            decision["status"] == J.DECIDED and decision["label"] == CID == decision["cluster_id"]
        )
        merge = next(m for m in decision["members"] if m["verdict"] == "MERGE")
        assert merge["quote_outcomes"] == ["found: visible text"] or merge["quote_outcomes"][
            0
        ].startswith("found")
        assert (
            merge["metres"] is not None and merge["metres"] < 2000 and merge["status"] == J.DECIDED
        )

    def test_a_quote_that_is_not_on_the_page_holds_the_cluster(self, tmp_path: Path) -> None:
        text = answer(
            [
                member(
                    A_ID,
                    "MERGE",
                    quotes=[{"source": URL_BANIAS, "quote": "a sentence that is not there"}],
                ),
                member(B_ID),
                member(C_ID),
            ]
        )
        decision = decided(text, tmp_path)
        assert (
            decision["status"] == J.HELD
            and "a quote does not count (not found" in decision["reason"]
        )
        assert [m["status"] for m in decision["members"] if m["verdict"] == "MERGE"] == [J.HELD]

    def test_a_page_that_could_not_be_fetched_holds_the_cluster(self, tmp_path: Path) -> None:
        store = tmp_path / "pages"
        Q.store_page(
            store,
            URL_BANIAS,
            status=403,
            final_url=URL_BANIAS,
            content_type="text/html",
            body=b"",
            error="",
            fetched_at="t",
        )
        decision = J.decide_verdict(CLUSTER, J.parse_verdict(a_merge_answer(), CLUSTER), round_name="r1", answered_by="x", library=Q.Library(REPO, store), overrides={})  # fmt: skip
        assert decision["status"] == J.HELD and "fetch failed" in decision["reason"]

    def far_cluster(self) -> dict[str, Any]:
        members = [dict(m) for m in CLUSTER["members"]]
        for m in members:
            if m["id"] == A_ID:
                m["lat"] = 33.2486 + 0.03  # about 3.3 km from the others
        return {**CLUSTER, "members": members}

    def test_a_merge_beyond_two_kilometres_is_held_without_an_override(
        self, tmp_path: Path
    ) -> None:
        decision = J.decide_verdict(self.far_cluster(), J.parse_verdict(a_merge_answer(), CLUSTER), round_name="r1", answered_by="x", library=library(tmp_path, PAGES), overrides={})  # fmt: skip
        assert decision["status"] == J.HELD and "beyond 2000 m" in decision["reason"]

    def test_an_override_with_a_found_quote_and_a_big_enough_limit_decides_it(
        self, tmp_path: Path
    ) -> None:
        override = {
            A_ID: {
                "metres_limit": 4000,
                "evidence": [{"source": URL_BANIAS, "quote": "ancient site at the foot"}],
            }
        }
        decision = J.decide_verdict(self.far_cluster(), J.parse_verdict(a_merge_answer(), CLUSTER), round_name="r1", answered_by="x", library=library(tmp_path, PAGES), overrides=override)  # fmt: skip
        assert decision["status"] == J.DECIDED

    @pytest.mark.parametrize(
        "override",
        [
            {
                "metres_limit": 3000,
                "evidence": [{"source": URL_BANIAS, "quote": "ancient site at the foot"}],
            },
            {"metres_limit": 4000, "evidence": []},
            {
                "metres_limit": 4000,
                "evidence": [{"source": URL_BANIAS, "quote": "not on the page"}],
            },
        ],
    )
    def test_an_override_too_small_without_evidence_or_with_a_false_quote_decides_nothing(
        self, tmp_path: Path, override: dict[str, Any]
    ) -> None:
        decision = J.decide_verdict(self.far_cluster(), J.parse_verdict(a_merge_answer(), CLUSTER), round_name="r1", answered_by="x", library=library(tmp_path, PAGES), overrides={A_ID: override})  # fmt: skip
        assert decision["status"] == J.HELD

    def test_a_distinct_only_answer_is_decided_with_nothing_to_check(self, tmp_path: Path) -> None:
        decision = decided(answer([member(A_ID), member(B_ID), member(C_ID)]), tmp_path)
        assert decision["status"] == J.DECIDED and all(
            m["quote_outcomes"] == [] for m in decision["members"]
        )

    def test_the_recheck_is_decided_on_its_quotes(self, tmp_path: Path) -> None:
        relations = J.parse_recheck(
            answer([{"site_id": A_ID, "decision": "CONFIRM", "target": B_ID, "why": "w", "quotes": [{"source": URL_BANIAS, "quote": "also known as"}]}]),
            CLUSTER, TestTheRecheckShape.ASKED,
        )  # fmt: skip
        ok = J.decide_recheck(
            CLUSTER, relations, round_name="r1", answered_by="x", library=library(tmp_path, PAGES)
        )
        assert ok["status"] == J.DECIDED and ok["members"][0]["decision"] == "CONFIRM"
        bad = J.decide_recheck(
            CLUSTER,
            relations,
            round_name="r1",
            answered_by="x",
            library=library(tmp_path, {URL_BANIAS: "something else"}),
        )
        assert bad["status"] == J.HELD

    def test_a_shape_held_cluster_has_no_members_and_says_why(self) -> None:
        held = rounds.shape_held(CID, "r1", "by", "not JSON")
        assert (
            held["status"] == J.HELD
            and held["members"] == []
            and held["reason"] == "shape: not JSON"
            and held["label"] == CID
        )


# --------------------------------------------------------------------------------- decisions
def verdict_decision(tmp_path: Path, members: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return decided(answer(members or [member(A_ID, "MERGE"), member(B_ID), member(C_ID)]), tmp_path)


def recheck_decision(
    tmp_path: Path, decision: str = "CONFIRM", target: str | None = B_ID, site_id: str = A_ID
) -> dict[str, Any]:
    relations = J.parse_recheck(
        answer([{"site_id": site_id, "decision": decision, "target": target if decision != "REJECT" else None, "why": "rw", "quotes": [{"source": URL_BANIAS, "quote": "also known as"}]}]),
        CLUSTER, {site_id: {"site_id": site_id, "verdict": "MERGE", "survivor": B_ID, "parent": None}},
    )  # fmt: skip
    return J.decide_recheck(
        CLUSTER,
        relations,
        round_name="r1",
        answered_by="adversarial:b1",
        library=library(tmp_path, PAGES),
    )


class TestTheDecisions:
    def build(
        self,
        verdicts: dict[str, Any],
        rechecks: dict[str, Any] | None = None,
        overrides=None,
        losers=(),
    ):
        ctx = J.Context(CTX.clusters, tuple(losers), CTX.shown, CTX.names, None, CTX.basis)
        return J.build_decisions(ctx, verdicts, rechecks or {}, overrides)

    def test_a_confirmed_merge_is_decided_with_both_readers_reasons(self, tmp_path: Path) -> None:
        [record] = self.build({CID: verdict_decision(tmp_path)}, {CID: recheck_decision(tmp_path)})
        assert record["status"] == "complete" and record["held"] == []
        [merge] = record["merges"]
        assert (merge["site_id"], merge["target"], merge["kind"]) == (A_ID, B_ID, "MERGE")
        assert (
            merge["why"] == "because"
            and merge["recheck_why"] == "rw"
            and merge["metres_limit"] == 2000
        )
        assert len(merge["quotes"]) == 2 and set(record["distinct"]) == {B_ID, C_ID}
        assert record["answered_by"] == ["web_verifier:b1", "adversarial:b1"]

    def test_a_merge_waits_for_its_recheck(self, tmp_path: Path) -> None:
        [record] = self.build({CID: verdict_decision(tmp_path)})
        assert record["status"] == "pending-recheck" and record["merges"] == []

    @pytest.mark.parametrize("decision", ["REJECT", "RETARGET"])
    def test_a_reject_or_a_retarget_holds_the_merge(self, tmp_path: Path, decision: str) -> None:
        target = C_ID if decision == "RETARGET" else None
        [record] = self.build(
            {CID: verdict_decision(tmp_path)}, {CID: recheck_decision(tmp_path, decision, target)}
        )
        assert record["status"] == "held" and record["merges"] == []
        assert f"the recheck {decision}s (rw)" in record["held"][0]["reason"]

    def test_a_held_recheck_holds_the_merge(self, tmp_path: Path) -> None:
        relations = J.parse_recheck(
            answer([{"site_id": A_ID, "decision": "CONFIRM", "target": B_ID, "why": "rw", "quotes": [{"source": URL_BANIAS, "quote": "nope"}]}]),
            CLUSTER, TestTheRecheckShape.ASKED,
        )  # fmt: skip
        held = J.decide_recheck(
            CLUSTER, relations, round_name="r1", answered_by="x", library=library(tmp_path, PAGES)
        )
        [record] = self.build({CID: verdict_decision(tmp_path)}, {CID: held})
        assert record["status"] == "held" and "the recheck is held" in record["held"][0]["reason"]

    def test_wrong_id_and_distinct_need_no_recheck(self, tmp_path: Path) -> None:
        decision = verdict_decision(
            tmp_path, [member(A_ID, "WRONG_ID"), member(B_ID), member(C_ID)]
        )
        [record] = self.build({CID: decision})
        assert record["status"] == "complete" and [w["site_id"] for w in record["wrong_id"]] == [
            A_ID
        ]

    def test_a_part_of_goes_to_the_parents(self, tmp_path: Path) -> None:
        decision = verdict_decision(tmp_path, [member(A_ID, "PART_OF"), member(B_ID), member(C_ID)])
        recheck = recheck_decision(tmp_path)
        recheck["members"][0]["target"] = B_ID
        recheck_relations = recheck
        [record] = self.build({CID: decision}, {CID: recheck_relations})
        assert record["status"] == "complete" and record["merges"] == []
        assert [(p["site_id"], p["target"], p["kind"]) for p in record["part_of"]] == [
            (A_ID, B_ID, "PART_OF")
        ]

    def test_a_cluster_without_a_verdict_is_unanswered(self) -> None:
        [record] = self.build({})
        assert record["status"] == "unanswered" and record["merges"] == []

    def test_a_shape_held_cluster_is_held_with_its_reason(self) -> None:
        [record] = self.build({CID: rounds.shape_held(CID, "r1", "by", "not JSON")})
        assert record["status"] == "held" and record["held"][0]["reason"] == "shape: not JSON"

    def test_a_held_member_holds_the_cluster_and_names_why(self, tmp_path: Path) -> None:
        text = answer(
            [
                member(A_ID, "MERGE", quotes=[{"source": URL_BANIAS, "quote": "absent"}]),
                member(B_ID),
                member(C_ID),
            ]
        )
        [record] = self.build({CID: decided(text, tmp_path)})
        assert (
            record["status"] == "held" and "a quote does not count" in record["held"][0]["reason"]
        )

    def test_an_override_widens_the_limit_the_lanes_read(self, tmp_path: Path) -> None:
        decision = verdict_decision(tmp_path)
        decision["members"][0]["metres"] = 2300.0
        [record] = self.build(
            {CID: decision}, {CID: recheck_decision(tmp_path)}, {A_ID: {"metres_limit": 2500}}
        )
        assert record["merges"][0]["metres_limit"] == 2500

    def test_an_already_retired_loser_is_a_move_with_no_model(self) -> None:
        loser = {
            "record": "retired_loser",
            "id": "l1",
            "name": "Old",
            "survivor_id": "s1",
            "survivor_name": "New",
            "images": 3,
            "links": 0,
        }
        records = self.build({}, losers=[loser])
        move = next(r for r in records if r["cluster_id"] == "retired-l1")
        assert move["status"] == "complete" and move["source"] == "retired-loser"
        assert (
            move["merges"][0]["target"],
            move["merges"][0]["already_retired"],
            move["merges"][0]["quotes"],
        ) == ("s1", True, [])

    def test_the_summary_counts_what_the_lanes_will_see(self, tmp_path: Path) -> None:
        records = self.build({CID: verdict_decision(tmp_path)}, {CID: recheck_decision(tmp_path)})
        assert J.decisions_summary(records) == {
            "clusters": 1,
            "status": {"complete": 1},
            "merges": 1,
            "part_of": 0,
            "wrong_id": 0,
            "held_members": 0,
        }


# ------------------------------------------------------------------------------------ the rounds
def fake_fetch(pages: dict[str, str]):
    def fetch(urls: list[str], store: Path) -> dict[str, int]:
        for url in urls:
            Q.store_page(
                store,
                url,
                status=200,
                final_url=url,
                content_type="text/plain",
                body=pages[url].encode(),
                error="",
                fetched_at="t",
            )
        return {"fetched": len(urls)}

    return fetch


def write_answer(
    handoff: Path,
    batch: str,
    stage: str,
    label: str,
    text: str,
    *,
    by: str = "web_verifier:b1",
    model: str = SONNET,
) -> None:
    OH.write_answer(
        handoff, batch_id=batch, stage=stage, label=label, text=text, answered_by=by, model=model
    )


class TestTheRounds:
    def run_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "run"

    def test_round_one_asks_every_cluster_and_is_recorded(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        record = J.export_verdicts(run, CTX, tmp_path / "handoff", now=lambda: NOW)
        assert record.name == "r1" and record.labels == [CID] and list(record.batches) == ["r1-b01"]
        manifest = OH.read_manifest(tmp_path / "handoff", "r1-b01")
        assert [(stage, label) for stage, label in manifest] == [("dup-verdict", CID)]
        prompt = (tmp_path / "handoff" / manifest[("dup-verdict", CID)]["prompt_path"]).read_text(
            encoding="utf-8"
        )
        assert prompt == J.verdict_prompt(CLUSTER, CTX)
        assert rounds.load_rounds(run / J.DUP_DIR, J.STAGE_VERDICT) == [record]

    def test_a_handoff_directory_with_files_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "handoff").mkdir()
        (tmp_path / "handoff" / "x").write_text("x")
        with pytest.raises(rounds.RoundError, match="is not empty"):
            J.export_verdicts(self.run_dir(tmp_path), CTX, tmp_path / "handoff")

    def test_a_second_round_needs_the_first_imported_and_asks_only_the_held(
        self, tmp_path: Path
    ) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="exported but not imported"):
            J.export_verdicts(run, CTX, tmp_path / "h2")
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, "not json")
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        second = J.export_verdicts(run, CTX, tmp_path / "h2", now=lambda: NOW)
        assert (
            second.name == "r2"
            and second.labels == [CID]
            and "shape: not JSON" in second.earlier[CID]
        )
        manifest = OH.read_manifest(tmp_path / "h2", "r2-b01")
        prompt = (tmp_path / "h2" / manifest[(J.STAGE_VERDICT, CID)]["prompt_path"]).read_text(
            encoding="utf-8"
        )
        assert "shape: not JSON" in prompt

    def test_a_clean_round_leaves_nothing_to_ask_again(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer())
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="no question to ask"):
            J.export_verdicts(run, CTX, tmp_path / "h2")

    def test_at_most_three_rounds(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        for n in (1, 2, 3):
            J.export_verdicts(run, CTX, tmp_path / f"h{n}", now=lambda: NOW)
            write_answer(tmp_path / f"h{n}", f"r{n}-b01", J.STAGE_VERDICT, CID, "not json")
            J.import_round(run, J.STAGE_VERDICT, f"r{n}", CTX, fake_fetch(PAGES), now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="3 dup-verdict rounds are out"):
            J.export_verdicts(run, CTX, tmp_path / "h4")

    def test_the_import_decides_the_answer_and_keeps_the_pages(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer())
        summary = J.import_round(
            run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW
        )
        assert (
            summary["decided"] == 1
            and summary["held"] == 0
            and summary["pages"] == {"cache": 0, "fetched": 1}
        )
        stored = J.load_decisions(run, J.STAGE_VERDICT)
        assert stored[CID]["status"] == "decided" and stored[CID]["answered_by"].startswith(
            "web_verifier:b1 ("
        )
        assert (
            run / J.DUP_DIR / J.STAGE_VERDICT / "pages" / f"{Q.url_key(URL_BANIAS)}.body"
        ).exists()
        assert (run / J.DUP_DIR / J.STAGE_VERDICT / "answers" / "r1.jsonl").exists()

    def test_a_cached_wikipedia_article_is_read_from_the_cache_not_fetched(
        self, tmp_path: Path
    ) -> None:
        cache = tmp_path / "wiki_cache"
        (cache / "en").mkdir(parents=True)
        page = {
            "lang": "en",
            "title": "Banias",
            "resolved_title": "Banias",
            "fetched_at": "2026-10-08",
            "text": TEXT_BANIAS,
        }
        (cache / "en" / "abc.json").write_text(json.dumps(page), encoding="utf-8")
        (cache / "INDEX.jsonl").write_text(
            json.dumps({"site_id": A_ID, "lang": "en", "title": "Banias", "file": "en\\abc.json"})
            + "\n",
            encoding="utf-8",
        )
        ctx = make_ctx(wiki=WikiIndex.load(cache))
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, ctx, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer())

        def never(urls: list[str], store: Path) -> dict[str, int]:
            raise AssertionError(f"fetched {urls}")

        summary = J.import_round(run, J.STAGE_VERDICT, "r1", ctx, never, now=lambda: NOW)
        assert summary["decided"] == 1 and summary["pages"] == {"cache": 1}

    def test_an_answer_that_is_not_in_shape_is_held_with_the_reason(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, answer([member(A_ID)]))
        summary = J.import_round(
            run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW
        )
        assert summary["held"] == 1 and summary["held_reasons"] == {"shape": 1}

    @pytest.mark.parametrize(
        ("by", "model", "message"),
        [
            ("agent-1", SONNET, "names no role"),
            ("adversarial:agent-1", SONNET, "this stage asks web_verifier"),
            ("web_verifier:agent-1", OH.MINIMAX_MODEL, "answered by MiniMax"),
            ("web_verifier:agent-1", OPUS, "is registered to claude-sonnet-5-5"),
            ("web_verifier:agent-1", OH.HAIKU_MODEL, "is registered to claude-sonnet-5-5"),
        ],
    )
    def test_an_answer_that_is_not_the_role_s_stops_the_import(
        self, tmp_path: Path, by: str, model: str, message: str
    ) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(
            tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer(), by=by, model=model
        )
        with pytest.raises(rounds.RoundError, match=message):
            J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        assert J.load_decisions(run, J.STAGE_VERDICT) == {}

    def test_an_unanswered_round_is_not_imported(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="does not validate"):
            J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES))

    def test_only_the_newest_round_is_imported(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, "not json")
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        J.export_verdicts(run, CTX, tmp_path / "h2", now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="is not the newest"):
            J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES))

    def test_the_recheck_asks_the_decided_relations_and_decides_them(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer())
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        record = J.export_rechecks(run, CTX, tmp_path / "h2", now=lambda: NOW)
        assert record.labels == [CID]
        manifest = OH.read_manifest(tmp_path / "h2", "r1-b01")
        prompt = (tmp_path / "h2" / manifest[(J.STAGE_RECHECK, CID)]["prompt_path"]).read_text(
            encoding="utf-8"
        )
        assert "MERGE: Banias" in prompt and "quote [found" in prompt and "try to REFUTE" in prompt
        recheck = json.dumps(
            {
                "cluster_id": CID,
                "members": [
                    {
                        "site_id": A_ID,
                        "decision": "CONFIRM",
                        "target": B_ID,
                        "why": "rw",
                        "quotes": [{"source": URL_BANIAS, "quote": "also known as"}],
                    }
                ],
            }
        )
        write_answer(
            tmp_path / "h2",
            "r1-b01",
            J.STAGE_RECHECK,
            CID,
            recheck,
            by="adversarial:r1",
            model=OPUS,
        )
        summary = J.import_round(
            run, J.STAGE_RECHECK, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW
        )
        assert summary["decided"] == 1
        written = J.write_decisions(run, CTX)
        assert written["merges"] == 1 and written["status"] == {"complete": 1}
        [record] = common.read_jsonl(run / J.DUP_DECISIONS)
        assert record["merges"][0]["site_id"] == A_ID

    def test_the_pilot_judge_may_recheck_and_a_web_verifier_may_not(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer())
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        J.export_rechecks(run, CTX, tmp_path / "h2", now=lambda: NOW)
        recheck = json.dumps(
            {
                "cluster_id": CID,
                "members": [
                    {
                        "site_id": A_ID,
                        "decision": "REJECT",
                        "target": None,
                        "why": "rw",
                        "quotes": [{"source": URL_BANIAS, "quote": "also known as"}],
                    }
                ],
            }
        )
        write_answer(
            tmp_path / "h2",
            "r1-b01",
            J.STAGE_RECHECK,
            CID,
            recheck,
            by="web_verifier:r1",
            model=SONNET,
        )
        with pytest.raises(rounds.RoundError, match="this stage asks adversarial or pilot_judge"):
            J.import_round(run, J.STAGE_RECHECK, "r1", CTX, fake_fetch(PAGES))

    def test_no_recheck_without_a_decided_relation(self, tmp_path: Path) -> None:
        run = self.run_dir(tmp_path)
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        write_answer(
            tmp_path / "h1",
            "r1-b01",
            J.STAGE_VERDICT,
            CID,
            answer([member(A_ID), member(B_ID), member(C_ID)]),
        )
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        with pytest.raises(rounds.RoundError, match="no cluster has a decided MERGE or PART_OF"):
            J.export_rechecks(run, CTX, tmp_path / "h2")


class TestTheBriefAndTheCheck:
    def exported(self, tmp_path: Path) -> Path:
        run = tmp_path / "run"
        J.export_verdicts(run, CTX, tmp_path / "h1", now=lambda: NOW)
        return run

    def test_the_brief_names_the_role_the_model_and_the_commands(self, tmp_path: Path) -> None:
        text = J.brief(self.exported(tmp_path), J.STAGE_VERDICT, "r1", "r1-b01")
        assert (
            "role web_verifier" in text and "--model claude-sonnet-5-5 --role web_verifier" in text
        )
        assert "dup_judge.py check-answer --stage dup-verdict --round r1" in text
        assert "403 or 429 is a throttle" in text and "4. Check its shape" in text

    def test_a_recheck_brief_names_the_adversarial_role(self, tmp_path: Path) -> None:
        run = self.exported(tmp_path)
        write_answer(tmp_path / "h1", "r1-b01", J.STAGE_VERDICT, CID, a_merge_answer())
        J.import_round(run, J.STAGE_VERDICT, "r1", CTX, fake_fetch(PAGES), now=lambda: NOW)
        J.export_rechecks(run, CTX, tmp_path / "h2", now=lambda: NOW)
        text = J.brief(run, J.STAGE_RECHECK, "r1", "r1-b01")
        assert "role adversarial" in text and "--model claude-opus-5-5 --role adversarial" in text

    def test_a_calibration_brief_has_no_shape_check(self, tmp_path: Path) -> None:
        run = self.exported(tmp_path)
        text = J.brief(run, J.STAGE_VERDICT, "r1", "r1-b01", check=False)
        assert "check-answer" not in text and "4. Record it" in text and "5. Record it" not in text

    def test_an_unknown_batch_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(rounds.RoundError, match="is no batch"):
            J.brief(self.exported(tmp_path), J.STAGE_VERDICT, "r1", "r1-b09")

    def test_the_shape_check_answers_with_the_problem_or_none(self, tmp_path: Path) -> None:
        run = self.exported(tmp_path)
        assert J.check_answer(run, CTX, J.STAGE_VERDICT, "r1", CID, a_merge_answer()) is None
        assert "missing" in str(
            J.check_answer(run, CTX, J.STAGE_VERDICT, "r1", CID, answer([member(A_ID)]))
        )
        with pytest.raises(rounds.RoundError, match="is no question of"):
            J.check_answer(run, CTX, J.STAGE_VERDICT, "r1", "dup-nope", "{}")


class TestTheContext:
    def test_the_context_is_read_from_the_run_directory(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        exported = export_of(
            [site(id=A_ID, name="Banias"), site(id=B_ID, name="Caesarea Philippi")],
            ext_ids=[ext(A_ID, "wikidata_qid", "Q1"), ext(B_ID, "wikidata_qid", "Q1")],
            names=[
                {"site_id": A_ID, "name": "Paneas", "name_type": "alias", "language_code": "en"}
            ],
        )
        records, _ = dup_clusters.build(exported, [])
        run.mkdir()
        common.write_jsonl(run / "DUP_CLUSTERS.jsonl", records)
        lines = ["\\set QUIET on"]
        for kind in ("shown", "ext_ids", "names"):
            for row in getattr(exported, kind):
                lines.append(json.dumps({"kind": kind, "row": row}))
        lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": exported.exported_at}}))
        (run / common.EXPORT_FILE).write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
        ctx = J.load_context(run, root=tmp_path)
        assert len(ctx.clusters) == 1 and ctx.wiki is None and ctx.basis == exported.exported_at
        assert ctx.names[A_ID] == ("Paneas",) and set(ctx.shown) == {A_ID, B_ID}
