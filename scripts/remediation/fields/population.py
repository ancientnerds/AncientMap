"""WD3 step 1: the open fields of the curated sites, and the run that asks them.

Lane WD3 (`rule.py`, the `one-family` rule) is WD1 again for the fields WD1 left open. A field is
**open** when no source stands behind what the database holds for it:

* `empty` - the column holds nothing: `period_start` NULL, `site_type` or `source_url` NULL or
  empty (read from production now, after WD1's clears landed). `lat`/`lon` are NOT NULL;
* `unresolved` - the stored point: WD1 found no two independent sources for it (a counted
  `unresolved` answer, or exhausted after three rounds). A site WD1 never saw is read by the
  machine's own status: a point no witness confirms is open. A point a journalled lane wrote with
  sourced evidence is **not** open, whatever WD1 decided before: the site's newest lat/lon journal
  row carries `two_source`, `authoritative` or `one_source` confidence and the value the row holds
  now (`POINTS.jsonl`, one SELECT) - another lane's sourced write is never asked again;
* `held` - WD1 held the field because the pages its agents cited could not be read (`HELD.jsonl` of
  its waves), so the stored value neither got a source nor was cleared;
* `unsourced` - WD1 decided `clear`, the value is still stored: the clear was refused at write
  (the step's SKIPPED.jsonl names why). It has no source either.

A field WD1 decided `keep` or `replace` stands on two quotes and is **never asked again**; a site
that is retired is not in the run. A site with at least one open field gets one question with exactly
those fields. What the question shows beyond WD1's: the field's open reason, WD1's reasoning for it (a
lead, not evidence) and the site's own links - `site_content_links`, the link icons of its page - with
its stored source_url (`LINKS.jsonl`, one SELECT).

    population.py --out DIR export                 STORED.jsonl, LINKS.jsonl and an empty SEEDS.jsonl
                                                   (a WD3 run asks no seeded field: WD1 asked them)
    population.py --out DIR build --root HARVEST [--pilot N --seed S | --without RUN]
                                                   RUN.json (the rule, pinned), CLASSIFIED.jsonl and
                                                   COUNTS.json - from files only

`HARVEST` is a copy of the shared harvest, refreshed (`harvest.py --root HARVEST export`, then
`fetch`): the shared one stays as the other lanes read it, and WD1's writes moved points and URLs
that the stored export must agree with (`classify.py` refuses a harvest and an export of different
states). The run reads WD1's own records - the four runs' CLASSIFIED/DECISIONS and the waves' HELD.jsonl
under `output/remediation/fields/wd1/write/` - and refuses a WD1 wave that is not fully accepted: the
population is what is left after WD1's writes landed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.plan import psql_json_reader  # noqa: E402

from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import rule as R  # noqa: E402

WHY_EMPTY, WHY_UNRESOLVED, WHY_HELD, WHY_UNSOURCED = "empty", "unresolved", "held", "unsourced"
WHYS = (WHY_EMPTY, WHY_UNRESOLVED, WHY_HELD, WHY_UNSOURCED)
HELD = "held"  # `handoff.HELD`, the import's decision for a field whose pages could not be read

FIELDS_DIR = REPO / "output" / "remediation" / "fields"
WD1_RUN_NAMES = ("wd1-pilot", "wd1", "wd1-rest-pilot", "wd1-rest")
DEFAULT_OUT = FIELDS_DIR / "wd3"
LINKS_FILE = "LINKS.jsonl"
POINTS_FILE = "POINTS.jsonl"
#: The journal confidences that stand for a sourced value (`remediation_change_log.confidence`):
#: two quotes (`two_source`, WD1 and the owner-case lanes), a register (`authoritative`), one quote
#: (`one_source`, WD3). `opus-checked` is a judgement without a quoted source: not one of them.
SOURCED_CONFIDENCE = frozenset({"two_source", "authoritative", "one_source"})
#: How a question describes WD1's decision of a field: the first characters of its reasoning.
WD1_SHOWN_CHARS = 600

LINKS_SQL = """\
SELECT u.id::text AS site_id,
       coalesce((SELECT json_agg(json_build_object(
                    'title', l.title, 'url', l.content_url,
                    'type', coalesce(l.link_metadata->>'link_type', l.content_type),
                    'domain', l.link_metadata->>'domain', 'score', l.relevance_score)
                  ORDER BY l.relevance_score DESC NULLS LAST, l.id)
                   FROM site_content_links l WHERE l.site_id = u.id), '[]'::json) AS links
  FROM unified_sites u
 WHERE u.source_id = 'ancient_nerds'
 ORDER BY u.id"""
LINK_KEYS = ("title", "url", "type", "domain", "score")
#: The newest journal row of each curated site's `lat` or `lon` (the point is written whole, but
#: only a coordinate that changed is journalled: the newest row of the two is the last write).
POINTS_SQL = """\
SELECT DISTINCT ON (c.row_pk) c.row_pk AS site_id, c.column_name, c.run_stamp,
       c.confidence, c.new_value
  FROM remediation_change_log c
  JOIN unified_sites u ON u.id::text = c.row_pk
 WHERE c.table_name = 'unified_sites' AND c.column_name IN ('lat', 'lon')
   AND u.source_id = 'ancient_nerds'
 ORDER BY c.row_pk, c.id DESC"""
POINT_KEYS = ("site_id", "column_name", "run_stamp", "confidence", "new_value")


class PopulationError(RuntimeError):
    """The population cannot be built from these inputs. Nothing is written."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise PopulationError(f"{path} is missing")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------------------ WD1's records
