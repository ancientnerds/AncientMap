"""D14: which shown sites may be one site? Clusters, with the facts a judge needs.

Four funnels, each an edge between two shown sites; a cluster is a connected set of them:

* `shared_qid`   - the sites carry the same Wikidata item (43 items, 98 sites on 2026-10-08);
* `shared_enwiki` - the sites carry the same English article under different items (12 groups);
* `name_point`   - the same country, within 300 m, trigram similarity of the stored name keys above
                   0.5 (computed in SQL on production, `export.PAIRS_SQL`: 81 pairs);
* `bcases`       - a pair the owner-case classification judged DUP or PART-OF
                   (`output/remediation/bcases/dup_pairs.jsonl`, 181 pairs; a pair whose two sites
                   are not both still shown is counted and left out).

A cluster does not say "duplicate": a shared item is sometimes a class or a container (Abu Simbel,
Aspendos, Kilmartin) and sometimes the wrong item. It carries the distance, the images and links,
the description lane, the items and `created_at` of every member, and the edges that put them
together. The verdict (MERGE, PART_OF, WRONG_ID, DISTINCT) is a later, model-judged stage.

The curated rows already retired as `duplicate_of:<survivor>` that still hold images or links are
written beside the clusters as `retired_loser` records (22 of 25 hold images, 12 hold links): the
merge lane has to move them.

Output `DUP_CLUSTERS.jsonl`: first the clusters (largest first), then the retired losers.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import common, export  # noqa: E402

OUTPUT = "DUP_CLUSTERS.jsonl"
DUP_PAIRS = common.REPO / "output" / "remediation" / "bcases" / "dup_pairs.jsonl"
#: The classes of `bcases/dup_pairs.jsonl` that make an edge.
BCASES_CLASSES = ("DUP", "PART-OF")
BANDS = ((200, "<=200m"), (2000, "<=2km"), (20000, "<=20km"))
FAR = ">20km"


def band(metres: float) -> str:
    for limit, label in BANDS:
        if metres <= limit:
            return label
    return FAR


class Clusters:
    """Union-find over site ids, remembering the edge that joined them."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.edges: list[dict[str, Any]] = []

    def find(self, site: str) -> str:
        self.parent.setdefault(site, site)
        while self.parent[site] != site:
            self.parent[site] = self.parent[self.parent[site]]
            site = self.parent[site]
        return site

    def join(self, sites: Iterable[str], edge: dict[str, Any]) -> None:
        members = sorted(set(sites))
        self.edges.append({**edge, "sites": members})
        root = self.find(members[0])
        for other in members[1:]:
            self.parent[self.find(other)] = root

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for site in list(self.parent):
            out[self.find(site)].append(site)
        return {root: sorted(members) for root, members in out.items()}


