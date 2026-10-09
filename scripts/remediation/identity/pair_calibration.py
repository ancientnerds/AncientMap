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

**Parents** - `parent_cases`: the `PART-OF` class of `dup_pairs.jsonl` and the pairs of the `NEITHER`
class whose names are contained in each other, oriented by `parents.candidate_pairs`' rule (the
shorter name is the parent); the same blind labelling by Opus xhigh makes the gold, and the
heuristic classes are the cross-check that `gold-check` reports (they are a heuristic, so
a disagreement is listed, not failed).

Sealing is `calibrate_claude.py seal --id ID --role web_verifier --handoff DIR --batches ...
--threshold 0.92` (the plan's 92 %), and the gate of "0 false MERGE" is carried by the verdict's
`--false-sources`: pass the spot-check count plus `false_merges(comparison)`.

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/identity/pair_calibration.py read --kind dup
    $PY scripts/remediation/identity/pair_calibration.py export --kind dup --handoff output/remediation/handoff/cal-dup-gold
    # Opus xhigh agents answer (role pilot_judge), then:
    $PY scripts/remediation/identity/pair_calibration.py gold-check --kind dup --handoff output/remediation/handoff/cal-dup-gold
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import opus_handoff as OH  # noqa: E402
from mechanical import dups  # noqa: E402
from mechanical import plan as P  # noqa: E402

from identity import common, dup_clusters, dup_judge, export, parent_judge  # noqa: E402
from identity import label_rounds as rounds  # noqa: E402
from identity.wiki import WikiIndex, load_cache  # noqa: E402

CAL_DIR = "calibration"
BCASES = common.REPO / "output" / "remediation" / "bcases"
DUPLICATES = BCASES / "DUPLICATES.jsonl"
DUP_PAIRS = BCASES / "dup_pairs.jsonl"
N_NEGATIVES = 15
N_PARENT_POSITIVES = 20
N_PARENT_NEGATIVES = 10
GOLD_ROLE = "pilot_judge"
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
    return run / CAL_DIR / kind


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
def parent_cases(
    pairs: Sequence[Mapping[str, Any]],
    shown: Mapping[str, Mapping[str, Any]],
    *,
    n_positive: int = N_PARENT_POSITIVES,
    n_negative: int = N_PARENT_NEGATIVES,
) -> list[Case]:
    """The `PART-OF` pairs (positives) and the contained-name `NEITHER` pairs (negatives) of the
    owner-case classification, each as a parent question with one child. The parent of a pair is the
    one whose significant words are the subset (`parents.candidate_pairs`' rule); a pair whose words
    are not nested has no parent and is left out."""
    out: list[Case] = []
    for klass, kind, wanted in (
        ("PART-OF", "positive", n_positive),
        ("NEITHER", "negative", n_negative),
    ):
        taken = 0
        for pair in sorted((p for p in pairs if p["class"] == klass), key=_hash_order):
            if taken >= wanted:
                break
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
            taken += 1
        if taken < wanted:
            raise P.PlanError(f"only {taken} {klass} pairs with nested names, {wanted} wanted")
    return out


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
def _load_cases(run: Path, kind: str) -> list[Case]:
    path = cal_dir(run, kind) / "CASES.jsonl"
    return [
        Case(c["case_id"], c["kind"], c["a"], c["b"], c["expected"], c["source"])
        for c in common.read_jsonl(path)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(
        description="Calibration sets of the duplicate verdict and the parent question."
    )
    ap.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    sub = ap.add_subparsers(dest="command", required=True)
    kinds = ("dup", "parent")
    read = sub.add_parser("read", help="choose the cases and read their sites (read-only)")
    read.add_argument("--kind", choices=kinds, required=True)
    read.add_argument("--negative", action="append", default=[], metavar="A=B",
                      help="dup only: a named negative pair, two shown site names")  # fmt: skip
    export_cmd = sub.add_parser("export", help="export every case as a verdict question")
    export_cmd.add_argument("--kind", choices=kinds, required=True)
    export_cmd.add_argument("--handoff", type=Path, required=True)
    check = sub.add_parser("gold-check", help="hold the gold answers to what was known")
    check.add_argument("--kind", choices=kinds, required=True)
    check.add_argument("--handoff", type=Path, required=True)
    fm = sub.add_parser("false-merges", help="count the MERGEs a re-answer made against the gold")
    fm.add_argument("--comparison", type=Path, required=True)
    args = ap.parse_args(argv)
    run = common.run_dir(args.root)
    try:
        if args.command == "false-merges":
            print(false_merges(json.loads(args.comparison.read_text(encoding="utf-8"))))
            return 0
        out = cal_dir(run, args.kind)
        stage = dup_judge.STAGE_VERDICT if args.kind == "dup" else parent_judge.STAGE_VERDICT
        if args.command == "read":
            exported = export.load_export(run / common.EXPORT_FILE)
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
                cases = parent_cases(
                    common.read_jsonl(DUP_PAIRS), common.rows_by_id(exported.shown)
                )
            ids = sorted({s for c in cases for s in c.sites()})
            read_facts(out / "READ.jsonl", ids)
            common.write_jsonl(
                out / "CASES.jsonl",
                [
                    {"case_id": c.case_id, "kind": c.kind, "a": c.a, "b": c.b,
                     "expected": c.expected, "source": c.source}
                    for c in cases
                ],
            )  # fmt: skip
            counts = {k: sum(1 for c in cases if c.kind == k) for k in ("positive", "negative")}
            print(json.dumps({"cases": len(cases), **counts, "sites": len(ids)}, indent=1))
            return 0
        cases = _load_cases(run, args.kind)
        ids = sorted({s for c in cases for s in c.sites()})
        facts = parse_facts((out / "READ.jsonl").read_text(encoding="utf-8"), ids)
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
