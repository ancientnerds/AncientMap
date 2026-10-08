"""D13: which records may describe a modern town or village instead of the ancient site?

The owner's decision D13 re-targets such a record to the ancient site (name, ids, description,
gallery). The funnel only chooses *what to ask*: three deterministic signals over the 4,900 shown
sites, each cheap and each noisy on its own (`plans/identity.md` section 2: 265 of the 346 tier A
sites are typed City/town/settlement, and some Wikidata items are simply the municipality).

* **P31** - the linked item is an instance of a modern settlement class (`MODERN`, a class label
  that is not an ancient/former/ruined kind, `NOT_MODERN`). *Tier A*: and none of its classes is an
  archaeological class (`ARCHAEOLOGICAL`); *tier B*: it has one as well.
* **Opening** - the first sentence of the description opens "X is a village/town/municipality/
  mountain/..." (`OPENING`). `opening_pure` when the sentence also carries no archaeological cue.
* **Shared item** - another shown site carries the same Wikidata item (the Alba Fucens amphitheatre
  type: a site linked to the item of the place around it).

Tiers, best first: `A+rx`, `B+rx`, `A`, `rx`, `B`, `shared_qid`. A site is listed at its best tier
with the evidence of every signal. The items come from `entities.EntityStore`; a site whose item no
root holds is listed in the counts as `entity_missing` (the run fetches them first).

Output `IDENTITY_FUNNEL.jsonl`, one line per site, sorted by tier, then pure opening, then name.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import common, entities, export  # noqa: E402

OUTPUT = "IDENTITY_FUNNEL.jsonl"
TIERS = ("A+rx", "B+rx", "A", "rx", "B", "shared_qid")

#: A class label that names a settlement (the first cut, as measured 2026-10-08).
SETTLEMENT = re.compile(
    r"\b(village|town|city|commune|civil parish|parish|municipality|hamlet|settlement|human "
    r"settlement|locality|borough|township|suburb|neighbourhood|neighborhood|frazione|comune|urban "
    r"area|census-designated|populated place|inhabited|market town|community|ward|district)\b",
    re.I,
)
#: ... and one that names a *modern* one.
MODERN = re.compile(
    r"^(village|civil parish|commune|comune|municipality|town|hamlet|frazione|locality|"
    r"neighbou?rhood|suburb|city|big city|market town|urban|settlement in|cadastral|community of|"
    r"municipal|parish|census|borough|township|seaside resort|spa town|college town|port city|"
    r"oblast seat|place with town|urban area)|(village of|commune of|comune of|municipality of|"
    r"town in|city in|village in|locality of|community of|city of|urban municipality|settlement in)",
    re.I,
)
#: A settlement class that is not a modern one (an ancient city, a former village, a polis ...).
NOT_MODERN = re.compile(
    r"(ancient|roman|former|abandoned|deserted|lost|destroyed|submerged|city[- ]state|city gate|"
    r"city wall|city-kingdom|historical|polis|colony|castrum|iberian|celtiberian|neolithic|bronze|"
    r"iron age|medieval|ruin|ghost|prehistoric|oppidum|municipium|vicus|civitas)",
    re.I,
)
#: A class label that names an archaeological or heritage kind.
ARCHAEOLOGICAL = re.compile(
    r"(archaeolog|ancient|ruin|polis|tell|necropolis|hillfort|hill fort|castle|temple|tomb|grave|"
    r"barrow|burial|mound|cave|villa|stone|dolmen|menhir|henge|cairn|broch|oppidum|pyramid|"
    r"castrum|settlement site|bronze age|neolithic|iron age|roman|monument|fort|wall|gate|rock|"
    r"cultural property|cultural heritage|historic site|museum|park|church|monastery|abbey|"
    r"cemetery|megalith|petroglyph|geoglyph|lost|abandoned|former|destroyed|submerged|deserted)",
    re.I,
)
#: "... is a village" at the start of the first sentence (at most 80 characters before the verb).
OPENING = re.compile(
    r"^(?:[^.]{0,80}?\b)?(?:is|was|are) (?:an? |the )?(?:small |large |historic |modern |former |"
    r"old |market |coastal |rural |urban |mountain(?:ous)? )*(village|municipality|commune|civil "
    r"parish|parish|town|city|hamlet|frazione|comune|suburb|neighbou?rhood|locality|townland|"
    r"borough|district|settlement|island|peninsula|mountain|river|region|county)\b",
    re.I,
)
#: ... and a first sentence that says it is about the ancient place all the same.
OPENING_ARCHAEOLOGICAL = re.compile(
    r"(archaeolog|ancient|ruin|site of|hillfort|hill fort|roman|iron age|bronze age|neolithic|"
    r"prehistoric|palaeolith|paleolith|mesolith|fort\b|castle|temple|tomb|cemetery|barrow|mound|"
    r"megalith|settlement site|oppidum|villas?|amphitheat|theatre|necropolis|burial)",
    re.I,
)
CITATION = re.compile(r"\s*\[[0-9][0-9,\s\-–]*\]")
FIRST_SENTENCE = re.compile(r"[^.]*\.")


def first_sentence(description: str) -> str:
    """The description's first sentence without its citation markers."""
    text = CITATION.sub("", description)
    found = FIRST_SENTENCE.match(text)
    return found.group(0) if found else text