def shared_qid_edges(qids: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    holders: dict[str, list[str]] = defaultdict(list)
    for site, listed in qids.items():
        for qid in listed:
            holders[qid].append(site)
    return {qid: sorted(sites) for qid, sites in sorted(holders.items()) if len(sites) > 1}


def shared_enwiki_edges(
    enwiki: Mapping[str, Sequence[str]], qids: Mapping[str, Sequence[str]]
) -> dict[str, list[str]]:
    """Articles held by more than one site where the holders do not all share one item."""
    holders: dict[str, list[str]] = defaultdict(list)
    for site, titles in enwiki.items():
        for title in titles:
            holders[title.replace("_", " ")].append(site)
    out: dict[str, list[str]] = {}
    for title, sites in sorted(holders.items()):
        if len(sites) < 2:
            continue
        items = {tuple(sorted(qids.get(s, ()))) for s in sites}
        if len(items) > 1:
            out[title] = sorted(sites)
    return out


def load_bcases(path: Path = DUP_PAIRS) -> list[dict[str, Any]]:
    return [r for r in common.read_jsonl(path) if r["class"] in BCASES_CLASSES]


def member(row: Mapping[str, Any], qids: Sequence[str], enwiki: Sequence[str]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "country": row["country"],
        "site_type": row["site_type"],
        "lat": row["lat"],
        "lon": row["lon"],
        "qids": list(qids),
        "enwiki": list(enwiki),
        "created_at": row["created_at"],
        "images": row["images"],
        "links": row["links"],
        "description_chars": row["description_chars"],
        "description_lane": row["description_lane"],
        "names_rows": row["names_rows"],
        "has_card": row["has_card"],
    }


def cluster_id(sites: Sequence[str]) -> str:
    return "dup-" + hashlib.sha256("\n".join(sorted(sites)).encode()).hexdigest()[:10]


def build(
    exported: export.Export, bcases: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    shown = common.rows_by_id(exported.shown)
    qids = export.qids_by_site(exported.ext_ids)
    enwiki = export.enwiki_by_site(exported.ext_ids)
    clusters = Clusters()
    counts: dict[str, Any] = {}

    for qid, sites in shared_qid_edges(qids).items():
        clusters.join(sites, {"kind": "shared_qid", "qid": qid})
    counts["shared_qid_items"] = len(clusters.edges)
    counts["shared_qid_sites"] = len({s for e in clusters.edges for s in e["sites"]})

    before = len(clusters.edges)
    for title, sites in shared_enwiki_edges(enwiki, qids).items():
        clusters.join(sites, {"kind": "shared_enwiki", "title": title})
    counts["shared_enwiki_groups"] = len(clusters.edges) - before

    before = len(clusters.edges)
    for pair in exported.pairs:
        clusters.join(
            (pair["a"], pair["b"]),
            {
                "kind": "name_point",
                "metres": pair["metres"],
                "similarity": pair["similarity"],
            },
        )
    counts["name_point_pairs"] = len(clusters.edges) - before

    before = len(clusters.edges)
    left_out = 0
    for pair in bcases:
        if pair["a"] not in shown or pair["b"] not in shown:
            left_out += 1
            continue
        clusters.join(
            (pair["a"], pair["b"]),
            {"kind": "bcases", "class": pair["class"], "metres": pair["distance_m"]},
        )
    counts["bcases_pairs"] = len(clusters.edges) - before
    counts["bcases_pairs_left_out_not_shown"] = left_out

    records: list[dict[str, Any]] = []
    for sites in clusters.groups().values():
        rows = sorted((shown[s] for s in sites), key=lambda r: (r["created_at"], r["id"]))
        distances = [common.metres(a, b) for a, b in combinations(rows, 2)]
        members = [member(r, qids.get(r["id"], []), enwiki.get(r["id"], [])) for r in rows]
        edges = [e for e in clusters.edges if e["sites"][0] in set(sites)]
        records.append(
            {
                "record": "cluster",
                "cluster_id": cluster_id(sites),
                "size": len(rows),
                "kinds": sorted({e["kind"] for e in edges}),
                "bcases_classes": sorted({e["class"] for e in edges if e["kind"] == "bcases"}),
                "max_distance_m": round(max(distances), 1),
                "min_distance_m": round(min(distances), 1),
                "distance_band": band(max(distances)),
                "edges": edges,
                "members": members,
            }
        )
    records.sort(key=lambda r: (-r["size"], r["cluster_id"]))
    counts["clusters"] = len(records)
    counts["cluster_sites"] = sum(r["size"] for r in records)
    counts["largest_cluster"] = max((r["size"] for r in records), default=0)
    counts["bands"] = {
        label: sum(1 for r in records if r["distance_band"] == label)
        for label in [b[1] for b in BANDS] + [FAR]
    }
    counts["kinds"] = {
        kind: sum(1 for r in records if kind in r["kinds"])
        for kind in ("shared_qid", "shared_enwiki", "name_point", "bcases")
    }

    losers = [
        {
            "record": "retired_loser",
            **loser,
            "holds": [k for k in ("images", "links") if loser[k] > 0],
        }
        for loser in exported.losers
        if loser["images"] > 0 or loser["links"] > 0
    ]
    counts["retired_losers"] = len(exported.losers)
    counts["retired_losers_holding"] = len(losers)
    counts["retired_losers_holding_images"] = sum(1 for r in losers if r["images"] > 0)
    counts["retired_losers_holding_links"] = sum(1 for r in losers if r["links"] > 0)
    counts["retired_losers_survivor_not_shown"] = sum(
        1 for r in exported.losers if r["survivor_scope_status"] == "retired"
    )
    return records + losers, counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D14 duplicate clusters.")
    parser.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    args = parser.parse_args(argv)
    run = common.run_dir(args.root)
    exported = export.load_export(run / common.EXPORT_FILE)
    records, counts = build(exported, load_bcases())
    common.write_jsonl(run / OUTPUT, records)
    common.record_counts(run, "dup_clusters", counts)
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
