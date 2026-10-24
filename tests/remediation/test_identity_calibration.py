"""The calibration sets of the duplicate verdict (D14) and the parent question (D25).

`identity/pair_calibration.py` builds the cases a role is measured on: the pairs judged one site before
(positives), the pairs the owner-case classification called WRONG-ID or NEITHER (negatives, no model
judged them yet) and, for parents, the PART-OF and the contained-name NEITHER pairs. It writes no
answer: the gold is a blind Opus xhigh labelling in the role `pilot_judge`, and `gold_check` holds it to
what was known. `mcode_driver` compares the sealed pool with the role's re-answers, so the identity
answer shapes are read as units there (`MERGE:<survivor>` is the unit's verdict).
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

import mcode_driver as D  # noqa: E402
import opus_handoff as OH  # noqa: E402
from identity import common, dup_judge, export, parent_judge  # noqa: E402
from identity import label_rounds as rounds  # noqa: E402
from identity import pair_calibration as C  # noqa: E402
from mechanical import plan as P  # noqa: E402

from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402

OPUS = OH.ANSWER_MODELS["claude-opus-5-5"]
SONNET = OH.ANSWER_MODELS["claude-sonnet-5-5"]
URL = "https://en.wikipedia.org/wiki/Banias"


def uid(n: int) -> str:
    return f"{n:08x}-0000-4000-8000-000000000000"


def pair_row(
    n: int, klass: str, a_name: str = "Alpha", b_name: str = "Alpha Temple"
) -> dict[str, Any]:
    return {
        "a": uid(2 * n),
        "b": uid(2 * n + 1),
        "class": klass,
        "a_name": a_name,
        "b_name": b_name,
        "distance_m": 10.0,
        "qid": f"Q{n}",
        "group_size": 2,
    }


# ------------------------------------------------------------------------------ the dup cases
class TestTheDuplicateCases:
    DUPLICATES = [
        {"loser_id": uid(100 + i), "survivor_id": uid(200 + i), "evidence": []} for i in range(19)
    ]
    O9 = [(uid(300 + i), uid(400 + i)) for i in range(5)]

    def pairs(self, wrong: int = 10, neither: int = 20) -> list[dict[str, Any]]:
        return (
            [pair_row(n, "WRONG-ID") for n in range(wrong)]
            + [pair_row(100 + n, "NEITHER") for n in range(neither)]
            + [pair_row(300, "DUP"), pair_row(301, "PART-OF")]
        )

    def test_the_positives_are_the_judged_pairs_counted_once_by_loser(self) -> None:
        cases = C.dup_cases(self.DUPLICATES, self.O9, self.pairs())
        positives = [c for c in cases if c.kind == "positive"]
        assert len(positives) == 24 and len({c.a for c in positives}) == 24
        assert all(c.expected == {"loser": c.a, "survivor": c.b} for c in positives)
        assert {c.source for c in positives} == {
            "bcases/DUPLICATES.jsonl",
            "mechanical/dups.PAIRS (O9)",
        }

    def test_banias_in_both_lists_counts_once(self) -> None:
        duplicates = [
            *self.DUPLICATES,
            {"loser_id": self.O9[0][0], "survivor_id": self.O9[0][1], "evidence": []},
        ]
        positives = [
            c for c in C.dup_cases(duplicates, self.O9, self.pairs()) if c.kind == "positive"
        ]
        assert len(positives) == 24
        assert (
            next(c for c in positives if c.a == self.O9[0][0]).source == "bcases/DUPLICATES.jsonl"
        )

    def test_fifteen_negatives_wrong_id_first_in_a_fixed_order(self) -> None:
        cases = C.dup_cases(self.DUPLICATES, self.O9, self.pairs())
        negatives = [c for c in cases if c.kind == "negative"]
        assert len(negatives) == 15 and all(c.expected is None for c in negatives)
        assert [c.source for c in negatives].count("bcases/dup_pairs.jsonl WRONG-ID") == 10
        assert [c.source for c in negatives].count("bcases/dup_pairs.jsonl NEITHER") == 5
        assert [c.case_id for c in negatives] == [
            c.case_id
            for c in C.dup_cases(self.DUPLICATES, self.O9, list(reversed(self.pairs())))
            if c.kind == "negative"
        ]

    def test_the_other_classes_are_no_negatives(self) -> None:
        negatives = {
            c.a for c in C.dup_cases(self.DUPLICATES, self.O9, self.pairs()) if c.kind == "negative"
        }
        assert uid(600) not in negatives and uid(602) not in negatives

    def test_the_named_negatives_come_first(self) -> None:
        extra = [(uid(900), uid(901))]
        negatives = [
            c
            for c in C.dup_cases(self.DUPLICATES, self.O9, self.pairs(), extra_negatives=extra)
            if c.kind == "negative"
        ]
        assert (negatives[0].a, negatives[0].source) == (uid(900), "named negative") and len(
            negatives
        ) == 15

    def test_a_named_negative_is_not_chosen_a_second_time(self) -> None:
        pairs = self.pairs()
        extra = [(pairs[0]["b"], pairs[0]["a"])]  # the first WRONG-ID pair, the other way round
        negatives = [
            c
            for c in C.dup_cases(self.DUPLICATES, self.O9, pairs, extra_negatives=extra)
            if c.kind == "negative"
        ]
        keys = [frozenset(c.sites()) for c in negatives]
        assert len(keys) == len(set(keys)) == 15 and negatives[0].source == "named negative"

    def test_too_few_negatives_are_an_error(self) -> None:
        with pytest.raises(P.PlanError, match="only 3 negatives available, 15 wanted"):
            C.dup_cases(self.DUPLICATES, self.O9, self.pairs(wrong=1, neither=2))

    def test_the_case_id_does_not_depend_on_the_order_of_the_pair(self) -> None:
        assert C.case_id("dup-pos", "a", "b") == C.case_id("dup-pos", "b", "a")
        assert C.case_id("dup-pos", "a", "b").startswith("dup-pos-")

    def test_a_named_pair_resolves_to_exactly_two_sites(self) -> None:
        rows = [
            site(id="s1", name="Lycian Mezarı 2"),
            site(id="s2", name="Amyntas Rock Tombs"),
            site(id="s3", name="Twin"),
            site(id="s4", name="Twin"),
        ]
        assert C.resolve_named(rows, "Lycian Mezarı 2", "Amyntas Rock Tombs") == ("s1", "s2")
        with pytest.raises(P.PlanError, match="'Twin' names 2 shown sites"):
            C.resolve_named(rows, "Twin", "Amyntas Rock Tombs")
        with pytest.raises(P.PlanError, match="'Nope' names 0 shown sites"):
            C.resolve_named(rows, "Nope", "Twin")

    def test_the_real_lists_make_twenty_four_positives(self) -> None:
        from mechanical import dups

        duplicates = C.DUPLICATES
        if not duplicates.exists():
            pytest.skip("the owner-case files are the main checkout's run data")
        positives = [
            c
            for c in C.dup_cases(
                common.read_jsonl(duplicates),
                [(p.loser, p.survivor) for p in dups.PAIRS],
                common.read_jsonl(C.DUP_PAIRS),
            )
            if c.kind == "positive"
        ]
        assert len(positives) == 24


# ------------------------------------------------------------------------------------ the read
class TestTheRead:
    def test_the_read_is_the_export_s_own_queries_for_exactly_these_ids(self) -> None:
        parts = dict(C.facts_parts([uid(1), uid(2)]))
        assert list(parts) == ["shown", "ext_ids", "names"]
        for sql in parts.values():
            assert export.SHOWN not in sql and uid(1) in sql and uid(2) in sql
        assert (
            "u.id IN (" in parts["shown"]
            and "e.site_id IN (" in parts["ext_ids"]
            and "n.site_id IN (" in parts["names"]
        )
        assert "n.name_type = 'label'" in parts["names"]

    def test_the_script_is_read_only(self) -> None:
        script = P.tagged_export_script(C.facts_parts([uid(1)]))
        assert "READ ONLY" in script
        for verb in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER"):
            assert verb not in script.upper().replace("ON_ERROR_STOP", "")

    def test_an_export_that_no_longer_filters_on_shown_stops_the_rewrite(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(export, "SHOWN_SQL", "SELECT 1")
        with pytest.raises(P.PlanError, match="no longer filters"):
            C.facts_parts([uid(1)])

    def test_the_tagged_read_becomes_facts_and_a_missing_site_is_named(self) -> None:
        ids = [uid(1)]
        lines = [
            {"kind": "shown", "row": site(id=uid(1))},
            {"kind": "ext_ids", "row": ext(uid(1), "wikidata_qid", "Q1")},
            {
                "kind": "names",
                "row": {
                    "site_id": uid(1),
                    "name": "Alias",
                    "name_type": "alias",
                    "language_code": "en",
                },
            },
            {"kind": "snapshot", "row": {"exported_at": "2026-10-10 10:00:00+00"}},
        ]
        text = "\n".join(json.dumps(x) for x in lines)
        facts = C.parse_facts(text, ids)
        assert (len(facts.shown), len(facts.ext_ids), len(facts.names), facts.read_at) == (
            1,
            1,
            1,
            "2026-10-10 10:00:00+00",
        )
        with pytest.raises(P.PlanError, match="1 calibration site\\(s\\) are not in unified_sites"):
            C.parse_facts(text, [uid(1), uid(2)])


# ------------------------------------------------------------------------------------- context
A, B, C_, D_ = uid(11), uid(12), uid(13), uid(14)


def facts_of(rows: list[dict[str, Any]], ext_ids: list[dict[str, str]] | None = None) -> C.Facts:
    return C.Facts(tuple(rows), tuple(ext_ids or ()), (), "2026-10-10 10:00:00+00")


def dup_facts() -> C.Facts:
    rows = [
        site(id=A, name="Olympos Ruins", lat=36.4, lon=30.46, created_at="2026-03-04 21:07:57"),
        site(
            id=B,
            name="Olympos Antique City",
            lat=36.4015,
            lon=30.46,
            created_at="2026-03-04 21:07:57",
        ),
        site(id=C_, name="Lycian Mezarı 2", lat=36.5, lon=29.1),
        site(id=D_, name="Amyntas Rock Tombs", lat=36.6, lon=29.2),
    ]
    return facts_of(
        rows,
        [
            ext(A, "wikidata_qid", "Q1380189"),
            ext(B, "wikidata_qid", "Q1380189"),
            ext(A, "enwiki_title", "Olympos"),
        ],
    )


CASES = [
    C.Case("dup-pos-1", "positive", A, B, {"loser": A, "survivor": B}, "t"),
    C.Case("dup-neg-1", "negative", C_, D_, None, "t"),
]


class TestTheDuplicateContext:
    def test_one_cluster_per_case_with_its_facts(self) -> None:
        ctx = C.dup_context(dup_facts(), CASES, None)
        assert (
            set(ctx.clusters) == {"dup-pos-1", "dup-neg-1"}
            and ctx.basis == "2026-10-10 10:00:00+00"
        )
        cluster = ctx.clusters["dup-pos-1"]
        assert (
            cluster["size"] == 2
            and cluster["edges"][0]["kind"] == "shared_qid"
            and cluster["edges"][0]["qid"] == "Q1380189"
        )
        assert [m["id"] for m in cluster["members"]] == [A, B] and cluster["members"][0][
            "enwiki"
        ] == ["Olympos"]
        assert cluster["distance_band"] == "<=200m" and cluster["bcases_classes"] == []

    def test_a_pair_without_a_shared_item_is_a_name_and_point_edge(self) -> None:
        edge = C.dup_context(dup_facts(), CASES, None).clusters["dup-neg-1"]["edges"][0]
        assert edge["kind"] == "name_point" and edge["metres"] > 10000

    def test_the_question_is_the_one_the_real_stage_asks(self) -> None:
        ctx = C.dup_context(dup_facts(), CASES, None)
        text = dup_judge.verdict_prompt(ctx.clusters["dup-pos-1"], ctx)
        assert "THE CLUSTER dup-pos-1" in text and "Olympos Ruins" in text and "Q1380189" in text

    def test_the_export_asks_every_case_in_the_calibration_s_own_stage_directory(
        self, tmp_path: Path
    ) -> None:
        ctx = C.dup_context(dup_facts(), CASES, None)
        record = C.export_gold(tmp_path / "cal", ctx, CASES, tmp_path / "gold")
        assert record.labels == ["dup-neg-1", "dup-pos-1"]
        assert (tmp_path / "cal" / "dup-verdict" / "ROUNDS.jsonl").exists()


def gold_answer(cluster: dict[str, Any], merges: dict[str, str]) -> str:
    members = []
    for m in cluster["members"]:
        row = {
            "site_id": m["id"],
            "verdict": "DISTINCT",
            "survivor": None,
            "parent": None,
            "why": "w",
            "quotes": [],
        }
        if m["id"] in merges:
            row |= {
                "verdict": "MERGE",
                "survivor": merges[m["id"]],
                "quotes": [{"source": URL, "quote": "q"}],
            }
        members.append(row)
    return json.dumps({"cluster_id": cluster["cluster_id"], "members": members})


class TestTheGoldCheck:
    def run(
        self,
        tmp_path: Path,
        answers: dict[str, dict[str, str]],
        by: str = "pilot_judge:g1",
        model: str = OPUS,
    ) -> dict[str, Any]:
        ctx = C.dup_context(dup_facts(), CASES, None)
        record = C.export_gold(tmp_path / "cal", ctx, CASES, tmp_path / "gold")
        for batch, labels in record.batches.items():
            for label in labels:
                OH.write_answer(
                    tmp_path / "gold",
                    batch_id=batch,
                    stage=dup_judge.STAGE_VERDICT,
                    label=label,
                    text=gold_answer(ctx.clusters[label], answers[label]),
                    answered_by=by,
                    model=model,
                )
        return C.gold_check(tmp_path / "gold", ctx, CASES, batches=record.batches)

    def test_a_gold_that_agrees_with_what_was_known_has_nothing_to_report(
        self, tmp_path: Path
    ) -> None:
        report = self.run(tmp_path, {"dup-pos-1": {A: B}, "dup-neg-1": {}})
        assert report["answered"] == 2 and report["gold_models"] == [OPUS]
        assert (
            report["positive_disagreements"],
            report["survivor_differs"],
            report["negative_merges"],
        ) == ([], [], [])

    def test_a_positive_the_gold_does_not_merge_is_listed(self, tmp_path: Path) -> None:
        report = self.run(tmp_path, {"dup-pos-1": {}, "dup-neg-1": {}})
        assert [d["case"] for d in report["positive_disagreements"]] == ["dup-pos-1"]

    def test_a_swapped_survivor_is_listed_apart(self, tmp_path: Path) -> None:
        report = self.run(tmp_path, {"dup-pos-1": {B: A}, "dup-neg-1": {}})
        assert report["positive_disagreements"] == [] and [
            d["case"] for d in report["survivor_differs"]
        ] == ["dup-pos-1"]

    def test_a_negative_the_gold_merges_is_a_finding_about_the_case(self, tmp_path: Path) -> None:
        report = self.run(tmp_path, {"dup-pos-1": {A: B}, "dup-neg-1": {C_: D_}})
        assert [d["case"] for d in report["negative_merges"]] == ["dup-neg-1"]

    @pytest.mark.parametrize(
        ("by", "model", "message"),
        [
            ("web_verifier:g1", SONNET, "this stage asks pilot_judge"),
            ("pilot_judge:g1", SONNET, "is registered to claude-opus-5-5"),
            ("pilot_judge:g1", OH.MINIMAX_MODEL, "never ground truth"),
            ("g1", OPUS, "names no role"),
        ],
    )
    def test_only_the_pilot_judge_labels_the_gold(
        self, tmp_path: Path, by: str, model: str, message: str
    ) -> None:
        with pytest.raises(rounds.RoundError, match=message):
            self.run(tmp_path, {"dup-pos-1": {A: B}, "dup-neg-1": {}}, by=by, model=model)


class TestTheFalseMerges:
    def test_a_merge_where_the_gold_made_none_is_false(self) -> None:
        comparison = {"disagreements": [
            {"recorded": "DISTINCT", "fresh": f"MERGE:{B}"},
            {"recorded": f"MERGE:{B}", "fresh": f"MERGE:{C_}"},  # another survivor: not false
            {"recorded": f"MERGE:{B}", "fresh": "DISTINCT"},  # a missed merge: not false
            {"recorded": "PART_OF:x", "fresh": f"MERGE:{B}"},
            {"recorded": "<none>", "fresh": f"MERGE:{B}"},
        ]}  # fmt: skip
        assert C.false_merges(comparison) == 3

    def test_the_cli_prints_the_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "COMPARISON.json"
        path.write_text(
            json.dumps({"disagreements": [{"recorded": "DISTINCT", "fresh": "MERGE:x"}]}),
            encoding="utf-8",
        )
        assert C.main(["false-merges", "--comparison", str(path)]) == 0
        assert capsys.readouterr().out.strip() == "1"


# ----------------------------------------------------------------------------------- parents
def no_item(qid: str) -> None:
    """An entity lookup that read no item."""
    return None


class TestTheParentCases:
    def shown(self, n: int) -> dict[str, dict[str, Any]]:
        return {i: site(id=i) for k in range(n) for i in (uid(2 * k), uid(2 * k + 1))}

    def pairs(self) -> list[dict[str, Any]]:
        return (
            [pair_row(n, "PART-OF", "Abu Simbel", "Abu Simbel Small Temple") for n in range(30)]
            + [pair_row(100 + n, "NEITHER", "Delphi", "Delphi Museum") for n in range(20)]
            + [pair_row(200 + n, "NEITHER", "Alpha", "Beta") for n in range(5)]
            + [pair_row(300 + n, "DUP", "Delphi", "Delphi Museum") for n in range(5)]
        )

    def shown_all(self) -> dict[str, dict[str, Any]]:
        return {
            i: site(id=i)
            for n in list(range(30)) + [100 + n for n in range(20)] + [200 + n for n in range(5)]
            for i in (uid(2 * n), uid(2 * n + 1))
        }

    def test_twenty_part_of_and_ten_contained_name_neither_pairs(self) -> None:
        cases = C.parent_cases(self.pairs(), self.shown_all(), candidates=[], entity_of=no_item)
        assert [c.kind for c in cases].count("positive") == 20 and [c.kind for c in cases].count(
            "negative"
        ) == 10

    def test_the_shorter_name_is_the_parent(self) -> None:
        for case in C.parent_cases(
            self.pairs(), self.shown_all(), candidates=[], entity_of=no_item
        ):
            assert case.source.endswith(("PART-OF", "NEITHER"))
        case = C.parent_cases(
            [pair_row(0, "PART-OF", "Abu Simbel Small Temple", "Abu Simbel")],
            {uid(0): site(id=uid(0)), uid(1): site(id=uid(1))},
            candidates=[],
            entity_of=no_item,
            n_positive=1,
            n_negative=0,
        )[0]
        assert (case.a, case.b) == (uid(1), uid(0))

    def test_names_that_are_not_nested_make_no_case(self) -> None:
        with pytest.raises(
            P.PlanError,
            match="only 0 parent negatives - 0 NEITHER pairs with nested names and 0 structure",
        ):
            C.parent_cases(
                [
                    pair_row(0, "PART-OF", "Abu Simbel", "Abu Simbel Small Temple"),
                    pair_row(1, "NEITHER", "Alpha", "Beta"),
                ],
                {i: site(id=i) for i in (uid(0), uid(1), uid(2), uid(3))},
                candidates=[],
                entity_of=no_item,
                n_positive=1,
                n_negative=1,
            )

    def test_a_pair_with_a_retired_member_is_left_out(self) -> None:
        shown = {uid(0): site(id=uid(0))}  # uid(1) is not shown
        with pytest.raises(P.PlanError, match="only 0 PART-OF pairs"):
            C.parent_cases(
                [pair_row(0, "PART-OF", "Abu Simbel", "Abu Simbel Small Temple")],
                shown,
                candidates=[],
                entity_of=no_item,
                n_positive=1,
                n_negative=0,
            )

    def test_the_context_asks_one_child_per_parent(self) -> None:
        rows = [
            site(id=A, name="Abu Simbel", lat=22.3, lon=31.6),
            site(id=B, name="Abu Simbel Small Temple", lat=22.3005, lon=31.6),
        ]
        case = C.Case("par-pos-1", "positive", A, B, None, "t")
        ctx = C.parent_context(facts_of(rows), [case], None)
        question = ctx.questions["par-pos-1"]
        assert question["parent"]["id"] == A and [c["id"] for c in question["children"]] == [B]
        text = parent_judge.verdict_prompt(question, ctx)
        assert A in text and "Abu Simbel Small Temple" in text

    def test_the_gold_is_checked_against_the_heuristic_classes(self, tmp_path: Path) -> None:
        rows = [site(id=A, name="Abu Simbel", lat=22.3, lon=31.6), site(id=B, name="Abu Simbel Small Temple", lat=22.3005, lon=31.6),
                site(id=C_, name="Delphi", lat=38.4, lon=22.5), site(id=D_, name="Delphi Museum", lat=38.4005, lon=22.5)]  # fmt: skip
        cases = [
            C.Case("par-pos-1", "positive", A, B, None, "t"),
            C.Case("par-pos-2", "positive", C_, D_, None, "t"),
            C.Case("par-neg-1", "negative", A, D_, None, "t"),
        ]
        ctx = C.parent_context(facts_of(rows), cases, None)
        record = C.export_parent_gold(tmp_path / "cal", ctx, cases, tmp_path / "gold")
        verdicts = {
            "par-pos-1": ("PART", A, B),
            "par-pos-2": ("NOT_PART", C_, D_),
            "par-neg-1": ("PART", A, D_),
        }
        for batch, labels in record.batches.items():
            for label in labels:
                verdict, parent, kid = verdicts[label]
                quotes = [{"source": URL, "quote": "q"}]
                text = json.dumps(
                    {
                        "parent_id": parent,
                        "children": [
                            {"site_id": kid, "verdict": verdict, "why": "w", "quotes": quotes}
                        ],
                    }
                )
                OH.write_answer(
                    tmp_path / "gold",
                    batch_id=batch,
                    stage=parent_judge.STAGE_VERDICT,
                    label=label,
                    text=text,
                    answered_by="pilot_judge:g1",
                    model=OPUS,
                )
        report = C.parent_gold_check(tmp_path / "gold", ctx, cases, batches=record.batches)
        assert report["answered"] == 3
        assert [d["case"] for d in report["positive_not_part"]] == ["par-pos-2"]
        assert [d["case"] for d in report["negative_part"]] == ["par-neg-1"]


# --------------------------------------------------------------- the structure-parent negatives
def wd(qid: str, *, part_of: tuple[str, ...] = (), has_part: tuple[str, ...] = ()) -> dict:
    """A raw entity with P361 (part of) and P527 (has part) statements."""

    def statements(values: tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            {
                "mainsnak": {
                    "snaktype": "value",
                    "datavalue": {"type": "wikibase-entityid", "value": {"id": v}},
                },
                "rank": "normal",
            }
            for v in values
        ]

    return {"id": qid, "claims": {"P361": statements(part_of), "P527": statements(has_part)}}


def brief_row(n: int, site_type: str = "Temple complex", qids: tuple[str, ...] = ()) -> dict:
    return {"id": uid(n), "name": f"Site {n}", "site_type": site_type,
            "qids": list(qids) if qids else [f"Q{n}"]}  # fmt: skip


def candidate(parent: dict[str, Any], *children: dict[str, Any]) -> dict[str, Any]:
    return {"parent": parent, "children": list(children)}


def items_of(*records: dict[str, Any], **special: dict) -> dict[str, dict]:
    """An entity per item the candidates name (no P361/P527), with `special` ones replaced."""
    out = {}
    for record in records:
        for row in (record["parent"], *record["children"]):
            for qid in row["qids"]:
                out[qid] = wd(qid)
    out.update(special)
    return out


class TestTheStructureNegatives:
    def shown(self, *records: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            row["id"]: site(id=row["id"])
            for record in records
            for row in (record["parent"], *record["children"])
        }

    def draw(
        self, records: list[dict[str, Any]], items: dict[str, dict], **kw: Any
    ) -> tuple[list[C.Case], dict[str, int]]:
        return C.structure_negatives(
            records, kw.pop("shown", self.shown(*records)), items.get, exclude=kw.pop("exclude", ()),
            **kw,
        )  # fmt: skip

    def test_a_structure_parent_with_no_containment_is_a_negative(self) -> None:
        record = candidate(brief_row(1, "Temple complex"), brief_row(2, "Gate/archway/bridge"))
        cases, counts = self.draw([record], items_of(record))
        assert [(c.a, c.b, c.kind, c.source) for c in cases] == [
            (uid(1), uid(2), "negative", C.STRUCTURE_SOURCE)
        ]
        assert counts["eligible"] == counts["drawn"] == 1

    @pytest.mark.parametrize(
        "site_type",
        ["City/town/settlement", "Sanctuary", "Fortress/citadel", "Forum", "Archaeological site",
         "City/town/settlement, Pyramid complex", ""],
    )  # fmt: skip
    def test_a_container_parent_is_no_negative(self, site_type: str) -> None:
        record = candidate(brief_row(1, site_type), brief_row(2))
        cases, counts = self.draw([record], items_of(record))
        assert cases == [] and counts["structure_parent"] == 0

    def test_a_cell_of_two_types_is_two_types(self) -> None:
        assert C.site_types("City/town/settlement, Pyramid complex") == {
            "City/town/settlement",
            "Pyramid complex",
        }
        assert C.site_types(None) == frozenset() and C.site_types("") == frozenset()

    def test_a_child_wikidata_places_in_the_parent_is_left_out(self) -> None:
        record = candidate(brief_row(1), brief_row(2))
        cases, counts = self.draw([record], items_of(record, Q2=wd("Q2", part_of=("Q1",))))
        assert cases == [] and counts["left_out_contained"] == 1

    def test_a_parent_wikidata_says_has_the_child_is_left_out(self) -> None:
        record = candidate(brief_row(1), brief_row(2))
        cases, counts = self.draw([record], items_of(record, Q1=wd("Q1", has_part=("Q2",))))
        assert cases == [] and counts["left_out_contained"] == 1

    def test_the_reverse_statement_keeps_the_pair_a_negative(self) -> None:
        # the would-be parent is the part: the asked orientation is false, a true negative
        record = candidate(brief_row(1), brief_row(2))
        cases, _ = self.draw([record], items_of(record, Q1=wd("Q1", part_of=("Q2",))))
        assert [(c.a, c.b) for c in cases] == [(uid(1), uid(2))]

    def test_a_shared_item_is_d14_s_and_left_out(self) -> None:
        record = candidate(brief_row(1, qids=("Q9",)), brief_row(2, qids=("Q9",)))
        cases, counts = self.draw([record], items_of(record))
        assert cases == [] and counts["left_out_shared_item"] == 1

    def test_a_site_without_an_item_is_left_out(self) -> None:
        parent = brief_row(1)
        child = {**brief_row(2), "qids": []}
        record = candidate(parent, child)
        cases, counts = self.draw([record], items_of(record))
        assert cases == [] and counts["left_out_no_item"] == 1

    def test_an_item_nobody_read_is_not_taken_as_silent(self) -> None:
        record = candidate(brief_row(1), brief_row(2))
        items = items_of(record)
        del items["Q2"]
        cases, counts = self.draw([record], items)
        assert cases == [] and counts["left_out_item_unread"] == 1

    def test_an_owner_case_pair_and_a_retired_site_are_left_out(self) -> None:
        record = candidate(brief_row(1), brief_row(2))
        cases, counts = self.draw([record], items_of(record), exclude={frozenset((uid(1), uid(2)))})
        assert cases == [] and counts["left_out_owner_case"] == 1
        cases, counts = self.draw([record], items_of(record), shown={uid(1): site(id=uid(1))})
        assert cases == [] and counts["left_out_not_shown"] == 1

    def test_one_negative_per_parent_and_per_child(self) -> None:
        records = [
            candidate(brief_row(1), brief_row(2), brief_row(3)),  # one parent, two children
            candidate(brief_row(6), brief_row(7)),
            candidate(brief_row(8), brief_row(7)),  # one child, two parents
            candidate(brief_row(4), brief_row(5)),
        ]
        cases, counts = self.draw(records, items_of(*records))
        assert counts["eligible"] == 5 and counts["drawn"] == len(cases) == 3
        parents, children = [c.a for c in cases], [c.b for c in cases]
        assert len(set(parents)) == len(parents) and len(set(children)) == len(children)
        assert (uid(4), uid(5)) in {(c.a, c.b) for c in cases}

    def test_the_draw_is_the_seed_s_order_and_the_same_on_every_run(self) -> None:
        records = [candidate(brief_row(10 + 2 * n), brief_row(11 + 2 * n)) for n in range(12)]
        items = items_of(*records)
        first, _ = self.draw(records, items)
        assert [c.case_id for c in first] == [c.case_id for c in self.draw(records, items)[0]]
        expected = sorted(
            ((r["parent"]["id"], r["children"][0]["id"]) for r in records),
            key=lambda pc: C._seeded_order(C.PARENT_NEGATIVE_SEED, *pc),
        )
        assert [(c.a, c.b) for c in first] == expected
        other, _ = self.draw(records, items, seed="another seed")
        assert {c.case_id for c in other} == {c.case_id for c in first}
        assert [c.case_id for c in other] != [c.case_id for c in first]


class TestTheParentPool:
    def owner_pairs(self, neither: int) -> list[dict[str, Any]]:
        return [pair_row(n, "PART-OF", "Abu Simbel", "Abu Simbel Small Temple") for n in range(3)] + [
            pair_row(100 + n, "NEITHER", "Delphi", "Delphi Museum") for n in range(neither)
        ]  # fmt: skip

    def structure(self, n: int) -> list[dict[str, Any]]:
        return [candidate(brief_row(500 + 2 * k), brief_row(501 + 2 * k)) for k in range(n)]

    def shown(self, pairs: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict:
        ids = {p[k] for p in pairs for k in ("a", "b")} | {
            row["id"] for r in records for row in (r["parent"], *r["children"])
        }
        return {i: site(id=i) for i in ids}

    def test_the_neither_pairs_come_first_and_the_structure_pairs_complete_them(self) -> None:
        pairs, records = self.owner_pairs(2), self.structure(12)
        cases, pool = C.parent_pool(
            pairs, self.shown(pairs, records), candidates=records,
            entity_of=items_of(*records).get, n_positive=3, n_negative=10,
        )  # fmt: skip
        negatives = [c for c in cases if c.kind == "negative"]
        assert [c.source for c in negatives] == [C.NEITHER_SOURCE] * 2 + [C.STRUCTURE_SOURCE] * 8
        assert pool["drawn"] == {"positive": 3, "negative_neither": 2, "negative_structure": 8}
        assert pool["neither_nested_available"] == 2 and pool["structure"]["drawn"] == 12

    def test_too_few_negatives_are_an_error_never_a_smaller_set(self) -> None:
        pairs, records = self.owner_pairs(2), self.structure(7)
        with pytest.raises(
            P.PlanError,
            match="only 9 parent negatives - 2 NEITHER pairs with nested names and 7 "
            "structure-parent candidates - 10 wanted",
        ):
            C.parent_cases(
                pairs, self.shown(pairs, records), candidates=records,
                entity_of=items_of(*records).get, n_positive=3, n_negative=10,
            )  # fmt: skip

    def test_an_owner_case_pair_listed_as_a_candidate_is_not_drawn_twice(self) -> None:
        pairs = self.owner_pairs(1)
        neither = pairs[-1]
        records = [
            candidate(
                {**brief_row(0), "id": neither["a"], "qids": ["Q900"]},
                {**brief_row(0), "id": neither["b"], "qids": ["Q901"]},
            )
        ]
        cases, pool = C.parent_pool(
            pairs, self.shown(pairs, records), candidates=records,
            entity_of=items_of(*records).get, n_positive=3, n_negative=1,
        )  # fmt: skip
        assert [c.source for c in cases if c.kind == "negative"] == [C.NEITHER_SOURCE]
        assert pool["structure"]["left_out_owner_case"] == 1


# ---------------------------------------------------------------------- the gold round's brief
def gold_dir_with(tmp_path: Path) -> tuple[Path, Path, C.Facts]:
    """A dup calibration directory as `read` and `export` leave it: cases, read, gold round."""
    run = tmp_path / "run"
    out = C.cal_dir(run, "dup")
    facts = dup_facts()
    out.mkdir(parents=True)
    common.write_jsonl(out / rounds.CASES_FILE, C._case_rows(CASES))
    lines = [
        {"kind": k, "row": r} for k in ("shown", "ext_ids", "names") for r in getattr(facts, k)
    ]
    lines.append({"kind": "snapshot", "row": {"exported_at": facts.read_at}})
    (out / C.READ_FILE).write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    C.export_gold(out, C.dup_context(facts, CASES, None), CASES, tmp_path / "gold")
    return run, out, facts


class TestTheGoldBrief:
    def test_the_gold_round_is_briefed_for_the_pilot_judge_by_default(self, tmp_path: Path) -> None:
        run, out, _ = gold_dir_with(tmp_path)
        text = dup_judge.brief(run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out)
        assert "role pilot_judge" in text and "--model claude-opus-5-5 --role pilot_judge" in text
        assert (
            dup_judge.brief(
                run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out, role="pilot_judge"
            )
            == text
        )

    def test_the_gold_round_is_checked_against_the_calibration_s_own_cases(
        self, tmp_path: Path
    ) -> None:
        run, out, _ = gold_dir_with(tmp_path)
        text = dup_judge.brief(run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out)
        assert (
            f"pair_calibration.py check-answer --stage-run {rounds.shown(out)} --round r1" in text
        )
        assert "dup_judge.py check-answer" not in text

    def test_no_other_role_labels_the_gold(self, tmp_path: Path) -> None:
        run, out, _ = gold_dir_with(tmp_path)
        with pytest.raises(
            rounds.RoundError,
            match="web_verifier is no role of the gold round of a calibration of dup-verdict",
        ):
            dup_judge.brief(
                run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out, role="web_verifier"
            )

    def test_the_copy_is_re_answered_by_the_role_under_calibration_never_the_gold_role(
        self, tmp_path: Path
    ) -> None:
        run, out, _ = gold_dir_with(tmp_path)
        copy = str(tmp_path / "copy")
        text = dup_judge.brief(
            run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out, handoff=copy
        )
        assert "--role web_verifier" in text and "pair_calibration.py check-answer" in text
        with pytest.raises(
            rounds.RoundError, match="pilot_judge is no role of a re-answer of a calibration copy"
        ):
            dup_judge.brief(
                run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out, handoff=copy,
                role="pilot_judge",
            )  # fmt: skip

    def test_only_a_calibration_directory_of_its_kind_is_a_gold_run(self, tmp_path: Path) -> None:
        run, out, _ = gold_dir_with(tmp_path)
        assert rounds.is_gold_run(out, "dup")
        assert not rounds.is_gold_run(out, "parent") and not rounds.is_gold_run(None, "dup")
        own = run / "dup"  # the stage's own run directory, even with a CASES file in it
        own.mkdir()
        (own / rounds.CASES_FILE).write_text("", encoding="utf-8")
        assert not rounds.is_gold_run(own, "dup")

    def test_a_directory_without_the_cases_is_no_calibration(self, tmp_path: Path) -> None:
        run, out, _ = gold_dir_with(tmp_path)
        (out / rounds.CASES_FILE).unlink()
        with pytest.raises(
            rounds.RoundError, match="pilot_judge is no role of dup-verdict: it asks web_verifier"
        ):
            dup_judge.brief(
                run, dup_judge.STAGE_VERDICT, "r1", "r1-b01", stage_run=out, role="pilot_judge"
            )

    def test_the_parent_gold_round_is_briefed_for_the_pilot_judge(self, tmp_path: Path) -> None:
        rows = [site(id=A, name="Abu Simbel", lat=22.3, lon=31.6),
                site(id=B, name="Abu Simbel Small Temple", lat=22.3005, lon=31.6)]  # fmt: skip
        cases = [C.Case("par-pos-1", "positive", A, B, None, "t")]
        run = tmp_path / "run"
        out = C.cal_dir(run, "parent")
        out.mkdir(parents=True)
        common.write_jsonl(out / rounds.CASES_FILE, C._case_rows(cases))
        C.export_parent_gold(out, C.parent_context(facts_of(rows), cases, None), cases,
                             tmp_path / "gold")  # fmt: skip
        stage = parent_judge.STAGE_VERDICT
        text = parent_judge.brief(run, stage, "r1", "r1-b01", stage_run=out)
        assert "--role pilot_judge" in text and "pair_calibration.py check-answer" in text
        with pytest.raises(rounds.RoundError, match="web_verifier is no role of the gold round"):
            parent_judge.brief(run, stage, "r1", "r1-b01", stage_run=out, role="web_verifier")
        copy = str(tmp_path / "copy")
        assert "--role web_verifier" in parent_judge.brief(
            run, stage, "r1", "r1-b01", stage_run=out, handoff=copy
        )

    @pytest.mark.parametrize("judge", [dup_judge, parent_judge], ids=["dup", "parent"])
    def test_the_cli_briefs_a_gold_round_before_the_run_s_stage_inputs_exist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], judge: Any
    ) -> None:
        # the run holds no clusters, no DUP_DECISIONS, no export: a brief reads the round only
        if judge is dup_judge:
            _, out, _ = gold_dir_with(tmp_path)
        else:
            rows = [site(id=A, name="Abu Simbel"), site(id=B, name="Abu Simbel Small Temple")]
            cases = [C.Case("par-pos-1", "positive", A, B, None, "t")]
            out = C.cal_dir(tmp_path / "run", "parent")
            out.mkdir(parents=True)
            common.write_jsonl(out / rounds.CASES_FILE, C._case_rows(cases))
            C.export_parent_gold(out, C.parent_context(facts_of(rows), cases, None), cases,
                                 tmp_path / "gold")  # fmt: skip
        argv = ["--root", str(tmp_path / "root"), "brief", "--stage", judge.STAGE_VERDICT,
                "--round", "r1", "--batch-id", "r1-b01", "--stage-run", str(out)]  # fmt: skip
        assert judge.main(argv) == 0
        assert "--role pilot_judge" in capsys.readouterr().out


class TestTheCalibrationShapeCheck:
    def test_an_answer_in_shape_passes_and_a_broken_one_names_its_problem(
        self, tmp_path: Path
    ) -> None:
        _, out, facts = gold_dir_with(tmp_path)
        cluster = C.dup_context(facts, CASES, None).clusters["dup-pos-1"]
        assert C.check_answer(out, "r1", "dup-pos-1", gold_answer(cluster, {A: B})) is None
        assert "is not this question's" in str(
            C.check_answer(out, "r1", "dup-pos-1", json.dumps({"cluster_id": "x", "members": []}))
        )

    def test_a_label_of_no_question_and_a_directory_of_no_calibration_are_refused(
        self, tmp_path: Path
    ) -> None:
        _, out, _ = gold_dir_with(tmp_path)
        with pytest.raises(rounds.RoundError, match="is no question of dup-verdict round r1"):
            C.check_answer(out, "r1", "dup-nope", "{}")
        with pytest.raises(rounds.RoundError, match="is no pair calibration directory"):
            C.check_answer(tmp_path / "run" / "dup", "r1", "dup-pos-1", "{}")

    def test_the_cli_exits_1_on_a_shape_problem(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out, _ = gold_dir_with(tmp_path)
        answer = tmp_path / "a.json"
        answer.write_text(json.dumps({"cluster_id": "x", "members": []}), encoding="utf-8")
        argv = ["check-answer", "--stage-run", str(out), "--round", "r1", "--label", "dup-pos-1",
                "--text-file", str(answer)]  # fmt: skip
        assert C.main(argv) == 1
        assert "is not this question's" in capsys.readouterr().out


class TestTheDryRun:
    def root_with(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, structure: int) -> Path:
        """A main checkout with an identity run: an export, its parent candidates and their items."""
        from fields import harvest as H

        root = tmp_path / "root"
        run = common.run_dir(root)
        positives = [
            pair_row(n, "PART-OF", "Abu Simbel", "Abu Simbel Small Temple") for n in range(3)
        ]
        records = [
            candidate(brief_row(500 + 2 * k), brief_row(501 + 2 * k)) for k in range(structure)
        ]
        ids = {p[k] for p in positives for k in ("a", "b")} | {
            row["id"] for r in records for row in (r["parent"], *r["children"])
        }
        lines = [{"kind": "shown", "row": site(id=i)} for i in sorted(ids)]
        lines.append({"kind": "snapshot", "row": {"exported_at": "2026-10-24 13:12:02+00"}})
        run.mkdir(parents=True)
        (run / common.EXPORT_FILE).write_text(
            "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
        )
        common.write_jsonl(run / "PARENT_CANDIDATES.jsonl", records)
        pairs_file = tmp_path / "dup_pairs.jsonl"
        common.write_jsonl(pairs_file, positives)
        monkeypatch.setattr(C, "DUP_PAIRS", pairs_file)
        for qid, item in items_of(*records).items():
            path = H.entity_path(common.harvest_dir(root), qid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(item), encoding="utf-8")
        monkeypatch.setattr(C, "N_PARENT_POSITIVES", 3)
        monkeypatch.setattr(C, "N_PARENT_NEGATIVES", 4)
        return root

    def test_the_parent_dry_run_prints_the_pool_and_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self.root_with(tmp_path, monkeypatch, structure=5)
        monkeypatch.setattr(C, "read_facts", lambda *a: pytest.fail("a dry run reads production"))
        assert C.main(["--root", str(root), "read", "--kind", "parent", "--dry-run"]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert (printed["positive"], printed["negative"], printed["dry_run"]) == (3, 4, True)
        assert printed["by_source"][f"negative: {C.STRUCTURE_SOURCE}"] == 4
        assert printed["pool"]["structure"]["drawn"] == 5
        assert not C.cal_dir(common.run_dir(root), "parent").exists()

    def test_a_pool_short_of_the_sealed_count_is_refused_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self.root_with(tmp_path, monkeypatch, structure=3)
        assert C.main(["--root", str(root), "read", "--kind", "parent", "--dry-run"]) == 2
        assert "only 3 parent negatives" in capsys.readouterr().err


# ------------------------------------------------------------------------- the compared shapes
class TestTheComparedShapes:
    def test_a_verdict_answer_is_a_unit_per_site_with_the_survivor_in_it(self) -> None:
        text = gold_answer({"cluster_id": "c", "members": [{"id": A}, {"id": B}]}, {A: B})
        assert D._verdicts(text) == ((A, f"MERGE:{B}"), (B, "DISTINCT"))

    def test_a_parent_answer_is_a_unit_per_child(self) -> None:
        text = json.dumps(
            {
                "parent_id": A,
                "children": [{"site_id": B, "verdict": "PART", "why": "w", "quotes": []}],
            }
        )
        assert D._verdicts(text) == ((B, "PART"),)

    def test_a_recheck_answer_reads_its_decision_and_target(self) -> None:
        text = json.dumps(
            {
                "cluster_id": "c",
                "members": [
                    {"site_id": A, "decision": "RETARGET", "target": B, "why": "w", "quotes": []},
                    {"site_id": B, "decision": "REJECT", "target": None, "why": "w", "quotes": []},
                ],
            }
        )
        assert D._verdicts(text) == ((A, f"RETARGET:{B}"), (B, "REJECT"))

    @pytest.mark.parametrize(
        "text",
        [
            "not json",
            "[]",
            json.dumps({"members": [1]}),
            json.dumps({"members": [{"verdict": "MERGE"}]}),
            json.dumps({"members": [{"site_id": A}]}),
            json.dumps({"foo": 1}),
        ],
    )
    def test_what_is_no_identity_answer_is_not_read_as_one(self, text: str) -> None:
        assert D._verdicts(text) is None

    def test_the_older_shapes_are_read_as_before(self) -> None:
        assert D._verdicts(
            json.dumps({"sentences": [{"n": 1, "verdict": "keep"}], "coherent": True})
        ) == (("sentence-1", "keep"), ("coherent", "True"))

    def test_the_urls_of_the_quotes_are_listed_whatever_they_call_the_key(self) -> None:
        text = json.dumps(
            {
                "members": [
                    {
                        "site_id": A,
                        "verdict": "MERGE",
                        "survivor": B,
                        "quotes": [{"source": URL, "quote": "q"}],
                    }
                ],
                "sentences": [{"quotes": [{"url": "https://example.org/x"}]}],
            }
        )
        assert D._sources(text) == ("https://example.org/x", URL)

    def test_a_different_survivor_is_a_disagreement_and_a_false_merge_is_countable(self) -> None:
        recorded = {
            "l1": gold_answer({"cluster_id": "c", "members": [{"id": A}, {"id": B}]}, {A: B}),
            "l2": gold_answer({"cluster_id": "c", "members": [{"id": C_}, {"id": D_}]}, {}),
        }
        fresh = {
            "l1": gold_answer({"cluster_id": "c", "members": [{"id": A}, {"id": B}]}, {B: A}),
            "l2": gold_answer({"cluster_id": "c", "members": [{"id": C_}, {"id": D_}]}, {C_: D_}),
        }
        report = D.compare_answers("web_verifier", ["l1", "l2"], recorded, fresh).to_dict()
        assert report["units"] == 4 and report["agreed"] == 1 and report["agreement"] == 0.25
        assert C.false_merges(report) == 2  # B retired where the gold kept it, and C_ merged at all
        same = D.compare_answers("web_verifier", ["l1"], recorded, recorded).to_dict()
        assert same["agreement"] == 1.0 and same["unanswered"] == []
