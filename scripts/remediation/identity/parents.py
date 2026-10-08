"""D25: which shown sites are components of another shown site (`parent_site_id`)?

A candidate pair is two shown sites of one country within 2 km where the significant words of one
name are a strict subset of the other's ("Abu Simbel" and "Abu Simbel Small Temple"): the shorter
name is the parent, the longer the child. The column is empty on every row today; the page already
renders a "part of" link for a parent (`api/routes/sites_html.py`).

This is a candidate list, not a verdict. A pair can be a duplicate (it also shares an item), a
different place with a similar name, or a chain (the parent is itself a child). The record carries
what the later question needs: both items, the distance, and the flags `shared_qid` (one item
for both: a D14 cluster as well), `parent_is_child` (depth above one), `competing_parents`
(the child has more than one candidate parent). The write lane's own invariants (same country,
at most 5 km, parent shown and not a duplicate loser, depth one) are tested there.

Output `PARENT_CANDIDATES.jsonl`: one line per parent, the one with most children first.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import common, export  # noqa: E402

OUTPUT = "PARENT_CANDIDATES.jsonl"
MAX_METRES = 2000.0
#: One degree of latitude in metres: the sweep stops when the latitudes are further apart.
METRES_PER_DEGREE = 111_320.0
LIMITS = (200, 500, 1000, 2000)


def candidate_pairs(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[float, Mapping[str, Any], Mapping[str, Any]]]:
    """`(metres, parent, child)` for every pair within `MAX_METRES`, same country, whose parent's
    significant words are a strict subset of the child's."""
    words = {r["id"]: common.tokens(r["name"]) for r in rows}
    ordered = sorted(rows, key=lambda r: (r["lat"], r["id"]))
    reach = MAX_METRES / METRES_PER_DEGREE
    pairs: list[tuple[float, Mapping[str, Any], Mapping[str, Any]]] = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if b["lat"] - a["lat"] > reach:
                break
            if a["country"] != b["country"]:
                continue
            left, right = words[a["id"]], words[b["id"]]
            if not left or not right or left == right or not (left < right or right < left):
                continue
            metres = common.metres(a, b)
            if metres > MAX_METRES:
                continue
            pairs.append((metres, a, b) if left < right else (metres, b, a))
    return sorted(pairs, key=lambda p: (p[0], p[1]["id"], p[2]["id"]))


def brief(row: Mapping[str, Any], qids: Sequence[str]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "country": row["country"],
        "site_type": row["site_type"],
        "lat": row["lat"],
        "lon": row["lon"],
        "qids": list(qids),
        "images": row["images"],
        "links": row["links"],
        "description_lane": row["description_lane"],
        "parent_site_id": row["parent_site_id"],
    }


def build(exported: export.Export) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    qids = export.qids_by_site(exported.ext_ids)
    pairs = candidate_pairs(exported.shown)
    children_of: dict[str, list[tuple[float, Mapping[str, Any]]]] = defaultdict(list)
    parents_of: dict[str, set[str]] = defaultdict(set)
    parent_rows: dict[str, Mapping[str, Any]] = {}
    for metres, parent, child in pairs:
        children_of[parent["id"]].append((metres, child))
        parents_of[child["id"]].add(parent["id"])
        parent_rows[parent["id"]] = parent

    records: list[dict[str, Any]] = []
    for parent_id, kids in children_of.items():
        parent = parent_rows[parent_id]
        listed = []
        for metres, child in sorted(kids, key=lambda k: (k[0], k[1]["id"])):
            listed.append(
                {
                    **brief(child, qids.get(child["id"], [])),
                    "metres": round(metres, 1),
                    "shared_qid": bool(
                        set(qids.get(child["id"], [])) & set(qids.get(parent_id, []))
                    ),
                    "competing_parents": sorted(parents_of[child["id"]] - {parent_id}),
                }
            )
        records.append(
            {
                "parent": brief(parent, qids.get(parent_id, [])),
                "parent_is_child": parent_id in parents_of,
                "n_children": len(listed),
                "max_metres": listed[-1]["metres"],
                "children": listed,
            }
        )
    records.sort(
        key=lambda r: (-r["n_children"], r["parent"]["name"].casefold(), r["parent"]["id"])
    )

    counts: dict[str, Any] = {
        "shown": len(exported.shown),
        "pairs": len(pairs),
        "parents": len(records),
        "children": len(parents_of),
        "shared_qid_pairs": sum(1 for r in records for c in r["children"] if c["shared_qid"]),
        "parents_that_are_children": sum(1 for r in records if r["parent_is_child"]),
        "children_with_competing_parents": sum(1 for p in parents_of.values() if len(p) > 1),
        "parent_site_id_already_set": sum(1 for r in exported.shown if r["parent_site_id"]),
    }
    for limit in LIMITS:
        within = [p for p in pairs if p[0] <= limit]
        counts[f"pairs_within_{limit}m"] = len(within)
        counts[f"parents_within_{limit}m"] = len({p[1]["id"] for p in within})
    counts["largest_family"] = max((r["n_children"] for r in records), default=0)
    counts["countries"] = len(Counter(r["parent"]["country"] for r in records))
    return records, counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D25 parent candidates.")
    parser.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    args = parser.parse_args(argv)
    run = common.run_dir(args.root)
    exported = export.load_export(run / common.EXPORT_FILE)
    records, counts = build(exported)
    common.write_jsonl(run / OUTPUT, records)
    common.record_counts(run, "parents", counts)
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
