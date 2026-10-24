"""The calibration sets of the duplicate verdict (D14) and the parent question (D25).

Owner decision D6 (2026-10-08): a role calibrates against already-judged cases with a threshold
sealed before its first answer (`calibrate_claude.py`). The two identity roles are the web verifier
(Sonnet, high) of `dup-verdict` and `parent-verdict`; the pool they are measured on is a handoff
directory of **answered** questions, and an answer in it must be a real model's (the seal refuses a
MiniMax stamp and an unstamped one), so this module builds the questions and checks the gold, and
never writes an answer itself.

**Duplicates** - `dup_cases`: the positives are the pairs that were judged one site before - the 19
retired by the scope lane (`bcases/DUPLICATES.jsonl`) and the 5 of the owner's decision O9
(`mechanical/dups.PAIRS`), 24 pairs once Banias, which is in both lists, is counted once. The
negatives are 15 pairs the owner-case classification called `WRONG-ID` or `NEITHER`
(`bcases/dup_pairs.jsonl`: a shared item that names a class or a neighbour), the pairs named in
`--negative A=B` and nothing else; **no negative was judged by a model yet**, so
the gold is made by one labelling: `export` writes every case as a `dup-verdict` question, Opus xhigh
agents answer it blind in the role `pilot_judge`, and `gold-check` holds those answers to what was
known - every positive must come out MERGE, and a positive the gold calls something else is listed
for the orchestrator to decide before the pool is sealed. The pool is then the answered batches.

**Parents** - `parent_cases`: 20 `PART-OF` pairs of `dup_pairs.jsonl` with nested names (positives) and
10 negatives: the 2 `NEITHER` pairs with nested names (two parts of one item, neither the other's),
completed from the run's own `PARENT_CANDIDATES.jsonl` (`structure_negatives`: a would-be parent of
`STRUCTURE_TYPES` only, both sites with distinct Wikidata items that were read, no P361/P527 statement
placing the child in the parent; a seeded draw, one per parent and per child). A pair's parent is the
one whose significant words are the subset (`parents.candidate_pairs`' rule). Fewer than the sealed
count is refused, never a smaller set. The same blind labelling by Opus xhigh makes the gold, and the
classes are the cross-check that `gold-check` reports (a heuristic: a disagreement is listed, not
failed).

**Briefing the gold.** `read` and `export` keep a calibration in `<run>/calibration/<kind>`. Briefed
with `--stage-run` at that directory, `dup_judge.py brief` / `parent_judge.py brief` name the gold
role `pilot_judge` (the default, and the only role allowed into the round's own handoff) and point the
shape check at `check-answer` here, which reads the calibration's own cases; briefed into another
handoff (the `calibrate_claude.py prepare` copy) they name the role under calibration, never
`pilot_judge`. A production verdict round refuses `pilot_judge` (`label_rounds.brief_role`).

Sealing is `calibrate_claude.py seal --id ID --role web_verifier --handoff DIR --batches ...
--threshold 0.92` (the plan's 92 %), and the gate of "0 false MERGE" is carried by the verdict's
`--false-sources`: pass the spot-check count plus `false_merges(comparison)`.

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/identity/pair_calibration.py read --kind dup --dry-run   # the pool, no read
    $PY scripts/remediation/identity/pair_calibration.py read --kind dup
    $PY scripts/remediation/identity/pair_calibration.py export --kind dup --handoff output/remediation/handoff/cal-dup-gold
    $PY scripts/remediation/identity/dup_judge.py brief --stage dup-verdict --round r1 --batch-id r1-b01 --stage-run <run>/calibration/dup
    # Opus xhigh agents answer as pilot_judge, then:
    $PY scripts/remediation/identity/pair_calibration.py gold-check --kind dup --handoff output/remediation/handoff/cal-dup-gold
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import opus_handoff as OH  # noqa: E402
from fields import harvest as H  # noqa: E402
from mechanical import dups  # noqa: E402
from mechanical import plan as P  # noqa: E402

from identity import common, dup_clusters, dup_judge, export, parent_judge, parents  # noqa: E402
from identity import label_rounds as rounds  # noqa: E402
from identity.wiki import WikiIndex, load_cache  # noqa: E402

BCASES = common.REPO / "output" / "remediation" / "bcases"
DUPLICATES = BCASES / "DUPLICATES.jsonl"
DUP_PAIRS = BCASES / "dup_pairs.jsonl"
N_NEGATIVES = 15
N_PARENT_POSITIVES = 20
N_PARENT_NEGATIVES = 10
GOLD_ROLE = rounds.GOLD_ROLE
READ_FILE = "READ.jsonl"
KINDS = (dup_judge.CALIBRATION_KIND, parent_judge.CALIBRATION_KIND)
#: The verdict stage whose questions a calibration of each kind asks.
STAGES = {
    dup_judge.CALIBRATION_KIND: dup_judge.STAGE_VERDICT,
    parent_judge.CALIBRATION_KIND: parent_judge.STAGE_VERDICT,
}
NEGATIVE_CLASSES = ("WRONG-ID", "NEITHER")


@dataclass(frozen=True)
class Case:
    """One calibration case: a pair of sites, what was known of it, and where that came from."""

    case_id: str
    kind: str  # positive | negative
    a: str
    b: str
    #: for a positive, the loser and survivor the earlier judgement named; `None` for a negative
    expected: Mapping[str, str] | None
    source: str

    def sites(self) -> tuple[str, str]:
        return (self.a, self.b)


def case_id(prefix: str, a: str, b: str) -> str:
    digest = hashlib.sha256("\n".join(sorted((a, b))).encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


def _hash_order(pair: Mapping[str, Any]) -> str:
    return hashlib.sha256(f"{pair['a']}|{pair['b']}".encode()).hexdigest()


# ------------------------------------------------------------------------------------ duplicates
def dup_cases(
    duplicates: Sequence[Mapping[str, Any]],
    o9: Sequence[tuple[str, str]],
    pairs: Sequence[Mapping[str, Any]],
    *,
    extra_negatives: Sequence[tuple[str, str]] = (),
    n_negatives: int = N_NEGATIVES,
) -> list[Case]:
    """The duplicate calibration cases: every pair judged one site before (by loser id, so a pair in
    both lists counts once), then `n_negatives` negatives - the extra ones first, the rest of the
    `WRONG-ID` class before the `NEITHER` class, each class in a hash order, so the choice is the
    same on every run."""
    cases: dict[str, Case] = {}
    for item in duplicates:
        loser, survivor = item["loser_id"], item["survivor_id"]
        cases[loser] = Case(
            case_id("dup-pos", loser, survivor), "positive", loser, survivor,
            {"loser": loser, "survivor": survivor}, "bcases/DUPLICATES.jsonl",
        )  # fmt: skip
    for loser, survivor in o9:
        cases.setdefault(
            loser,
            Case(
                case_id("dup-pos", loser, survivor), "positive", loser, survivor,
                {"loser": loser, "survivor": survivor}, "mechanical/dups.PAIRS (O9)",
            ),
        )  # fmt: skip
    negatives = [
        Case(case_id("dup-neg", a, b), "negative", a, b, None, "named negative")
        for a, b in extra_negatives
    ]
    seen = {frozenset(c.sites()) for c in negatives}
    for klass in NEGATIVE_CLASSES:
        for pair in sorted((p for p in pairs if p["class"] == klass), key=_hash_order):
            key = frozenset((pair["a"], pair["b"]))
            if key in seen:
                continue
            seen.add(key)
            negatives.append(
                Case(
                    case_id("dup-neg", pair["a"], pair["b"]),
                    "negative",
                    pair["a"],
                    pair["b"],
                    None,
                    f"bcases/dup_pairs.jsonl {klass}",
                )
            )
    if len(negatives) < n_negatives:
        raise P.PlanError(f"only {len(negatives)} negatives available, {n_negatives} wanted")
    return sorted(cases.values(), key=lambda c: c.case_id) + negatives[:n_negatives]


def resolve_named(shown_rows: Sequence[Mapping[str, Any]], a: str, b: str) -> tuple[str, str]:
    """The ids of two shown sites named `a` and `b`; a name that is not exactly one site is refused."""
    found = []
    for name in (a, b):
        ids = [r["id"] for r in shown_rows if r["name"] == name]
        if len(ids) != 1:
            raise P.PlanError(f"{name!r} names {len(ids)} shown sites, not one")
        found.append(ids[0])
    return found[0], found[1]


def facts_parts(site_ids: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """The read of the cases' sites: the columns `export` reads for every shown site, for exactly
    these ids (a retired loser included)."""
    ids = P.sql_ids(site_ids)
    swaps = (
        (export.SHOWN_SQL, f"WHERE {export.SHOWN}", f"WHERE u.id IN ({ids})"),
        (export.EXT_IDS_SQL, f"WHERE {export.SHOWN}", f"WHERE e.site_id IN ({ids})"),
        (export.NAMES_SQL, f"WHERE {export.SHOWN} AND", f"WHERE n.site_id IN ({ids}) AND"),
    )
    queries = []
    for sql, old, new in swaps:
        if sql.count(old) != 1:
            raise P.PlanError(
                f"export.py no longer filters on {old!r} once: the calibration read must be rewritten"
            )
        queries.append(sql.replace(old, new))
    return (("shown", queries[0]), ("ext_ids", queries[1]), ("names", queries[2]))


@dataclass(frozen=True)
class Facts:
    """The sites of a calibration set, as `export.py` would read them."""

    shown: tuple[Mapping[str, Any], ...]
    ext_ids: tuple[Mapping[str, Any], ...]
    names: tuple[Mapping[str, Any], ...]
    read_at: str


def read_facts(path: Path, site_ids: Sequence[str]) -> Path:
    """Read production (read-only, one snapshot) and keep the answer as it came."""
    return P.write_tagged_export(P.tagged_export_script(facts_parts(site_ids)), path)


def parse_facts(text: str, site_ids: Sequence[str]) -> Facts:
    rows, read_at = P.parse_tagged_export(text, [k for k, _ in facts_parts(site_ids)])
    held = {r["id"] for r in rows["shown"]}
    missing = sorted(set(site_ids) - held)
    if missing:
        raise P.PlanError(
            f"{len(missing)} calibration site(s) are not in unified_sites: {missing[:3]}"
        )
    return Facts(tuple(rows["shown"]), tuple(rows["ext_ids"]), tuple(rows["names"]), read_at)


def dup_context(facts: Facts, cases: Sequence[Case], wiki: WikiIndex | None) -> dup_judge.Context:
    """The context of the calibration questions: one cluster per case, its members read as
    `dup_clusters.member` reads them."""
    shown = common.rows_by_id(facts.shown)
    qids = export.qids_by_site(facts.ext_ids)
    enwiki = export.enwiki_by_site(facts.ext_ids)
    clusters: dict[str, Mapping[str, Any]] = {}
    for case in cases:
        rows = sorted((shown[s] for s in case.sites()), key=lambda r: (r["created_at"], r["id"]))
        metres = common.metres(rows[0], rows[1])
        shared = sorted(set(qids.get(case.a, ())) & set(qids.get(case.b, ())))
        edge: dict[str, Any] = (
            {"kind": "shared_qid", "qid": shared[0], "sites": sorted(case.sites())}
            if shared
            else {
                "kind": "name_point",
                "metres": round(metres),
                "similarity": 0.0,
                "sites": sorted(case.sites()),
            }
        )
        clusters[case.case_id] = {
            "record": "cluster",
            "cluster_id": case.case_id,
            "size": 2,
            "kinds": [edge["kind"]],
            "bcases_classes": [],
            "max_distance_m": round(metres, 1),
            "min_distance_m": round(metres, 1),
            "distance_band": dup_clusters.band(metres),
            "edges": [edge],
            "members": [
                dup_clusters.member(r, qids.get(r["id"], []), enwiki.get(r["id"], [])) for r in rows
            ],
        }
    names: dict[str, list[str]] = {}
    for row in facts.names:
        names.setdefault(row["site_id"], []).append(row["name"])
    return dup_judge.Context(
        clusters=clusters,
        retired_losers=(),
        shown=shown,
        names={k: tuple(sorted(set(v))) for k, v in names.items()},
        wiki=wiki,
        basis=facts.read_at,
    )


def cal_dir(run: Path, kind: str) -> Path:
    return rounds.gold_dir(run, kind)


def export_gold(
    stage_run: Path, ctx: dup_judge.Context, cases: Sequence[Case], handoff: Path
) -> rounds.Round:
    """Every case as a `dup-verdict` question, in the calibration's own stage directory."""
    return rounds.export_round(
        stage_run, dup_judge.STAGE_VERDICT, [c.case_id for c in cases],
        dup_judge._prompt_of(dup_judge.STAGE_VERDICT, ctx), handoff, basis=ctx.basis,
    )  # fmt: skip


