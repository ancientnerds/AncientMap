"""D14 duplicate clusters: the four funnels, one cluster per connected set, the facts a judge needs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from identity import dup_clusters as D  # noqa: E402

from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402


def loser(**over):
    row = {
        "id": "l1",
        "name": "Old",
        "created_at": "2026-03-04 00:00:00",
        "survivor_id": "s1",
        "survivor_name": "New",
        "survivor_scope_status": None,
        "images": 0,
        "images_all": 0,
        "links": 0,
        "survivor_images": 0,
        "survivor_links": 0,
        "name_is_alias_on_survivor": False,
    }
    row.update(over)
    return row


class TestTheUnion:
    def test_edges_that_share_a_site_make_one_cluster(self) -> None:
        clusters = D.Clusters()
        clusters.join(["a", "b"], {"kind": "x"})
        clusters.join(["b", "c"], {"kind": "y"})
        clusters.join(["d", "e"], {"kind": "x"})
        groups = sorted(clusters.groups().values())
        assert groups == [["a", "b", "c"], ["d", "e"]]

    def test_the_distance_band_is_the_first_limit_not_exceeded(self) -> None:
        assert D.band(0) == "<=200m"
        assert D.band(200) == "<=200m"
        assert D.band(200.1) == "<=2km"
        assert D.band(20000) == "<=20km"
        assert D.band(20001) == ">20km"


class TestTheFunnels:
    def test_a_shared_item_is_an_edge_only_with_two_holders(self) -> None:
        qids = {"a": ["Q1"], "b": ["Q1"], "c": ["Q2"]}
        assert D.shared_qid_edges(qids) == {"Q1": ["a", "b"]}

    def test_a_shared_article_under_different_items_is_an_edge(self) -> None:
        enwiki = {"a": ["Foo_bar"], "b": ["Foo bar"]}
        qids = {"a": ["Q1"], "b": ["Q2"]}
        assert D.shared_enwiki_edges(enwiki, qids) == {"Foo bar": ["a", "b"]}

    def test_a_shared_article_under_one_item_is_left_to_the_shared_item(self) -> None:
        enwiki = {"a": ["Foo"], "b": ["Foo"]}
        qids = {"a": ["Q1"], "b": ["Q1"]}
        assert D.shared_enwiki_edges(enwiki, qids) == {}

    def test_an_article_held_once_is_no_edge(self) -> None:
        assert D.shared_enwiki_edges({"a": ["Foo"]}, {"a": ["Q1"]}) == {}

    def test_only_the_dup_and_part_of_pairs_of_the_owner_cases_count(self, tmp_path) -> None:
        path = tmp_path / "dup_pairs.jsonl"
        classes = ["DUP", "PART-OF", "NEITHER", "WRONG-ID"]
        path.write_text(
            "".join(
                f'{{"a": "a{i}", "b": "b{i}", "class": "{c}", "distance_m": 1.0}}\n'
                for i, c in enumerate(classes)
            ),
            encoding="utf-8",
        )
        assert [p["class"] for p in D.load_bcases(path)] == ["DUP", "PART-OF"]


class TestTheClusters:
    def test_a_shared_item_makes_a_cluster_with_the_facts_of_each_member(self) -> None:
        a = site(name="Dolmen de Menga", lat=37.0, lon=-4.0, images=3, links=2)
        b = site(name="Dolmen of Menga", lat=37.0, lon=-4.001, images=0, links=0)
        records, counts = D.build(
            export_of(
                [a, b],
                ext_ids=[
                    ext(a["id"], "wikidata_qid", "Q1"),
                    ext(b["id"], "wikidata_qid", "Q1"),
                    ext(a["id"], "enwiki_title", "Menga"),
                ],
            ),
            [],
        )
        assert counts["clusters"] == 1 and counts["shared_qid_items"] == 1
        cluster = records[0]
        assert cluster["record"] == "cluster" and cluster["size"] == 2
        assert cluster["kinds"] == ["shared_qid"]
        assert cluster["distance_band"] == "<=200m"
        by_name = {m["name"]: m for m in cluster["members"]}
        assert by_name["Dolmen de Menga"]["images"] == 3
        assert by_name["Dolmen de Menga"]["enwiki"] == ["Menga"]
        assert by_name["Dolmen of Menga"]["qids"] == ["Q1"]

    def test_a_name_and_point_pair_makes_a_cluster_without_any_id(self) -> None:
        a, b = site(name="Oldbury"), site(name="Oldbury Camp")
        records, counts = D.build(
            export_of(
                [a, b], pairs=[{"a": a["id"], "b": b["id"], "metres": 40.0, "similarity": 0.7}]
            ),
            [],
        )
        assert counts["name_point_pairs"] == 1
        assert records[0]["edges"][0]["similarity"] == 0.7

    def test_the_members_are_ordered_by_age_then_id(self) -> None:
        old = site(name="Old", created_at="2026-01-01 00:00:00")
        new = site(name="New", created_at="2026-05-01 00:00:00")
        records, _ = D.build(
            export_of(
                [new, old],
                pairs=[{"a": old["id"], "b": new["id"], "metres": 5.0, "similarity": 0.9}],
            ),
            [],
        )
        assert [m["name"] for m in records[0]["members"]] == ["Old", "New"]

    def test_an_owner_case_pair_with_a_retired_site_is_counted_and_left_out(self) -> None:
        a = site()
        pair = {"a": a["id"], "b": "not-shown", "class": "DUP", "distance_m": 3.0}
        records, counts = D.build(export_of([a]), [pair])
        assert records == [] and counts["bcases_pairs_left_out_not_shown"] == 1

    def test_an_owner_case_pair_between_shown_sites_is_an_edge(self) -> None:
        a, b = site(), site()
        pair = {"a": a["id"], "b": b["id"], "class": "PART-OF", "distance_m": 90.0}
        records, counts = D.build(export_of([a, b]), [pair])
        assert counts["bcases_pairs"] == 1
        assert records[0]["bcases_classes"] == ["PART-OF"]

    def test_the_clusters_come_largest_first(self) -> None:
        a, b, c, d, e = (site() for _ in range(5))
        pairs = [
            {"a": a["id"], "b": b["id"], "metres": 1.0, "similarity": 0.9},
            {"a": c["id"], "b": d["id"], "metres": 1.0, "similarity": 0.9},
            {"a": d["id"], "b": e["id"], "metres": 1.0, "similarity": 0.9},
        ]
        records, _ = D.build(export_of([a, b, c, d, e], pairs=pairs), [])
        assert [r["size"] for r in records] == [3, 2]

    def test_the_cluster_id_does_not_depend_on_the_order_of_the_members(self) -> None:
        assert D.cluster_id(["b", "a"]) == D.cluster_id(["a", "b"])
        assert D.cluster_id(["a", "b"]) != D.cluster_id(["a", "c"])


class TestTheRetiredLosers:
    def test_a_loser_that_holds_nothing_is_not_listed(self) -> None:
        records, counts = D.build(export_of([site()], losers=[loser()]), [])
        assert records == [] and counts["retired_losers"] == 1
        assert counts["retired_losers_holding"] == 0

    def test_a_loser_that_holds_images_or_links_is_listed_with_what_it_holds(self) -> None:
        both = loser(id="l1", images=4, links=1)
        images = loser(id="l2", images=2)
        links = loser(id="l3", links=5)
        records, counts = D.build(
            export_of([site()], losers=[both, images, links, loser(id="l4")]), []
        )
        held = {r["id"]: r["holds"] for r in records if r["record"] == "retired_loser"}
        assert held == {"l1": ["images", "links"], "l2": ["images"], "l3": ["links"]}
        assert counts["retired_losers_holding_images"] == 2
        assert counts["retired_losers_holding_links"] == 2

    def test_a_loser_whose_survivor_is_retired_too_is_counted(self) -> None:
        _, counts = D.build(
            export_of([site()], losers=[loser(survivor_scope_status="retired")]), []
        )
        assert counts["retired_losers_survivor_not_shown"] == 1