@dataclass(frozen=True)
class Wd1:
    """What WD1 decided: each (site, field)'s decision, the sites it classified, and the held
    pairs its waves listed."""

    decisions: Mapping[tuple[str, str], Mapping[str, Any]]
    classified: frozenset[str]
    held: frozenset[tuple[str, str]]
    runs: tuple[str, ...]
    waves: tuple[str, ...]


def _shown(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _names_run(recorded: str, run: Path) -> bool:
    """Whether a wave's recorded run (a path relative to the repository that planned it) is `run`:
    the main checkout's runs are read from a worktree too. An absolute record is compared as it is."""
    here = run.resolve().as_posix()
    if Path(recorded).is_absolute():
        return Path(recorded).resolve().as_posix() == here
    return here.endswith("/" + recorded.removeprefix("./"))


def _wave_held(wave: Path) -> tuple[str, list[tuple[str, str]]]:
    """A WD1 wave's run and the (site, field) pairs of its HELD.jsonl - refused unless the wave is
    the pinned file and every one of its steps is accepted with 0 deviations."""
    record_path = wave / "WAVE.json"
    if _sha256_text(record_path) != (wave / "WAVE.sha256").read_text(encoding="utf-8").strip():
        raise PopulationError(f"{record_path} is not the pinned wave: it was edited")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    for number in range(1, len(record["steps"]) + 1):
        accepted = wave / f"s{number:03d}" / "ACCEPTED.json"
        if not accepted.exists():
            raise PopulationError(f"{wave.name} step {number} is not accepted ({accepted})")
        if json.loads(accepted.read_text(encoding="utf-8"))["deviations"] != 0:
            raise PopulationError(f"{wave.name} step {number} was accepted with deviations")
    held = _read_jsonl(wave / "HELD.jsonl")
    return str(record["run"]), [(row["site_id"], row["field"]) for row in held]


def wd1_files(fields_dir: Path = FIELDS_DIR) -> tuple[list[Path], Path]:
    """WD1's four runs and the directory of its waves, under `fields_dir`."""
    return [fields_dir / name for name in WD1_RUN_NAMES], fields_dir / "wd1" / "write"


def read_wd1(runs: Sequence[Path], waves: Path) -> Wd1:
    """WD1's four runs: every decision (a cell decided by two runs is refused), the sites classified,
    and the held pairs of the waves that wrote them. Each run's unresolved and held decisions must
    be exactly the pairs its waves listed - a run whose wave was not planned has nothing written."""
    decisions: dict[tuple[str, str], Mapping[str, Any]] = {}
    classified: set[str] = set()
    held_of_run: dict[str, set[tuple[str, str]]] = {}
    for run in runs:
        reask_file = run / "REASK.json"
        if not reask_file.exists():
            raise PopulationError(
                f"{run} is not there - WD1's runs are untracked files of the checkout that holds "
                f"output/, and this one has none; --wd1-dir points the read at that checkout"
            )
        reask = json.loads(reask_file.read_text(encoding="utf-8"))
        if reask["fields"]:
            raise PopulationError(f"{run}: fields still wait for a re-ask - WD1 is not finished")
        rows = _read_jsonl(run / "DECISIONS.jsonl")
        if not rows:
            raise PopulationError(f"{run / 'DECISIONS.jsonl'} holds no decision")
        for row in rows:
            cell = (row["site_id"], row["field"])
            if cell in decisions:
                raise PopulationError(f"{cell} is decided by two WD1 runs")
            decisions[cell] = {**row, "run": _shown(run)}
        classified |= {line["site_id"] for line in _read_jsonl(run / C.CLASSIFIED_FILE)}
        held_of_run[_shown(run)] = {
            (row["site_id"], row["field"])
            for row in rows
            if row["decision"] in (A.UNRESOLVED, HELD)
        }
    listed: dict[str, set[tuple[str, str]]] = {}
    used: list[str] = []
    for wave in sorted(p for p in waves.iterdir() if (p / "WAVE.json").exists()):
        recorded, held = _wave_held(wave)
        for run in runs:
            if _names_run(recorded, run):
                listed.setdefault(_shown(run), set()).update(held)
                used.append(wave.name)
    for run, wanted in held_of_run.items():
        if listed.get(run) != wanted:
            raise PopulationError(
                f"{run}: its decisions hold {len(wanted)} unresolved/held field(s), the HELD.jsonl "
                f"of its waves {len(listed.get(run, ()))} - WD1's records disagree"
            )
    return Wd1(
        decisions,
        frozenset(classified),
        frozenset(cell for held in held_of_run.values() for cell in held),
        tuple(_shown(run) for run in runs),
        tuple(used),
    )


# ------------------------------------------------------------------------------ the open fields
def is_empty(field: str, stored: Mapping[str, Any]) -> bool:
    """Whether the column holds nothing (`''` and NULL both: `site_type` and `source_url` were
    written either way). A point is never empty: `lat`/`lon` are NOT NULL."""
    if field == "coordinates":
        return False
    value = stored[field]
    return value is None or (isinstance(value, str) and not value.strip())


def _wd1_summary(decision: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "decision": decision["decision"],
        "via": decision["via"],
        "run": decision["run"],
        "reasoning": str(decision["reasoning"])[:WD1_SHOWN_CHARS],
    }


def journal_sourced_point(stored: Mapping[str, Any], last: Mapping[str, Any] | None) -> bool:
    """Whether the stored point is the one a journalled lane wrote with sourced evidence: the site's
    newest lat/lon journal row (`POINTS_SQL`) carries a sourced confidence and the value the row
    holds now (compared as numbers: the journal keeps the text a writer gave)."""
    if last is None or last["confidence"] not in SOURCED_CONFIDENCE or last["new_value"] is None:
        return False
    return float(last["new_value"]) == float(stored[last["column_name"] + "_text"])


def open_fields(
    line: Mapping[str, Any],
    stored: Mapping[str, Any],
    wd1: Wd1,
    last_point_write: Mapping[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The open fields of one classified site: `{field: {"why", "wd1"}}`, and the fields WD1 decided
    with sources that are empty now (a state nothing explains - listed, never asked). A point whose
    newest journal row is a sourced write (`last_point_write`) is not open."""
    site = str(line["site_id"])
    seen = site in wd1.classified
    opened: dict[str, dict[str, Any]] = {}
    contradictions: list[str] = []
    for field in C.FIELDS:
        decision = wd1.decisions.get((site, field))
        verdict = None if decision is None else decision["decision"]
        empty = is_empty(field, stored)
        if verdict in (A.KEEP, A.REPLACE):
            if empty:
                contradictions.append(field)
            continue
        if empty:
            why = WHY_EMPTY
        elif field == "coordinates":
            if journal_sourced_point(stored, last_point_write):
                continue
            if verdict in (A.UNRESOLVED, HELD):
                why = WHY_UNRESOLVED
            elif not seen and line["fields"][field]["status"] != C.CONFIRMED:
                why = WHY_UNRESOLVED
            else:
                continue
        elif verdict == HELD:
            why = WHY_HELD
        elif verdict == A.CLEAR:
            why = WHY_UNSOURCED
        else:
            continue
        opened[field] = {"why": why, "wd1": _wd1_summary(decision)}
    return opened, contradictions


# ------------------------------------------------------------------------------ the links
def export_links(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    """LINKS.jsonl: each curated site's own links, best first, from one read-only SELECT."""
    rows = reader(LINKS_SQL)
    if not rows:
        raise PopulationError("the links export returned no curated site")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    tmp = out / (LINKS_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / LINKS_FILE)
    return len(rows)


def read_links(out: Path) -> dict[str, list[dict[str, Any]]]:
    path = out / LINKS_FILE
    if not path.exists():
        raise PopulationError(f"{path} is missing - run `population.py export` first")
    links: dict[str, list[dict[str, Any]]] = {}
    for row in _read_jsonl(path):
        for link in row["links"]:
            if set(link) != set(LINK_KEYS):
                raise PopulationError(
                    f"{path}: a link carries {sorted(link)}, not {sorted(LINK_KEYS)}"
                )
        links[str(row["site_id"])] = row["links"]
    return links


def export_points(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    """POINTS.jsonl: each curated site's newest lat/lon journal row, from one read-only SELECT. A
    site no lane ever moved has none."""
    rows = reader(POINTS_SQL)
    for row in rows:
        if set(row) != set(POINT_KEYS):
            raise PopulationError(f"a point journal row carries {sorted(row)}, not {POINT_KEYS}")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in sorted(rows, key=lambda r: r["site_id"])
    )
    tmp = out / (POINTS_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out / POINTS_FILE)
    return len(rows)


def read_points(out: Path) -> dict[str, dict[str, Any]]:
    path = out / POINTS_FILE
    if not path.exists():
        raise PopulationError(f"{path} is missing - run `population.py export` first")
    points: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(path):
        if set(row) != set(POINT_KEYS):
            raise PopulationError(f"{path}: a row carries {sorted(row)}, not {sorted(POINT_KEYS)}")
        points[str(row["site_id"])] = row
    return points


def export(out: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> dict[str, Any]:
    """STORED.jsonl (`classify.export_stored`), LINKS.jsonl, POINTS.jsonl and the empty SEEDS.jsonl
    a run needs."""
    stored = C.export_stored(out, reader=reader)
    links = export_links(out, reader=reader)
    points = export_points(out, reader=reader)
    (out / C.SEEDS_FILE).write_text("", encoding="utf-8", newline="\n")
    return {"stored": stored, "links": links, "points": points}


# ------------------------------------------------------------------------------ the run
def build(
    root: Path,
    out: Path,
    *,
    table: Mapping[str, C.ClassEntry],
    wd1: Wd1,
    stage: str = "wd3",
    pilot: tuple[int, int] | None = None,
    without: Path | None = None,
) -> dict[str, Any]:
    """RUN.json, CLASSIFIED.jsonl and COUNTS.json of the population (or of its pilot, or of the
    population less a pilot): every live curated site with an open field, each with exactly those.
    `stage` picks the rule `RUN.json` pins: `wd3` fills open fields, `wd4` asks the same question
    and adds the answer kind `period_name`, and a run pinned to another rule is refused."""
    rule = R.BY_STAGE.get(stage)
    if rule is None:
        raise R.RuleError(f"stage {stage!r} is not one of {sorted(R.BY_STAGE)}")
    if (out / "ROUNDS.jsonl").exists():
        raise PopulationError(f"{out} was asked already (ROUNDS.jsonl): a run is built once")
    C.read_stored(out)  # refused here, before anything is pinned, when the export is missing
    links = read_links(out)
    points = read_points(out)
    unseen: set[str] = set()
    journal_sourced: set[str] = set()
    contradictions: dict[str, list[str]] = {}

    def refine(line: Mapping[str, Any], stored: Mapping[str, Any]) -> dict[str, Any] | None:
        site = str(line["site_id"])
        opened, wrong = open_fields(line, stored, wd1, points.get(site))
        if "coordinates" in open_fields(line, stored, wd1)[0] and "coordinates" not in opened:
            journal_sourced.add(site)  # open but for the journal's sourced write
        if site not in wd1.classified:
            unseen.add(site)
        if wrong:
            contradictions[site] = wrong
        if not opened:
            return None
        return {
            "asked": [field for field in C.FIELDS if field in opened],
            "open": opened,
            "links": links[site],
        }

    R.write_run(
        out,
        rule,
        built_from={
            "harvest": _shown(root),
            "wd1_runs": list(wd1.runs),
            "wd1_waves": list(wd1.waves),
        },
        pilot=None if pilot is None else {"size": pilot[0], "seed": pilot[1]},
        without=None if without is None else _shown(without),
    )
    counts = C.classify_all(
        root, out, table=table, part="all", pilot=pilot, without=without, refine=refine
    )
    mine = {json.loads(raw)["site_id"] for raw in (out / C.CLASSIFIED_FILE).open(encoding="utf-8")}
    counts["population"] = {
        "sites": counts["sites"],
        **_tally(out),
        "wd1_unseen_sites": sorted(unseen & mine),
        "journal_sourced_points": {
            site: points[site]["run_stamp"] for site in sorted(journal_sourced)
        },
        "wd1_sourced_but_empty": {
            site: fields for site, fields in sorted(contradictions.items()) if site in mine
        },
    }
    counts["wd1"] = {
        "runs": list(wd1.runs),
        "waves": list(wd1.waves),
        "decisions": len(wd1.decisions),
        "unresolved_or_held": len(wd1.held),
        "sites_classified": len(wd1.classified),
    }
    (out / C.COUNTS_FILE).write_text(
        json.dumps(counts, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return counts


def _tally(out: Path) -> dict[str, Any]:
    """How many sites and fields of the run's CLASSIFIED.jsonl are open, and why."""
    fields: Counter[str] = Counter()
    why: Counter[str] = Counter()
    sets: Counter[str] = Counter()
    for raw in (out / C.CLASSIFIED_FILE).open(encoding="utf-8"):
        line = json.loads(raw)
        sets["+".join(line["asked"])] += 1
        for field in line["asked"]:
            fields[field] += 1
            why[f"{field}:{line['open'][field]['why']}"] += 1
    return {
        "fields": dict(sorted(fields.items())),
        "why": dict(sorted(why.items())),
        "field_sets": dict(sorted(sets.items())),
    }


# ------------------------------------------------------------------------------ the CLI
def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export", help="STORED.jsonl, LINKS.jsonl, an empty SEEDS.jsonl (read-only)")
    run = sub.add_parser("build", help="RUN.json, CLASSIFIED.jsonl, COUNTS.json, from files only")
    run.add_argument("--root", type=Path, required=True, help="the refreshed harvest copy")
    run.add_argument(
        "--stage",
        default="wd3",
        choices=sorted(R.BY_STAGE),
        help="the rule RUN.json pins: wd3 fills open fields, wd4 asks the same question and adds "
        "the answer kind period_name (default: wd3)",
    )
    run.add_argument(
        "--wd1-dir",
        type=Path,
        default=FIELDS_DIR,
        help="where WD1's runs (wd1, wd1-pilot, wd1-rest, wd1-rest-pilot) and its waves "
        "(wd1/write) live - this checkout's output/remediation/fields, which holds them only "
        "where the run itself was built; from a worktree, name the checkout that has them",
    )
    cut = run.add_mutually_exclusive_group()
    cut.add_argument("--pilot", type=int, help="a pilot: this many of the population's sites")
    cut.add_argument("--without", type=Path, help="the population less this pilot run's sites")
    run.add_argument("--seed", type=int, help="the pilot's draw (with --pilot)")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result: Any = export(args.out, reader=psql_json_reader())
        else:
            if (args.pilot is None) != (args.seed is None):
                parser.error("--pilot and --seed go together")
            result = build(
                args.root,
                args.out,
                table=C.load_table(),
                wd1=read_wd1(*wd1_files(args.wd1_dir)),
                stage=args.stage,
                pilot=None if args.pilot is None else (args.pilot, args.seed),
                without=args.without,
            )
    except (PopulationError, R.RuleError, C.ClassifyError, H.HarvestError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