def gold_relations(text: str, cluster: Mapping[str, Any]) -> dict[str, str]:
    """`{member: "MERGE:<survivor>" | "PART_OF:<parent>" | verdict}` of one gold answer."""
    members = dup_judge.parse_verdict(text, cluster)
    return {
        s: f"{m.verdict}:{m.survivor or m.parent}" if (m.survivor or m.parent) else m.verdict
        for s, m in members.items()
    }


def gold_check(
    handoff: Path,
    ctx: dup_judge.Context,
    cases: Sequence[Case],
    *,
    batches: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """The gold answers held to what was known. A positive whose loser the gold does not MERGE is
    listed in `positive_disagreements`; a negative the gold MERGEs in `negative_merges` (not a fault
    of the gold, a finding about the case); a different survivor in `survivor_differs`."""
    by_label = {label: batch for batch, labels in batches.items() for label in labels}
    report: dict[str, Any] = {"cases": len(cases), "answered": 0, "positive_disagreements": [],
                              "survivor_differs": [], "negative_merges": [], "gold_models": []}  # fmt: skip
    for case in cases:
        batch = by_label[case.case_id]
        cluster = ctx.clusters[case.case_id]
        prompt = dup_judge.verdict_prompt(cluster, ctx)
        answer = OH.read_answer(
            handoff,
            batch_id=batch,
            stage=dup_judge.STAGE_VERDICT,
            label=case.case_id,
            prompt=prompt,
        )
        problem = rounds.role_problem(answer, (GOLD_ROLE,))
        if problem is not None:
            raise rounds.RoundError(f"{case.case_id}: {problem}")
        report["answered"] += 1
        report["gold_models"].append(answer.model)
        relations = gold_relations(answer.text, cluster)
        merged = {s: r for s, r in relations.items() if r.startswith("MERGE:")}
        if case.kind == "positive":
            assert case.expected is not None
            if not merged:
                report["positive_disagreements"].append(
                    {"case": case.case_id, "relations": relations}
                )
            elif relations.get(case.expected["loser"]) != f"MERGE:{case.expected['survivor']}":
                report["survivor_differs"].append({"case": case.case_id, "relations": relations})
        elif merged:
            report["negative_merges"].append({"case": case.case_id, "relations": relations})
    report["gold_models"] = sorted(set(report["gold_models"]))
    return report


def false_merges(comparison: Mapping[str, Any]) -> int:
    """The MERGEs a re-answering role made where the recorded gold made none: a false MERGE retires
    a real site, and the seal allows none. Read from `COMPARISON.json` (`calibrate_claude compare`)."""
    return sum(
        1
        for d in comparison["disagreements"]
        if str(d["fresh"]).startswith("MERGE:") and not str(d["recorded"]).startswith("MERGE:")
    )


# --------------------------------------------------------------------------------------- parents
#: The would-be parent types that hold no other site record: one built structure or one monument
#: (a temple or a pyramid with its own precinct counts as one). A candidate pair whose parent has
#: only such types is a neighbour, a predecessor, a namesake or the same structure - not a parent
#: and its component - unless Wikidata says the one contains the other (which takes it out).
#: Settlements, sanctuaries, forts, palaces, fora, necropoleis, henges and the like are containers
#: and are not here; `Monument` is (an altar, a bridge, a column).
STRUCTURE_TYPES = frozenset(
    {
        "Temple", "Temple complex", "Pyramid complex", "Theatre", "Theater", "Amphitheatre",
        "Stadium", "Bath", "Gate", "Gate/archway/bridge", "Bridge", "Aqueduct", "Minaret/tower",
        "Well", "Church", "Church/cathedral", "Tomb", "Burial", "Dolmen", "Cairn", "Barrow",
        "Mound/tumulus", "Stone circle", "Timber circle", "Standing stone", "Megalithic stones",
        "Megalithic statues", "Sculptured stone", "Inscription", "Rock art", "Petroglyphs",
        "Rock relief/carving", "Geoglyphs", "Monument", "Shipwreck",
    }
)  # fmt: skip
#: The seed of the draw among the structure-parent candidates (a new seed is a new pool).
PARENT_NEGATIVE_SEED = "d25-parent-negatives-v1"
P_PART_OF, P_HAS_PART = "P361", "P527"
NEITHER_SOURCE = "bcases/dup_pairs.jsonl NEITHER"
STRUCTURE_SOURCE = "PARENT_CANDIDATES.jsonl structure parent, no P361/P527 between the items"
EntityOf = Callable[[str], Mapping[str, Any] | None]


def _seeded_order(seed: str, a: str, b: str) -> str:
    return hashlib.sha256(f"{seed}|{a}|{b}".encode()).hexdigest()


def site_types(value: str | None) -> frozenset[str]:
    """The types of a `site_type` cell (`"City/town/settlement, Pyramid complex"` holds two)."""
    return frozenset(t.strip() for t in (value or "").split(",") if t.strip())


def nested_cases(
    pairs: Sequence[Mapping[str, Any]], shown: Mapping[str, Any], klass: str, kind: str
) -> list[Case]:
    """The pairs of one owner-case class whose names are contained in each other, both shown, as
    parent questions in a hash order. The parent of a pair is the one whose significant words are
    the subset (`parents.candidate_pairs`' rule); a pair whose words are not nested has no parent and
    is left out."""
    out: list[Case] = []
    for pair in sorted((p for p in pairs if p["class"] == klass), key=_hash_order):
        if pair["a"] not in shown or pair["b"] not in shown:
            continue
        left, right = common.tokens(pair["a_name"]), common.tokens(pair["b_name"])
        if not left or not right or not (left < right or right < left):
            continue
        parent, child = (pair["a"], pair["b"]) if left < right else (pair["b"], pair["a"])
        out.append(
            Case(
                case_id("par-" + kind[:3], parent, child),
                kind,
                parent,
                child,
                None,
                f"bcases/dup_pairs.jsonl {klass}",
            )
        )
    return out


def structure_negatives(
    candidates: Sequence[Mapping[str, Any]],
    shown: Mapping[str, Any],
    entity_of: EntityOf,
    *,
    exclude: Iterable[frozenset[str]],
    seed: str = PARENT_NEGATIVE_SEED,
) -> tuple[list[Case], dict[str, int]]:
    """The second source of true non-parent pairs: the run's own parent candidates
    (`PARENT_CANDIDATES.jsonl`, the very pairs the parent verdict is asked about) on which a would-be
    parent of `STRUCTURE_TYPES` only meets a child whose Wikidata item it does not contain.

    A pair counts when both sites are shown, the pair is not in `exclude` (the owner-case pairs: a
    class of their own), both carry Wikidata items and share none (a shared item is D14's question),
    every item is read (`entity_of` answers it: an item nobody read is not taken as silent), and
    neither the child's P361 names a parent item nor the parent's P527 a child item. The pairs are
    drawn in the order of `seed`, at most one per would-be parent and one per child, so one big
    family (the Giza pyramids) cannot fill the set. Returns the cases and what was counted."""
    skip = set(exclude)
    counts = {"candidate_pairs": 0, "structure_parent": 0, "eligible": 0, "drawn": 0}
    counts |= {"left_out_" + k: 0 for k in ("not_shown", "owner_case", "no_item", "shared_item",
                                            "item_unread", "contained")}  # fmt: skip
    eligible: list[tuple[str, str]] = []
    for record in candidates:
        parent = record["parent"]
        types = site_types(parent["site_type"])
        structure = bool(types) and types <= STRUCTURE_TYPES
        for child in record["children"]:
            counts["candidate_pairs"] += 1
            if not structure:
                continue
            counts["structure_parent"] += 1
            reason = _structure_left_out(parent, child, shown, entity_of, skip)
            if reason is not None:
                counts["left_out_" + reason] += 1
                continue
            eligible.append((parent["id"], child["id"]))
    counts["eligible"] = len(eligible)
    used: set[str] = set()
    out: list[Case] = []
    for parent_id, child_id in sorted(eligible, key=lambda pc: _seeded_order(seed, *pc)):
        if parent_id in used or child_id in used:
            continue
        used |= {parent_id, child_id}
        out.append(
            Case(
                case_id("par-neg", parent_id, child_id),
                "negative",
                parent_id,
                child_id,
                None,
                STRUCTURE_SOURCE,
            )
        )
    counts["drawn"] = len(out)
    return out, counts


def _structure_left_out(
    parent: Mapping[str, Any],
    child: Mapping[str, Any],
    shown: Mapping[str, Any],
    entity_of: EntityOf,
    exclude: set[frozenset[str]],
) -> str | None:
    """Why a structure-parent candidate is no negative, or `None` when it is one."""
    if parent["id"] not in shown or child["id"] not in shown:
        return "not_shown"
    if frozenset((parent["id"], child["id"])) in exclude:
        return "owner_case"
    parent_items, child_items = set(parent["qids"]), set(child["qids"])
    if not parent_items or not child_items:
        return "no_item"
    if parent_items & child_items:
        return "shared_item"
    read = {q: entity_of(q) for q in sorted(parent_items | child_items)}
    entities = {q: e for q, e in read.items() if e is not None}
    if len(entities) < len(read):
        return "item_unread"
    part_of = {i for q in child_items for i in H.item_ids(entities[q], P_PART_OF)}
    has_part = {i for q in parent_items for i in H.item_ids(entities[q], P_HAS_PART)}
    if part_of & parent_items or has_part & child_items:
        return "contained"
    return None


def parent_cases(
    pairs: Sequence[Mapping[str, Any]],
    shown: Mapping[str, Mapping[str, Any]],
    *,
    candidates: Sequence[Mapping[str, Any]],
    entity_of: EntityOf,
    n_positive: int = N_PARENT_POSITIVES,
    n_negative: int = N_PARENT_NEGATIVES,
) -> list[Case]:
    """The parent calibration cases: `n_positive` `PART-OF` pairs of the owner-case classification
    (positives), then `n_negative` negatives - the contained-name `NEITHER` pairs first (two parts of
    one shared item, neither the other's), the rest drawn from the structure-parent candidates
    (`structure_negatives`). Fewer than either count is an error, never a smaller set."""
    return parent_pool(
        pairs, shown, candidates=candidates, entity_of=entity_of, n_positive=n_positive,
        n_negative=n_negative,
    )[0]  # fmt: skip


def parent_pool(
    pairs: Sequence[Mapping[str, Any]],
    shown: Mapping[str, Mapping[str, Any]],
    *,
    candidates: Sequence[Mapping[str, Any]],
    entity_of: EntityOf,
    n_positive: int = N_PARENT_POSITIVES,
    n_negative: int = N_PARENT_NEGATIVES,
) -> tuple[list[Case], dict[str, Any]]:
    """`parent_cases` with what each source held (the dry run prints it)."""
    positives = nested_cases(pairs, shown, "PART-OF", "positive")
    if len(positives) < n_positive:
        raise P.PlanError(
            f"only {len(positives)} PART-OF pairs with nested names, {n_positive} wanted"
        )
    neither = nested_cases(pairs, shown, "NEITHER", "negative")
    structure, counts = structure_negatives(
        candidates, shown, entity_of, exclude={frozenset((p["a"], p["b"])) for p in pairs}
    )
    negatives = (neither + structure)[:n_negative]
    if len(negatives) < n_negative:
        raise P.PlanError(
            f"only {len(neither) + len(structure)} parent negatives - {len(neither)} NEITHER pairs "
            f"with nested names and {len(structure)} structure-parent candidates - "
            f"{n_negative} wanted"
        )
    pool = {
        "positives_available": len(positives),
        "neither_nested_available": len(neither),
        "structure": counts,
        "drawn": {
            "positive": n_positive,
            "negative_neither": sum(1 for c in negatives if c.source == NEITHER_SOURCE),
            "negative_structure": sum(1 for c in negatives if c.source == STRUCTURE_SOURCE),
        },
    }
    return positives[:n_positive] + negatives, pool


def parent_context(
    facts: Facts, cases: Sequence[Case], wiki: WikiIndex | None
) -> parent_judge.Context:
    shown = common.rows_by_id(facts.shown)
    qids = export.qids_by_site(facts.ext_ids)
    questions: dict[str, dict[str, Any]] = {}
    for case in cases:
        parent, child = shown[case.a], shown[case.b]
        questions[case.case_id] = {
            "parent": parent_judge._brief(parent, qids.get(parent["id"], ())),
            "parent_is_child": False,
            "children": [
                {
                    **parent_judge._brief(child, qids.get(child["id"], ())),
                    "metres": round(common.metres(parent, child), 1),
                    "shared_qid": bool(
                        set(qids.get(parent["id"], ())) & set(qids.get(child["id"], ()))
                    ),
                    "competing_parents": [],
                    "sources": ["calibration"],
                }
            ],
        }
    names: dict[str, list[str]] = {}
    for row in facts.names:
        names.setdefault(row["site_id"], []).append(row["name"])
    return parent_judge.Context(
        questions=questions,
        shown=shown,
        names={k: tuple(sorted(set(v))) for k, v in names.items()},
        qids={k: tuple(v) for k, v in qids.items()},
        wiki=wiki,
        store=None,
        basis=facts.read_at,
    )


def export_parent_gold(
    stage_run: Path, ctx: parent_judge.Context, cases: Sequence[Case], handoff: Path
) -> rounds.Round:
    """Every case as a `parent-verdict` question. A question's label is its case id (a file name);
    the answer's `parent_id` is the real parent's, which the prompt prints."""

    def build(label: str, earlier: str | None) -> str:
        return parent_judge.verdict_prompt(ctx.questions[label], ctx, earlier)

    return rounds.export_round(
        stage_run, parent_judge.STAGE_VERDICT, [c.case_id for c in cases], build, handoff,
        basis=ctx.basis,
    )  # fmt: skip


def parent_gold_check(
    handoff: Path,
    ctx: parent_judge.Context,
    cases: Sequence[Case],
    *,
    batches: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """The gold answers against the owner-case classes (a heuristic: a disagreement is listed for
    the orchestrator to read, not counted a fault of the gold)."""
    by_label = {label: batch for batch, labels in batches.items() for label in labels}
    report: dict[str, Any] = {"cases": len(cases), "answered": 0, "positive_not_part": [],
                              "negative_part": [], "gold_models": []}  # fmt: skip
    for case in cases:
        question = ctx.questions[case.case_id]
        answer = OH.read_answer(
            handoff, batch_id=by_label[case.case_id], stage=parent_judge.STAGE_VERDICT,
            label=case.case_id, prompt=parent_judge.verdict_prompt(question, ctx),
        )  # fmt: skip
        problem = rounds.role_problem(answer, (GOLD_ROLE,))
        if problem is not None:
            raise rounds.RoundError(f"{case.case_id}: {problem}")
        report["answered"] += 1
        report["gold_models"].append(answer.model)
        verdict = parent_judge.parse_verdict(answer.text, question)[case.b].verdict
        if case.kind == "positive" and verdict != "PART":
            report["positive_not_part"].append({"case": case.case_id, "verdict": verdict})
        elif case.kind == "negative" and verdict == "PART":
            report["negative_part"].append({"case": case.case_id, "verdict": verdict})
    report["gold_models"] = sorted(set(report["gold_models"]))
    return report


# ------------------------------------------------------------------------------------------ CLI
def load_cases(out: Path) -> list[Case]:
    """The cases `read` wrote into the calibration directory `out`."""
    return [
        Case(c["case_id"], c["kind"], c["a"], c["b"], c["expected"], c["source"])
        for c in common.read_jsonl(out / rounds.CASES_FILE)
    ]


def check_answer(stage_run: Path, round_name: str, label: str, text: str) -> str | None:
    """The shape problem of an answer to a question of a calibration's round, or `None` - the
    calibration's own cases and read (`stage_run` is `<run>/calibration/<kind>`), never the run's
    clusters or parents, which hold no calibration case. Nothing is fetched, no verdict judged."""
    kind = stage_run.name
    if kind not in KINDS or not rounds.is_gold_run(stage_run, kind):
        raise rounds.RoundError(
            f"{stage_run} is no pair calibration directory (<run>/{rounds.CALIBRATION_DIR}/<kind>, "
            f"kind {' or '.join(KINDS)}, with the {rounds.CASES_FILE} its read wrote)"
        )
    stage = STAGES[kind]
    record = rounds.find_round(stage_run, stage, round_name)
    if label not in record.labels:
        raise rounds.RoundError(f"{label} is no question of {stage} round {round_name}")
    cases = load_cases(stage_run)
    ids = sorted({s for c in cases for s in c.sites()})
    facts = parse_facts((stage_run / READ_FILE).read_text(encoding="utf-8"), ids)
    try:
        if kind == "dup":
            dup_judge.parse_verdict(text, dup_context(facts, cases, None).clusters[label])
        else:
            parent_judge.parse_verdict(text, parent_context(facts, cases, None).questions[label])
    except rounds.AnswerError as exc:
        return str(exc)
    return None


def _case_rows(cases: Sequence[Case]) -> list[dict[str, Any]]:
    return [
        {"case_id": c.case_id, "kind": c.kind, "a": c.a, "b": c.b, "expected": c.expected,
         "source": c.source}
        for c in cases
    ]  # fmt: skip


def _counts(cases: Sequence[Case]) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    for c in cases:
        by_source[f"{c.kind}: {c.source}"] = by_source.get(f"{c.kind}: {c.source}", 0) + 1
    return {
        "cases": len(cases),
        **{k: sum(1 for c in cases if c.kind == k) for k in ("positive", "negative")},
        "sites": len({s for c in cases for s in c.sites()}),
        "by_source": dict(sorted(by_source.items())),
    }


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(
        description="Calibration sets of the duplicate verdict and the parent question."
    )
    ap.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    sub = ap.add_subparsers(dest="command", required=True)
    read = sub.add_parser("read", help="choose the cases and read their sites (read-only)")
    read.add_argument("--kind", choices=KINDS, required=True)
    read.add_argument("--negative", action="append", default=[], metavar="A=B",
                      help="dup only: a named negative pair, two shown site names")  # fmt: skip
    read.add_argument(
        "--dry-run", action="store_true",
        help="print the cases and the pool they are drawn from; read and write nothing",
    )  # fmt: skip
    export_cmd = sub.add_parser("export", help="export every case as a verdict question")
    export_cmd.add_argument("--kind", choices=KINDS, required=True)
    export_cmd.add_argument("--handoff", type=Path, required=True)
    check = sub.add_parser("gold-check", help="hold the gold answers to what was known")
    check.add_argument("--kind", choices=KINDS, required=True)
    check.add_argument("--handoff", type=Path, required=True)
    shape = sub.add_parser("check-answer", help="the shape check of an answer to a calibration")
    shape.add_argument("--stage-run", type=Path, required=True,
                       help="the calibration directory, <run>/calibration/<kind>")  # fmt: skip
    shape.add_argument("--round", required=True)
    shape.add_argument("--label", required=True)
    shape.add_argument("--text-file", type=Path, required=True)
    fm = sub.add_parser("false-merges", help="count the MERGEs a re-answer made against the gold")
    fm.add_argument("--comparison", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.command == "false-merges":
            print(false_merges(json.loads(args.comparison.read_text(encoding="utf-8"))))
            return 0
        if args.command == "check-answer":
            problem = check_answer(
                rounds.resolve(args.stage_run, args.root),
                args.round,
                args.label,
                args.text_file.read_text(encoding="utf-8"),
            )
            print(problem or "shape ok")
            return 1 if problem else 0
        run = common.run_dir(args.root)
        out = cal_dir(run, args.kind)
        stage = STAGES[args.kind]
        if args.command == "read":
            exported = export.load_export(run / common.EXPORT_FILE)
            pool: dict[str, Any] = {}
            if args.kind == "dup":
                extra = [
                    resolve_named(exported.shown, *spec.split("=", 1)) for spec in args.negative
                ]
                o9 = [(p.loser, p.survivor) for p in dups.PAIRS]
                cases = dup_cases(
                    common.read_jsonl(DUPLICATES),
                    o9,
                    common.read_jsonl(DUP_PAIRS),
                    extra_negatives=extra,
                )
            else:
                from identity.entities import default_store

                store = default_store(args.root)
                cases, pool = parent_pool(
                    common.read_jsonl(DUP_PAIRS),
                    common.rows_by_id(exported.shown),
                    candidates=common.read_jsonl(run / parents.OUTPUT),
                    entity_of=lambda qid: store.get(qid)[0],
                    n_positive=N_PARENT_POSITIVES,
                    n_negative=N_PARENT_NEGATIVES,
                )
            summary = _counts(cases)
            if args.dry_run:
                names = {r["id"]: r["name"] for r in exported.shown}
                print(json.dumps({**summary, "pool": pool, "dry_run": True, "cases_drawn": [
                    {**row, "a_name": names.get(row["a"]), "b_name": names.get(row["b"])}
                    for row in _case_rows(cases)
                ]}, ensure_ascii=False, indent=1))  # fmt: skip
                return 0
            read_facts(out / READ_FILE, sorted({s for c in cases for s in c.sites()}))
            common.write_jsonl(out / rounds.CASES_FILE, _case_rows(cases))
            print(json.dumps({**summary, "pool": pool}, ensure_ascii=False, indent=1))
            return 0
        cases = load_cases(out)
        ids = sorted({s for c in cases for s in c.sites()})
        facts = parse_facts((out / READ_FILE).read_text(encoding="utf-8"), ids)
        wiki = load_cache(args.root)
        if args.command == "export":
            if args.kind == "dup":
                record = export_gold(out, dup_context(facts, cases, wiki), cases, args.handoff)
            else:
                record = export_parent_gold(
                    out, parent_context(facts, cases, wiki), cases, args.handoff
                )
            print(json.dumps({"round": record.name, "run": str(rounds.stage_dir(out, stage)),
                              "batches": {b: len(v) for b, v in record.batches.items()}}, indent=1))  # fmt: skip
            return 0
        batches = rounds.find_round(out, stage, "r1").batches
        if args.kind == "dup":
            report = gold_check(
                args.handoff, dup_context(facts, cases, wiki), cases, batches=batches
            )
        else:
            report = parent_gold_check(
                args.handoff, parent_context(facts, cases, wiki), cases, batches=batches
            )
        print(json.dumps(report, indent=1, sort_keys=True))
    except (P.PlanError, rounds.RoundError, OH.HandoffError, common.IdentityError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