def modern_class(label: str) -> bool:
    return bool(SETTLEMENT.search(label) and MODERN.search(label) and not NOT_MODERN.search(label))


def classify_classes(labels: Sequence[str]) -> tuple[list[str], list[str]]:
    """`(modern, archaeological)` among an item's P31 class labels. A label that is modern is
    never also counted as archaeological."""
    modern = [label for label in labels if modern_class(label)]
    archaeological = [
        label for label in labels if ARCHAEOLOGICAL.search(label) and label not in modern
    ]
    return modern, archaeological


def tier_of(p31_tier: str | None, opening: bool, shared: bool) -> str | None:
    """The best tier a site's signals reach; `None` when it has none."""
    if p31_tier == "A" and opening:
        return "A+rx"
    if p31_tier == "B" and opening:
        return "B+rx"
    if p31_tier == "A":
        return "A"
    if opening:
        return "rx"
    if p31_tier == "B":
        return "B"
    if shared:
        return "shared_qid"
    return None


def build(
    exported: export.Export, store: entities.EntityStore
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The funnel records and their counts."""
    qids = export.qids_by_site(exported.ext_ids)
    enwiki = export.enwiki_by_site(exported.ext_ids)
    holders: dict[str, list[str]] = defaultdict(list)
    for site_id, listed in qids.items():
        for qid in listed:
            holders[qid].append(site_id)
    by_id = {row["id"]: row for row in exported.shown}

    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in exported.shown:
        site_id = row["id"]
        labels: list[str] = []
        sources: dict[str, str | None] = {}
        for qid in qids.get(site_id, []):
            entity, source = store.get(qid)
            sources[qid] = source
            if entity is None:
                counts["entity_missing"] += 1
                continue
            labels.extend(store.class_label(c) for c in entities.instance_of(entity))
        modern, archaeological = classify_classes(labels)
        p31_tier = ("B" if archaeological else "A") if modern else None
        sentence = first_sentence(row["description"])
        opened = OPENING.search(sentence)
        pure = bool(opened) and not OPENING_ARCHAEOLOGICAL.search(sentence)
        sharing = sorted({o for q in qids.get(site_id, []) for o in holders[q]} - {site_id})
        tier = tier_of(p31_tier, bool(opened), bool(sharing))
        counts["p31_" + (p31_tier or "none")] += 1
        counts["opening"] += bool(opened)
        counts["opening_pure"] += pure
        counts["shared_qid"] += bool(sharing)
        if tier is None:
            continue
        counts["tier_" + tier] += 1
        records.append(
            {
                "id": site_id,
                "name": row["name"],
                "country": row["country"],
                "site_type": row["site_type"],
                "tier": tier,
                "signals": {
                    "p31_tier": p31_tier,
                    "opening": bool(opened),
                    "opening_pure": pure,
                    "shared_qid": bool(sharing),
                },
                "qids": qids.get(site_id, []),
                "enwiki": enwiki.get(site_id, []),
                "entity_source": sources,
                "p31": sorted(set(labels)),
                "p31_modern": sorted(set(modern)),
                "p31_archaeological": sorted(set(archaeological)),
                "sentence1": sentence,
                "opening_match": opened.group(1).lower() if opened else None,
                "shared_with": [{"id": o, "name": by_id[o]["name"]} for o in sharing],
                "description_lane": row["description_lane"],
                "images": row["images"],
                "links": row["links"],
                "period_start": row["period_start"],
                "period_name": row["period_name"],
                "source_url": row["source_url"],
            }
        )
    records.sort(
        key=lambda r: (
            TIERS.index(r["tier"]),
            not r["signals"]["opening_pure"],
            r["name"].casefold(),
            r["id"],
        )
    )
    counts_out: dict[str, Any] = {
        "shown": len(exported.shown),
        "listed": len(records),
        "p31_union_opening": sum(
            1 for r in records if r["signals"]["p31_tier"] or r["signals"]["opening"]
        ),
        **dict(sorted(counts.items())),
    }
    return records, counts_out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D13 funnel: modern-town records.")
    parser.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="fetch the items the harvest lacks (wbgetentities, 50 per call, 1 request/s) first",
    )
    args = parser.parse_args(argv)
    run = common.run_dir(args.root)
    exported = export.load_export(run / common.EXPORT_FILE)
    store = entities.default_store(args.root)
    if args.fetch:
        wanted = [q for listed in export.qids_by_site(exported.ext_ids).values() for q in listed]
        print(
            "fetch:",
            entities.fetch_delta(wanted, common.harvest_dir(args.root), entities.delta_dir(run)),
        )
        store = entities.default_store(args.root)
    records, counts = build(exported, store)
    common.write_jsonl(run / OUTPUT, records)
    common.record_counts(run, "funnel", counts)
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
