"""D13 funnel: which records may describe a modern town instead of the ancient site?"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from identity import funnel  # noqa: E402

from tests.remediation.identity_fixtures import (  # noqa: E402
    entity,
    export_of,
    ext,
    site,
    store_of,
)

CLASSES = {
    "Q1": "village",
    "Q2": "civil parish",
    "Q3": "archaeological site",
    "Q4": "ancient city",
    "Q5": "village in a park",
    "Q6": "Roman villa",
}


class TestTheClassLabels:
    def test_a_village_is_a_modern_settlement_class(self) -> None:
        assert funnel.modern_class("village")
        assert funnel.modern_class("civil parish")
        assert funnel.modern_class("municipality of Spain")

    def test_an_ancient_settlement_class_is_not_modern(self) -> None:
        for label in ("ancient city", "deserted village", "Roman city", "former municipality"):
            assert not funnel.modern_class(label), label

    def test_the_settlement_cut_comes_first_a_resort_is_not_a_settlement_class(self) -> None:
        assert not funnel.modern_class("seaside resort")

    def test_a_class_that_is_no_settlement_is_not_modern(self) -> None:
        assert not funnel.modern_class("archaeological site")
        assert not funnel.modern_class("mountain")

    def test_a_modern_class_is_never_also_archaeological(self) -> None:
        # "village in a park" matches the modern pattern and the word "park"
        modern, archaeological = funnel.classify_classes(["village in a park", "Roman villa"])
        assert modern == ["village in a park"]
        assert archaeological == ["Roman villa"]


class TestTheOpening:
    def test_the_word_village_is_not_an_archaeological_villa(self) -> None:
        sentence = "Pure is a village in Kent."
        assert funnel.OPENING.search(sentence)
        assert not funnel.OPENING_ARCHAEOLOGICAL.search(sentence)
        assert funnel.OPENING_ARCHAEOLOGICAL.search("Mixed is a village with a Roman villa.")

    def test_the_first_sentence_loses_its_citation_markers(self) -> None:
        text = "Foo is a village in Kent [1] [2]. It has a church."
        assert funnel.first_sentence(text) == "Foo is a village in Kent."

    def test_a_description_that_opens_on_a_village_is_an_opening(self) -> None:
        match = funnel.OPENING.search("Bayston Hill is a village in Shropshire, England.")
        assert match and match.group(1) == "village"

    def test_a_description_that_opens_on_an_ancient_site_is_not(self) -> None:
        assert not funnel.OPENING.search("Stonehenge is a prehistoric monument in Wiltshire.")

    def test_the_verb_may_come_late_but_not_after_eighty_characters(self) -> None:
        near = "Foo, in the county of Bar, near the sea, is a hamlet."
        far = "x" * 90 + " is a hamlet."
        assert funnel.OPENING.search(near)
        assert not funnel.OPENING.search(far)


class TestTheTiers:
    def test_a_modern_class_with_an_opening_is_the_first_tier(self) -> None:
        assert funnel.tier_of("A", True, False) == "A+rx"
        assert funnel.tier_of("B", True, False) == "B+rx"

    def test_each_signal_alone_has_its_own_tier(self) -> None:
        assert funnel.tier_of("A", False, False) == "A"
        assert funnel.tier_of(None, True, False) == "rx"
        assert funnel.tier_of("B", False, False) == "B"
        assert funnel.tier_of(None, False, True) == "shared_qid"

    def test_a_site_with_no_signal_has_no_tier(self) -> None:
        assert funnel.tier_of(None, False, False) is None

    def test_the_best_tier_wins_over_a_shared_item(self) -> None:
        assert funnel.tier_of("A", False, True) == "A"


class TestTheFunnel:
    def run(self, tmp_path, shown, ext_ids, items):
        store = store_of(tmp_path, items, CLASSES)
        return funnel.build(export_of(shown, ext_ids=ext_ids), store)

    def test_a_site_whose_item_is_a_village_is_tier_a_and_carries_its_evidence(
        self, tmp_path
    ) -> None:
        town = site(name="Tiverton", description="Tiverton lies on the Exe in Devon [1].")
        records, counts = self.run(
            tmp_path,
            [town],
            [ext(town["id"], "wikidata_qid", "Q10")],
            {"Q10": entity("Q10", p31=("Q1", "Q2"))},
        )
        assert [r["tier"] for r in records] == ["A"]
        record = records[0]
        assert record["p31_modern"] == ["civil parish", "village"]
        assert record["p31_archaeological"] == []
        assert record["sentence1"] == "Tiverton lies on the Exe in Devon."
        assert record["entity_source"] == {"Q10": "harvest"}
        assert counts["p31_A"] == 1

    def test_a_village_that_is_also_an_archaeological_site_is_tier_b(self, tmp_path) -> None:
        both = site(name="Both")
        records, _ = self.run(
            tmp_path,
            [both],
            [ext(both["id"], "wikidata_qid", "Q11")],
            {"Q11": entity("Q11", p31=("Q1", "Q3"))},
        )
        assert [r["tier"] for r in records] == ["B"]

    def test_a_site_with_no_signal_is_not_listed(self, tmp_path) -> None:
        plain = site()
        records, counts = self.run(
            tmp_path,
            [plain],
            [ext(plain["id"], "wikidata_qid", "Q12")],
            {"Q12": entity("Q12", p31=("Q3",))},
        )
        assert records == [] and counts["listed"] == 0

    def test_two_sites_that_share_an_item_are_each_listed_with_the_other_named(
        self, tmp_path
    ) -> None:
        one, two = site(name="Alba Fucens"), site(name="Amphitheatre Alba Fucens")
        records, counts = self.run(
            tmp_path,
            [one, two],
            [ext(one["id"], "wikidata_qid", "Q13"), ext(two["id"], "wikidata_qid", "Q13")],
            {"Q13": entity("Q13", p31=("Q3",))},
        )
        assert {r["tier"] for r in records} == {"shared_qid"}
        by_name = {r["name"]: r for r in records}
        assert by_name["Alba Fucens"]["shared_with"] == [
            {"id": two["id"], "name": "Amphitheatre Alba Fucens"}
        ]
        assert counts["shared_qid"] == 2

    def test_a_site_is_never_shared_with_itself(self, tmp_path) -> None:
        alone = site()
        records, counts = self.run(
            tmp_path,
            [alone],
            [ext(alone["id"], "wikidata_qid", "Q14")],
            {"Q14": entity("Q14", p31=("Q3",))},
        )
        assert records == [] and counts["shared_qid"] == 0

    def test_a_site_whose_item_no_root_holds_is_counted_not_guessed(self, tmp_path) -> None:
        orphan = site()
        records, counts = self.run(
            tmp_path, [orphan], [ext(orphan["id"], "wikidata_qid", "Q15")], {}
        )
        assert records == [] and counts["entity_missing"] == 1

    def test_a_delta_item_is_marked_as_the_delta(self, tmp_path) -> None:
        late = site()
        store = store_of(tmp_path, {}, CLASSES, delta={"Q16": entity("Q16", p31=("Q1",))})
        records, _ = funnel.build(
            export_of([late], ext_ids=[ext(late["id"], "wikidata_qid", "Q16")]), store
        )
        assert records[0]["entity_source"] == {"Q16": "delta"}

    def test_an_opening_that_names_an_ancient_cue_is_not_a_pure_opening(self, tmp_path) -> None:
        pure = site(name="Pure", description="Pure is a village in Kent.")
        mixed = site(name="Mixed", description="Mixed is a village with a Roman villa.")
        records, counts = self.run(tmp_path, [pure, mixed], [], {})
        assert counts["opening"] == 2 and counts["opening_pure"] == 1
        # the pure opening is listed before the mixed one within the same tier
        assert [r["name"] for r in records] == ["Pure", "Mixed"]

    def test_the_records_are_ordered_by_tier_first(self, tmp_path) -> None:
        a_only = site(name="Aaa A only")
        opening = site(name="Zzz opening", description="Zzz is a hamlet in Kent.")
        both = site(name="Mmm both", description="Mmm is a village in Kent.")
        ids = [
            ext(a_only["id"], "wikidata_qid", "Q20"),
            ext(both["id"], "wikidata_qid", "Q21"),
        ]
        items = {"Q20": entity("Q20", p31=("Q1",)), "Q21": entity("Q21", p31=("Q1",))}
        records, _ = self.run(tmp_path, [a_only, opening, both], ids, items)
        assert [r["tier"] for r in records] == ["A+rx", "A", "rx"]
